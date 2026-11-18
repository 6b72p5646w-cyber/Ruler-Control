import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as api from './shift_settlement_core_v09.mjs';
import {acceptDawnPromise} from './condition_core_v06.mjs';
import {registerBenefitEncounter,presentDeclaredGift,recordBenefitFact,settleFriendlyBenefit,
  registerSupplierBatch,updateConsumerContext,beginFoodInspection,finishFoodInspection} from './consumer_core_v08.mjs';
const read=name=>JSON.parse(readFileSync(new URL('../content/'+name+'.json',import.meta.url)));
const configs={conditionContract:read('condition_lifecycle_v06'),storeConfig:read('store_systems_v05'),
  consumerContract:read('consumer_closure_v08'),itemData:read('items'),balance:read('balance')};
const passed=[];
function test(name,fn){fn();passed.push(name);}
function must(r){assert.equal(r.ok,true,r.reason);return r;}
function make(options={}) {return api.createShiftSettlementSession(configs,{campaignId:'campaign',nightId:'night-1',
  runId:'attempt-1',initialSan:50,objects:[{id:'water-container',kind:'reserved_water',sealed:false}],
  transferItemIds:['I04'],foodInspectionImplemented:true,...options});}
let seq=0;
function fact(s,kind,fields={}) {const id='world-fact:'+ ++seq;return {id,kind,committed:true,...s.scope,
  sourceActionId:'engine-action:'+id,worldAt:s.condition.world,budgetAt:s.condition.budget,...fields};}
function tick(s,seconds){return must(api.advanceSettlementWorld(s,seconds));}
function until(s,budget){return tick(s,budget-s.condition.budget);}
function baselines(s) {
  for(const [method,value] of [['private_arrangement','six-copper'],['body_baseline','left-thread']])
    must(api.registerManagerBaseline(s,fact(s,'pre_shift_manager_baseline',{method,value,rootEvidenceId:'baseline:'+method})));
}
function observe(s,{bodyId='real-body',privateValue='six-copper',sameRoot=false}={}) {
  const p=must(api.recordManagerPresence(s,fact(s,'actual_manager_body_presence',{bodyId})));
  const ids=[];
  for(const [method,value] of [['private_arrangement',privateValue],['body_baseline','left-thread']]) {
    const r=fact(s,'actual_manager_counter_observation',{bodyId,continuityId:p.continuityId,
      method,value,rootEvidenceId:sameRoot?'one-source':'observation:'+method+':'+seq});
    must(api.recordManagerObservation(s,r));ids.push(r.id);
  }
  return ids;
}
function verify(s,options={}){return must(api.completeManagerCheck(s,observe(s,options)));}
function transfer(s,extra={}){const v=s.manager.verification;return fact(s,'actual_keys_and_records_handover',
  {bodyId:v?.bodyId,continuityId:v?.continuityId,verificationId:v?.id,objectIds:[...s.handoverObjectIds],...extra});}
function ready(s){baselines(s);until(s,720);verify(s);return s;}
function promise(s) {
  if(s.condition.budget===0)until(s,20);
  const command={id:'f53-real',rootRewardId:'root:f53',bindings:{bottle1:'b1',bottle2:'b2',container:'water-container'},
    saleableBottleIds:['b3','b4','b5','b6'],storageSlots:['shelf','water-container']};
  must(api.registerSettlementDawnPromise(s,command,fact(s,'actual_dawn_promise_accepted',
    {encounterId:command.id,rootRewardId:command.rootRewardId,objectIds:['b1','b2','water-container']})));
  return command.id;
}
function place(s,id='f53-real') {for(const bottleId of ['b1','b2'])must(api.placeSettlementPromisedBottle(s,
  fact(s,'actual_promised_bottle_placed',{encounterId:id,bottleId,slotId:'water-container'})));}
function seal(s){place(s);must(api.beginSettlementDawnSeal(s,'f53-real'));tick(s,2);}
function completeDuty(s,phase){must(api.recordSettlementDuty(s,fact(s,'actual_duty_completed',
  {dutyId:'D0'+(phase+1),objectIds:['actual-duty-object:'+phase]})));}
function service(s,type) {
  const order=s.store.orders.findLast(o=>o.requiresEntry===(type==='browse')&&o.status==='waiting');assert.ok(order);
  if(type==='browse')must(api.recordSettlementCustomerEntry(s,fact(s,'actual_customer_threshold_crossing',{orderId:order.id})));
  const started=must(api.beginSettlementService(s,order.id));tick(s,started.duration);assert.equal(s.store.orders.find(o=>o.id===order.id).status,'complete');
}

