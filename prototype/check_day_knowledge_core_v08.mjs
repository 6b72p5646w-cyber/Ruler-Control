import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createDayKnowledgeState,canSelectDayAction,settleStudyAction,settleCaseReview} from './day_knowledge_core_v08.mjs';

const balance=JSON.parse(readFileSync(new URL('../content/balance.json',import.meta.url),'utf8'));
const checks=[];
function check(name,fn){fn();checks.push(name);}
function record(id,root,predicateId,value=true,extra={}) {
  return {id,rootSourceId:root,runId:'night-1',sceneId:'MAP_STORE',subjectId:'F13-1/delivery-1',
    evaluationWindow:'after_settled_world_update',producerKind:predicateId==='registered_meat_delivery_committed'?'actual_work_receipt':'actual_observation_receipt',
    completed:true,visible:true,claimId:'C01',observations:[{predicateId,value,visible:true,
      method:predicateId==='registered_meat_delivery_committed'?'world_action_receipt':'direct_world_observation'}],...extra};
}
const delivery=record('delivery','root-delivery','registered_meat_delivery_committed');
const departure=record('departure','root-observation','same_instance_cleared_observed');
const fixture=opts=>createDayKnowledgeState(balance,{sourceRecords:[delivery,departure],...opts});
function unchanged(s,call){const before=JSON.stringify(s);assert.equal(call().ok,false);assert.equal(JSON.stringify(s),before);}

