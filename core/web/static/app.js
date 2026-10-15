'use strict';

const $ = (id) => document.getElementById(id);
const sessionToken = readSessionToken();

let connected = false;
let active = false;
let stopped = false;
let submitting = false;
let runId = null;
let uploadId = null;
let generation = 0;
let lastJobs = '';
let lastErrors = '';
let refreshedRun = null;
let systems = [];
let loadedHistory = [];

function readSessionToken() {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const token = fragment.get('token') || sessionStorage.getItem('robot-session') || '';

  if (token) sessionStorage.setItem('robot-session', token);
  history.replaceState(null, '', location.pathname);
  return token;
}

function notice(message) {
  $('notice').textContent = message || '';
  $('notice').hidden = !message;
}

async function api(path, data) {
  const hasBody = data !== undefined;
  const response = await fetch(path, {
    method: hasBody ? 'POST' : 'GET',
    headers: {
      'X-Session-Token': sessionToken,
      ...(hasBody ? {'Content-Type': 'application/json'} : {}),
    },
    body: hasBody ? JSON.stringify(data) : undefined,
  });
  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.error || 'Não foi possível completar a operação.');
  }
  return result;
}

function updateControls() {
  const disabled = !connected || active || submitting || stopped;

  $('configuration').disabled = disabled;
  $('preview').disabled = disabled || !$('zip-file').files.length;
  $('import').disabled = disabled || !uploadId;
  $('cancel').disabled = !active || stopped;
  $('shutdown').disabled = !connected || stopped;
}

