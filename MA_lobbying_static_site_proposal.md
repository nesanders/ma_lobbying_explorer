# Static Browsable Site for MA Lobbying Data — Proposal

This document contains the prompt used to commission a separate AI agent to build
a static browsable site for the MA legislative lobbying dataset.

---

## Agent Prompt

You are building a **standalone static website** that makes the Massachusetts lobbying
dataset explorable by journalists, researchers, and the general public. The site covers
**all bills with any lobbying record** — not just environmental ones. Environmental
classification is one filter among many, not a scope constraint.

The site will be hosted on GitHub Pages and must work entirely without a backend — all
data is loaded as pre-built JSON files at page load, and all filtering, routing, and
rendering runs client-side in the browser. There is no build step that generates a
page per entity; instead, bill and employer detail views are rendered on-the-fly by
reading the URL query string (e.g. `bills.html?id=H1234&gc=194`).

### Source data

The source data is exported from the AMEND project (`github.com/nesanders/MAenvironmentaldata`).
You will work from pre-built JSON exports (described below). You do NOT need to access
any databases or APIs at runtime.

The **primary public data sources** this site presents are:

- **MA Secretary of State — Lobbyist Public Search portal**
  `https://www.sec.state.ma.us/LobbyistPublicSearch/`
  Source of all lobbying registration and disclosure data: employers, lobbying firms,
  compensation, and bill positions. Every employer and lobbyist record should link back here.

- **MA General Court (Legislature) website**
  `https://malegislature.gov/Bills/{general_court}/{bill_id}`
  e.g. `https://malegislature.gov/Bills/194/H1234`
  Full bill text, docket history, committee assignments, votes. Every bill record must
  link here. The general_court number and bill_id together form the permalink.

These links must appear prominently — on every bill detail page, every employer detail
page (linking to their SoS disclosure filing), and in the site footer.

### JSON data files

The key tables are:

1. **`data/bills_list.json`** — lean records for the bill list view (fast initial load).
   One record per unique MA legislative bill that was lobbied. Fields:
   - `bill_id` (string, e.g. "H1234")
   - `bill_number` (int), `general_court` (int, 186–194)
   - `bill_title` (string)
   - `is_env_llm` (bool) — LLM environmental classification
   - `env_relevance_score` (float 0–1)
   - `cluster_id` (int or null), `cluster_label` (string or null)
   - `n_supporters` (int), `n_opposers` (int), `n_neutrals` (int), `n_no_position` (int)
   - `passed` (bool or null)

2. **`data/bills_detail.json`** — full records for bill detail views (lazy-loaded).
   Keyed dict: `"{bill_id}_{general_court}"` → full record. Same fields as above plus:
   - `summary` (string or null — 1–3 sentence LLM summary)
   - `categories` (array of strings, e.g. ["Environmental Protection", "Energy"])
   - `tags` (array of strings, e.g. ["Renewable energy sources", "Pollution control"])

3. **`data/employers.json`** — one record per unique lobbying client (employer).
   Fields:
   - `client_name` (string) — the paying employer (not the lobbying firm)
   - `client_slug` (string) — URL-safe slug: `re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')`
   - `n_bills_total` (int), `n_bills_env` (int)
   - `env_fraction` (float 0–1)
   - `total_compensation` (float)
   - `env_compensation` (float)
   - `years_active` (array of ints)
   - `top_tags` (array of strings — top 5 LLM tags from their env bills; empty if none)
   - `positions` (object: `{support: int, oppose: int, neutral: int, none: int}`)
   - `sos_search_url` (string) — pre-built URL to the SoS portal search for this employer:
     `https://www.sec.state.ma.us/LobbyistPublicSearch/Default.aspx` with the employer
     name pre-filled as a query parameter (include the GET param pattern used by the portal)

