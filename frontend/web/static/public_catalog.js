'use strict';

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
const reportStatus = document.querySelector('#report-status');
const report = document.querySelector('#report');
const overview = document.querySelector('#overview');
let loadedSystems = [];

const pdfModal = document.querySelector('#pdf-modal');
const openPdfModalBtn = document.querySelector('#open-pdf-modal');
const closePdfModalBtn = document.querySelector('#close-pdf-modal');
const cancelPdfModalBtn = document.querySelector('#cancel-pdf-modal');
const submitPdfModalBtn = document.querySelector('#submit-pdf-modal');
const pdfTitleInput = document.querySelector('#pdf-title');
const pdfSystemsContainer = document.querySelector('#pdf-systems-container');
const pdfStatus = document.querySelector('#pdf-status');
const pdfAllSystemsBtn = document.querySelector('#pdf-all-systems');
const pdfNoneSystemsBtn = document.querySelector('#pdf-none-systems');
const pdfAllSectionsBtn = document.querySelector('#pdf-all-sections');
const pdfNoneSectionsBtn = document.querySelector('#pdf-none-sections');

function getTheme() {
  try {
    const saved = localStorage.getItem('robot_report_theme');
    if (saved === 'dark' || saved === 'light') return saved;
  } catch (_) {
    // A disabled browser storage must not prevent the report from loading.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function setTheme(theme) {
  if (theme !== 'dark' && theme !== 'light') return;

  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('robot_report_theme', theme);
  } catch (_) {
    // The theme remains active for this page even when persistence is unavailable.
  }
}

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

