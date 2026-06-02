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

## How to update the data

1. Ensure the [MAenvironmentaldata](https://github.com/nesanders/MAenvironmentaldata) repository is checked out as a sibling of this repo.

2. Run the export script:
   ```bash
   cd build/
   python export_json.py
   ```
   This reads `AMEND.db` and `MA_bill_embeddings.parquet` from the AMEND repo and writes JSON files to `data/`.

   Optional flags:
   ```
   --db-path /path/to/AMEND.db
   --parquet-path /path/to/MA_bill_embeddings.parquet
   --output-dir /path/to/output/
   ```

3. Copy the generated JSON files to the `data/` directory (already done if you used the default output dir).

4. Commit and push:
   ```bash
   git add data/
   git commit -m "Update data $(date +%Y-%m-%d)"
   git push
   ```

GitHub Pages will automatically serve the updated site within a minute or two.

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
