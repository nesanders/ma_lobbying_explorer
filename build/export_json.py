#!/usr/bin/env python3
"""
Export JSON data files for the MA Lobbying Explorer static site.

Reads from:
  - AMEND.db  (SQLite via SQLAlchemy)
  - MA_bill_embeddings.parquet  (env scores + LLM classifications + summaries)

Writes to --output-dir (default: ../data/)

Run from repo root or build/:
  python build/export_json.py
  python build/export_json.py --db-path /path/to/AMEND.db --output-dir /path/to/data/

Actual DB schema (as of 2026-06-01):
  MA_Lobbying_Bills_Scored: bill_id, bill_number, general_court, bill_title, env_relevance_score,
                            is_environmental, cluster_id
  MA_Lobbying_Bills:        entity_name, client_name, year, general_court, chamber,
                            bill_number, bill_title, position, amount
                            (position values: 'Support', 'Oppose', 'Neutral', null)
  MA_Lobbying_Employers:    entity_name, client_name, year, reg_type, compensation
  MA_Legislature_Bills:     bill_id, bill_number, bill_prefix, general_court, title,
                            sponsor_name, status, passed
  MA_Bill_Cluster_Labels:   cluster_id, label, n_bills, n_env_bills
  Parquet:                  bill_id, bill_number, general_court, is_env_llm,
                            env_relevance_score, summary, categories, tags
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

SEP = (',', ':')


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')


SOS_BASE = 'https://www.sec.state.ma.us/LobbyistPublicSearch/'


def sos_employer_url(_name: str) -> str:
    return SOS_BASE


def sos_entity_url(_name: str) -> str:
    return SOS_BASE


def _clean(obj):
    """Recursively replace float NaN/Inf with None so json.dump produces valid JSON."""
    if isinstance(obj, float):
        return None if (obj != obj or obj == float('inf') or obj == float('-inf')) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def write_json(path: Path, data, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(_clean(data), f, separators=SEP, ensure_ascii=False, allow_nan=False)
    size_kb = path.stat().st_size / 1024
    print(f'  {label}: {path.name} ({size_kb:.0f} KB)')


def load_parquet(parquet_path: Path) -> pd.DataFrame:
    if not parquet_path.exists():
        print(f'  [warn] Parquet not found: {parquet_path}; env/summary columns will be empty')
        return pd.DataFrame(columns=['bill_id', 'general_court', 'is_env_llm', 'env_relevance_score',
                                     'summary', 'categories', 'tags'])
    df = pd.read_parquet(parquet_path,
                         columns=['bill_id', 'general_court', 'is_env_llm', 'env_relevance_score',
                                  'summary', 'categories', 'tags'])
    df = df.drop_duplicates(subset=['bill_id', 'general_court'])
    print(f'  Loaded parquet: {len(df):,} rows')
    return df


def export_clusters(engine, out_dir: Path):
    print('Exporting clusters.json…')
    df = pd.read_sql('SELECT cluster_id, label, n_bills, n_env_bills FROM MA_Bill_Cluster_Labels', engine)
    df = df.where(pd.notnull(df), None)
    write_json(out_dir / 'clusters.json', df.to_dict(orient='records'), 'clusters')


def _load_scored_base(engine) -> pd.DataFrame:
    """Load MA_Lobbying_Bills_Scored joined with cluster labels and passed status."""
    scored = pd.read_sql("""
        SELECT s.bill_id, s.bill_number, s.general_court, s.bill_title,
               s.env_relevance_score, s.is_environmental, s.cluster_id,
               c.label AS cluster_label,
               l.passed
        FROM MA_Lobbying_Bills_Scored s
        LEFT JOIN MA_Bill_Cluster_Labels c ON s.cluster_id = c.cluster_id
        LEFT JOIN MA_Legislature_Bills l
               ON s.bill_id = l.bill_id AND s.general_court = l.general_court
    """, engine)
    return scored


def _load_position_counts(engine) -> pd.DataFrame:
    """Count distinct client positions per bill (bill_number + general_court)."""
    lb = pd.read_sql(
        "SELECT bill_number, general_court, client_name, position FROM MA_Lobbying_Bills",
        engine
    )
    # Deduplicate: one position per (client, bill) — keep the first occurrence
    lb = lb.drop_duplicates(subset=['bill_number', 'general_court', 'client_name'])

    def count_pos(grp):
        pos = grp['position'].fillna('No position')
        c = pos.value_counts()
        return pd.Series({
            'n_supporters': int(c.get('Support', 0)),
            'n_opposers':   int(c.get('Oppose', 0)),
            'n_neutrals':   int(c.get('Neutral', 0)),
            'n_no_position': int(c.get('No position', 0)),
        })

    counts = lb.groupby(['bill_number', 'general_court']).apply(count_pos).reset_index()
    return counts


def export_bills_list(engine, parquet_df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    print('Exporting bills_list.json…')
    scored = _load_scored_base(engine)
    pos = _load_position_counts(engine)
    df = scored.merge(pos, on=['bill_number', 'general_court'], how='left')

    for col in ['n_supporters', 'n_opposers', 'n_neutrals', 'n_no_position']:
        df[col] = df[col].fillna(0).astype(int)

    if len(parquet_df):
        df = df.merge(
            parquet_df[['bill_id', 'general_court', 'is_env_llm', 'env_relevance_score']],
            on=['bill_id', 'general_court'], how='left', suffixes=('', '_par')
        )
        if 'env_relevance_score_par' in df.columns:
            df['env_relevance_score'] = df['env_relevance_score_par'].fillna(df['env_relevance_score'])
            df.drop(columns=['env_relevance_score_par'], inplace=True)
    else:
        df['is_env_llm'] = False

    df['is_env_llm'] = df.get('is_env_llm', False).fillna(False).astype(bool)
    df['env_relevance_score'] = df['env_relevance_score'].fillna(0.0)
    df['passed'] = df['passed'].where(pd.notnull(df['passed']), None)
    df = df.where(pd.notnull(df), None)

    col_order = ['bill_id', 'bill_number', 'general_court', 'bill_title',
                 'is_env_llm', 'env_relevance_score', 'cluster_id', 'cluster_label',
                 'n_supporters', 'n_opposers', 'n_neutrals', 'n_no_position', 'passed']
    df = df[[c for c in col_order if c in df.columns]]

    records = []
    for rec in df.to_dict(orient='records'):
        records.append({k: (None if isinstance(v, float) and pd.isna(v) else v)
                        for k, v in rec.items()})

    write_json(out_dir / 'bills_list.json', records, 'bills_list')
    return df


def export_bills_detail(engine, parquet_df: pd.DataFrame, out_dir: Path):
    print('Exporting bills_detail.json…')
    scored = _load_scored_base(engine)
    pos = _load_position_counts(engine)
    df = scored.merge(pos, on=['bill_number', 'general_court'], how='left')

    for col in ['n_supporters', 'n_opposers', 'n_neutrals', 'n_no_position']:
        df[col] = df[col].fillna(0).astype(int)

    if len(parquet_df):
        df = df.merge(parquet_df, on=['bill_id', 'general_court'], how='left',
                      suffixes=('', '_par'))
        for col in ['env_relevance_score', 'is_env_llm']:
            par_col = col + '_par'
            if par_col in df.columns:
                df[col] = df[par_col].fillna(df[col])
                df.drop(columns=[par_col], inplace=True)
    else:
        for col in ['is_env_llm', 'summary', 'categories', 'tags']:
            if col not in df.columns:
                df[col] = None

    df['is_env_llm'] = df.get('is_env_llm', False).fillna(False).astype(bool)
    df['env_relevance_score'] = df['env_relevance_score'].fillna(0.0)
    df = df.where(pd.notnull(df), None)

    result = {}
    for _, row in df.iterrows():
        key = f"{row['bill_id']}_{int(row['general_court'])}"
        rec = {}
        for k, v in row.items():
            if isinstance(v, float) and pd.isna(v):
                rec[k] = None
            elif isinstance(v, str) and v in ('', 'nan'):
                rec[k] = None if k in ('summary', 'categories', 'tags') else v
            else:
                rec[k] = v
        for col in ('categories', 'tags'):
            val = rec.get(col)
            if isinstance(val, str):
                try:
                    rec[col] = json.loads(val)
                except Exception:
                    rec[col] = []
            elif val is None:
                rec[col] = []
        result[key] = rec

    write_json(out_dir / 'bills_detail.json', result, 'bills_detail')


def _load_lobbying_bills_with_ids(engine) -> pd.DataFrame:
    """Load MA_Lobbying_Bills joined to MA_Lobbying_Bills_Scored to get bill_id."""
    lb = pd.read_sql("""
        SELECT lb.entity_name, lb.client_name, lb.year, lb.general_court,
               lb.bill_number, lb.bill_title, lb.position, lb.amount,
               s.bill_id
        FROM MA_Lobbying_Bills lb
        LEFT JOIN MA_Lobbying_Bills_Scored s
               ON lb.bill_number = s.bill_number AND lb.general_court = s.general_court
    """, engine)
    lb['position'] = lb['position'].fillna('No position')
    lb['amount'] = pd.to_numeric(lb['amount'], errors='coerce').fillna(0.0)
    return lb


def _load_env_flags(engine, parquet_df: pd.DataFrame) -> pd.DataFrame:
    """Return a DF of bill_id, general_court → is_env_llm."""
    if len(parquet_df):
        return parquet_df[['bill_id', 'general_court', 'is_env_llm']].copy()
    scored = pd.read_sql(
        "SELECT bill_id, general_court, is_environmental AS is_env_llm FROM MA_Lobbying_Bills_Scored",
        engine
    )
    scored['is_env_llm'] = scored['is_env_llm'].fillna(False).astype(bool)
    return scored


def _load_compensation(engine) -> pd.DataFrame:
    """Load per-client total compensation from MA_Lobbying_Employers."""
    return pd.read_sql(
        "SELECT entity_name, client_name, year, compensation FROM MA_Lobbying_Employers",
        engine
    )


def export_employers(engine, parquet_df: pd.DataFrame, out_dir: Path):
    print('Exporting employers.json…')
    lb = _load_lobbying_bills_with_ids(engine)
    env = _load_env_flags(engine, parquet_df)
    comp_df = _load_compensation(engine)

    lb = lb.merge(env[['bill_id', 'general_court', 'is_env_llm']],
                  on=['bill_id', 'general_court'], how='left')
    lb['is_env_llm'] = lb['is_env_llm'].fillna(False).astype(bool)

    tag_map = {}
    if len(parquet_df) and 'tags' in parquet_df.columns:
        env_par = parquet_df[parquet_df['is_env_llm'] == True][['bill_id', 'general_court', 'tags']].copy()
        for _, row in env_par.iterrows():
            key = (row['bill_id'], row['general_court'])
            t = row['tags']
            if isinstance(t, list):
                tag_map[key] = t
            elif isinstance(t, str):
                try:
                    tag_map[key] = json.loads(t)
                except Exception:
                    pass

    records = []
    for client_name, group in lb.groupby('client_name', sort=False):
        slug = slugify(client_name)
        bills = group[['bill_id', 'general_court']].drop_duplicates()
        n_total = len(bills)
        env_bills = group[group['is_env_llm']][['bill_id', 'general_court']].drop_duplicates()
        n_env = len(env_bills)

        # Compensation from MA_Lobbying_Employers
        client_comp = comp_df[comp_df['client_name'] == client_name]
        total_comp = float(client_comp['compensation'].sum())
        env_frac = n_env / n_total if n_total > 0 else 0.0
        env_comp = round(total_comp * env_frac, 2)

        years = sorted(group['year'].dropna().astype(int).unique().tolist())

        pos_by_client_bill = group.drop_duplicates(subset=['bill_number', 'general_court'])
        pos_counts = pos_by_client_bill['position'].value_counts().to_dict()
        positions = {
            'support': int(pos_counts.get('Support', 0)),
            'oppose':  int(pos_counts.get('Oppose', 0)),
            'neutral': int(pos_counts.get('Neutral', 0)),
            'none':    int(pos_counts.get('No position', 0)),
        }

        all_tags = []
        for _, row in env_bills.iterrows():
            key = (row['bill_id'], row['general_court'])
            all_tags.extend(tag_map.get(key, []))
        top_tags = [t for t, _ in Counter(all_tags).most_common(5)]

        records.append({
            'client_name': client_name,
            'client_slug': slug,
            'n_bills_total': n_total,
            'n_bills_env': n_env,
            'env_fraction': round(env_frac, 4),
            'total_compensation': round(total_comp, 2),
            'env_compensation': env_comp,
            'years_active': years,
            'top_tags': top_tags,
            'positions': positions,
            'sos_search_url': sos_employer_url(client_name),
        })

    write_json(out_dir / 'employers.json', records, 'employers')


def export_lobbyists(engine, parquet_df: pd.DataFrame, out_dir: Path):
    print('Exporting lobbyists.json…')
    comp_df = _load_compensation(engine)
    env = _load_env_flags(engine, parquet_df)

    lb = pd.read_sql("""
        SELECT lb.entity_name, lb.client_name, lb.year, lb.general_court, lb.bill_number,
               s.bill_id
        FROM MA_Lobbying_Bills lb
        LEFT JOIN MA_Lobbying_Bills_Scored s
               ON lb.bill_number = s.bill_number AND lb.general_court = s.general_court
    """, engine)
    lb = lb.merge(env[['bill_id', 'general_court', 'is_env_llm']],
                  on=['bill_id', 'general_court'], how='left')
    lb['is_env_llm'] = lb['is_env_llm'].fillna(False).astype(bool)

    records = []
    for entity_name, group in lb.groupby('entity_name', sort=False):
        slug = slugify(entity_name)
        clients = group['client_name'].dropna().unique().tolist()
        env_clients = group[group['is_env_llm']]['client_name'].dropna().unique().tolist()
        entity_comp = comp_df[comp_df['entity_name'] == entity_name]
        total_comp = float(entity_comp['compensation'].sum())
        years = sorted(group['year'].dropna().astype(int).unique().tolist())

        records.append({
            'entity_name': entity_name,
            'entity_slug': slug,
            'n_clients': len(clients),
            'n_env_clients': len(set(env_clients)),
            'total_compensation': round(total_comp, 2),
            'years_active': years,
            'sos_search_url': sos_entity_url(entity_name),
        })

    write_json(out_dir / 'lobbyists.json', records, 'lobbyists')


def export_edges_by_bill(engine, out_dir: Path):
    print('Exporting edges_by_bill.json…')
    lb = pd.read_sql("""
        SELECT lb.entity_name, lb.client_name, lb.year, lb.general_court,
               lb.bill_number, lb.position,
               COALESCE(s.bill_id, leg.bill_id) AS bill_id
        FROM MA_Lobbying_Bills lb
        LEFT JOIN MA_Lobbying_Bills_Scored s
               ON lb.bill_number = s.bill_number AND lb.general_court = s.general_court
        LEFT JOIN MA_Legislature_Bills leg
               ON lb.bill_number = leg.bill_number AND lb.general_court = leg.general_court
    """, engine)
    lb = lb.where(pd.notnull(lb), None)

    result = {}
    for (bill_id, gc), group in lb.groupby(['bill_id', 'general_court'], sort=False):
        if bill_id is None:
            continue
        key = f'{bill_id}_{int(gc)}'
        recs = []
        for _, row in group.iterrows():
            cn = row['client_name']
            en = row['entity_name']
            recs.append({
                'client_name': cn,
                'client_slug': slugify(cn) if cn else None,
                'entity_name': en,
                'entity_slug': slugify(en) if en else None,
                'year': int(row['year']) if row['year'] is not None else None,
                'position': row['position'] or 'No position',
            })
        result[key] = recs

    write_json(out_dir / 'edges_by_bill.json', result, 'edges_by_bill')


def export_edges_by_employer(engine, parquet_df: pd.DataFrame, out_dir: Path):
    print('Exporting edges_by_employer.json…')
    lb = pd.read_sql("""
        SELECT lb.client_name, lb.entity_name, lb.year, lb.general_court,
               lb.bill_number, lb.bill_title, lb.position,
               COALESCE(s.bill_id, leg.bill_id) AS bill_id
        FROM MA_Lobbying_Bills lb
        LEFT JOIN MA_Lobbying_Bills_Scored s
               ON lb.bill_number = s.bill_number AND lb.general_court = s.general_court
        LEFT JOIN MA_Legislature_Bills leg
               ON lb.bill_number = leg.bill_number AND lb.general_court = leg.general_court
    """, engine)

    env = _load_env_flags(engine, parquet_df)
    lb = lb.merge(env[['bill_id', 'general_court', 'is_env_llm']],
                  on=['bill_id', 'general_court'], how='left')
    lb['is_env_llm'] = lb['is_env_llm'].fillna(False).astype(bool)
    lb = lb.where(pd.notnull(lb), None)

    result = {}
    for client_name, group in lb.groupby('client_name', sort=False):
        if not client_name:
            continue
        slug = slugify(str(client_name))
        recs = []
        for _, row in group.iterrows():
            en = row['entity_name']
            recs.append({
                'bill_id': row['bill_id'],
                'general_court': int(row['general_court']) if row['general_court'] is not None else None,
                'bill_title': row['bill_title'],
                'entity_name': en,
                'entity_slug': slugify(en) if en else None,
                'year': int(row['year']) if row['year'] is not None else None,
                'position': row['position'] or 'No position',
                'is_env_llm': bool(row['is_env_llm']),
            })
        result[slug] = recs

    write_json(out_dir / 'edges_by_employer.json', result, 'edges_by_employer')


def main():
    parser = argparse.ArgumentParser(description='Export JSON data files for MA Lobbying Explorer')
    parser.add_argument('--db-path', default=None)
    parser.add_argument('--parquet-path', default=None)
    parser.add_argument('--output-dir', default=None)
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    db_path = Path(args.db_path) if args.db_path else None
    if db_path is None:
        for candidate in [
            repo_root.parent / 'MAenvironmentaldata' / 'get_data' / 'AMEND.db',
            repo_root.parent / 'AMEND' / 'get_data' / 'AMEND.db',
        ]:
            if candidate.exists():
                db_path = candidate
                break

    parquet_path = Path(args.parquet_path) if args.parquet_path else None
    if parquet_path is None:
        for candidate in [
            repo_root.parent / 'MAenvironmentaldata' / 'docs' / 'data' / 'MA_bill_embeddings.parquet',
            repo_root.parent / 'AMEND' / 'docs' / 'data' / 'MA_bill_embeddings.parquet',
        ]:
            if candidate.exists():
                parquet_path = candidate
                break

    out_dir = Path(args.output_dir) if args.output_dir else repo_root / 'data'

    print(f'Database: {db_path}')
    print(f'Parquet:  {parquet_path}')
    print(f'Output:   {out_dir}')
    print()

    if db_path is None or not db_path.exists():
        print(f'ERROR: Database not found. Use --db-path.', file=sys.stderr)
        sys.exit(1)

    engine = create_engine(f'sqlite:///{db_path}')
    parquet_df = load_parquet(parquet_path) if parquet_path else pd.DataFrame()

    out_dir.mkdir(parents=True, exist_ok=True)

    export_clusters(engine, out_dir)
    export_bills_list(engine, parquet_df, out_dir)
    export_bills_detail(engine, parquet_df, out_dir)
    export_employers(engine, parquet_df, out_dir)
    export_lobbyists(engine, parquet_df, out_dir)
    export_edges_by_bill(engine, out_dir)
    export_edges_by_employer(engine, parquet_df, out_dir)

    write_json(out_dir / 'last_updated.json', {'date': date.today().isoformat()}, 'last_updated')
    print('\nExport complete.')


if __name__ == '__main__':
    main()
