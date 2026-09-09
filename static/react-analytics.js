// IronTrack Summary — plain JavaScript (no runtime Babel needed).
// Reads chart colors from the design system tokens in /css/tokens.css,
// so charts match whatever theme is active.
const { useState, useEffect, useRef } = React;

function themeColors() {
  const s = getComputedStyle(document.documentElement);
  const cv = (n, fb) => (s.getPropertyValue(n) || fb).trim();
  return {
    lime:    cv('--lime', '#e8ff00'),
    surface: cv('--card3', '#242424'),
    muted:   cv('--g2', '#888'),
    success: cv('--emerald', '#22c55e'),
    amber:   cv('--amber', '#f59e0b'),
    panel:   cv('--card', '#101010'),
    grid:    cv('--line', '#2e2e2e'),
  };
}

function OverviewCards({ stats }) {
  const config = [
    { icon: 'check-circle', label: 'Completed', value: stats.completed, highlight: false },
    { icon: 'bar-chart-2', label: 'Overall Rate', value: stats.percent + '%', highlight: true },
    { icon: 'list', label: 'Total Exercises', value: stats.total, highlight: false },
  ];
  return React.createElement('div', { className: 'summary-overview' },
    ...config.map((c, i) =>
      React.createElement('div', {
        key: i,
        className: 'overview-card' + (c.highlight ? ' highlight' : '')
      },
        React.createElement('span', { className: 'overview-icon' },
          React.createElement('svg', {
            width: 20, height: 20, viewBox: '0 0 24 24',
            fill: 'none', stroke: 'currentColor', strokeWidth: 2,
            strokeLinecap: 'round', strokeLinejoin: 'round'
          },
            c.icon === 'check-circle' &&
              React.createElement(React.Fragment, null,
                React.createElement('path', { d: 'M22 11.08V12a10 10 0 1 1-5.93-9.14' }),
                React.createElement('polyline', { points: '22 4 12 14.01 9 11.01' })
              ),
            c.icon === 'bar-chart-2' &&
              React.createElement(React.Fragment, null,
                React.createElement('line', { x1: 18, y1: 20, x2: 18, y2: 10 }),
                React.createElement('line', { x1: 12, y1: 20, x2: 12, y2: 4 }),
                React.createElement('line', { x1: 6, y1: 20, x2: 6, y2: 14 })
              ),
            c.icon === 'list' &&
              React.createElement(React.Fragment, null,
                React.createElement('line', { x1: 8, y1: 6, x2: 21, y2: 6 }),
                React.createElement('line', { x1: 8, y1: 12, x2: 21, y2: 12 }),
                React.createElement('line', { x1: 8, y1: 18, x2: 21, y2: 18 }),
                React.createElement('line', { x1: 3, y1: 6, x2: 3.01, y2: 6 }),
                React.createElement('line', { x1: 3, y1: 12, x2: 3.01, y2: 12 }),
                React.createElement('line', { x1: 3, y1: 18, x2: 3.01, y2: 18 })
              )
          )
        ),
        React.createElement('span', { className: 'overview-number' }, c.value),
        React.createElement('span', { className: 'overview-label' }, c.label)
      )
    )
  );
}

function ProgressBar({ pct }) {
  return React.createElement('div', null,
    React.createElement('div', { className: 'progress-bar-container' },
      React.createElement('div', {
        className: 'progress-bar',
        style: { width: pct + '%' }
      })
    ),
    React.createElement('p', { className: 'progress-label' }, pct + '% Complete')
  );
}

function DonutChart({ stats, theme }) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    if (chartRef.current) chartRef.current.destroy();
    const ctx = ref.current.getContext('2d');
    const c = themeColors();
    chartRef.current = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Completed', 'Remaining'],
        datasets: [{
          data: [stats.completed, stats.total - stats.completed],
          backgroundColor: [c.lime, c.surface],
          borderColor: [c.panel, c.panel],
          borderWidth: 4,
          hoverOffset: 6
        }]
      },
      options: {
        cutout: '72%',
        plugins: {
          legend: { labels: { color: c.muted, font: { size: 12 } } }
        }
      }
    });
    return () => { if (chartRef.current) chartRef.current.destroy(); };
  }, [stats, theme]);

  return React.createElement('div', { className: 'chart-card' },
    React.createElement('h3', { className: 'chart-title' }, 'COMPLETION RATE'),
    React.createElement('canvas', { ref, width: 220, height: 220 }),
    React.createElement('p', { className: 'chart-sub' }, `${stats.completed} of ${stats.total} exercises done`)
  );
}

