'use strict';
const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);
const identity={run_id:params.get('run'),attempt:params.get('attempt')};
let busy=false;
let loaded=false;
async function send(payload){
  const result=await chrome.runtime.sendMessage({...identity,...payload});
  if(!result?.ok)throw Error(result?.error||'Não foi possível confirmar a operação.');
  return result;
}
function element(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
async function load(){
  try {
    const {run,candidate,artifacts}=await send({type:'FORM_DATA'});
    $('status').textContent=`Candidato ${run.index+1} de ${run.candidates.length} · ${candidate.suite_path}`;
    const fields={Organização:run.config.organization,Projeto:run.config.project,Equipe:run.config.team||'Não informada',
      Tipo:run.config.work_item_type,Estado:run.config.initial_state||'Padrão do projeto',
      'Coluna desejada':(run.config.desired_column||'Não informada')+' — ainda não validada',
      Área:run.config.area_path||'Não informada',Iteração:run.config.iteration_path||'Não informada',
      Responsável:run.config.assigned_to||'Não atribuído',Prioridade:run.config.priority||'Não informada',Tags:run.config.tags||'Sem tags adicionais'};
    for(const [key,value]of Object.entries(fields))$('destination').append(element('dt',key),element('dd',value));
    $('title').value=candidate.test_name.slice(0,255);
    $('description').value=[`Teste: ${candidate.test_name}`,`Suíte: ${candidate.suite_path}`,
      `Mensagem: ${candidate.message||'Sem mensagem registrada.'}`,`Passo com falha: ${candidate.failed_step||'Não informado.'}`,
      'Passos disponíveis:',...candidate.gherkin_steps,`Tags do teste: ${candidate.tags.join('; ')}`,
      `Ambiente: ${JSON.stringify(candidate.environment)}`,
      'Comportamento esperado: conferir com o caso de teste; não inferido automaticamente.'].join('\n');
    if(!artifacts.length)$('evidence').append(element('p','Nenhuma evidência disponível para este candidato.'));
    for(const artifact of artifacts){
      if(artifact.missing){$('evidence').append(element('p',`Evidência ausente ou formato não suportado: ${artifact.name}`));continue;}
      const figure=element('figure'),image=element('img');image.src=artifact.data_uri;image.alt=`Evidência fictícia: ${artifact.name}`;
      figure.append(image,element('figcaption',artifact.name+' · disponível somente na simulação'));$('evidence').append(figure);
    }
    loaded=true;$('review').hidden=false;$('save').disabled=false;$('discard').disabled=false;$('title').focus();
  }catch(error){$('status').textContent='Não foi possível carregar o candidato.';$('error').textContent=error.message;$('review').hidden=false;$('save').disabled=true;$('discard').disabled=true;}
}
async function decision(action){
  if(busy)return;busy=true;$('save').disabled=true;$('discard').disabled=true;$('error').textContent='';
  try {
    const result=await send({type:'DECIDE',action,title:$('title').value,description:$('description').value});
    if(result.completed){$('review').hidden=true;$('status').textContent='Todos os candidatos foram revisados. Nenhum card real foi criado.';$('complete').hidden=false;}
  }catch(error){$('error').textContent=error.message;}
  finally{busy=false;$('save').disabled=false;$('discard').disabled=false;}
}
$('review').onsubmit=event=>{event.preventDefault();if($('review').reportValidity())decision('save');};
$('discard').onclick=()=>{if(confirm('Descartar este candidato sem criar um card e seguir para o próximo?'))decision('discard');};
chrome.runtime.onMessage.addListener((message,sender)=>{
  if(sender.id===chrome.runtime.id&&message.type==='RUZY_RECONNECTED'&&!loaded){
    $('destination').replaceChildren();$('evidence').replaceChildren();$('error').textContent='';load();
  }
});
load();
