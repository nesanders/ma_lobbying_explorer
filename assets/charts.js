let _chartJsReady = null;

function loadChartJs() {
  if (_chartJsReady) return _chartJsReady;
  _chartJsReady = new Promise((resolve, reject) => {
    if (window.Chart) { resolve(window.Chart); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js';
    s.onload = () => resolve(window.Chart);
    s.onerror = () => reject(new Error('Failed to load Chart.js from CDN'));
    document.head.appendChild(s);
  });
  return _chartJsReady;
}

const COLORS = {
  support: '#16a34a',
  oppose:  '#dc2626',
  neutral: '#6b7280',
  none:    '#e5e7eb',
  primary: '#2563eb',
  env:     '#16a34a',
};

function destroyChart(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();
}

function renderPositionBar(canvasId, { n_supporters = 0, n_opposers = 0, n_neutrals = 0, n_no_position = 0 } = {}) {
  return loadChartJs().then(Chart => {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ['Positions'],
        datasets: [
          { label: 'Support', data: [n_supporters], backgroundColor: COLORS.support },
          { label: 'Oppose',  data: [n_opposers],  backgroundColor: COLORS.oppose },
          { label: 'Neutral', data: [n_neutrals],  backgroundColor: COLORS.neutral },
          { label: 'No position', data: [n_no_position], backgroundColor: COLORS.none },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw}` } },
        },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, display: false },
        },
      },
    });
  });
}

function renderPositionDonut(canvasId, positions = {}) {
  return loadChartJs().then(Chart => {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const sup = positions.support ?? 0;
    const opp = positions.oppose ?? 0;
    const neu = positions.neutral ?? 0;
    const non = positions.none ?? 0;
    return new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['Support', 'Oppose', 'Neutral', 'No position'],
        datasets: [{
          data: [sup, opp, neu, non],
          backgroundColor: [COLORS.support, COLORS.oppose, COLORS.neutral, COLORS.none],
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } },
        },
      },
    });
  });
}

function renderScatter(canvasId, data, opts = {}) {
  return loadChartJs().then(Chart => {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    return new Chart(canvas, {
      type: 'scatter',
      data: {
        datasets: [{
          label: opts.label || 'Employers',
          data,
          backgroundColor: opts.color || 'rgba(37,99,235,0.5)',
          pointRadius: d => d.r || 5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const pt = ctx.raw;
                return opts.tooltipLabel ? opts.tooltipLabel(pt) : `(${pt.x}, ${pt.y})`;
              },
            },
          },
        },
        scales: {
          x: {
            type: opts.xType || 'logarithmic',
            title: { display: !!opts.xLabel, text: opts.xLabel || '' },
            ticks: {
              callback: v => {
                if (opts.xFormat) return opts.xFormat(v);
                if (v >= 1e6) return '$' + (v/1e6).toFixed(0) + 'M';
                if (v >= 1e3) return '$' + (v/1e3).toFixed(0) + 'K';
                return '$' + v;
              },
            },
          },
          y: {
            title: { display: !!opts.yLabel, text: opts.yLabel || '' },
            ticks: {
              callback: v => opts.yFormat ? opts.yFormat(v) : v + '%',
            },
          },
        },
        onClick: opts.onClick,
      },
    });
  });
}

function renderBar(canvasId, labels, values, opts = {}) {
  return loadChartJs().then(Chart => {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: opts.label || '',
          data: values,
          backgroundColor: opts.color || COLORS.primary,
        }],
      },
      options: {
        indexAxis: opts.horizontal !== false ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => opts.tooltipLabel ? opts.tooltipLabel(ctx.raw) : ctx.raw,
            },
          },
        },
        scales: {
          x: {
            grid: { display: opts.horizontal !== false },
            ticks: {
              callback: opts.horizontal !== false && opts.xFormat
                ? v => opts.xFormat(v)
                : function(val) {
                    const label = this.getLabelForValue(val);
                    return label && label.length > 28 ? label.substring(0, 26) + '…' : label;
                  },
            },
          },
          y: {
            grid: { display: opts.horizontal === false },
            ticks: {
              font: { size: 11 },
              callback: opts.horizontal === false && opts.xFormat
                ? v => opts.xFormat(v)
                : function(val) {
                    const label = this.getLabelForValue(val);
                    return label && label.length > 28 ? label.substring(0, 26) + '…' : label;
                  },
            },
          },
        },
      },
    });
  });
}

function renderTimeline(canvasId, yearData, opts = {}) {
  return loadChartJs().then(Chart => {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const years = Object.keys(yearData).sort();
    const billCounts = years.map(y => yearData[y].bills || 0);
    const compensations = years.map(y => yearData[y].compensation || 0);
    return new Chart(canvas, {
      type: 'line',
      data: {
        labels: years,
        datasets: [
          {
            label: 'Bills',
            data: billCounts,
            borderColor: COLORS.primary,
            backgroundColor: 'rgba(37,99,235,0.1)',
            yAxisID: 'y',
            tension: 0.3,
            pointRadius: 4,
          },
          {
            label: 'Compensation',
            data: compensations,
            borderColor: COLORS.env,
            backgroundColor: 'rgba(22,163,74,0.1)',
            yAxisID: 'y1',
            tension: 0.3,
            pointRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: ctx => {
                if (ctx.datasetIndex === 1) return `Compensation: ${formatMoney(ctx.raw)}`;
                return `Bills: ${ctx.raw}`;
              },
            },
          },
        },
        scales: {
          y: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: 'Bills' },
            ticks: { precision: 0 },
          },
          y1: {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Compensation' },
            grid: { drawOnChartArea: false },
            ticks: { callback: v => formatMoney(v) },
          },
        },
      },
    });
  });
}
