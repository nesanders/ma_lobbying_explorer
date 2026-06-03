# MA Lobbying Explorer

A static site for browsing Massachusetts Legislature lobbying disclosures, 2009–2026.

**Live site:** https://nesanders.github.io/ma_lobbying_explorer

## Data sources

- **MA Secretary of State — Lobbyist Public Search**
  https://www.sec.state.ma.us/LobbyistPublicSearch/
  Source of all lobbying registration and disclosure data: employers, lobbying firms, compensation, and bill positions.

- **MA General Court (Legislature)**
  https://malegislature.gov
  Full bill text, docket history, committee assignments.

Data is processed by the [AMEND project](https://github.com/nesanders/MAenvironmentaldata) which adds LLM-based environmental relevance scoring, bill summaries, categories, and tags.

## Automated deploys

A GitHub Actions workflow (`.github/workflows/rebuild.yml`) runs every Monday at 06:00 UTC. It:
1. Downloads `amend.db.gz` and `MA_bill_embeddings.parquet` from `gs://openamend-data/` (public, no auth required)
2. Runs `build/export_json.py` to generate the JSON data files
3. Deploys the full site (HTML + CSS + JS + data) to GitHub Pages

To trigger a manual rebuild: **Actions → Rebuild and deploy → Run workflow**.

The `data/` directory is not committed to git — JSON files are generated fresh on each deploy and served directly from GitHub Pages alongside the HTML:

| File | URL |
|------|-----|
| bills_list.json | https://nesanders.github.io/ma_lobbying_explorer/data/bills_list.json |
| bills_detail.json | https://nesanders.github.io/ma_lobbying_explorer/data/bills_detail.json |
| employers.json | https://nesanders.github.io/ma_lobbying_explorer/data/employers.json |
| lobbyists.json | https://nesanders.github.io/ma_lobbying_explorer/data/lobbyists.json |
| edges_by_bill.json | https://nesanders.github.io/ma_lobbying_explorer/data/edges_by_bill.json |
| edges_by_employer.json | https://nesanders.github.io/ma_lobbying_explorer/data/edges_by_employer.json |
| clusters.json | https://nesanders.github.io/ma_lobbying_explorer/data/clusters.json |

## How to update the data locally

```bash
curl -fL https://storage.googleapis.com/openamend-data/amend.db.gz | gunzip > amend.db
curl -fL https://storage.googleapis.com/openamend-data/MA_bill_embeddings.parquet \
     -o MA_bill_embeddings.parquet

python build/export_json.py \
  --db-path amend.db \
  --parquet-path MA_bill_embeddings.parquet \
  --output-dir data/
```

Then serve locally:
```bash
node server.js --port=8080
```

## File structure

```
index.html          Landing page with global search and summary stats
bills.html          Bill list + detail view
employers.html      Employer list + detail view
lobbyists.html      Lobbying firm list + detail view
assets/
  style.css         Shared styles
  app.js            Shared data loading, routing, table rendering
  charts.js         Chart.js wrapper helpers
build/
  export_json.py    Data export script (requires AMEND repo)
data/               JSON data files (generated, not committed by default)
  bills_list.json
  bills_detail.json
  employers.json
  lobbyists.json
  edges_by_bill.json
  edges_by_employer.json
  clusters.json
  last_updated.json
```

## Architecture

Pure static site — no Node.js, no build step, no server required. All data is pre-built JSON loaded by the browser. Routing uses URL query parameters (`bills.html?id=H1234&gc=194`). All filtering runs client-side.

Large files (`bills_detail.json`, `edges_by_bill.json`, `edges_by_employer.json`) are lazy-loaded on first use and cached in memory for the session.