test('One world and budget clock also initializes one shared SAN',()=>{
  const s=make({resources:{san:99}});assert.equal(s.condition.san,50);assert.equal(s.consumer.resources.san,50);
  tick(s,2);const p=must(api.beginSettlementPrecision(s,{costSeconds:8}));
  must(api.advanceSettlementPrecisionLocal(s,3));must(api.finishSettlementPrecision(s,{attemptId:p.attemptId,outcome:'success'}));
  assert.deepEqual([s.condition.world,s.consumer.world,s.store.now],[2,2,2]);
  assert.equal(s.condition.budget,10);assert.equal(s.consumer.budget,10);
  assert.equal(s.store.orders.length,1);assert.equal(s.store.orders[0].arrivedAt,2);assert.equal(s.store.orders[0].expiresAt,26);
});
test('Pause cannot produce work, time, resources or fresh identity observations',()=>{
  const s=make();baselines(s);until(s,700);must(api.setSettlementPause(s,true));
  const before=api.snapshotSettlement(s);tick(s,20);assert.deepEqual(api.snapshotSettlement(s),before);
  assert.equal(api.recordManagerPresence(s,fact(s,'actual_manager_body_presence',{bodyId:'b'})).ok,false);
  assert.equal(api.commitSettlementSanDelta(s,{receiptId:'pause-hit',delta:-10,sourceKind:'actual_hit'}).ok,false);
});
test('Clock/SAN drift and the old single-object F53 truth are rejected',()=>{
  const s=make();s.consumer.budget=1;assert.equal(api.advanceSettlementWorld(s,2).ok,false);
  const other=make();must(acceptDawnPromise(other.condition,{id:'legacy',objectId:'water-container'}));
  assert.equal(api.advanceSettlementWorld(other,2).reason,'legacy_single_object_f53_not_admitted_in_integrated_session');
});
test('A real early panic failure stops every consumer at the actual elapsed world time',()=>{
  const s=make({initialSan:0});const r=tick(s,720);assert.equal(r.advancedWorld,20);
  assert.equal(s.condition.mode,'failed_shift');assert.equal(s.consumer.budget,20);assert.equal(s.store.now,20);
  assert.equal(s.condition.managerArrived,false);assert.equal(api.commitSettlementHandover(s,{verifiedHandover:true}).ok,false);
});
test('A large frame still commits an already-started service before later patience expiry',()=>{
  const s=make();until(s,10);const id=s.store.orders[0].id;must(api.beginSettlementService(s,id));tick(s,40);
  assert.equal(s.store.orders[0].status,'complete');assert.equal(s.store.orders[0].completedAt,11.5);
  assert.equal(s.events.filter(x=>x.type==='ordinary_order_completed').length,1);
});
test('The authored schedule retains six pickup and six physical-entry orders',()=>{
  const s=make();tick(s,720);assert.equal(s.store.orders.length,12);
  assert.equal(s.store.orders.filter(o=>o.requiresEntry).length,6);
  assert.equal(api.arriveSettlementOrder(s,{orderId:'bonus-pickup'}).ok,false);
});
test('A browser needs its actual threshold receipt; window mode cannot invent entry',()=>{
  const s=make();until(s,55);const id=s.store.orders.find(o=>o.requiresEntry).id;
  assert.equal(api.beginSettlementService(s,id).ok,false);
  must(api.changeSettlementServiceMode(s,'window','window-commit'));
  assert.equal(api.recordSettlementCustomerEntry(s,fact(s,'actual_customer_threshold_crossing',{orderId:id})).ok,false);
});
test('An already accepted two-bottle promise is not a second critical F53 in condition state',()=>{
  const s=make();promise(s);seal(s);assert.equal(Object.keys(s.condition.promises).length,0);
  assert.equal(Object.values(s.condition.encounters).some(e=>e.monsterId==='F53'),false);
  until(s,720);assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,true);
  assert.equal(s.condition.mode,'handover_only');assert.equal(s.condition.san,50);
});
test('Only both original bottles permit an actual two-second seal',()=>{
  const s=make();promise(s);
  must(api.placeSettlementPromisedBottle(s,fact(s,'actual_promised_bottle_placed',
    {encounterId:'f53-real',bottleId:'b1',slotId:'water-container'})));
  assert.equal(api.beginSettlementDawnSeal(s,'f53-real').ok,false);
  assert.equal(api.placeSettlementPromisedBottle(s,fact(s,'actual_promised_bottle_placed',
    {encounterId:'f53-real',bottleId:'b3',slotId:'water-container'})).ok,false);
  until(s,720);assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,false);
});
test('A real seal ending exactly at 720 qualifies before the shared critical verdict',()=>{
  const s=make();promise(s);place(s);until(s,718);must(api.beginSettlementDawnSeal(s,'f53-real'));tick(s,2);
  assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,true);
  const types=s.events.map(x=>x.type);
  assert.ok(types.indexOf('actual_container_seal_committed')<types.indexOf('dawn_qualification_frozen'));
  assert.ok(types.indexOf('dawn_qualification_frozen')<types.indexOf('shared_critical_verdict'));
});
test('A bare aggregate seal flag cannot substitute for the two original bottle positions',()=>{
  const s=make();promise(s);s.condition.objects['water-container'].sealed=true;
  until(s,720);assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,false);
  assert.equal(api.beginSettlementDawnSeal(s,'f53-real').ok,false);
});
test('Body schedule at 700 is necessary but is never a completed manager check',()=>{
  const s=make();baselines(s);until(s,699);
  assert.equal(api.recordManagerPresence(s,fact(s,'actual_manager_body_presence',{bodyId:'b'})).ok,false);
  until(s,720);assert.equal(s.condition.managerArrived,true);assert.equal(s.manager.verification,null);
  assert.equal(api.commitSettlementHandover(s,transfer(s)).ok,false);assert.equal(s.ledger.coins,0);
});
test('A late baseline or another run cannot be fabricated for an existing night',()=>{
  const s=make();baselines(s);until(s,700);
  assert.equal(api.registerManagerBaseline(s,fact(s,'pre_shift_manager_baseline',
    {method:'private_arrangement',value:'late',rootEvidenceId:'late'})).ok,false);
  assert.equal(api.recordManagerPresence(s,fact(s,'actual_manager_body_presence',{bodyId:'b',runId:'another-attempt'})).ok,false);
});
test('Two copies of one root and two names for one check cannot authenticate a manager',()=>{
  const s=make();baselines(s);until(s,720);
  const ids=observe(s,{sameRoot:true});assert.equal(api.completeManagerCheck(s,ids).ok,false);
  assert.equal(api.completeManagerCheck(s,[ids[0],ids[0]]).ok,false);
});
test('Specific mismatched observations remain pending even with two independent roots',()=>{
  const s=make();baselines(s);until(s,720);
  assert.equal(api.completeManagerCheck(s,observe(s,{privateValue:'wrong'})).ok,false);
  assert.equal(s.manager.verification,null);assert.equal(s.ledger.coins,0);
});
test('Expired body snapshots require fresh observations under a new continuity token',()=>{
  const s=make();baselines(s);until(s,700);const ids=observe(s);must(api.completeManagerCheck(s,ids));
  until(s,709);assert.equal(api.completeManagerCheck(s,ids).ok,false);
  must(api.recordManagerPresence(s,fact(s,'actual_manager_body_presence',{bodyId:'real-body'})));
  assert.equal(api.completeManagerCheck(s,ids).ok,false);verify(s);
});
test('Changing bodies or losing continuity invalidates a previously completed check',()=>{
  const s=ready(make());const old=transfer(s);
  must(api.interruptManagerContinuity(s));assert.equal(api.commitSettlementHandover(s,old).ok,false);
  verify(s,{bodyId:'new-current-body'});assert.equal(api.commitSettlementHandover(s,old).ok,false);
});
test('A valid current manager still needs the same actual keys and record objects',()=>{
  const s=ready(make());assert.equal(api.commitSettlementHandover(s,transfer(s,{objectIds:['other-keys','shift-records']})).ok,false);
  assert.equal(s.ledger.coins,0);must(api.commitSettlementHandover(s,transfer(s)));assert.equal(s.ledger.coins,60);
});
test('F53 pays SAN only after safe handover and updates the unique SAN source',()=>{
  const s=make();baselines(s);promise(s);seal(s);until(s,720);assert.equal(s.condition.san,50);
  verify(s);const result=must(api.commitSettlementHandover(s,transfer(s)));
  assert.equal(result.sanBonus,5);assert.equal(s.condition.san,55);assert.equal(s.consumer.resources.san,55);
  assert.equal(api.commitSettlementHandover(s,transfer(s)).ok,false);assert.equal(s.condition.san,55);
});
test('A still-active panic at 720 cannot spend a qualified F53 reward to pass handover',()=>{
  const s=make({initialSan:5});baselines(s);promise(s);seal(s);until(s,710);
  must(api.commitSettlementSanDelta(s,{receiptId:'late-hit',delta:-5,sourceKind:'actual_hit'}));until(s,720);
  assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,true);
  assert.equal(s.condition.mode,'failed_shift');assert.equal(s.condition.san,0);
  assert.equal(api.commitSettlementHandover(s,{verifiedHandover:true,panicActive:false}).ok,false);
  assert.equal(s.ledger.coins,0);assert.equal(s.consumer.resources.san,0);
});
test('Resource caps apply to post-handover F53 gains and the ledger records only the actual gain',()=>{
  const s=make({initialSan:98});baselines(s);promise(s);seal(s);until(s,720);verify(s);
  const r=must(api.commitSettlementHandover(s,transfer(s)));assert.equal(r.sanBonus,2);assert.equal(s.condition.san,100);
});
test('Stable campaign/night keys prevent rewards from being paid again in another retry run',()=>{
  const ledger=api.createSettlementLedger();const first=ready(make({ledger}));
  must(api.commitSettlementHandover(first,transfer(first)));assert.equal(ledger.coins,60);
  const retry=ready(make({ledger,runId:'attempt-2'}));const r=must(api.commitSettlementHandover(retry,transfer(retry)));
  assert.equal(r.replayedNight,true);assert.equal(r.paidCoins,0);assert.equal(ledger.coins,60);
});
test('Serializing and restoring the ledger preserves deduplication, while distinct campaign keys stay distinct',()=>{
  const a=ready(make({campaignId:'a/b',nightId:'c'}));must(api.commitSettlementHandover(a,transfer(a)));
  const ledger=api.restoreSettlementLedger(api.serializeSettlementLedger(a.ledger));
  const retry=ready(make({campaignId:'a/b',nightId:'c',runId:'later',ledger}));
  assert.equal(must(api.commitSettlementHandover(retry,transfer(retry))).paidCoins,0);
  const other=ready(make({campaignId:'a',nightId:'b/c',ledger}));
  assert.equal(must(api.commitSettlementHandover(other,transfer(other))).paidCoins,60);assert.equal(ledger.coins,120);
});
test('Real completed duties and eight scheduled sales produce one A wage and one ticket',()=>{
  const s=make();baselines(s);
  for(let phase=0;phase<6;phase++) {
    until(s,phase*120+10);service(s,'pickup');until(s,phase*120+40);completeDuty(s,phase);
    until(s,phase*120+55);if(phase<2)service(s,'browse');
  }
  until(s,720);verify(s);const r=must(api.commitSettlementHandover(s,transfer(s)));
  assert.equal(r.award.grade,'A');assert.equal(r.paidCoins,120);assert.equal(r.paidTickets,1);
  assert.equal(s.ledger.tickets,1);assert.equal(api.recordSettlementDuty(s,fact(s,'actual_duty_completed',
    {dutyId:'D01',objectIds:['late']})).ok,false);
});
test('All-window service is bounded to six orders and cannot manufacture an A grade',()=>{
  const s=make();baselines(s);must(api.changeSettlementServiceMode(s,'window','actual-window-commit'));
  for(let phase=0;phase<6;phase++) {
    until(s,phase*120+10);service(s,'pickup');until(s,phase*120+40);completeDuty(s,phase);
  }
  until(s,720);verify(s);const r=must(api.commitSettlementHandover(s,transfer(s)));
  assert.equal(r.award.orders,6);assert.equal(r.award.grade,'B');assert.equal(r.paidTickets,1);
});
test('F31 outcome and budget end atomically at six; no late SAN failure is lost',()=>{
  const s=make({initialSan:5,pet:{id:'P08',prepared:true,cared:true,charges:1}});until(s,600);
  must(api.registerSettlementRest(s,{encounterId:'mara',rootRewardId:'root:mara'}));until(s,712);
  const p=must(api.beginSettlementPrecision(s,{costSeconds:8,tag:{kind:'F31',encounterId:'mara',rootRewardId:'root:mara'}}));
  assert.equal(api.finishSettlementPrecision(s,{attemptId:p.attemptId,outcome:'failed'}).ok,false);
  must(api.advanceSettlementPrecisionLocal(s,3));
  const r=must(api.finishSettlementRestPrecision(s,{attemptId:p.attemptId,encounterId:'mara',rootRewardId:'root:mara',outcome:'failed'}));
  assert.equal(r.energyDelta,2);assert.equal(s.condition.san,0);assert.equal(s.condition.mode,'failed_shift');
  assert.equal(s.condition.panic.active,true);assert.equal(s.consumer.resources.san,0);assert.equal(s.consumer.resources.energy,52);
});
test('Wrong F31 binding cannot partially spend a precision attempt or grant compensation',()=>{
  const s=make();until(s,600);must(api.registerSettlementRest(s,{encounterId:'mara',rootRewardId:'root:mara'}));
  const p=must(api.beginSettlementPrecision(s,{costSeconds:8,tag:{kind:'F31',encounterId:'mara',rootRewardId:'root:mara'}}));
  const before=JSON.stringify(s);
  assert.equal(api.finishSettlementRestPrecision(s,{attemptId:p.attemptId,encounterId:'mara',rootRewardId:'wrong',outcome:'failed'}).ok,false);
  assert.equal(JSON.stringify(s),before);
  const r=must(api.finishSettlementRestPrecision(s,{attemptId:p.attemptId,encounterId:'mara',rootRewardId:'root:mara',outcome:'success'}));
  assert.equal(r.energyDelta,4);assert.equal(s.condition.budget,608);
});
test('A verified consumed mint closes the same global panic and cannot be consumed again',()=>{
  const s=make({initialSan:5});const c=s.consumer;
  must(registerSupplierBatch(c,{id:'supplier',runId:s.scope.runId,itemId:'I04',batchId:'batch',createdAtBudget:-1,
    producerKind:'actual_pre_shift_supplier_record',committed:true}));
  must(registerBenefitEncounter(c,{id:'tomte',monsterId:'F29',rootRewardId:'root:tomte',bindings:{porridge:'porridge',butter:'butter',gift:'mint'}}));
  must(presentDeclaredGift(c,{encounterId:'tomte',itemInstanceId:'mint',itemId:'I04',batchId:'batch',productClass:'factory_sealed_known_catalog_product'}));
  must(recordBenefitFact(c,{receiptId:'porridge-r',encounterId:'tomte',rootRewardId:'root:tomte',rewardKey:'gift',
    predicate:'same_porridge_and_visible_butter_delivered',objectIds:['porridge','butter']}));
  must(recordBenefitFact(c,{receiptId:'gift-r',encounterId:'tomte',rootRewardId:'root:tomte',rewardKey:'gift',
    predicate:'declared_gift_actually_claimed',objectIds:['mint']}));
  must(settleFriendlyBenefit(c,{encounterId:'tomte',rootRewardId:'root:tomte',rewardKey:'gift'}));
  updateConsumerContext(c,{anchor:'cashier',slotItemId:'mint',activeChase:false});
  must(beginFoodInspection(c,{inspectionId:'inspection',itemInstanceId:'mint'}));tick(s,3);
  must(finishFoodInspection(s.consumer,{inspectionId:'inspection',observedItemId:'mint',observedSealIntact:true,
    observedBatchId:'batch',supplierRecordId:'supplier'}));
  must(api.commitSettlementSanDelta(s,{receiptId:'actual-hit',delta:-5,sourceKind:'actual_hit'}));assert.equal(s.condition.panic.active,true);
  must(api.consumeSettlementFood(s,'mint'));assert.equal(s.condition.san,8);assert.equal(s.condition.panic.active,false);
  assert.equal(s.condition.panic.used,false);assert.equal(s.consumer.resources.san,8);
  assert.equal(api.consumeSettlementFood(s,'mint').ok,false);
});

test('Small frames preserve one exact-six F53 snapshot without false mixed-clock errors',()=>{
  const s=make();baselines(s);promise(s);seal(s);until(s,700);
  for(let i=0;i<400;i++)tick(s,0.05);
  assert.equal(s.condition.budget,720);assert.equal(s.consumer.budget,720);assert.equal(s.condition.mode,'handover_only');
  assert.equal(s.consumer.encounters['f53-real'].dawnSnapshot.qualified,true);
  assert.ok(Math.abs(s.consumer.world-s.condition.world)<1e-8);verify(s);
  assert.equal(must(api.commitSettlementHandover(s,transfer(s))).sanBonus,5);
});

console.log(JSON.stringify({status:'PASS',scenarioCount:passed.length,scenarios:passed,
  scope:'Finite integration: one clock/SAN, fixed ordinary order schedule, actual service timing, bound two-bottle F53, authored manager comparisons/current-body continuity, scoped transfer and durable-ledger-shaped once-per-campaign-night settlement. Physical observations/duty receipts remain trusted engine inputs; no complete monster director, actual store navigation, production crash-atomic storage, or security authentication.'},null,2));
