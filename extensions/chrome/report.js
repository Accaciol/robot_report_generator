/* Content script: only activates on a report that contains the explicit Ruzy matrix. */
(async()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const source=$('ruzy-matrix'),panel=$('ruzy-panel');
  if(!source||!panel||$('ruzy-final-result'))return;
  let matrix;
  try{matrix=JSON.parse(source.textContent);}catch{return;}
  let run=null,busy=false,preferences=null,exportedRun=null;
  const message=async data=>{
    const response=await chrome.runtime.sendMessage(data);
    if(!response?.ok)throw Error(response?.error||'A extensão não respondeu.');
    return response;
  };
  const notice=text=>{$('ruzy-status').textContent=text;};
  function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
  function render(current) {
    run=current;
    $('ruzy-prepare').disabled=busy||!!run;
    $('ruzy-start').hidden=!run||run.status!=='ready';
    $('ruzy-start').textContent=`Iniciar abertura de cards simulados — ${run?.candidates.length||0} falhas`;
    $('ruzy-resume').hidden=!run||['ready','completed'].includes(run.status);
    $('ruzy-export').hidden=!run;
    $('ruzy-clear').hidden=!run;
    if(!run)return;
    $('ruzy-progress').hidden=true;
    const labels={ready:'Pronto para iniciar',awaiting_decision:'Aguardando decisão no formulário',paused:'Fila pausada — retome para continuar',running:'Preparando próximo formulário',completed:'Revisão simulada concluída'};
    notice(`${labels[run.status]||run.status}. ${run.results.length} de ${run.candidates.length} revisadas. Nenhum card real criado.`);
    const container=$('ruzy-results');container.replaceChildren();
    container.append(node('p',`Destino configurado: ${run.config.organization} / ${run.config.project} · Estado: ${run.config.initial_state||'padrão'} · Coluna desejada: ${run.config.desired_column||'não informada'} (não validada no Azure)`));
    const table=node('table'),head=node('tr');
    for(const title of ['Teste / título revisado','Decisão','Código simulado','Evidências'])head.append(node('th',title));
    const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');
    for(const candidate of run.candidates){
      const result=run.results.find(r=>r.candidate_id===candidate.candidate_id);const row=node('tr');
      const state=!result?'Pendente':result.status==='discarded'?'Descartado':'Salvo na simulação';
      const evidenceLabels={available_in_simulation:'Disponível na simulação',missing:'Ausente ou não suportada',not_applicable:'Sem evidência'};
      for(const value of [result?.reviewed_title||candidate.test_name,state,result?.simulation_id||'—',evidenceLabels[result?.attachments_status]||'A revisar'])row.append(node('td',value));
      body.append(row);
    }
    table.append(body);container.append(table);
    if(run.status==='completed'&&run.candidates.length&&exportedRun!==run.id){
      exportedRun=run.id;
      // Give the final table a chance to paint before serializing a portable copy.
      requestAnimationFrame(()=>download('html'));
    }
  }
  function download(kind) {
    if(!run)return;
    let value,type;
    if(kind==='json'){value=JSON.stringify({mode:'simulation',report_id:run.report_id,config:run.config,results:run.results},null,2);type='application/json';}
    else {
      const clone=document.documentElement.cloneNode(true);
      const clonedPanel=clone.querySelector('#ruzy-panel');
      clonedPanel.querySelectorAll('button,progress').forEach(el=>el.remove());
      clone.querySelectorAll('.ruzy-dialog').forEach(el=>el.remove());
      const marker=document.createElement('meta');marker.id='ruzy-final-result';marker.name='ruzy-result';marker.content='simulation';clone.querySelector('head').append(marker);
      const style=node('style');style.textContent='#ruzy-panel table{width:100%;border-collapse:collapse;text-align:left}#ruzy-panel td,#ruzy-panel th{padding:8px;border-bottom:1px solid #ccd8d2}';clone.querySelector('head').append(style);
      value='<!doctype html>\n'+clone.outerHTML;type='text/html';
    }
    const blob=new Blob([value],{type:type+';charset=utf-8'}),url=URL.createObjectURL(blob);
    const a=node('a');a.href=url;a.download=`ruzy-resultado-SIMULADO-${run.report_id.slice(0,8)}.${kind}`;
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }
  function configuration() {
    const dialog=node('dialog');dialog.className='ruzy-dialog';dialog.setAttribute('aria-labelledby','ruzy-config-title');
    const title=node('h2','Configure o destino');title.id='ruzy-config-title';dialog.append(title);
    dialog.append(node('p','DEMONSTRAÇÃO: os dados abaixo serão usados em formulários fictícios. Nenhum board será acessado.'));
    const form=node('form'),fields=node('div');fields.className='ruzy-fields';
    const inputs={};
    const definitions=[['board_url','Link do board','https://dev.azure.com/exemplo/Projeto%20Demo/_boards/board/t/Equipe/Stories'],
      ['work_item_type','Tipo de card','Bug'],['initial_state','Estado inicial','New'],['desired_column','Coluna desejada (a validar)','A classificar'],
      ['area_path','Área',''],['iteration_path','Iteração / sprint',''],['assigned_to','Responsável (opcional)',''],['priority','Prioridade','2'],['tags','Tags adicionais','Ruzy; Revisão']];
    for(const [key,label,fallback]of definitions){
      const wrap=node('label',label);if(key==='board_url')wrap.className='wide';
      const input=node('input');input.name=key;input.id='ruzy-config-'+key;input.value=preferences?.[key]??fallback;input.maxLength=key==='board_url'?2000:500;
      input.required=['board_url','work_item_type'].includes(key);if(key==='board_url')input.type='url';
      wrap.append(input);fields.append(wrap);inputs[key]=input;
    }
    form.append(fields,node('p','Estado e coluna são diferentes: o mapeamento e os campos obrigatórios serão conferidos no Azure da equipe.'));
    const rememberLabel=node('label','Lembrar estas preferências somente neste navegador');rememberLabel.className='check';
    const remember=node('input');remember.type='checkbox';remember.id='ruzy-remember';remember.checked=!!preferences;rememberLabel.prepend(remember);form.append(rememberLabel);
    const error=node('p');error.className='ruzy-error';error.setAttribute('role','alert');form.append(error);
    const submit=node('button','Confirmar e preparar');submit.type='submit';const cancel=node('button','Cancelar');cancel.type='button';cancel.className='secondary';
    cancel.onclick=()=>dialog.close();form.append(submit,cancel);dialog.append(form);document.body.append(dialog);
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    form.onsubmit=async event=>{
      event.preventDefault();submit.disabled=true;error.textContent='';busy=true;
      try {
        const config=Object.fromEntries(Object.entries(inputs).map(([k,input])=>[k,input.value]));
        $('ruzy-progress').hidden=false;$('ruzy-progress').value=0;notice('Validando e preparando os candidatos…');
        const candidates=[];
        for(let i=0;i<matrix.candidates.length;i++){
          candidates.push(matrix.candidates[i]);$('ruzy-progress').value=((i+1)/matrix.candidates.length)*90;
          if(i%20===0)await new Promise(resolve=>requestAnimationFrame(resolve));
        }
        const response=await message({type:'PREPARE',matrix:{...matrix,candidates,artifacts:undefined},config,remember:remember.checked});
        $('ruzy-progress').value=100;dialog.close();preferences=remember.checked?config:null;render(response.run);
      }catch(e){error.textContent=e.message;notice(e.message);$('ruzy-progress').hidden=true;}
      finally{busy=false;submit.disabled=false;$('ruzy-prepare').disabled=!!run;}
    };
    dialog.showModal();inputs.board_url.focus();
  }
  $('ruzy-prepare').onclick=event=>{if(event.isTrusted&&!busy)configuration();};
  const act=async type=>{
    if(busy)return;busy=true;
    try{const response=await message({type,report_id:matrix.report_id});render(response.run);}
    catch(e){notice(e.message);}finally{busy=false;}
  };
  $('ruzy-start').onclick=()=>act('START');$('ruzy-resume').onclick=()=>act('RESUME');
  $('ruzy-export').onclick=()=>download('html');
  const jsonButton=node('button','Exportar decisões JSON');jsonButton.id='ruzy-json';jsonButton.type='button';jsonButton.hidden=true;jsonButton.onclick=()=>download('json');panel.insertBefore(jsonButton,$('ruzy-clear'));
  $('ruzy-clear').onclick=async()=>{
    if(!confirm('Limpar a fila e suas decisões? Exporte o resultado antes de continuar.'))return;
    try{await message({type:'CLEAR',report_id:matrix.report_id});run=null;exportedRun=null;$('ruzy-results').replaceChildren();$('ruzy-progress').hidden=true;render(null);jsonButton.hidden=true;notice('Dados da execução removidos. Você pode configurar uma nova fila.');}
    catch(e){notice(e.message);}
  };
  chrome.runtime.onMessage.addListener((request,sender,respond)=>{
    if(sender.id!==chrome.runtime.id)return;
    if(request.type==='RUZY_STATE'&&request.run?.report_id===matrix.report_id){render(request.run);jsonButton.hidden=false;return;}
    if(request.type==='RUZY_ARTIFACTS'){
      if(request.report_id!==matrix.report_id){respond({ok:false,error:'Relatório não corresponde à fila.'});return;}
      const candidate=matrix.candidates.find(c=>c.candidate_id===request.candidate_id);
      if(!candidate){respond({ok:false,error:'Candidato ausente.'});return;}
      const artifacts=(matrix.artifacts||[]).filter(a=>candidate.artifact_ids.includes(a.artifact_id)).map(a=>{
        const allowed=typeof a.data_uri==='string'&&/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(a.data_uri)&&a.data_uri.length<=4*1024*1024;
        return {artifact_id:a.artifact_id,name:String(a.name).slice(0,200),kind:a.kind,missing:a.missing||!allowed,data_uri:allowed?a.data_uri:''};
      });
      if(JSON.stringify(artifacts).length>8*1024*1024){respond({ok:false,error:'Evidências excedem 8 MB por formulário na demonstração.'});return;}
      respond({ok:true,artifacts});
    }
  });
  try{const response=await message({type:'HELLO',report_id:matrix.report_id});preferences=response.preferences;render(response.run);jsonButton.hidden=!response.run;if(!response.run)notice('Extensão conectada. Configure o destino para preparar os formulários simulados.');}
  catch(e){notice(e.message);}
})();
