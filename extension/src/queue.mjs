// Pure state transitions. Browser tabs and persistence belong to background.mjs.
function text(value, label, max=10000) {
  if (typeof value !== 'string' || value.length > max) throw Error(`Campo inválido: ${label}.`);
  return value;
}
function strings(value, label, count=100) {
  if (!Array.isArray(value) || value.length > count) throw Error(`Lista inválida: ${label}.`);
  return value.map(v=>text(v,label,500));
}
export function validateConfig(raw) {
  if (!raw || typeof raw!=='object') throw Error('Configure o destino.');
  let url;
  try { url=new URL(raw.board_url); } catch { throw Error('Informe uma URL válida do board.'); }
  if (url.protocol!=='https:' || url.hostname!=='dev.azure.com' || url.port || url.username || url.password)
    throw Error('Nesta demonstração use https://dev.azure.com, sem credenciais na URL.');
  const parts=url.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  if(parts.length<3 || parts[2]!=='_boards' || parts.some(p=>/[\\/\x00-\x1f]/.test(p)))
    throw Error('Informe o link do board: organização/projeto/_boards/…');
  url.search='';url.hash='';
  const result={board_url:url.href,organization:parts[0],project:parts[1],team:''};
  const team=parts.indexOf('t',3);if(team>=0) result.team=parts[team+1]||'';
  for (const key of ['work_item_type','initial_state','desired_column','area_path','iteration_path','assigned_to','priority','tags'])
    result[key]=text(raw[key]??'',key,500).trim();
  if(!result.work_item_type) throw Error('Informe o tipo de card.');
  return result;
}
export function validateMatrix(raw) {
  if(!raw || raw.schema_version!==1 || raw.mode!=='simulation' || !/^[a-f0-9]{64}$/.test(raw.report_id))
    throw Error('Relatório de demonstração inválido ou versão incompatível.');
  if(!Array.isArray(raw.candidates) || raw.candidates.length>2000) throw Error('Limite: 2.000 falhas por demonstração.');
  const seen=new Set();
  const candidates=raw.candidates.map(c=>{
    if(!c || c.status!=='FAIL') throw Error('A fila deve conter somente falhas.');
    const item={status:'FAIL'};
    for(const k of ['candidate_id','stable_test_id','suite_path','test_name','message','failed_step'])
      item[k]=text(c[k]??'',k,k==='message'?50000:2000);
    if(!item.candidate_id || seen.has(item.candidate_id)) throw Error('Identificador de candidato repetido ou vazio.');
    seen.add(item.candidate_id);
    for(const k of ['gherkin_steps','tags','artifact_ids'])item[k]=strings(c[k]??[],k);
    if(item.artifact_ids.some(id=>!/^[a-f0-9]{24}$/.test(id))) throw Error('Referência de evidência inválida.');
    item.environment={};
    if(!c.environment || typeof c.environment!=='object' || Array.isArray(c.environment) || Object.keys(c.environment).length>50)
      throw Error('Ambiente inválido.');
    for(const [key,value]of Object.entries(c.environment)) {
      if(['__proto__','constructor','prototype'].includes(key))throw Error('Chave de ambiente inválida.');
      item.environment[text(key,'ambiente',100)]=text(value,'ambiente',2000);
    }
    return item;
  });
  const result={schema_version:1,mode:'simulation',report_id:raw.report_id,candidates};
  if(new TextEncoder().encode(JSON.stringify(result)).length>2*1024*1024)throw Error('Metadados excedem 2 MB.');
  return result;
}
export function createRun(matrix,config,id) {
  return {id,report_id:matrix.report_id,config:structuredClone(config),candidates:matrix.candidates,
    index:0,results:[],status:matrix.candidates.length?'ready':'completed',attempt:null,
    report_tab_id:null,form_tab_id:null,created_at:new Date().toISOString()};
}
export function beginCandidate(run,attempt) {
  if(!['ready','paused','running'].includes(run.status) || run.index>=run.candidates.length || run.attempt)
    throw Error('Já existe formulário aberto ou a fila terminou.');
  run.attempt=attempt;run.status='awaiting_decision';
}
export function decide(run,event) {
  const previous=run.results.find(r=>r.candidate_id===event.candidate_id&&r.attempt===event.attempt);
  if(previous)return false;
  if(run.status!=='awaiting_decision' || run.attempt!==event.attempt ||
     run.candidates[run.index]?.candidate_id!==event.candidate_id) throw Error('Decisão fora do formulário atual.');
  if(!['save','discard'].includes(event.action))throw Error('Decisão inválida.');
  if(event.action==='save' && !/^SIM-\d{4,}$/.test(event.simulation_id))throw Error('Confirmação simulada inválida.');
  run.results.push({candidate_id:event.candidate_id,test_name:run.candidates[run.index].test_name,
    attempt:event.attempt,status:event.action==='save'?'saved_simulation':'discarded',
    simulation_id:event.action==='save'?event.simulation_id:null,azure_id:null,azure_url:null,
    attachments_status:event.attachments_status||'not_applicable',
    reviewed_title:event.action==='save'?text(event.title??run.candidates[run.index].test_name,'título',255):null,
    reviewed_description:event.action==='save'?text(event.description??'','descrição',50000):null,
    decided_at:new Date().toISOString()});
  run.index++;run.attempt=null;
  run.status=run.index===run.candidates.length?'completed':'running';
  return true;
}