function BarChart({ days, theme }) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const labels = Object.keys(days);
  const values = Object.values(days).map(d => d.percent);

  useEffect(() => {
    if (!ref.current) return;
    if (chartRef.current) chartRef.current.destroy();
    const ctx = ref.current.getContext('2d');
    const c = themeColors();
    const colors = values.map(p => p === 100 ? c.success : p > 50 ? c.lime : p > 0 ? c.amber : c.surface);
    chartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels.map(d => d.split(' ')[0] + ' ' + d.split(' ')[1]),
        datasets: [{
          label: 'Completion %',
          data: values,
          backgroundColor: colors,
          borderRadius: 6,
          borderSkipped: false
        }]
      },
      options: {
        responsive: true,
        scales: {
          y: {
            min: 0, max: 100,
            ticks: { color: c.muted, callback: v => v + '%' },
            grid: { color: c.grid }
          },
          x: {
            ticks: { color: c.muted, font: { size: 10 } },
            grid: { display: false }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: ctx => ctx.parsed.y + '% complete' }
          }
        }
      }
    });
    return () => { if (chartRef.current) chartRef.current.destroy(); };
  }, [days, theme]);

  return React.createElement('div', { className: 'chart-card chart-card-wide' },
    React.createElement('h3', { className: 'chart-title' }, 'PROGRESS BY DAY'),
    React.createElement('canvas', { ref, height: 220 })
  );
}

function DayBreakdown({ days }) {
  const entries = Object.entries(days);
  return React.createElement('div', { className: 'day-breakdown glass' },
    React.createElement('div', { className: 'day-breakdown-header' },
      React.createElement('h2', null, 'DAY BY DAY'),
      React.createElement('span', { className: 'day-breakdown-badge' }, `${entries.length} days`)
    ),
    ...entries.map(([day, data]) =>
      React.createElement('div', { key: day, className: 'day-row' },
        React.createElement('span', { className: 'day-name' }, day),
        React.createElement('div', { className: 'day-bar-wrap' },
          React.createElement('div', { className: 'day-bar', style: { width: data.percent + '%' } })
        ),
        React.createElement('span', { className: 'day-count' }, `${data.completed}/${data.total}`),
        React.createElement('span', { className: 'day-percent' }, `${data.percent}%`)
      )
    )
  );
}

function useTheme() {
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  useEffect(() => {
    const onTheme = () => setTheme(document.documentElement.getAttribute('data-theme') || 'dark');
    document.addEventListener('themechange', onTheme);
    return () => document.removeEventListener('themechange', onTheme);
  }, []);
  return theme;
}

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const theme = useTheme();

  useEffect(() => {
    fetch('/api/summary-data')
      .then(r => r.json())
      .then(d => {
        if (d.error) setError(d.error);
        else setData(d);
      })
      .catch(() => setError('Failed to load analytics'));
  }, []);

  if (error) {
    return React.createElement('div', { className: 'flash-message' }, error);
  }
  if (!data) {
    return React.createElement('div', { style: { textAlign: 'center', padding: '3rem', color: 'var(--g3)' } },
      React.createElement('div', { className: 'typing-dots' },
        React.createElement('span', null),
        React.createElement('span', null),
        React.createElement('span', null)
      )
    );
  }

  const { stats, streak } = data;
  return React.createElement(React.Fragment, null,
    React.createElement(OverviewCards, { stats }),
    React.createElement(ProgressBar, { pct: stats.percent }),
    React.createElement('div', { className: 'charts-row' },
      React.createElement(DonutChart, { stats, theme }),
      React.createElement(BarChart, { days: stats.days, theme })
    ),
    React.createElement(DayBreakdown, { days: stats.days })
  );
}

const root = ReactDOM.createRoot(document.getElementById('react-analytics-root'));
root.render(React.createElement(App));