4. **`data/lobbyists.json`** — one record per unique lobbying firm (entity).
   Fields:
   - `entity_name` (string)
   - `entity_slug` (string)
   - `n_clients` (int), `n_env_clients` (int)
   - `total_compensation` (float)
   - `years_active` (array of ints)
   - `sos_search_url` (string) — pre-built SoS portal search URL for this firm

5. **`data/edges_by_bill.json`** — edge records indexed by bill, for bill detail views.
   Keyed dict: `"{bill_id}_{general_court}"` → array of disclosure records.
   Each record: `{client_name, client_slug, entity_name, entity_slug, year, position}`.
   Note: `bill_id` and `general_court` are omitted from each record (redundant with the key).

6. **`data/edges_by_employer.json`** — edge records indexed by employer, for employer
   detail views. Keyed dict: `client_slug` → array of disclosure records.
   Each record: `{bill_id, general_court, bill_title, entity_name, entity_slug, year, position, is_env_llm}`.
   Note: `client_name` and `client_slug` omitted (redundant with the key).

7. **`data/clusters.json`** — one record per k-means cluster.
   Fields: `cluster_id`, `label`, `n_bills`, `n_env_bills`

**Realistic data size estimates** (strip JSON whitespace with `separators=(',',':')`):

| File | Raw | Gzipped | Load timing |
|------|-----|---------|-------------|
| bills_list.json | ~5 MB | ~1.2 MB | Eager — needed for list view |
| bills_detail.json | ~15 MB | ~4 MB | Lazy — first bill detail view |
| employers.json | ~3 MB | ~0.7 MB | Eager |
| lobbyists.json | ~0.5 MB | ~0.15 MB | Eager |
| edges_by_bill.json | ~25 MB | ~5 MB | Lazy — first bill detail view (same fetch trigger as bills_detail) |
| edges_by_employer.json | ~25 MB | ~5 MB | Lazy — first employer detail view |
| clusters.json | <5 KB | <2 KB | Eager |

The ~200k edges split across two keyed dicts gives O(1) lookup in either direction.
Employer names are long and repeat heavily within each employer's shard, so the gzip
ratio on `edges_by_employer.json` is especially good (~5×).

### URL and routing design

No server-side routing. All navigation uses query strings on flat HTML files:

| View | URL pattern |
|------|-------------|
| Landing page | `index.html` |
| Bill list | `bills.html` |
| Bill detail | `bills.html?id=H1234&gc=194` |
| Employer list | `employers.html` |
| Employer detail | `employers.html?name=associated-industries-of-massachusetts-aim` |
| Lobbyist list | `lobbyists.html` |
| Lobbyist detail | `lobbyists.html?name=some-firm-slug` |

Each `.html` file checks `new URLSearchParams(location.search)` on load. If detail
params are present → render detail view; otherwise → render list view. Filter state
is also reflected in query params via `history.replaceState` so filtered views are
bookmarkable and shareable.

### File structure

```
index.html
bills.html
employers.html
lobbyists.html
data/
  bills_list.json
  bills_detail.json       ← lazy-loaded
  employers.json
  lobbyists.json
  edges_by_bill.json      ← lazy-loaded with bills_detail
  edges_by_employer.json  ← lazy-loaded on first employer detail view
  clusters.json
assets/
  style.css
  app.js
  charts.js
build/
  export_json.py
```

No Jinja2, no templating engine, no build step beyond the Python export script.

### Shared JS architecture (`assets/app.js`)