check('Seven finite method pages contain phenomena, actual operations and limits while basic rules remain free',()=>{
 const k=balance.knowledge;assert.equal(k.method_pages.length,7);assert.equal(k.base_twenty_rules_always_free,true);
 assert.equal(k.base_safe_actions_never_require_method_page,true);assert.equal(k.method_pages_grant_combat_stats,false);
 for(const p of k.method_pages){assert(p.applicable_phenomena.length);assert(p.method_steps.length);assert(p.limits.length);}
});
check('A selected new page earns and spends two points in one completed day action',()=>{
 const s=fixture();const r=settleStudyAction(s,{actionId:'learn-1',pageId:'K01'});assert.equal(r.ok,true);
 assert.equal(s.remainingSlots,5);assert.equal(s.energy,44);assert.equal(s.studyPoints,0);
 assert.equal(s.studyPointsEarned,2);assert.equal(s.studyPointsSpent,2);assert(s.unlockedPages.K01);
});
check('Replaying a study receipt or renaming an already learned page cannot charge again',()=>{
 const s=fixture();settleStudyAction(s,{actionId:'learn-1',pageId:'K01'});
 unchanged(s,()=>settleStudyAction(s,{actionId:'learn-1',pageId:'K02'}));
 unchanged(s,()=>settleStudyAction(s,{actionId:'learn-2',pageId:'K01'}));
});
check('Unknown pages and exhausted method content do not consume a slot or resources',()=>{
 const s=fixture({unlockedPageIds:balance.knowledge.method_pages.map(p=>p.id)});
 unchanged(s,()=>settleStudyAction(s,{actionId:'learn-1',pageId:'K08'}));
 unchanged(s,()=>settleStudyAction(s,{actionId:'learn-2',pageId:'K07'}));
});
check('A full day cannot secretly append another learning or research slot',()=>{
 const s=fixture({availableSlots:0});unchanged(s,()=>settleStudyAction(s,{actionId:'learn-1',pageId:'K01'}));
 unchanged(s,()=>settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['delivery','departure']}));
});
check('Disabled equipment repair remains unavailable without consuming a day slot',()=>{
 const s=fixture();unchanged(s,()=>canSelectDayAction(s,'A06'));assert.equal(balance.day_actions.find(x=>x.id==='A06').unavailable_consumes_slot,false);
});
check('A study page remains learned after serialization and does not reveal a hidden identity',()=>{
 const s=fixture();settleStudyAction(s,{actionId:'learn-1',pageId:'K01'});const saved=JSON.parse(JSON.stringify(s));
 unchanged(saved,()=>settleStudyAction(saved,{actionId:'learn-2',pageId:'K01'}));assert(!('currentTrueIdentity' in saved));
});
check('One genuine record makes a searchable hypothesis page, not an automatic truth',()=>{
 const s=fixture();const r=settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['delivery']});
 assert.equal(r.ok,true);assert.equal(r.casePage.status,'HYPOTHESIS');assert.equal(s.energy,47);
 assert.equal(s.researchProgress,0);assert.equal(s.researchProgressEarned,1);assert.equal(s.researchProgressSpent,1);
});
check('A missing or unfinished record is not a research source',()=>{
 const s=fixture({sourceRecords:[record('pending','r-pending','registered_meat_delivery_committed',true,{completed:false})]});
 unchanged(s,()=>settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['pending']}));
 unchanged(s,()=>settleCaseReview(s,{actionId:'review-2',claimId:'C01',sourceRecordIds:['invented']}));
});
check('A hidden truth snapshot cannot enter the visible record registry',()=>{
 const s=fixture({sourceRecords:[record('truth','r-truth','same_instance_cleared_observed',true,{producerKind:'hidden_truth_snapshot',hiddenIdentity:'real'})]});
 unchanged(s,()=>settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['truth']}));
});
check('Two printouts of one root never satisfy independent evidence count',()=>{
 const s=fixture({sourceRecords:[delivery,record('copy','root-delivery','same_instance_cleared_observed')]});
 const r=settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['delivery','copy']});assert.equal(r.casePage.status,'HYPOTHESIS');
});
check('Two independent roots lacking the required observed outcome remain a hypothesis',()=>{
 const other=record('other','root-other','registered_meat_delivery_committed');const s=fixture({sourceRecords:[delivery,other]});
 const r=settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['delivery','other']});assert.equal(r.casePage.status,'HYPOTHESIS');
});
check('A matching predicate measured with an unapproved method cannot prove the claim',()=>{
 const bad=record('bad','root-bad','same_instance_cleared_observed');bad.observations[0].method='pet_reaction';
 const s=fixture({sourceRecords:[delivery,bad]});assert.equal(settleCaseReview(s,{actionId:'r',claimId:'C01',sourceRecordIds:['delivery','bad']}).casePage.status,'HYPOTHESIS');
});
check('Only the registered criteria plus independent relevant roots verify a bound past case',()=>{
 const s=fixture();const r=settleCaseReview(s,{actionId:'review-1',claimId:'C01',sourceRecordIds:['delivery','departure']});
 assert.equal(r.casePage.status,'VERIFIED');assert.equal(r.casePage.authenticatesCurrentIdentity,false);assert.equal(r.casePage.changesCurrentPermissions,false);
});
check('A declared contrary observation follows the registered refutation instead of becoming an unsupported certainty',()=>{
 const failed=record('not-cleared','root-not-cleared','same_instance_cleared_observed',false);
 const s=fixture({sourceRecords:[delivery,failed]});assert.equal(settleCaseReview(s,{actionId:'r',claimId:'C01',sourceRecordIds:['delivery','not-cleared']}).casePage.status,'REFUTED');
});
check('Conflicting observations at the same evaluation point stay conflicted',()=>{
 const contrary=record('contrary','root-contrary','same_instance_cleared_observed',false);const s=fixture({sourceRecords:[delivery,departure,contrary]});
 assert.equal(settleCaseReview(s,{actionId:'r',claimId:'C01',sourceRecordIds:['delivery','departure','contrary']}).casePage.status,'CONFLICTED');
});
check('Another night, object or evaluation point cannot fill a missing proof for this case',()=>{
 for(const extra of [{runId:'night-2'},{subjectId:'F13-other/delivery-other'},{evaluationWindow:'before_world_update'},{sceneId:'MAP_HOME'}]){
  const mixed=record('mixed','root-mixed','same_instance_cleared_observed',true,extra);const s=fixture({sourceRecords:[delivery,mixed]});
  unchanged(s,()=>settleCaseReview(s,{actionId:'r',claimId:'C01',sourceRecordIds:['delivery','mixed']}));
 }
});
check('New root evidence updates the existing case page without inventing another original record',()=>{
 const s=fixture();settleCaseReview(s,{actionId:'r1',claimId:'C01',sourceRecordIds:['delivery']});
 const r=settleCaseReview(s,{actionId:'r2',claimId:'C01',sourceRecordIds:['departure']});
 assert.equal(Object.keys(s.cases).length,1);assert.equal(r.casePage.revision,2);assert.equal(r.casePage.status,'VERIFIED');
});
check('Reprinting or renaming a reviewed root cannot farm a second case reward',()=>{
 const copy={...cloneRecord(delivery),id:'copy'};const s=fixture({sourceRecords:[delivery,copy]});
 settleCaseReview(s,{actionId:'r1',claimId:'C01',sourceRecordIds:['delivery']});
 unchanged(s,()=>settleCaseReview(s,{actionId:'r2',claimId:null,sourceRecordIds:['copy']}));
});
check('Unknown propositions can be stored as unverified notes but cannot inject a verdict',()=>{
 const s=fixture();unchanged(s,()=>settleCaseReview(s,{actionId:'r1',claimId:'player_claims_real_identity',sourceRecordIds:['delivery']}));
 const r=settleCaseReview(s,{actionId:'r2',sourceRecordIds:['delivery'],verdict:'VERIFIED'});assert.equal(r.casePage.status,'HYPOTHESIS');
});
check('Original records are immutable and hidden fields are excluded from the readable case',()=>{
 const original={...cloneRecord(delivery),hiddenIdentity:'secret',hiddenMonsterName:'not-for-player'};
 const copy=JSON.stringify(original);const s=fixture({sourceRecords:[original,departure]});
 const r=settleCaseReview(s,{actionId:'r',claimId:'C01',sourceRecordIds:['delivery','departure']});
 assert.equal(JSON.stringify(original),copy);assert(!JSON.stringify(r.casePage).includes('not-for-player'));assert(!JSON.stringify(r.casePage).includes('hiddenIdentity'));
});
check('A review action ID cannot be replayed or reused as a study action',()=>{
 const s=fixture();settleCaseReview(s,{actionId:'same',claimId:'C01',sourceRecordIds:['delivery']});
 unchanged(s,()=>settleCaseReview(s,{actionId:'same',claimId:'C01',sourceRecordIds:['departure']}));
 unchanged(s,()=>settleStudyAction(s,{actionId:'same',pageId:'K01'}));
});
function cloneRecord(x){return JSON.parse(JSON.stringify(x));}
console.log(JSON.stringify({status:'PASS',scenarios:checks.length,checks,
 scope:'Finite completed-day-action ledger and predeclared visible-record criteria only; no full day UI, truthful-world-event producer, current identity inference or client implementation.'},null,2));
