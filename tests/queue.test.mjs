import test from 'node:test';
import assert from 'node:assert/strict';
import {validateConfig, validateMatrix, createRun, beginCandidate, decide} from '../extension/src/queue.mjs';

const matrix = () => ({schema_version:1, mode:'simulation', report_id:'a'.repeat(64),
  candidates:[0,1].map(n => ({candidate_id:`test:${n}`, status:'FAIL', test_name:`Test ${n}`,
    stable_test_id:`Test ${n}`, suite_path:'Suite', message:'Fail', failed_step:'',
    gherkin_steps:[], tags:[], environment:{}, artifact_ids:[]}))});
const config = () => validateConfig({board_url:'https://dev.azure.com/org/Projeto%20QA/_boards/board/t/Equipe/Stories',
  work_item_type:'Bug', initial_state:'New', desired_column:'A classificar'});

test('destination preserves project and separates column from state', () => {
  const c=config(); assert.equal(c.project,'Projeto QA'); assert.equal(c.initial_state,'New');
  assert.equal(c.desired_column,'A classificar');
});
test('rejects credentials, external host and non-board paths', () => {
  for(const url of ['http://dev.azure.com/o/p/_boards', 'https://evil.test/o/p/_boards',
    'https://me:secret@dev.azure.com/o/p/_boards', 'https://dev.azure.com/o/p/_git/repo'])
    assert.throws(()=>validateConfig({board_url:url,work_item_type:'Bug'}));
});
test('rejects PASS candidates, duplicate ids and malformed metadata', () => {
  let m=matrix(); m.candidates[0].status='PASS'; assert.throws(()=>validateMatrix(m));
  m=matrix(); m.candidates[1].candidate_id=m.candidates[0].candidate_id; assert.throws(()=>validateMatrix(m));
  m=matrix(); m.candidates[0].artifact_ids=['x'.repeat(1000)]; assert.throws(()=>validateMatrix(m));
});
test('empty report completes without opening any candidate',()=>{
  let m=matrix();m.candidates=[];const run=createRun(validateMatrix(m),config(),'run');
  assert.equal(run.status,'completed'); assert.throws(()=>beginCandidate(run,'attempt'));
});
test('only a confirmed current decision advances; duplicate receipt is idempotent',()=>{
  const run=createRun(validateMatrix(matrix()),config(),'run');beginCandidate(run,'attempt');
  assert.throws(()=>beginCandidate(run,'another'));
  assert.throws(()=>decide(run,{candidate_id:'test:0',attempt:'wrong',action:'discard'}));
  const event={candidate_id:'test:0',attempt:'attempt',action:'save',simulation_id:'SIM-0001'};
  decide(run,event); assert.equal(run.index,1); assert.equal(run.results[0].simulation_id,'SIM-0001');
  decide(run,event);assert.equal(run.index,1);
  beginCandidate(run,'second');decide(run,{candidate_id:'test:1',attempt:'second',action:'discard'});
  assert.equal(run.status,'completed');assert.equal(run.results[1].simulation_id,null);
});
test('configuration snapshot is not changed by later preference edits',()=>{
 const c=config();const run=createRun(validateMatrix(matrix()),c,'run');c.initial_state='Closed';
 assert.equal(run.config.initial_state,'New');
});
test('a saved result preserves the reviewed title and description',()=>{
 const run=createRun(validateMatrix(matrix()),config(),'run');beginCandidate(run,'one');
 decide(run,{candidate_id:'test:0',attempt:'one',action:'save',simulation_id:'SIM-0001',
   title:'Reviewed title',description:'Reviewed description'});
 assert.equal(run.results[0].reviewed_title,'Reviewed title');
 assert.equal(run.results[0].reviewed_description,'Reviewed description');
});