```js
// Eager data loaded once at page start
const DATA = {
  billsList: fetch('data/bills_list.json').then(r => r.json()),
  employers:  fetch('data/employers.json').then(r => r.json()),
  lobbyists:  fetch('data/lobbyists.json').then(r => r.json()),
  clusters:   fetch('data/clusters.json').then(r => r.json()),
};

// Lazy singletons — fetched at most once per session
let _billsDetail = null, _edgesByBill = null, _edgesByEmployer = null;
function getBillsDetail()     { return (_billsDetail     ??= Promise.all([
  fetch('data/bills_detail.json').then(r => r.json()),
  fetch('data/edges_by_bill.json').then(r => r.json()),
]).then(([d, e]) => { _billsDetail = d; _edgesByBill = e; return d; })); }
function getEdgesByEmployer() { return (_edgesByEmployer ??=
  fetch('data/edges_by_employer.json').then(r => r.json())); }

// Route dispatcher
function routePage(listFn, detailParamKey, detailFn) {
  const p = new URLSearchParams(location.search);
  if (p.has(detailParamKey)) detailFn(p);
  else listFn();
}

// Shared virtualized table (renders only visible rows)
function renderTable(container, columns, rows, { pageSize = 50 } = {}) { ... }

// Shared fuzzy text filter
function fuzzyFilter(rows, query, fields) { ... }
```

`bills_detail.json` and `edges_by_bill.json` are always fetched together — a bill
detail view needs both. Fetch them in `Promise.all` to parallelize the two downloads.

### Pages specification

#### `index.html` — Landing page

