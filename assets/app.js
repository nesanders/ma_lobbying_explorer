const DATA = {
  billsList: fetch('data/bills_list.json').then(r => { if (!r.ok) throw new Error('bills_list.json not found'); return r.json(); }),
  employers:  fetch('data/employers.json').then(r => { if (!r.ok) throw new Error('employers.json not found'); return r.json(); }),
  lobbyists:  fetch('data/lobbyists.json').then(r => { if (!r.ok) throw new Error('lobbyists.json not found'); return r.json(); }),
  clusters:   fetch('data/clusters.json').then(r => { if (!r.ok) throw new Error('clusters.json not found'); return r.json(); }),
};

let _billsDetail = null, _edgesByBill = null, _edgesByEmployer = null;
let _billsDetailPromise = null, _edgesByEmployerPromise = null;

function getBillsDetail() {
  if (_billsDetailPromise) return _billsDetailPromise;
  _billsDetailPromise = Promise.all([
    fetch('data/bills_detail.json').then(r => { if (!r.ok) throw new Error('bills_detail.json not found'); return r.json(); }),
    fetch('data/edges_by_bill.json').then(r => { if (!r.ok) throw new Error('edges_by_bill.json not found'); return r.json(); }),
  ]).then(([d, e]) => {
    _billsDetail = d;
    _edgesByBill = e;
    return d;
  });
  return _billsDetailPromise;
}

function getEdgesByBill() {
  return getBillsDetail().then(() => _edgesByBill);
}

function getEdgesByEmployer() {
  if (_edgesByEmployerPromise) return _edgesByEmployerPromise;
  _edgesByEmployerPromise = fetch('data/edges_by_employer.json')
    .then(r => { if (!r.ok) throw new Error('edges_by_employer.json not found'); return r.json(); })
    .then(d => { _edgesByEmployer = d; return d; });
  return _edgesByEmployerPromise;
}

function routePage(listFn, detailParamKey, detailFn) {
  const p = new URLSearchParams(location.search);
  if (p.has(detailParamKey)) detailFn(p);
  else listFn();
}

function getParam(key) {
  return new URLSearchParams(location.search).get(key);
}

function setParam(key, val) {
  const p = new URLSearchParams(location.search);
  if (val === null || val === undefined || val === '') {
    p.delete(key);
  } else {
    p.set(key, val);
  }
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : location.pathname);
}

function pushState(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') p.set(k, v);
  }
  const qs = p.toString();
  history.pushState(null, '', qs ? '?' + qs : location.pathname);
}

