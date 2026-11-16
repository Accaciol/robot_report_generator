import {validateConfig,validateMatrix,createRun,beginCandidate,decide} from './queue.mjs';

// Serialize changes across tabs. Persistence is completed before opening the next form.
let serial=Promise.resolve();
const store=async run=>chrome.storage.local.set({run});
const load=async()=>(await chrome.storage.local.get('run')).run;
const formUrl=()=>chrome.runtime.getURL('form.html');
const isReport=sender=>sender.tab && sender.frameId===0 && /^(file:\/\/\/|http:\/\/127\.0\.0\.1(?::\d+)?\/)/.test(sender.url||'');
function requireReport(sender){if(!isReport(sender))throw Error('Origem de relatório inválida.');}
function requireBoundReport(sender,run,reportId) {
  requireReport(sender);
  if(!run || run.report_id!==reportId || run.report_tab_id!==sender.tab.id)throw Error('Esta aba não controla a fila atual. Retome por este relatório.');
}
function requireForm(sender,run,message) {
  if(!run || !sender.tab || sender.tab.id!==run.form_tab_id ||
     !sender.url?.startsWith(formUrl()+'?') || message.run_id!==run.id || message.attempt!==run.attempt)
    throw Error('Formulário não corresponde ao candidato ativo.');
}
async function notify(run) {
  if(!run?.report_tab_id)return;
  try{await chrome.tabs.sendMessage(run.report_tab_id,{type:'RUZY_STATE',run});}catch{/* Report can be closed; state remains stored. */}
}
async function openNext(run) {
  const old=run.form_tab_id;
  beginCandidate(run,crypto.randomUUID());
  run.form_tab_id=null;
  await store(run);
  const url=formUrl()+`?run=${encodeURIComponent(run.id)}&attempt=${encodeURIComponent(run.attempt)}`;
  try {
    let tab;
    if(old) {try{tab=await chrome.tabs.update(old,{url,active:true});}catch{/* Closed tab: create a new one. */}}
    if(!tab)tab=await chrome.tabs.create({url,active:true});
    run.form_tab_id=tab.id;await store(run);await notify(run);
  } catch(error) {
    run.status='paused';run.attempt=null;run.form_tab_id=null;await store(run);await notify(run);throw error;
  }
}
async function reportArtifacts(run) {
  const response=await chrome.tabs.sendMessage(run.report_tab_id,{
    type:'RUZY_ARTIFACTS',report_id:run.report_id,candidate_id:run.candidates[run.index].candidate_id});
  if(!response?.ok)throw Error(response?.error||'Reabra o relatório de origem para recuperar as evidências.');
  return response.artifacts;
}
async function handle(message,sender) {
  if(!message || typeof message.type!=='string')throw Error('Mensagem inválida.');
  let run=await load();
  switch(message.type) {
    case 'HELLO': {
      requireReport(sender);
      const preferences=(await chrome.storage.local.get('preferences')).preferences||null;
      return {preferences,run:run?.report_id===message.report_id?run:null};
    }
    case 'PREPARE': {
      requireReport(sender);const matrix=validateMatrix(message.matrix);const config=validateConfig(message.config);
      if(run && !['completed'].includes(run.status))throw Error('Já existe uma fila. Retome ou limpe a execução antes de preparar outra.');
      if(run?.report_id===matrix.report_id)throw Error('Este relatório já foi processado. Exporte ou limpe a execução antes de repetir.');
      run=createRun(matrix,config,crypto.randomUUID());run.report_tab_id=sender.tab.id;
      await store(run);
      if(message.remember===true)await chrome.storage.local.set({preferences:config});
      else await chrome.storage.local.remove('preferences');
      return {run};
    }
    case 'START': {
      requireBoundReport(sender,run,message.report_id);
      if(run.status!=='ready')throw Error('A fila já foi iniciada.');
      await openNext(run);return {run};
    }
    case 'RESUME': {
      requireReport(sender);
      if(!run || run.report_id!==message.report_id)throw Error('Não há fila para este relatório.');
      run.report_tab_id=sender.tab.id;
      if(run.status==='completed'){await store(run);return {run};}
      if(run.form_tab_id && run.attempt){
        try {
          const tab=await chrome.tabs.get(run.form_tab_id);
          if(tab.url?.startsWith(formUrl()+'?') && new URL(tab.url).searchParams.get('attempt')===run.attempt){
            run.status='awaiting_decision';await store(run);await chrome.tabs.update(tab.id,{active:true});
            await chrome.tabs.sendMessage(tab.id,{type:'RUZY_RECONNECTED'}).catch(()=>{});return {run};
          }
        }catch{/* Existing decisions remain preserved. */}
      }
      run.status='paused';run.attempt=null;run.form_tab_id=null;await openNext(run);return {run};
    }
    case 'FORM_DATA': {
      requireForm(sender,run,message);
      const artifacts=await reportArtifacts(run);
      return {run,candidate:run.candidates[run.index],artifacts};
    }
    case 'DECIDE': {
      requireForm(sender,run,message);
      if(!['save','discard'].includes(message.action))throw Error('Decisão inválida.');
      let simulationId=null;
      if(message.action==='save') {
        if(typeof message.title!=='string'||!message.title.trim()||message.title.length>255)throw Error('Preencha um título de até 255 caracteres.');
        if(typeof message.description!=='string'||message.description.length>50000)throw Error('Descrição inválida ou maior que 50.000 caracteres.');
        const artifacts=await reportArtifacts(run);
        const counter=((await chrome.storage.local.get('counter')).counter||0)+1;
        simulationId='SIM-'+String(counter).padStart(4,'0');
        await chrome.storage.local.set({counter});
        message.attachments_status=artifacts.length?(artifacts.every(a=>!a.missing)?'available_in_simulation':'missing'):'not_applicable';
      }
      decide(run,{...message,candidate_id:run.candidates[run.index].candidate_id,simulation_id:simulationId});
      await store(run);await notify(run);
      if(run.status==='completed')return {run,completed:true};
      await openNext(run);return {run};
    }
    case 'CLEAR': {
      requireBoundReport(sender,run,message.report_id);
      if(run.form_tab_id)throw Error('Feche o formulário ativo antes de limpar a fila.');
      await chrome.storage.local.remove('run');return {};
    }
    default:throw Error('Operação desconhecida.');
  }
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  serial=serial.catch(()=>{}).then(()=>handle(message,sender));
  serial.then(value=>respond({ok:true,...value}),error=>respond({ok:false,error:error.message}));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId=>{
  serial=serial.catch(()=>{}).then(async()=>{
    const run=await load();if(!run)return;
    if(tabId===run.form_tab_id){
      run.form_tab_id=null;run.attempt=null;
      if(run.status!=='completed')run.status='paused';
      await store(run);await notify(run);
    }else if(tabId===run.report_tab_id && run.status!=='completed'){
      run.status='paused';await store(run);
    }
  });
});
