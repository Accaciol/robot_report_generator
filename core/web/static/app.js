'use strict';
const $ = id => document.getElementById(id);
const labels = {waiting:'Aguardando', running:'Executando', completed:'Concluído', failed:'Falhou', cancelled:'Cancelado'};
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('robot-session') || '';
if (token) sessionStorage.setItem('robot-session', token);
history.replaceState(null, '', location.pathname);
let folders = [], active = false, connected = false, stopped = false, submitting = false;
let runId = null, generation = 0, home = '', selectionMode = 'results', selectedFolder = null, browseSequence = 0;
let lastJobs = '';

function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(path, data) {
  const response = await fetch(path, {method:data === undefined ? 'GET':'POST', headers:{'X-Session-Token':token, 'Content-Type':'application/json'}, body:data === undefined ? undefined:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível completar a operação.');
  return result;
}
function controls() {
  $('configuration').disabled = !connected || active || submitting || stopped;
  $('generate').disabled = !connected || active || submitting || stopped || !folders.length;
  $('cancel').disabled = !active || stopped;
  $('shutdown').disabled = !connected || stopped;
}
function queueView() {
  $('queue').replaceChildren();
  folders.forEach((path, index) => {
    const li = document.createElement('li'), text = document.createElement('div'), strong = document.createElement('strong'), small = document.createElement('small'), button = document.createElement('button');
    text.className = 'item-text'; strong.textContent = path.split(/[\\/]/).filter(Boolean).pop() || path; small.textContent = path;
    text.append(strong, small); button.textContent = 'Remover'; button.className = 'quiet'; button.setAttribute('aria-label', `Remover ${path}`);
    button.onclick = () => {folders.splice(index, 1); queueView();}; li.append(text, button); $('queue').append(li);
  });
  $('empty').hidden = !!folders.length;
  if (!runId) $('summary').textContent = folders.length ? `${folders.length} pasta(s) na fila` : 'Pronto para começar';
  controls();
}
async function browse(path) {
  const sequence = ++browseSequence;
  selectedFolder = null; $('select-folder').disabled = true; $('folder-error').textContent = ''; $('folder-status').textContent = 'Carregando…'; $('folders').replaceChildren();
  try {
    const data = await api('/api/folders?path=' + encodeURIComponent(path));
    if (sequence !== browseSequence) return;
    selectedFolder = data; $('folder-path').value = data.path;
    $('parent-folder').disabled = data.path === data.parent;
    $('folder-status').textContent = data.has_output ? 'output.xml encontrado' : 'Sem output.xml';
    $('select-folder').disabled = selectionMode === 'results' && !data.has_output;
    data.folders.forEach(folder => {
      const li = document.createElement('li'), button = document.createElement('button');
      button.type = 'button'; button.textContent = folder.name; button.onclick = () => browse(folder.path); li.append(button); $('folders').append(li);
    });
    if (!data.folders.length) { const li = document.createElement('li'); li.textContent = 'Nenhuma subpasta.'; $('folders').append(li); }
  } catch (error) { if (sequence === browseSequence) { $('folder-error').textContent = error.message; $('folder-status').textContent = ''; } }
}
function openPicker(mode) {
  selectionMode = mode;
  $('folder-title').textContent = mode === 'results' ? 'Adicionar pasta de resultados' : 'Selecionar pasta de destino';
  $('select-folder').textContent = mode === 'results' ? 'Adicionar à fila' : 'Usar esta pasta';
  $('folder-dialog').showModal(); browse(mode === 'destination' ? $('destination').value : home);
}
$('add-folder').onclick = () => openPicker('results');
$('choose-destination').onclick = () => openPicker('destination');
$('choose-history').onclick = () => openPicker('history');
$('folder-form').onsubmit = event => {event.preventDefault(); browse($('folder-path').value);};
$('close-dialog').onclick = () => $('folder-dialog').close();
$('parent-folder').onclick = () => {if (selectedFolder) browse(selectedFolder.parent);};
$('select-folder').onclick = () => {
  if (!selectedFolder) return;
  const path = selectedFolder.path;
  if (selectionMode === 'results') {if (!folders.includes(path)) folders.push(path); queueView();}
  else if (selectionMode === 'destination') $('destination').value = path;
  else $('history').value = path.replace(/[\\/]$/, '') + (path.includes('\\') ? '\\':'/') + 'robot-report-history.json';
  $('folder-dialog').close();
};
function showState(data) {
  runId = data.run_id; active = data.active;
  $('results').hidden = !runId;
  const done = data.items.filter(item => !['waiting','running'].includes(item.status)).length;
  $('progress').max = data.items.length || 1; $('progress').value = done;
  const signature = JSON.stringify(data.items);
  if (signature !== lastJobs) {
    lastJobs = signature; $('jobs').replaceChildren();
    data.items.forEach(item => {
      const li = document.createElement('li'), text = document.createElement('div'), name = document.createElement('strong'), detail = document.createElement('small'), badge = document.createElement('span');
      text.className = 'item-text'; name.textContent = item.folder; detail.textContent = item.error || item.report; text.append(name, detail);
      badge.className = 'badge ' + item.status; badge.textContent = labels[item.status]; li.append(text, badge);
      if (item.status === 'completed') {
        const links = document.createElement('div'); links.className = 'report-links';
        [['Abrir', ''], ['Baixar', '?download=1']].forEach(([label, suffix]) => {
          const a = document.createElement('a'); a.textContent = label; a.href = '/reports/' + encodeURIComponent(item.id) + suffix;
          if (!suffix) {a.target = '_blank'; a.rel = 'noopener noreferrer';} else a.setAttribute('download', '');
          links.append(a);
        }); li.append(links);
      }
      $('jobs').append(li);
    });
  }
  const logText = data.logs.join('\n') || 'Nenhuma execução iniciada.';
  if ($('logs').textContent !== logText) { $('logs').textContent = logText; $('logs').scrollTop = $('logs').scrollHeight; }
  if (runId) {
    const failures = data.items.filter(item => item.status === 'failed').length;
    const cancelled = data.items.some(item => item.status === 'cancelled');
    $('summary').textContent = data.cancelling ? 'Cancelando… aguardando o processo encerrar' : active ? `Processando · ${done} de ${data.items.length} finalizados` : cancelled ? 'Execução cancelada' : failures ? `Finalizado com ${failures} falha(s)` : 'Relatórios concluídos';
  }
  controls(); if (data.cancelling) $('cancel').disabled = true;
}
async function poll() {
  if (stopped) return;
  const epoch = generation;
  try {const data = await api('/api/state'); if (epoch === generation && !submitting && !stopped) {connected = true; showState(data);}}
  catch (error) {if (!stopped) {connected = false; controls(); notice('Conexão interrompida. Verifique se o servidor continua aberto.');}}
  if (!stopped) setTimeout(poll, 700);
}
$('generate').onclick = async () => {
  submitting = true; ++generation; controls(); notice('');
  try {
    const data = await api('/api/runs', {folders, destination:$('destination').value, history:$('history').value});
    runId = data.run_id; active = true; ++generation; $('summary').textContent = 'Iniciando geração…';
  } catch (error) {notice(error.message);}
  finally {submitting = false; controls();}
};
$('cancel').onclick = async () => {
  $('cancel').disabled = true;
  try {await api('/api/cancel', {run_id:runId});} catch (error) {notice(error.message);}
};
$('shutdown').onclick = async () => {
  if (active && !confirm('Encerrar o servidor e cancelar os itens ainda em processamento?')) return;
  try {
    await api('/api/shutdown', {}); stopped = true; ++generation; controls();
    $('summary').textContent = 'Servidor encerrando'; $('detail').textContent = 'Você pode fechar esta aba. Para voltar, execute robot-report-gui.';
  } catch (error) {notice(error.message);}
};
(async () => {
  try {
    const defaults = await api('/api/session', {}); home = defaults.home;
    $('destination').value = defaults.destination; $('history').value = defaults.history;
    connected = true; queueView(); poll();
  } catch (error) {notice(error.message); $('summary').textContent = 'Não foi possível conectar';}
})();