function svgElement(name, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function drawAxes() {
  [0, 50, 100].forEach((rate) => {
    const y = 24 + (100 - rate) * 1.55;
    const line = svgElement('line', {
      x1: 50,
      x2: 690,
      y1: y,
      y2: y,
      class: 'chart-grid',
    });
    const label = svgElement('text', {
      x: 0,
      y: y + 4,
      class: 'chart-axis-label',
    });
    label.textContent = `${rate}%`;
    systemsTrendChart.append(line, label);
  });
}

function formatDate(date) {
  return new Date(`${date}T00:00:00`).toLocaleDateString('pt-BR');
}

function drawDateLabels(series) {
  const dates = [...new Set(series.flatMap((item) => item.trend.map((point) => point.date)))].sort();
  if (!dates.length) return;

  const midpoint = dates[Math.floor((dates.length - 1) / 2)];
  const labels = [...new Set([dates[0], midpoint, dates[dates.length - 1]])].map(formatDate);
  const elements = [document.createElement('span'), document.createElement('span'), document.createElement('span')];

  elements[0].textContent = labels[0] || '';
  elements[1].textContent = labels.length > 2 ? labels[1] : '';
  elements[2].textContent = labels.length > 1 ? labels[labels.length - 1] : '';
  systemsTrendLabels.append(...elements);
}

function setSeriesHighlight(systemId, highlighted) {
  systemsTrendChart.querySelectorAll('.system-approval-series').forEach((element) => {
    if (element.dataset.systemId === systemId) {
      element.classList.toggle('is-highlighted', highlighted);
    }
  });
}

function appendLegendItem(item, color, duplicateNames) {
  const legendItem = document.createElement('button');
  const swatch = document.createElement('i');
  const label = document.createElement('span');

  legendItem.type = 'button';
  legendItem.className = 'systems-trend-legend-item';
  legendItem.setAttribute('aria-pressed', 'true');
  legendItem.setAttribute('aria-label', `Ocultar ${item.name}`);
  swatch.style.borderColor = color;
  // Include the ID only when equal display names would otherwise be ambiguous.
  label.textContent = duplicateNames.has(item.name) ? `${item.name} (${item.id})` : item.name;
  legendItem.append(swatch, label);
  legendItem.addEventListener('click', () => {
    const visible = legendItem.getAttribute('aria-pressed') !== 'true';
    legendItem.setAttribute('aria-pressed', String(visible));
    legendItem.setAttribute(
      'aria-label',
      `${visible ? 'Ocultar' : 'Mostrar'} ${item.name}`
    );
    systemsTrendChart.querySelectorAll('.system-approval-series').forEach((element) => {
      if (element.dataset.systemId === item.id) {
        element.classList.toggle('is-hidden', !visible);
      }
    });
  });
  legendItem.addEventListener('pointerenter', () => setSeriesHighlight(item.id, true));
  legendItem.addEventListener('pointerleave', () => setSeriesHighlight(item.id, false));
  legendItem.addEventListener('focus', () => setSeriesHighlight(item.id, true));
  legendItem.addEventListener('blur', () => setSeriesHighlight(item.id, false));
  systemsTrendLegend.append(legendItem);
}

function drawSystemsTrend(series) {
  systemsTrendChart.replaceChildren();
  systemsTrendLabels.replaceChildren();
  systemsTrendLegend.replaceChildren();

  const visible = series.filter((item) => item.trend?.length);
  systemsTrendPanel.hidden = !visible.length;
  if (!visible.length) return;

  const palette = [
    '#16835a', '#2878c8', '#d94b43', '#9057b2', '#d68b17',
    '#159eaa', '#dc4c91', '#626cbe', '#668c2d', '#a95d37',
  ];
  const timestamps = visible
    .flatMap((item) => item.trend.map((point) => Date.parse(`${point.date}T00:00:00Z`)))
    .filter(Number.isFinite);
  const minDate = Math.min(...timestamps);
  const maxDate = Math.max(...timestamps);
  const dateSpan = maxDate - minDate || 1;
  const xFor = (date) => (
    56 + ((Date.parse(`${date}T00:00:00Z`) - minDate) / dateSpan) * 620
  );
  const yFor = (rate) => 24 + (100 - Number(rate || 0)) * 1.55;
  const nameCounts = new Map();

  visible.forEach((item) => nameCounts.set(item.name, (nameCounts.get(item.name) || 0) + 1));
  const duplicateNames = new Set(
    [...nameCounts.entries()].filter(([, count]) => count > 1).map(([name]) => name)
  );
  drawAxes();

  visible.forEach((item, index) => {
    const color = palette[index % palette.length];
    const points = item.trend.map((point) => ({
      x: xFor(point.date),
      y: yFor(point.pass_rate),
      entry: point,
    }));

    if (points.length > 1) {
      const line = svgElement('polyline', {
        class: 'system-approval-line system-approval-series',
        'data-system-id': item.id,
        stroke: color,
        points: points.map((point) => `${point.x},${point.y}`).join(' '),
      });
      systemsTrendChart.append(line);
    }

    points.forEach((point) => {
      const circle = svgElement('circle', {
        cx: point.x,
        cy: point.y,
        r: 4,
        class: 'system-approval-point system-approval-series',
        'data-system-id': item.id,
        role: 'img',
        stroke: color,
        tabindex: 0,
      });
      const title = svgElement('title');
      title.textContent = (
        `${item.name} (${item.id}) · ${point.entry.date} · ` +
        `${formatNumber(point.entry.pass_rate)}% · ` +
        `${point.entry.passed}/${point.entry.total} casos aprovados`
      );
      circle.setAttribute('aria-label', title.textContent);
      circle.append(title);
      circle.addEventListener('pointerenter', () => setSeriesHighlight(item.id, true));
      circle.addEventListener('pointerleave', () => setSeriesHighlight(item.id, false));
      circle.addEventListener('focus', () => setSeriesHighlight(item.id, true));
      circle.addEventListener('blur', () => setSeriesHighlight(item.id, false));
      systemsTrendChart.append(circle);
    });

    appendLegendItem(item, color, duplicateNames);
  });

  drawDateLabels(visible);
}

let overviewRequest = 0;
async function loadOverview(period = overviewPeriod.value) {
  const requestId = ++overviewRequest;
  const response = await fetch(
    `/public/api/overview?period=${encodeURIComponent(period)}`,
    {cache: 'no-store'}
  );
  if (!response.ok) {
    throw new Error(`A API do resumo respondeu com HTTP ${response.status}.`);
  }

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

function updateUrl(systemId) {
  const url = new URL(location.href);
  if (systemId) url.searchParams.set('system', systemId);
  else url.searchParams.delete('system');
  history.replaceState(null, '', url);
}

function showReport(systemId, systemName) {
  if (!systemId) {
    reportSection.hidden = true;
    report.removeAttribute('src');
    reportStatus.hidden = true;
    overview.hidden = false;
    updateUrl('');
    return;
  }

  overview.hidden = true;
  reportSection.hidden = false;
  report.title = `Relatório de ${systemName}`;
  reportStatus.hidden = false;
  reportStatus.textContent = 'Carregando relatório detalhado…';

  // The query value prevents the browser from reusing an old rendered report after an import.
  report.src = `/public/reports/${encodeURIComponent(systemId)}?v=${Date.now()}`;
  updateUrl(systemId);
}

function syncThemeWithReport() {
  reportStatus.hidden = true;
  report.contentWindow?.postMessage(
    {type: 'robot-report-theme-sync', theme: getTheme()},
    '*'
  );
}

function handleThemeMessage(event) {
  if (event.source !== report.contentWindow || !event.data || event.data.type !== 'robot-report-theme') {
    return;
  }
  setTheme(event.data.theme);
}

function renderSystemCard(system) {
  const item = document.createElement('li');
  const button = document.createElement('button');
  const name = document.createElement('strong');
  const detail = document.createElement('small');

  button.type = 'button';
  name.textContent = system.name;
  detail.textContent = (
    `ID: ${system.id} · ${system.executions} execução(ões) · ` +
    `versão ${system.system_version || 'não informada'} · Abrir relatório`
  );
  button.append(name, detail);
  button.addEventListener('click', () => {
    select.value = system.id;
    showReport(system.id, system.name);
  });
  item.append(button);
  return item;
}

async function loadSystems() {
  const response = await fetch('/public/api/systems', {cache: 'no-store'});
  if (!response.ok) throw new Error('Não foi possível carregar os sistemas.');

  const data = await response.json();
  loadedSystems = data.systems || [];
  select.replaceChildren(new Option('Visão geral', ''));
  loadedSystems.forEach((system) => {
    select.add(new Option(
      `${system.name} · ${system.id} (${system.executions} execuções)`,
      system.id
    ));
    systemsList.append(renderSystemCard(system));
  });

  select.disabled = false;
  statusText.textContent = loadedSystems.length
    ? 'Selecione um sistema para abrir o relatório completo.'
    : 'Nenhum sistema foi importado ainda.';

  const requestedId = new URLSearchParams(location.search).get('system');
  const requestedSystem = loadedSystems.find((system) => system.id === requestedId);
  if (requestedSystem) {
    select.value = requestedId;
    showReport(requestedId, requestedSystem.name);
  }
}

function openPdfModal() {
  if (!pdfModal) return;
  pdfSystemsContainer.innerHTML = '';
  const currentSelectedSystem = select.value;

  if (loadedSystems.length === 0) {
    pdfSystemsContainer.innerHTML = '<p style="margin:4px 0; color:var(--muted)">Nenhum sistema disponível no catálogo.</p>';
  } else {
    loadedSystems.forEach((sys) => {
      const label = document.createElement('label');
      label.className = 'checkbox-item';
      const isChecked = !currentSelectedSystem || currentSelectedSystem === sys.id;
      label.innerHTML = `
        <input type="checkbox" name="pdf_sys" value="${sys.id}" ${isChecked ? 'checked' : ''}>
        <span><strong>${sys.name}</strong> <small style="color:var(--muted)">· ${sys.id} (${sys.system_version || 'sem versão'})</small></span>
      `;
      pdfSystemsContainer.appendChild(label);
    });
  }

  if (currentSelectedSystem && select.selectedOptions[0]) {
    pdfTitleInput.value = `Relatório de Testes — ${select.selectedOptions[0].textContent.split('·')[0].trim()}`;
  } else {
    pdfTitleInput.value = 'Relatório Consolidado de Testes Automatizados';
  }

  pdfStatus.hidden = true;
  pdfStatus.textContent = '';
  pdfStatus.className = 'modal-status';
  submitPdfModalBtn.disabled = false;
  submitPdfModalBtn.textContent = 'Baixar PDF';
  pdfModal.hidden = false;
}

function closePdfModal() {
  if (pdfModal) pdfModal.hidden = true;
}

async function generateCustomPdf() {
  const selectedSystems = Array.from(document.querySelectorAll('input[name="pdf_sys"]:checked')).map((i) => i.value);
  const selectedSections = Array.from(document.querySelectorAll('input[name="pdf_sec"]:checked')).map((i) => i.value);
  const title = pdfTitleInput.value.trim() || 'Relatório de Testes Automatizados';

  if (selectedSystems.length === 0) {
    pdfStatus.hidden = false;
    pdfStatus.className = 'modal-status error';
    pdfStatus.textContent = 'Selecione pelo menos um sistema para o relatório.';
    return;
  }

  if (selectedSections.length === 0) {
    pdfStatus.hidden = false;
    pdfStatus.className = 'modal-status error';
    pdfStatus.textContent = 'Selecione pelo menos uma informação/seção para incluir.';
    return;
  }

  submitPdfModalBtn.disabled = true;
  submitPdfModalBtn.textContent = 'Gerando PDF...';
  pdfStatus.hidden = false;
  pdfStatus.className = 'modal-status loading';
  pdfStatus.textContent = 'Processando dados e compilando documento paginado...';

  try {
    const response = await fetch('/public/api/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        systems: selectedSystems,
        sections: selectedSections,
        title: title,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Falha ao gerar o relatório PDF.');
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    const safeName = selectedSystems.length === 1 ? selectedSystems[0] : 'consolidado';
    link.href = downloadUrl;
    link.download = `relatorio_${safeName}_${new Date().toISOString().slice(0, 10)}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(downloadUrl);

    closePdfModal();
  } catch (error) {
    pdfStatus.hidden = false;
    pdfStatus.className = 'modal-status error';
    pdfStatus.textContent = error.message;
    submitPdfModalBtn.disabled = false;
    submitPdfModalBtn.textContent = 'Baixar PDF';
  }
}

async function initialize() {
  try {
    await loadSystems();
    if (location.hash === '#export-pdf') {
      openPdfModal();
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
}

setTheme(getTheme());
report.addEventListener('load', syncThemeWithReport);
window.addEventListener('message', handleThemeMessage);
select.addEventListener('change', () => {
  const option = select.selectedOptions[0];
  showReport(select.value, option?.textContent || '');
});
overviewPeriod.addEventListener('change', () => {
  loadOverview(overviewPeriod.value).catch((error) => {
    statusText.textContent = `Não foi possível carregar as tendências: ${error.message}`;
  });
});
document.querySelector('#refresh-page').addEventListener('click', () => location.reload());

if (openPdfModalBtn) openPdfModalBtn.addEventListener('click', openPdfModal);
if (closePdfModalBtn) closePdfModalBtn.addEventListener('click', closePdfModal);
if (cancelPdfModalBtn) cancelPdfModalBtn.addEventListener('click', closePdfModal);
if (submitPdfModalBtn) submitPdfModalBtn.addEventListener('click', generateCustomPdf);

if (pdfAllSystemsBtn) {
  pdfAllSystemsBtn.addEventListener('click', () => {
    document.querySelectorAll('input[name="pdf_sys"]').forEach((i) => { i.checked = true; });
  });
}
if (pdfNoneSystemsBtn) {
  pdfNoneSystemsBtn.addEventListener('click', () => {
    document.querySelectorAll('input[name="pdf_sys"]').forEach((i) => { i.checked = false; });
  });
}
if (pdfAllSectionsBtn) {
  pdfAllSectionsBtn.addEventListener('click', () => {
    document.querySelectorAll('input[name="pdf_sec"]').forEach((i) => { i.checked = true; });
  });
}
if (pdfNoneSectionsBtn) {
  pdfNoneSectionsBtn.addEventListener('click', () => {
    document.querySelectorAll('input[name="pdf_sec"]').forEach((i) => { i.checked = false; });
  });
}

if (pdfModal) {
  pdfModal.addEventListener('click', (event) => {
    if (event.target === pdfModal) closePdfModal();
  });
}

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && pdfModal && !pdfModal.hidden) {
    closePdfModal();
  }
});

initialize();