- Site title: "MA Lobbying Explorer"
- Subtitle: "Browse Massachusetts Legislature lobbying disclosures, 2009–2026"
- Source attribution bar (prominent, near the top):
  > Data sourced from the [MA Secretary of State Lobbyist Public Search](https://www.sec.state.ma.us/LobbyistPublicSearch/)
  > and the [MA General Court](https://malegislature.gov). See [methodology](#) for details.
- Summary stat cards: total bills · total employers · sessions covered · total compensation
- Env highlight: "X bills were flagged environmentally relevant — [explore them →](`bills.html?env=1`)"
- Global search bar (searches bill titles + employer names, shows top-5 dropdown per category)
- Three explorer cards → bills.html, employers.html, lobbyists.html
- Footer:
  - Data: [MA Secretary of State](https://www.sec.state.ma.us/LobbyistPublicSearch/) ·
    [MA General Court](https://malegislature.gov)
  - Source code: [AMEND project](https://github.com/nesanders/MAenvironmentaldata) ·
    [this site](https://github.com/nesanders/ma_lobbying_explorer)
  - License: data CC BY 4.0, code MIT
  - Last updated date (written into the HTML by `export_json.py`)

#### `bills.html` — Bill list and bill detail

**List view** (no `?id` param):

- Filter bar (all params reflected in URL):
  - Text search (bill title)
  - 🌿 Environmental only toggle (default off)
  - General Court multi-select (GC186–GC194)
  - Cluster label dropdown
  - Position activity: any / has supporters / has opposers / contested
  - Passed: All / Passed / Not passed / Unknown
- Results: virtualized table, 50 rows rendered at a time, total count shown
  - Columns: Bill ID, Title, GC, Cluster, Clients, Sup/Opp, 🌿, Passed
  - Bill ID is a link to `bills.html?id=...&gc=...`; also opens detail in-page if preferred
  - Default sort: n_supporters + n_opposers descending

**Detail view** (`?id=H1234&gc=194`):

- "← All bills" breadcrumb
- Bill title (h1)
- **External links (prominent, above the fold):**
  - "📋 Full text on malegislature.gov ↗" → `https://malegislature.gov/Bills/{gc}/{bill_id}`
  - "🔍 View SoS lobbying disclosures ↗" → SoS portal deep-link to disclosures for this bill
    (construct URL using the portal's bill search parameters)
- Metadata chips row: GC badge · 🌿 env badge (if applicable) · env score · cluster label ·
  categories · tags · Passed badge
- LLM summary (blockquote styling; show "No summary available" in grey italic if null)
- "Who lobbied this bill" — fetches `bills_detail.json` + `edges_by_bill.json`:
  - Columns: Employer (→ `employers.html?name=slug`), Lobbying firm (→ `lobbyists.html?name=slug`),
    Year, Position chip
  - Position chips: Support = `#16a34a` green, Oppose = `#dc2626` red, Neutral = `#6b7280` grey
  - Sort: year desc
- Mini stacked bar (Chart.js inline): supporters vs opposers vs neutral vs none
- "See also" — 3 bills with most shared tags + same cluster, computed from `bills_list.json`

#### `employers.html` — Employer list and employer detail

**List view**:

- Source note: "Employer data from the [MA Secretary of State Lobbyist Public Search](https://www.sec.state.ma.us/LobbyistPublicSearch/)"
- Filters: text search · env fraction slider · min spend · active sessions
- Scatter (Chart.js): total_compensation (log x) vs env_fraction% (y), bubble = √n_bills
- Synced table: Employer · Total bills · Env bills · Env% · Total spend · Years active

**Detail view** (`?name=slug`):

- Employer name (h1) + "← All employers" breadcrumb
- **External links (prominent):**
  - "🔍 View on MA Secretary of State ↗" → `employer.sos_search_url`
    This is the SoS Lobbyist Public Search portal pre-filtered to this employer's disclosures.
    If a direct URL cannot be constructed for all employers, fall back to the base search URL
    `https://www.sec.state.ma.us/LobbyistPublicSearch/` with a note to search by name.
- Stats bar: Total spend · Env bills · Env fraction · Years active
- Top tags horizontal bar (Chart.js; only if n_bills_env > 0)
- Position donut (Support / Oppose / Neutral / No position)
- Timeline chart: bills per year + compensation per year (dual axis, Chart.js)
- Bills lobbied table (from `edges_by_employer.json`):
  - Columns: Bill ID (→ bill detail + `malegislature.gov` icon ↗), Title, GC, Year, Position, 🌿
  - Toggle: env only / all bills; default all
  - Sort: year desc
- "Most often on opposite sides" table (top 5, computed from `edges_by_employer.json`):
  - Find all bills this employer lobbied; for each, find others with opposite position;
    count and deduplicate by bill; rank by collision count
  - Columns: Opponent employer (→ employer detail), Bills in opposition
  - Link each opponent to their own employer detail page

#### `lobbyists.html` — Lobbyist firm list and detail

**List view**:
- Source note linking to SoS portal
- Table: Firm · Clients · Env clients · Total compensation · Years active
- Filters: text search, env clients only

**Detail view** (`?name=slug`):
- Firm name + **"🔍 View on MA Secretary of State ↗"** → `entity.sos_search_url`
- Stats: total clients · env clients · total compensation · years active
- Clients table (from `employers.json` filtered to this entity's appearances in edges):
  - Employer (→ employer detail) · Bills · Env bills · Years worked together
- Compensation per year bar chart (Chart.js)

### Data loading summary

```
Eager (page load):    bills_list.json   ~1.2 MB gzipped
                      employers.json    ~0.7 MB gzipped
                      lobbyists.json    ~0.15 MB gzipped
                      clusters.json     <2 KB
                      ─────────────────────────────────
                      Total eager:      ~2.1 MB gzipped

Lazy (bill detail):   bills_detail.json ~4 MB gzipped  ┐ fetched in parallel
                      edges_by_bill.json ~5 MB gzipped  ┘ Promise.all, cached

Lazy (emp detail):    edges_by_employer.json ~5 MB gzipped, cached
```

First bill detail view in a session: ~9 MB gzipped (~2–3s on 4G, <1s on broadband).
Subsequent bill detail views: instant (cached). Employer detail views use a separate
5 MB fetch also cached after first use. The page-load cost (2.1 MB) is always fast.

### Styling

- Font: system-ui / -apple-system (no web fonts)
- Links: `#2563eb` (blue); visited: `#7c3aed` (purple)
- Env accent: `#16a34a` (green) — used for 🌿 badges and env-related highlights only
- Background: `#f8f9fa`, card: `#fff`, `box-shadow: 0 1px 3px rgba(0,0,0,0.10)`
- Position chips: green / red / grey / light-grey as above
- Tables: sticky thead, alternating row shading, no outer border
- External links always open in a new tab (`target="_blank" rel="noopener"`) and
  display a `↗` icon so users know they're leaving the site
- Mobile responsive: single column below 640px; table columns collapse to hide
  less-critical columns (Env%, cluster) on small screens

### Non-goals

- Server-side rendering, Node.js, or any build toolchain
- User accounts or saved searches
- Real-time updates
- Per-entity static HTML files

### JSON export script (`build/export_json.py`)

Runs against `get_data/AMEND.db` + `docs/data/MA_bill_embeddings.parquet` in the AMEND repo.

**Actual DB tables (as implemented):**

| Table | Key columns |
|-------|-------------|
| `MA_Lobbying_Bills_Scored` | `bill_id`, `bill_number`, `general_court`, `bill_title`, `env_relevance_score`, `is_environmental`, `cluster_id` |
| `MA_Lobbying_Bills` | `entity_name`, `client_name`, `year`, `general_court`, `bill_number`, `bill_title`, `position`, `amount` — positions are `'Support'`, `'Oppose'`, `'Neutral'`, or null; **no `bill_id`** (join to Scored on `bill_number + general_court`) |
| `MA_Lobbying_Employers` | `entity_name`, `client_name`, `year`, `compensation` — annual per-client totals; used for all compensation aggregation |
| `MA_Legislature_Bills` | `bill_id`, `bill_number`, `general_court`, `bill_prefix`, `title`, `sponsor_name`, `status`, `passed` |
| `MA_Bill_Cluster_Labels` | `cluster_id`, `label`, `n_bills`, `n_env_bills` |
| Parquet | `bill_id`, `general_court`, `is_env_llm`, `env_relevance_score`, `summary`, `categories`, `tags` |

Key implementation notes:
- `cluster_label` is not in `MA_Lobbying_Bills_Scored`; join from `MA_Bill_Cluster_Labels`
- `passed` is not in `MA_Lobbying_Bills_Scored`; join from `MA_Legislature_Bills`
- `n_supporters`, `n_opposers`, etc. computed by counting distinct `client_name`s per position per bill in `MA_Lobbying_Bills`
- `bill_id` must be obtained via join to `MA_Lobbying_Bills_Scored` (not present in `MA_Lobbying_Bills`)
- Compensation comes from `MA_Lobbying_Employers`, not `MA_Lobbying_Bills.amount` (most `amount` values are zero)
- `env_compensation` is estimated as `total_compensation × env_fraction`

Key outputs:
- `bills_list.json`: lean bill records from `MA_Lobbying_Bills_Scored` + cluster labels + passed + position counts + parquet env flag
- `bills_detail.json`: full records including summary/categories/tags, keyed by `{bill_id}_{gc}`
- `employers.json`: per-`client_name` aggregates; compute `client_slug` and `sos_search_url`
- `lobbyists.json`: per-`entity_name` aggregates; compute `entity_slug` and `sos_search_url`
- `edges_by_bill.json`: `MA_Lobbying_Bills` grouped by `{bill_id}_{gc}`, fields trimmed
- `edges_by_employer.json`: same data grouped by `client_slug`, fields trimmed, `bill_title` joined in
- `clusters.json`: `MA_Bill_Cluster_Labels`

Run from repo root: `python build/export_json.py`
Dependencies: pandas, sqlalchemy, pyarrow. Use the `amend_python` conda env.

### Repository setup

New GitHub repository: `ma-lobbying-explorer` (public).
GitHub Pages: serve from `main` branch, root directory.

`README.md` must include:
- Live URL
- Data sources: MA Secretary of State (`https://www.sec.state.ma.us/LobbyistPublicSearch/`)
  and MA General Court (`https://malegislature.gov`), with attribution and CC BY 4.0 note
- How to update: re-run `export_json.py` → copy JSON files → commit and push
- Code license: MIT

---

*This proposal was drafted on 2026-06-01 as part of the AMEND environmental
data project. See the source repo at `github.com/nesanders/MAenvironmentaldata`.*
