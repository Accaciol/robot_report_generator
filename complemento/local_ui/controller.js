'use strict';
(async () => {
  const token = location.hash.slice(1);
  history.replaceState(null, '', location.pathname);
  const $ = id => document.getElementById(id);
  let online = false, busy = false, exported = false, polling = false;
  const api = async (path, method = 'GET', data) => {
    const response = await fetch(path, {method, headers: {'X-Ruzy-Token': token, 'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
    if (!response.ok) { const error = await response.json(); throw Error(error.error || 'Operação não concluída.'); }
    return response;
  };
  // The sandboxed frame has an opaque origin. Only availability crosses this boundary, never the token.
  const relay = () => $('report').contentWindow.postMessage({type: 'RUZY_AVAILABLE', available: online}, '*');
  const download = async kind => {
    const response = await api('/api/export/' + kind), blob = await response.blob(), url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'ruzy-resultado-simulado.' + kind;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  };
  function render(state) {
    $('configuration').hidden = state.status !== 'idle';
    $('start').hidden = !['ready', 'paused'].includes(state.status);
    $('html').hidden = $('json').hidden = state.status === 'idle';
    const labels = {idle: 'Configure o destino para esta execução.', ready: 'Pronto para iniciar.', opening: 'Abrindo navegador de simulação…', awaiting_decision: 'Aguardando salvar ou descartar no formulário.', paused: 'Fila pausada; retome para continuar.', completed: 'Revisão simulada concluída.'};
    $('status').textContent = `${labels[state.status]} ${state.results.length} de ${state.total} revisados.`;
    $('results').replaceChildren();
    for (const result of state.results) {
      const row = document.createElement('tr');
      for (const text of [result.reviewed_title, result.status === 'saved' ? 'Salvo na simulação' : 'Descartado', result.simulation_id || '—']) {
        const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
      }
      $('results').append(row);
    }
    if (state.status === 'completed' && state.total && !exported) { exported = true; download('html').catch(e => { $('status').textContent = e.message; }); }
  }
  async function poll() {
    if (polling) return;
    polling = true;
    try { render(await (await api('/api/state')).json()); online = true; }
    catch { online = false; }
    finally { polling = false; relay(); }
  }
  window.addEventListener('message', event => {
    if (event.source === $('report').contentWindow && event.origin === 'null' && event.data?.type === 'RUZY_CONFIGURE' && online) {
      $('controls').hidden = false; $('controls').scrollIntoView({behavior: 'smooth'});
    }
  });
  $('report').addEventListener('load', relay);
  $('configuration').onsubmit = async event => {
    event.preventDefault(); if (busy) return; busy = true;
    try { await api('/api/prepare', 'POST', Object.fromEntries(new FormData(event.target))); await poll(); }
    catch (e) { $('status').textContent = e.message; } finally { busy = false; }
  };
  $('start').onclick = async () => {
    if (busy) return; busy = true; $('start').disabled = true;
    try { await api('/api/start', 'POST', {}); await poll(); }
    catch (e) { $('status').textContent = e.message; } finally { busy = false; $('start').disabled = false; }
  };
  for (const kind of ['html', 'json']) $(kind).onclick = () => download(kind).catch(e => { $('status').textContent = e.message; });
  if (!token) return;
  try { await api('/api/session', 'POST', {}); online = true; $('report').src = '/report'; await poll(); setInterval(poll, 2000); }
  catch { online = false; }
})();