function dateInput(value) {
  if (!value) return '';

  const match = String(value).match(
    /^(\d{4})[- ]?(\d{2})[- ]?(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/
  );
  if (!match) return '';
  return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}`;
}

function applySystemSuggestion(result) {
  const suggestedId = result.system_id || '';
  const suggestedName = result.system_name || '';
  const match = systems.find((system) => system.id === suggestedId) ||
    (!suggestedId && systems.find((system) => (
      suggestedName && system.name.trim().toLocaleLowerCase() === suggestedName.trim().toLocaleLowerCase()
    )));

  $('system-select').value = match?.id || '';
  $('system-id').value = match?.id || suggestedId;
  $('system-name').value = match?.name || suggestedName;
}

async function refreshSystems(preferredId = '') {
  const result = await api('/api/systems');
  systems = result.systems;

  // Keep both selectors in sync while preserving a valid selection after refresh.
  for (const id of ['system-select', 'history-system']) {
    const select = $(id);
    const previous = select.value;
    const emptyLabel = id === 'system-select' ? 'Novo sistema' : 'Selecione um sistema';

    select.replaceChildren(new Option(emptyLabel, ''));
    systems.forEach((system) => {
      select.add(new Option(`${system.name} · ${system.id}`, system.id));
    });

    const preferred = id === 'system-select' ? preferredId : '';
    if (preferred && systems.some((system) => system.id === preferred)) {
      select.value = preferred;
    } else if (systems.some((system) => system.id === previous)) {
      select.value = previous;
    } else if (systems.length === 1) {
      select.value = systems[0].id;
    }

    if (id === 'system-select' && select.value) {
      const system = systems.find((item) => item.id === select.value);
      $('system-id').value = system.id;
      $('system-name').value = system.name;
    }
  }
}

async function previewUpload() {
  const file = $('zip-file').files[0];
  if (!file) return;

  submitting = true;
  uploadId = null;
  updateControls();
  notice('');
  $('preview-status').textContent = 'Enviando e analisando ZIP…';

  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch('/api/imports/preview', {
      method: 'POST',
      headers: {'X-Session-Token': sessionToken},
      body: form,
    });
    const result = await response.json();

    if (!response.ok) throw new Error(result.error || 'Falha ao analisar ZIP.');

    uploadId = result.upload_id;
    $('preview-status').textContent = (
      `${result.total} cenários · ${result.passed} aprovados · ` +
      `${result.failed} falharam · ${result.skipped} ignorados`
    );
    $('preview-details').hidden = false;
    $('preview-details').textContent = (
      `ZIP válido · ${result.output_xml || 'output.xml'} encontrado · ` +
      `${result.archive_members} arquivos no total · ${result.evidence_files} evidência(s).` +
      (result.errors?.length ? ` Avisos: ${result.errors.join(' · ')}` : '')
    );
    applySystemSuggestion(result);

    if (result.execution_date) {
      $('execution-date').value = dateInput(result.execution_date);
    }
  } catch (error) {
    $('preview-status').textContent = '';
    notice(error.message);
  } finally {
    submitting = false;
    updateControls();
  }
}

async function importExecution() {
  const id = $('system-id').value.trim();
  const name = $('system-name').value.trim();
  const version = $('system-version').value.trim();

  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) {
    notice('Informe um identificador válido para o sistema.');
    return;
  }
  if (!name || !version) {
    notice('Informe o nome e a versão do produto.');
    return;
  }
  if (!$('execution-date').value) {
    notice('Informe a data e hora da execução.');
    return;
  }

  submitting = true;
  updateControls();
  notice('');

  try {
    const result = await api('/api/imports', {
      upload_id: uploadId,
      system_id: id,
      system_name: name,
      system_version: version,
      execution_date: $('execution-date').value,
    });
    runId = result.run_id;
    active = true;
    uploadId = null;
    $('summary').textContent = 'Importação iniciada…';
  } catch (error) {
    notice(error.message);
  } finally {
    submitting = false;
    updateControls();
  }
}

function renderErrors(errors) {
  const signature = JSON.stringify(errors);
  if (signature === lastErrors) return;

  lastErrors = signature;
  $('error-count').textContent = `(${errors.length})`;
  $('error-empty').hidden = errors.length > 0;
  $('error-entries').replaceChildren();

  errors.slice().reverse().forEach((error) => {
    const item = document.createElement('li');
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    const message = document.createElement('p');
    const log = document.createElement('pre');

    summary.textContent = `${error.timestamp.replace('T', ' ')} · ${error.folder}`;
    message.textContent = error.message;
    log.textContent = error.log || 'Sem detalhes adicionais.';
    details.append(summary, message, log);
    item.append(details);
    $('error-entries').append(item);
  });
}

function renderJobs(items) {
  $('jobs').replaceChildren();

  items.forEach((item) => {
    const row = document.createElement('li');
    const info = document.createElement('div');
    const title = document.createElement('strong');
    const detail = document.createElement('small');
    const badge = document.createElement('span');
    const labels = {
      waiting: 'Aguardando',
      running: 'Importando',
      completed: 'Concluído',
      failed: 'Falhou',
      cancelled: 'Cancelado',
    };

    info.className = 'item-text';
    title.textContent = item.folder;
    detail.textContent = item.error || (
      item.status === 'completed'
        ? 'Os dados estão disponíveis no link público.'
        : 'Aguardando importação no SQLite.'
    );
    info.append(title, detail);
    badge.className = `badge ${item.status}`;
    badge.textContent = labels[item.status] || item.status;
    row.append(info, badge);

    if (item.status === 'completed') {
      const link = document.createElement('a');
      link.textContent = 'Abrir link fixo';
      link.href = item.report_url || '/public';
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      row.append(link);
    }

    $('jobs').append(row);
  });
}

function updateRunSummary(data, completedCount) {
  if (!data.run_id) {
    $('summary').textContent = 'Pronto para importar';
    $('detail').textContent = 'Selecione o ZIP e clique em “Enviar e analisar ZIP” para continuar.';
    return;
  }

  const failures = data.items.filter((item) => item.status === 'failed').length;
  $('summary').textContent = data.active
    ? `Importando · ${completedCount} de ${data.items.length} finalizados`
    : failures ? `Finalizado com ${failures} falha(s)` : 'Importação concluída';
}

function showState(data) {
  runId = data.run_id;
  active = data.active;
  $('results').hidden = !runId;

  if (active) {
    const current = data.items.find((item) => item.status === 'running');
    $('detail').textContent = current
      ? `Registrando métricas e salvando artefatos · ${current.system_name || current.system_id || current.folder}`
      : 'Importação na fila; aguardando processamento.';
  } else if (runId) {
    const failures = data.items.filter((item) => item.status === 'failed').length;
    $('detail').textContent = failures
      ? `${failures} item(ns) precisam de atenção. Consulte Erros e logs para ver o motivo.`
      : 'Dados gravados no SQLite; o relatório compartilhado já mostra os resultados atualizados.';
  }

  if (runId && !active && refreshedRun !== runId) {
    refreshedRun = runId;
    refreshSystems(data.items[0]?.system_id || '')
      .then(() => $('refresh-history').onclick())
      .catch((error) => notice(error.message));
  }

  const completedCount = data.items.filter((item) => !['waiting', 'running'].includes(item.status)).length;
  $('progress').max = data.items.length || 1;
  $('progress').value = completedCount;

  const jobsSignature = JSON.stringify(data.items);
  if (jobsSignature !== lastJobs) {
    lastJobs = jobsSignature;
    renderJobs(data.items);
  }

  $('logs').textContent = data.logs.join('\n') || 'Nenhuma execução iniciada.';
  renderErrors(data.errors || []);
  updateRunSummary(data, completedCount);
  updateControls();
}

async function pollState() {
  if (stopped) return;

  const requestGeneration = generation;
  try {
    const data = await api('/api/state');
    if (requestGeneration === generation && !submitting && !stopped) {
      connected = true;
      showState(data);
    }
  } catch (error) {
    connected = false;
    updateControls();
    $('summary').textContent = 'Conexão interrompida';
    $('detail').textContent = 'Abra o link atual exibido nos logs do Docker para renovar a sessão.';
    notice(error.message || 'Conexão interrompida. Verifique se o servidor continua aberto.');
  }

  if (!stopped) setTimeout(pollState, 700);
}

function renderHistory() {
  const systemId = $('history-system').value;
  const query = $('history-filter').value.trim().toLocaleLowerCase();
  const visible = loadedHistory.filter((entry) => {
    const resultLabel = entry.failed ? 'falha falhas fail' : 'aprovado pass';
    const skippedLabel = entry.skipped ? 'ignorado skip' : '';
    const searchable = [
      entry.timestamp,
      entry.system_version,
      entry.version,
      entry.total,
      entry.failed,
      entry.pass_rate,
      resultLabel,
      skippedLabel,
    ].join(' ').toLocaleLowerCase();
    return searchable.includes(query);
  });

  $('history-entries').replaceChildren();
  $('history-status').textContent = `${visible.length} de ${loadedHistory.length} execução(ões)`;

  visible.slice().reverse().forEach((entry) => {
    const item = document.createElement('li');
    const info = document.createElement('div');
    const title = document.createElement('strong');
    const detail = document.createElement('small');
    const removeButton = document.createElement('button');

    info.className = 'item-text';
    title.textContent = entry.system_version || entry.version || entry.timestamp;
    detail.textContent = (
      `${entry.timestamp} · ${entry.total} cenários · ${entry.passed} aprovados · ` +
      `${entry.failed} falhas · ${entry.pass_rate}%`
    );
    info.append(title, detail);
    removeButton.className = 'secondary danger';
    removeButton.textContent = 'Remover';
    removeButton.onclick = () => removeExecution(systemId, entry.execution_id);
    item.append(info, removeButton);
    $('history-entries').append(item);
  });
}

async function removeExecution(systemId, executionId) {
  const message = (
    'Remover esta execução do histórico? Esta ação também remove os artefatos ' +
    'dessa execução quando não forem mais necessários.'
  );
  if (!confirm(message)) return;

  try {
    await api('/api/history/remove', {system_id: systemId, execution_id: executionId});
    await $('refresh-history').onclick();
    await refreshSystems();
  } catch (error) {
    notice(error.message);
  }
}

async function downloadBackup() {
  const status = $('maintenance-status');
  status.textContent = 'Preparando backup completo…';

  try {
    const response = await fetch('/api/database/backup', {
      headers: {'X-Session-Token': sessionToken},
      cache: 'no-store',
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || 'Falha ao criar backup.');
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'robot-report-backup.zip';
    link.click();
    URL.revokeObjectURL(url);
    status.textContent = 'Backup completo baixado (SQLite e artefatos).';
  } catch (error) {
    status.textContent = error.message;
  }
}

async function restoreBackup() {
  const file = $('restore-database').files[0];
  if (!file) {
    $('maintenance-status').textContent = 'Selecione um pacote ZIP de backup.';
    return;
  }
  if (!confirm('Restaurar este backup substituirá o histórico e os arquivos atuais. Deseja continuar?')) {
    return;
  }

  const status = $('maintenance-status');
  const form = new FormData();
  form.append('file', file);
  status.textContent = 'Validando e restaurando backup…';

  try {
    const response = await fetch('/api/database/restore', {
      method: 'POST',
      headers: {'X-Session-Token': sessionToken},
      body: form,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Falha ao restaurar backup.');

    status.textContent = `Backup restaurado · ${result.systems} sistema(s).`;
    await refreshSystems();
    if ($('history-system').value) await $('refresh-history').onclick();
  } catch (error) {
    status.textContent = error.message;
  }
}

async function cleanupArtifacts() {
  const status = $('maintenance-status');

  try {
    const scan = await api('/api/artifacts/orphans');
    if (!scan.count) {
      status.textContent = 'Nenhum diretório órfão encontrado.';
      return;
    }

    const paths = scan.paths.slice(0, 8).join('\n');
    const suffix = scan.count > 8 ? '\n…' : '';
    const prompt = `${scan.count} pasta(s) de artefatos sem registro serão removidas:\n\n${paths}${suffix}\n\nContinuar?`;
    if (!confirm(prompt)) {
      status.textContent = 'Limpeza cancelada.';
      return;
    }

    const result = await api('/api/artifacts/cleanup', {});
    status.textContent = `${result.removed} pasta(s) órfã(s) removida(s).`;
  } catch (error) {
    status.textContent = error.message;
  }
}

function showLogTab() {
  $('panel-log').hidden = false;
  $('panel-errors').hidden = true;
  $('tab-log').setAttribute('aria-selected', 'true');
  $('tab-errors').setAttribute('aria-selected', 'false');
}

function showErrorsTab() {
  $('panel-log').hidden = true;
  $('panel-errors').hidden = false;
  $('tab-log').setAttribute('aria-selected', 'false');
  $('tab-errors').setAttribute('aria-selected', 'true');
}

async function initialize() {
  try {
    const defaults = await api('/api/session', {});
    $('database-path').textContent = defaults.database;
    await refreshSystems();
    connected = true;
    updateControls();
    pollState();
  } catch (error) {
    notice(error.message);
    $('summary').textContent = 'Não foi possível conectar';
  }
}

$('system-select').onchange = () => {
  const system = systems.find((item) => item.id === $('system-select').value);
  $('system-id').value = system?.id || '';
  $('system-name').value = system?.name || '';
};
$('preview').onclick = previewUpload;
$('zip-file').onchange = () => {
  uploadId = null;
  $('preview-status').textContent = '';
  $('preview-details').hidden = true;
  updateControls();
};
$('import').onclick = importExecution;
$('cancel').onclick = async () => {
  try {
    await api('/api/cancel', {run_id: runId});
  } catch (error) {
    notice(error.message);
  }
};
$('shutdown').onclick = async () => {
  if (active && !confirm('Encerrar o servidor e cancelar os itens em processamento?')) return;

  try {
    await api('/api/shutdown', {});
    stopped = true;
    generation += 1;
    updateControls();
    $('summary').textContent = 'Servidor encerrando';
  } catch (error) {
    notice(error.message);
  }
};
$('history-system').onchange = () => $('refresh-history').onclick();
$('history-filter').oninput = renderHistory;
$('refresh-history').onclick = async () => {
  const systemId = $('history-system').value;
  if (!systemId) return;

  $('history-status').textContent = 'Carregando histórico…';
  try {
    const data = await api(`/api/history?system_id=${encodeURIComponent(systemId)}`);
    loadedHistory = data.entries;
    renderHistory();
  } catch (error) {
    $('history-status').textContent = error.message;
  }
};
$('backup-database').onclick = downloadBackup;
$('restore-database-button').onclick = restoreBackup;
$('cleanup-artifacts').onclick = cleanupArtifacts;
$('tab-log').onclick = showLogTab;
$('tab-errors').onclick = showErrorsTab;

initialize();
