const select = document.querySelector('#system-select');
const statusText = document.querySelector('#status');
const summary = document.querySelector('#summary');
const systemsTrendPanel = document.querySelector('#systems-trend-panel');
const systemsTrendChart = document.querySelector('#systems-trend-chart');
const systemsTrendLabels = document.querySelector('#systems-trend-labels');
const systemsTrendLegend = document.querySelector('#systems-trend-legend');
const overviewPeriod = document.querySelector('#overview-period');
const systemsList = document.querySelector('#systems');
const reportSection = document.querySelector('#report-section');
const report = document.querySelector('#report');
const reportStatus = document.querySelector('#report-status');
const overview = document.querySelector('#overview');

function getTheme() {
  try {
    const saved = localStorage.getItem('robot_report_theme');
    if (saved === 'dark' || saved === 'light') return saved;
  } catch (_) { /* Armazenamento opcional. */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function setTheme(theme) {
  if (theme !== 'dark' && theme !== 'light') return;
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('robot_report_theme', theme); } catch (_) { /* Armazenamento opcional. */ }
}

setTheme(getTheme());

function makeCard(label, value) {
  const card = document.createElement('div');
  const strong = document.createElement('strong');
  const small = document.createElement('small');
  card.className = 'card';
  strong.textContent = value;
  small.textContent = label;
  card.append(strong, small);
  return card;
}

function formatNumber(value, digits = 1) {
  return new Intl.NumberFormat('pt-BR', {maximumFractionDigits: digits}).format(Number(value) || 0);
}

function drawSystemsTrend(series) {
  const ns = 'http://www.w3.org/2000/svg';
  systemsTrendChart.replaceChildren();
  systemsTrendLabels.replaceChildren();
  systemsTrendLegend.replaceChildren();
  const visible = series.filter(item => item.trend?.length);
  systemsTrendPanel.hidden = !visible.length;
  if (!visible.length) return;

  const palette = ['#16835a', '#2878c8', '#d94b43', '#9057b2', '#d68b17', '#159eaa', '#dc4c91', '#626cbe', '#668c2d', '#a95d37'];
  const allDates = visible.flatMap(item => item.trend.map(point => Date.parse(`${point.date}T00:00:00Z`))).filter(Number.isFinite);
  const minDate = Math.min(...allDates), maxDate = Math.max(...allDates);
  const dateSpan = maxDate - minDate || 1;
  const xFor = date => 56 + ((Date.parse(`${date}T00:00:00Z`) - minDate) / dateSpan) * 620;
  const yFor = rate => 24 + (100 - Number(rate || 0)) * 1.55;

  [0, 50, 100].forEach(rate => {
    const y = yFor(rate);
    const line = document.createElementNS(ns, 'line');
    const label = document.createElementNS(ns, 'text');
    line.setAttribute('x1', '50'); line.setAttribute('x2', '690');
    line.setAttribute('y1', String(y)); line.setAttribute('y2', String(y));
    line.setAttribute('class', 'chart-grid');
    label.setAttribute('x', '0'); label.setAttribute('y', String(y + 4));
    label.setAttribute('class', 'chart-axis-label'); label.textContent = `${rate}%`;
    systemsTrendChart.append(line, label);
  });

  const nameCounts = new Map();
  visible.forEach(item => nameCounts.set(item.name, (nameCounts.get(item.name) || 0) + 1));
  visible.forEach((item, index) => {
    const color = palette[index % palette.length];
    const points = item.trend.map(point => ({x: xFor(point.date), y: yFor(point.pass_rate), entry: point}));
    if (points.length > 1) {
      const line = document.createElementNS(ns, 'polyline');
      line.setAttribute('class', 'system-approval-line');
      line.setAttribute('stroke', color);
      line.setAttribute('points', points.map(point => `${point.x},${point.y}`).join(' '));
      systemsTrendChart.append(line);
    }
    points.forEach(point => {
      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('cx', String(point.x)); circle.setAttribute('cy', String(point.y));
      circle.setAttribute('r', '4'); circle.setAttribute('class', 'system-approval-point');
      circle.setAttribute('stroke', color);
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${item.name} (${item.id}) · ${point.entry.date} · ${formatNumber(point.entry.pass_rate)}% · ${point.entry.passed}/${point.entry.total} casos aprovados`;
      circle.append(title); systemsTrendChart.append(circle);
    });
    const legendItem = document.createElement('span');
    const swatch = document.createElement('i');
    const label = document.createElement('span');
    swatch.style.borderColor = color;
    label.textContent = nameCounts.get(item.name) > 1 ? `${item.name} (${item.id})` : item.name;
    legendItem.append(swatch, label); systemsTrendLegend.append(legendItem);
  });

  const dates = [...new Set(visible.flatMap(item => item.trend.map(point => point.date)))].sort();
  const dateLabels = [...new Set([dates[0], dates[Math.floor((dates.length - 1) / 2)], dates.at(-1)])]
    .map(value => new Date(`${value}T00:00:00`).toLocaleDateString('pt-BR'));
  const labels = [document.createElement('span'), document.createElement('span'), document.createElement('span')];
  labels[0].textContent = dateLabels[0] || '';
  labels[1].textContent = dateLabels.length > 2 ? dateLabels[1] : '';
  labels[2].textContent = dateLabels.length > 1 ? dateLabels.at(-1) : '';
  systemsTrendLabels.append(...labels);
}

let overviewRequest = 0;
async function loadOverview(period = overviewPeriod.value) {
  const requestId = ++overviewRequest;
  const response = await fetch(`/public/api/overview?period=${encodeURIComponent(period)}`, {cache: 'no-store'});
  if (!response.ok) throw new Error(`A API do resumo respondeu com HTTP ${response.status}.`);
  const data = await response.json();
  if (requestId !== overviewRequest) return;
  summary.replaceChildren(
    makeCard('Sistemas', data.applications.length),
    makeCard('Cenários nas execuções mais recentes', data.latest.total),
    makeCard('Aprovados', data.latest.passed),
    makeCard('Falhas', data.latest.failed),
    makeCard('Aprovação', `${formatNumber(data.latest.pass_rate)}%`)
  );
  summary.hidden = data.applications.length === 0;
  drawSystemsTrend(data.history_trend || []);
}

function showReport(systemId, systemName) {
  if (!systemId) {
    reportSection.hidden = true;
    report.removeAttribute('src');
    reportStatus.hidden = true;
    overview.hidden = false;
    const url = new URL(location.href);
    url.searchParams.delete('system');
    history.replaceState(null, '', url);
    return;
  }
  overview.hidden = true;
  reportSection.hidden = false;
  report.title = `Relatório de ${systemName}`;
  reportStatus.hidden = false;
  reportStatus.textContent = 'Carregando relatório detalhado…';
  const reportUrl = `/public/reports/${encodeURIComponent(systemId)}`;
  report.src = `${reportUrl}?v=${Date.now()}`;
  const url = new URL(location.href);
  url.searchParams.set('system', systemId);
  history.replaceState(null, '', url);
}

report.addEventListener('load', () => {
  reportStatus.hidden = true;
  report.contentWindow?.postMessage({type: 'robot-report-theme-sync', theme: getTheme()}, '*');
});
window.addEventListener('message', event => {
  if (event.source !== report.contentWindow || !event.data || event.data.type !== 'robot-report-theme') return;
  setTheme(event.data.theme);
});
select.addEventListener('change', () => {
  const option = select.selectedOptions[0];
  showReport(select.value, option?.textContent || '');
});
overviewPeriod.addEventListener('change', () => {
  loadOverview(overviewPeriod.value).catch(error => {
    statusText.textContent = `Não foi possível carregar as tendências: ${error.message}`;
  });
});
document.querySelector('#refresh-page').addEventListener('click', () => location.reload());

(async () => {
  try {
    const response = await fetch('/public/api/systems', {cache: 'no-store'});
    if (!response.ok) throw new Error('Não foi possível carregar os sistemas.');
    const data = await response.json();
    select.replaceChildren(new Option('Visão geral', ''));
    for (const system of data.systems) {
      select.add(new Option(`${system.name} · ${system.id} (${system.executions} execuções)`, system.id));
      const item = document.createElement('li');
      const button = document.createElement('button');
      const name = document.createElement('strong');
      const detail = document.createElement('small');
      button.type = 'button';
      name.textContent = system.name;
      detail.textContent = `ID: ${system.id} · ${system.executions} execução(ões) · versão ${system.system_version || 'não informada'} · Abrir relatório`;
      button.append(name, detail);
      button.addEventListener('click', () => {
        select.value = system.id;
        showReport(system.id, system.name);
      });
      item.append(button);
      systemsList.append(item);
    }
    select.disabled = false;
    statusText.textContent = data.systems.length ? 'Selecione um sistema para abrir o relatório completo.' : 'Nenhum sistema foi importado ainda.';
    const requestedId = new URLSearchParams(location.search).get('system');
    if (requestedId && data.systems.some(system => system.id === requestedId)) {
      select.value = requestedId;
      showReport(requestedId, data.systems.find(system => system.id === requestedId).name);
    }
  } catch (error) {
    statusText.textContent = error.message;
    select.disabled = true;
    return;
  }

  try {
    await loadOverview();
  } catch (error) {
    console.error('Falha ao carregar o resumo público:', error);
    statusText.textContent = `${statusText.textContent} O resumo geral está indisponível: ${error.message}`;
  }
})();
