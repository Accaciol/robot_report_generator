'use strict';
const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('robot-session') || '';
if (token) sessionStorage.setItem('robot-session', token);
history.replaceState(null, '', location.pathname);
let connected = false, active = false, stopped = false, submitting = false, runId = null, uploadId = null, generation = 0, lastJobs = '', lastErrors = '', refreshedRun = null;
let systems = [];
function notice(message) { $('notice').textContent = message || ''; $('notice').hidden = !message; }
async function api(path, data) {
  const response = await fetch(path, {method:data === undefined ? 'GET':'POST', headers:{'X-Session-Token':token, ...(data === undefined ? {}:{'Content-Type':'application/json'})}, body:data === undefined ? undefined:JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Não foi possível completar a operação.'); return result;
}
function controls() {
  $('configuration').disabled = !connected || active || submitting || stopped;
  $('preview').disabled = !connected || active || submitting || stopped || !$('zip-file').files.length;
  $('import').disabled = !connected || active || submitting || stopped || !uploadId;
  $('cancel').disabled = !active || stopped; $('shutdown').disabled = !connected || stopped;
}
function dateInput(value) {
  if (!value) return '';
  const match = String(value).match(/^(\d{4})[- ]?(\d{2})[- ]?(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return '';
  return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}`;
}
function applySystemSuggestion(result) {
  const suggestedId = result.system_id || '';
  const suggestedName = result.system_name || '';
  const match = systems.find(system => system.id === suggestedId) || (!suggestedId &&
    systems.find(system => suggestedName && system.name.trim().toLocaleLowerCase() === suggestedName.trim().toLocaleLowerCase()));
  $('system-select').value = match?.id || '';
  $('system-id').value = match?.id || suggestedId;
  $('system-name').value = match?.name || suggestedName;
}
async function refreshSystems(preferredId = '') {
  const result = await api('/api/systems'); systems = result.systems;
  for (const id of ['system-select','history-system']) {
    const select = $(id), previous = select.value;
    select.replaceChildren(new Option(id === 'system-select' ? 'Novo sistema':'Selecione um sistema', ''));
    systems.forEach(system => select.add(new Option(`${system.name} · ${system.id}`, system.id)));
    const preferred = id === 'system-select' ? preferredId : '';
    if (preferred && systems.some(system => system.id === preferred)) select.value = preferred;
    else if (systems.some(system => system.id === previous)) select.value = previous;
    else if (systems.length === 1) select.value = systems[0].id;
    if (id === 'system-select' && select.value) {
      const system = systems.find(item => item.id === select.value);
      $('system-id').value = system.id;
      $('system-name').value = system.name;
    }
  }
}
$('system-select').onchange = () => {
  const system = systems.find(item => item.id === $('system-select').value);
  $('system-id').value = system?.id || ''; $('system-name').value = system?.name || '';
};
$('preview').onclick = async () => {
  const file = $('zip-file').files[0]; if (!file) return;
  submitting=true; uploadId=null; controls(); notice(''); $('preview-status').textContent='Enviando e analisando ZIP…';
  try {
    const form=new FormData(); form.append('file',file);
    const response=await fetch('/api/imports/preview',{method:'POST',headers:{'X-Session-Token':token},body:form});
    const result=await response.json(); if(!response.ok) throw new Error(result.error || 'Falha ao analisar ZIP.');
    uploadId=result.upload_id; $('preview-status').textContent=`${result.total} cenários · ${result.passed} aprovados · ${result.failed} falharam · ${result.skipped} ignorados`;
    $('preview-details').hidden=false; $('preview-details').textContent=`ZIP válido · ${result.output_xml || 'output.xml'} encontrado · ${result.archive_members} arquivos no total · ${result.evidence_files} evidência(s).${result.errors?.length ? ` Avisos: ${result.errors.join(' · ')}` : ''}`;
    applySystemSuggestion(result);
    if (result.execution_date) $('execution-date').value=dateInput(result.execution_date);
  } catch(error) {$('preview-status').textContent='';notice(error.message);}
  finally{submitting=false;controls();}
};
$('zip-file').onchange=()=>{uploadId=null;$('preview-status').textContent='';$('preview-details').hidden=true;controls();};
$('import').onclick = async () => {
  const id=$('system-id').value.trim(), name=$('system-name').value.trim(), version=$('system-version').value.trim();
  if(!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) return notice('Informe um identificador válido para o sistema.');
  if(!name||!version) return notice('Informe o nome e a versão do produto.');
  if(!$('execution-date').value) return notice('Informe a data e hora da execução.');
  submitting=true;controls();notice('');
  try {const result=await api('/api/imports',{upload_id:uploadId,system_id:id,system_name:name,system_version:version,execution_date:$('execution-date').value});runId=result.run_id;active=true;uploadId=null;$('summary').textContent='Importação iniciada…';}
  catch(error){notice(error.message);} finally{submitting=false;controls();}
};
function showErrors(errors) {
  const signature=JSON.stringify(errors);if(signature===lastErrors)return;lastErrors=signature;$('error-count').textContent=`(${errors.length})`;$('error-empty').hidden=errors.length>0;$('error-entries').replaceChildren();
  errors.slice().reverse().forEach(error=>{const li=document.createElement('li'),details=document.createElement('details'),summary=document.createElement('summary'),message=document.createElement('p'),log=document.createElement('pre');summary.textContent=`${error.timestamp.replace('T',' ')} · ${error.folder}`;message.textContent=error.message;log.textContent=error.log||'Sem detalhes adicionais.';details.append(summary,message,log);li.append(details);$('error-entries').append(li);});
}
function showState(data) {
  runId=data.run_id;active=data.active;$('results').hidden=!runId;
  if(active){const current=data.items.find(item=>item.status==='running');$('detail').textContent=current?`Registrando métricas e salvando artefatos · ${current.system_name||current.system_id||current.folder}`:'Importação na fila; aguardando processamento.';}
  else if(runId){const failures=data.items.filter(item=>item.status==='failed').length;$('detail').textContent=failures?`${failures} item(ns) precisam de atenção. Consulte Erros e logs para ver o motivo.`:'Dados gravados no SQLite; o relatório compartilhado já mostra os resultados atualizados.';}
  if(runId && !active && refreshedRun!==runId){refreshedRun=runId;refreshSystems(data.items[0]?.system_id || '').then(()=>$('refresh-history').onclick()).catch(error=>notice(error.message));}
  const done=data.items.filter(item=>!['waiting','running'].includes(item.status)).length;$('progress').max=data.items.length||1;$('progress').value=done;
  const signature=JSON.stringify(data.items);
  if(signature!==lastJobs){lastJobs=signature;$('jobs').replaceChildren();data.items.forEach(item=>{const li=document.createElement('li'),info=document.createElement('div'),strong=document.createElement('strong'),small=document.createElement('small'),badge=document.createElement('span');info.className='item-text';strong.textContent=item.folder;small.textContent=item.error|| (item.status==='completed'?'Os dados estão disponíveis no link público.':'Aguardando importação no SQLite.');info.append(strong,small);badge.className='badge '+item.status;badge.textContent={waiting:'Aguardando',running:'Importando',completed:'Concluído',failed:'Falhou',cancelled:'Cancelado'}[item.status];li.append(info,badge);
    if(item.status==='completed'){const a=document.createElement('a');a.textContent='Abrir link fixo';a.href=item.report_url||'/public';a.target='_blank';a.rel='noopener noreferrer';li.append(a);} $('jobs').append(li);});}
  $('logs').textContent=data.logs.join('\n')||'Nenhuma execução iniciada.';showErrors(data.errors||[]);
  if(runId){const failed=data.items.filter(x=>x.status==='failed').length;$('summary').textContent=active?`Importando · ${done} de ${data.items.length} finalizados`:failed?`Finalizado com ${failed} falha(s)`:'Importação concluída';}
  else {$('summary').textContent='Pronto para importar';$('detail').textContent='Selecione o ZIP e clique em “Enviar e analisar ZIP” para continuar.';}
  controls();
}
async function poll(){if(stopped)return;const epoch=generation;try{const data=await api('/api/state');if(epoch===generation&&!submitting&&!stopped){connected=true;showState(data);}}catch(error){connected=false;controls();$('summary').textContent='Conexão interrompida';$('detail').textContent='Abra o link atual exibido nos logs do Docker para renovar a sessão.';notice(error.message || 'Conexão interrompida. Verifique se o servidor continua aberto.');}if(!stopped)setTimeout(poll,700);}
$('cancel').onclick=async()=>{try{await api('/api/cancel',{run_id:runId});}catch(e){notice(e.message);}};
$('shutdown').onclick=async()=>{if(active&&!confirm('Encerrar o servidor e cancelar os itens em processamento?'))return;try{await api('/api/shutdown',{});stopped=true;++generation;controls();$('summary').textContent='Servidor encerrando';}catch(e){notice(e.message);}};
$('history-system').onchange=()=>$('refresh-history').onclick();
let loadedHistory=[];
function renderHistory(){const id=$('history-system').value,query=$('history-filter').value.trim().toLocaleLowerCase();const visible=loadedHistory.filter(entry=>`${entry.timestamp} ${entry.system_version} ${entry.version} ${entry.total} ${entry.failed} ${entry.pass_rate} ${entry.failed?'falha falhas fail':'aprovado pass'} ${entry.skipped?'ignorado skip':''}`.toLocaleLowerCase().includes(query));$('history-entries').replaceChildren();$('history-status').textContent=`${visible.length} de ${loadedHistory.length} execução(ões)`;visible.slice().reverse().forEach(entry=>{const li=document.createElement('li'),info=document.createElement('div'),title=document.createElement('strong'),small=document.createElement('small'),button=document.createElement('button');info.className='item-text';title.textContent=entry.system_version||entry.version||entry.timestamp;small.textContent=`${entry.timestamp} · ${entry.total} cenários · ${entry.passed} aprovados · ${entry.failed} falhas · ${entry.pass_rate}%`;info.append(title,small);button.className='secondary danger';button.textContent='Remover';button.onclick=async()=>{if(!confirm('Remover esta execução do histórico? Esta ação também remove os artefatos dessa execução quando não forem mais necessários.'))return;try{await api('/api/history/remove',{system_id:id,execution_id:entry.execution_id});await $('refresh-history').onclick();await refreshSystems();}catch(e){notice(e.message);}};li.append(info,button);$('history-entries').append(li);});}
$('history-filter').oninput=renderHistory;
$('refresh-history').onclick=async()=>{const id=$('history-system').value;if(!id)return;$('history-status').textContent='Carregando histórico…';try{const data=await api('/api/history?system_id='+encodeURIComponent(id));loadedHistory=data.entries;renderHistory();}catch(e){$('history-status').textContent=e.message;}};
$('backup-database').onclick=async()=>{const status=$('maintenance-status');status.textContent='Preparando backup completo…';try{const response=await fetch('/api/database/backup',{headers:{'X-Session-Token':token},cache:'no-store'});if(!response.ok){const result=await response.json();throw new Error(result.error||'Falha ao criar backup.');}const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='robot-report-backup.zip';link.click();URL.revokeObjectURL(url);status.textContent='Backup completo baixado (SQLite e artefatos).';}catch(e){status.textContent=e.message;}};
$('restore-database-button').onclick=async()=>{const file=$('restore-database').files[0];if(!file)return $('maintenance-status').textContent='Selecione um pacote ZIP de backup.';if(!confirm('Restaurar este backup substituirá o histórico e os arquivos atuais. Deseja continuar?'))return;const status=$('maintenance-status'),form=new FormData();form.append('file',file);status.textContent='Validando e restaurando backup…';try{const response=await fetch('/api/database/restore',{method:'POST',headers:{'X-Session-Token':token},body:form});const result=await response.json();if(!response.ok)throw new Error(result.error||'Falha ao restaurar backup.');status.textContent=`Backup restaurado · ${result.systems} sistema(s).`;await refreshSystems();if($('history-system').value)await $('refresh-history').onclick();}catch(e){status.textContent=e.message;}};
$('cleanup-artifacts').onclick=async()=>{const status=$('maintenance-status');try{const scan=await api('/api/artifacts/orphans');if(!scan.count){status.textContent='Nenhum diretório órfão encontrado.';return;}if(!confirm(`${scan.count} pasta(s) de artefatos sem registro serão removidas:\n\n${scan.paths.slice(0,8).join('\n')}${scan.count>8?'\n…':''}\n\nContinuar?`)){status.textContent='Limpeza cancelada.';return;}const result=await api('/api/artifacts/cleanup',{});status.textContent=`${result.removed} pasta(s) órfã(s) removida(s).`;}catch(e){status.textContent=e.message;}};
$('tab-log').onclick=()=>{ $('panel-log').hidden=false;$('panel-errors').hidden=true;$('tab-log').setAttribute('aria-selected','true');$('tab-errors').setAttribute('aria-selected','false');};
$('tab-errors').onclick=()=>{ $('panel-log').hidden=true;$('panel-errors').hidden=false;$('tab-log').setAttribute('aria-selected','false');$('tab-errors').setAttribute('aria-selected','true');};
(async()=>{try{const defaults=await api('/api/session',{});$('database-path').textContent=defaults.database;await refreshSystems();connected=true;controls();poll();}catch(e){notice(e.message);$('summary').textContent='Não foi possível conectar';}})();