function formatMoney(n) {
  if (n == null || isNaN(n)) return '$0';
  const abs = Math.abs(n);
  if (abs >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
  if (abs >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
  if (abs >= 1e3) return '$' + (n / 1e3).toFixed(0) + 'K';
  return '$' + Math.round(n).toLocaleString();
}

function positionChip(pos) {
  const map = {
    'Support':     { bg: '#16a34a', text: '#fff' },
    'Oppose':      { bg: '#dc2626', text: '#fff' },
    'Neutral':     { bg: '#6b7280', text: '#fff' },
    'No position': { bg: '#e5e7eb', text: '#374151' },
  };
  const normalized = pos ? pos.trim() : 'No position';
  const style = map[normalized] || map['No position'];
  return `<span class="position-chip" style="background:${style.bg};color:${style.text}">${escHtml(normalized)}</span>`;
}

function slugify(name) {
  return String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

// Normalize a slug to match entity normalization applied in export_json.py.
// Used as a fallback lookup when a URL slug predates the normalization (e.g.
// "partners-in-democracy-inc" -> "partners-in-democracy").
function normalizeSlug(slug) {
  return slug
    .replace(/[- ]+(llc|llp|inc|incorporated|corporation|corp|ltd|limited|pc|pllc)\b/gi, '')
    .replace(/[- ]+the\b/gi, '')
    .replace(/\bthe[- ]+/gi, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fuzzyFilter(rows, query, fields) {
  if (!query || !query.trim()) return rows;
  const q = query.trim().toLowerCase();
  const terms = q.split(/\s+/);
  return rows.filter(row => {
    const haystack = fields.map(f => String(row[f] ?? '')).join(' ').toLowerCase();
    return terms.every(t => haystack.includes(t));
  });
}

function renderTable(container, columns, rows, opts = {}) {
  const { pageSize = 50, sortable = true } = opts;
  let currentPage = 0;
  let sortCol = opts.defaultSortCol ?? null;
  let sortDir = opts.defaultSortDir ?? 'desc';
  let sortedRows = [...rows];

  function doSort() {
    if (!sortCol) return;
    const col = columns.find(c => c.key === sortCol);
    sortedRows = [...rows].sort((a, b) => {
      let va = col && col.sortVal ? col.sortVal(a) : (a[sortCol] ?? 0);
      let vb = col && col.sortVal ? col.sortVal(b) : (b[sortCol] ?? 0);
      if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      return sortDir === 'asc' ? va - vb : vb - va;
    });
  }

  function render() {
    doSort();
    const total = sortedRows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.min(currentPage, totalPages - 1);
    const slice = sortedRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize);

    const head = columns.map(c => {
      const isSorted = c.key === sortCol;
      const icon = isSorted ? (sortDir === 'asc' ? '▲' : '▼') : '⇅';
      const sortAttr = sortable && c.sortable !== false ? `data-sort="${c.key}"` : '';
      return `<th class="${isSorted ? 'sorted' : ''} ${c.className || ''}" ${sortAttr}>${escHtml(c.label)}<span class="sort-icon">${sortable && c.sortable !== false ? icon : ''}</span></th>`;
    }).join('');

    const body = slice.map((row, i) => {
      const cells = columns.map(c => {
        const val = c.render ? c.render(row) : escHtml(row[c.key]);
        return `<td class="${c.className || ''}">${val}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    const showing = total === 0 ? 'No results' : `Showing ${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, total)} of ${total.toLocaleString()}`;

    container.innerHTML = `
      <div class="results-count">${showing}</div>
      <div class="table-wrap">
        <table>
          <thead><tr>${head}</tr></thead>
          <tbody>${body || '<tr><td colspan="${columns.length}" class="no-data">No results found.</td></tr>'}</tbody>
        </table>
      </div>
      ${totalPages > 1 ? `<div class="pagination">
        <button id="pg-first" ${currentPage === 0 ? 'disabled' : ''}>«</button>
        <button id="pg-prev" ${currentPage === 0 ? 'disabled' : ''}>‹</button>
        <span class="page-info">Page ${currentPage + 1} of ${totalPages}</span>
        <button id="pg-next" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>›</button>
        <button id="pg-last" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>»</button>
      </div>` : ''}
    `;

    if (sortable) {
      container.querySelectorAll('thead th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.sort;
          if (sortCol === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
          else { sortCol = key; sortDir = 'desc'; }
          currentPage = 0;
          render();
        });
      });
    }

    const pgFirst = container.querySelector('#pg-first');
    const pgPrev = container.querySelector('#pg-prev');
    const pgNext = container.querySelector('#pg-next');
    const pgLast = container.querySelector('#pg-last');
    if (pgFirst) pgFirst.addEventListener('click', () => { currentPage = 0; render(); });
    if (pgPrev) pgPrev.addEventListener('click', () => { currentPage = Math.max(0, currentPage - 1); render(); });
    if (pgNext) pgNext.addEventListener('click', () => { currentPage = Math.min(totalPages - 1, currentPage + 1); render(); });
    if (pgLast) pgLast.addEventListener('click', () => { currentPage = totalPages - 1; render(); });
  }

  render();

  return {
    update(newRows) {
      rows = newRows;
      sortedRows = [...rows];
      currentPage = 0;
      render();
    }
  };
}

function showLoading(el, msg = 'Loading…') {
  el.innerHTML = `<div class="loading">${escHtml(msg)}</div>`;
}

function showError(el, msg) {
  el.innerHTML = `<div class="error-state"><strong>Data not yet available</strong>${msg ? escHtml(msg) : 'The data files have not been generated yet. Run <code>build/export_json.py</code> to create them.'}</div>`;
}

function passedBadge(passed) {
  if (passed === true || passed === 1) return '<span class="chip chip-passed">Passed</span>';
  if (passed === false || passed === 0) return '<span class="chip chip-failed">Not passed</span>';
  return '<span class="chip chip-unknown">Unknown</span>';
}

function malegLink(gc, billId, label) {
  const url = `https://malegislature.gov/Bills/${escHtml(String(gc))}/${escHtml(String(billId))}`;
  return `<a href="${url}" class="ext" target="_blank" rel="noopener">${escHtml(label || billId)}</a>`;
}

function sosEmployerUrl(name) {
  const encoded = encodeURIComponent(name);
  return `https://www.sec.state.ma.us/LobbyistPublicSearch/Default.aspx?searchType=employer&employerName=${encoded}`;
}
