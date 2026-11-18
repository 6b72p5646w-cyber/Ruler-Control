import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createConsumerState, registerBenefitEncounter, presentDeclaredGift, recordBenefitFact,
  completeExistingCleaningWork, revokeLeaseEarly, updateConsumerContext, advanceConsumerClock,
  registerSupplierBatch, beginFoodInspection, cancelFoodInspection, finishFoodInspection,
  consumeVerifiedFood, movePromisedBottle, setPromiseContainerSeal, sellUnreservedBottle,
  recordVerifiedHandover, settleFriendlyBenefit, cancelConsumerEncounter,
  registerRestEpisode, settleRestAttempt, exitUnstartedRest} from './consumer_core_v08.mjs';
import {createRewardState, completeRewardWork, claimFragmentReward} from './reward_core_v07.mjs';
const contract = JSON.parse(readFileSync(new URL('../content/consumer_closure_v08.json', import.meta.url), 'utf8'));
const items = JSON.parse(readFileSync(new URL('../content/items.json', import.meta.url), 'utf8'));
const passed = [];
const test = (name, fn) => { fn(); passed.push(name); };
const must = r => { assert.equal(r.ok, true, r.reason); return r; };
const make = options => createConsumerState(contract, items, {runId:'run-1', nightId:'night-1',
  transferItemIds:['I04','I21'], foodInspectionImplemented:true, ...options});
const declare = (s, id, monsterId, bindings, extra = {}) => must(registerBenefitEncounter(s,
  {id, monsterId, rootRewardId:`root:${id}`, bindings, ...extra}));
let serial = 0;
const fact = (s, id, key, predicate, objectIds, extra = {}) => recordBenefitFact(s,
  {receiptId:`adapter-fact:${++serial}`, encounterId:id, rootRewardId:`root:${id}`, rewardKey:key, predicate, objectIds, ...extra});
const settle = (s, id, key, extra = {}) => settleFriendlyBenefit(s,
  {encounterId:id, rootRewardId:`root:${id}`, rewardKey:key, ...extra});
const tick = (s, worldSeconds) => must(advanceConsumerClock(s, {worldSeconds}));
function supplier(s, extra = {}) {
  return registerSupplierBatch(s, {id:'supplier-1', runId:s.runId, itemId:'I04', batchId:'B-001',
    createdAtBudget:-1, producerKind:'actual_pre_shift_supplier_record', committed:true, ...extra});
}
function gift29(s, {productClass='factory_sealed_known_catalog_product', prepareSupplier=true} = {}) {
  if (prepareSupplier) must(supplier(s));
  declare(s,'f29','F29',{porridge:'porridge-1',butter:'butter-1',gift:'mint-gift'});
  tick(s,10); must(presentDeclaredGift(s,{encounterId:'f29',itemInstanceId:'mint-gift',itemId:'I04',batchId:'B-001',productClass}));
  must(fact(s,'f29','gift','same_porridge_and_visible_butter_delivered',['porridge-1','butter-1']));
  must(fact(s,'f29','gift','declared_gift_actually_claimed',['mint-gift']));
  return must(settle(s,'f29','gift'));
}
function inspect(s, id='inspection-1') {
  updateConsumerContext(s,{anchor:'cashier',slotItemId:'mint-gift',activeChase:false});
  must(beginFoodInspection(s,{inspectionId:id,itemInstanceId:'mint-gift'}));
  return id;
}
function finish(s, id, extra = {}) {
  return finishFoodInspection(s,{inspectionId:id,observedItemId:'mint-gift',observedSealIntact:true,
    observedBatchId:'B-001',supplierRecordId:'supplier-1',...extra});
}

test('F29 gift ownership does not grant edible status even though I04 has a san effect tag', () => {
  const s=make(); const reward=gift29(s);
  assert.equal(s.items.I04.tag,'san'); assert.equal(reward.foodStatus,'sealed_unverified');
  assert.equal(s.inventory['mint-gift'].owned,true);
  assert.equal(consumeVerifiedFood(s,'mint-gift').reason,'personal_food_verification_required');
  assert.equal(s.resources.san,50); assert.equal(s.inventory['mint-gift'].consumed,false);
});

test('Same-item inspection takes three world seconds and the verified mint is eaten once for SAN8', () => {
  const s=make();gift29(s);const id=inspect(s);
  tick(s,2.9);assert.equal(finish(s,id).reason,'three_world_seconds_not_completed');tick(s,0.1);
  assert.equal(must(finish(s,id)).foodStatus,'personal_verified');
  assert.equal(must(consumeVerifiedFood(s,'mint-gift')).actualDeltas.san,8);assert.equal(s.resources.san,58);
  assert.equal(consumeVerifiedFood(s,'mint-gift').ok,false);assert.equal(s.resources.san,58);
});

test('Budget-only precision or paused time cannot substitute for the three world seconds', () => {
  const s=make();gift29(s);const id=inspect(s);
  must(advanceConsumerClock(s,{budgetCost:3}));assert.equal(finish(s,id).ok,false);
  must(advanceConsumerClock(s,{worldSeconds:10,paused:true}));assert.equal(finish(s,id).ok,false);
  tick(s,3);must(finish(s,id));
});

test('Wrong item, broken seal and mismatched batch each leave the owned gift unverified and unconsumed', () => {
  for(const change of [{observedItemId:'another-mint'},{observedSealIntact:false},{observedBatchId:'B-002'}]) {
    const s=make();gift29(s);const id=inspect(s);tick(s,3);
    assert.equal(finish(s,id,change).ok,false);assert.equal(s.inventory['mint-gift'].foodStatus,'sealed_unverified');
    assert.equal(s.inventory['mint-gift'].owned,true);assert.equal(s.inventory['mint-gift'].consumed,false);
  }
});

test('Unknown homemade food cannot become verified merely by using a catalog item ID', () => {
  const s=make();gift29(s,{productClass:'unknown_homemade_food'});const id=inspect(s);tick(s,3);
  assert.equal(finish(s,id).ok,false);assert.equal(consumeVerifiedFood(s,'mint-gift').ok,false);
  assert.equal(s.inventory['mint-gift'].owned,true);
});

test('Future, post-opening, wrong-run or uncommitted supplier records cannot authenticate a gift', () => {
  const s=make();gift29(s,{prepareSupplier:false});
  for(const change of [{createdAtBudget:999},{createdAtBudget:5},{runId:'other-run'},{committed:false}]) assert.equal(supplier(s,change).ok,false);
  const id=inspect(s);tick(s,3);assert.equal(finish(s,id).ok,false);
  assert.equal(s.inventory['mint-gift'].foodStatus,'sealed_unverified');
});

test('Cancelling inspection releases the same object without making it safe or consuming it', () => {
  const s=make();gift29(s);const id=inspect(s);tick(s,1);must(cancelFoodInspection(s,id));tick(s,3);
  assert.equal(finish(s,id).ok,false);assert.equal(s.inventory['mint-gift'].lockedBy,null);
  assert.equal(s.inventory['mint-gift'].owned,true);assert.equal(s.inventory['mint-gift'].foodStatus,'sealed_unverified');
});

test('Leaving the safe inspection slot or beginning a chase cancels rather than banks inspection', () => {
  for(const change of [{anchor:'rear_yard'},{slotItemId:'different-object'},{activeChase:true}]) {
    const s=make();gift29(s);const id=inspect(s);tick(s,1);updateConsumerContext(s,change);tick(s,3);
    assert.equal(finish(s,id).ok,false);assert.equal(s.inventory['mint-gift'].foodStatus,'sealed_unverified');
  }
});

test('An edible gift cannot be promised when its inspection or transfer handler is unavailable', () => {
  for(const options of [{foodInspectionImplemented:false},{transferItemIds:['I21']}]) {
    const s=make(options);
    assert.equal(registerBenefitEncounter(s,{id:'f29',monsterId:'F29',rootRewardId:'r',bindings:{porridge:'p',butter:'b',gift:'g'}}).ok,false);
    assert.equal(Object.keys(s.inventory).length,0);
  }
});

test('F33 needs actual aid and the same visitor departure, then grants capped SAN once', () => {
  const s=make({resources:{san:98}});declare(s,'f33','F33',{visitor:'visitor-33',aid:'aid-33'});
  must(fact(s,'f33','aid','visitor_first_aid_actually_delivered',['visitor-33','aid-33']));
  assert.equal(settle(s,'f33','aid').ok,false);
  assert.equal(fact(s,'f33','aid','same_visitor_departed',['other-visitor']).ok,false);
  must(fact(s,'f33','aid','same_visitor_departed',['visitor-33']));
  assert.equal(must(settle(s,'f33','aid')).actualDelta,2);assert.equal(s.resources.san,100);
  assert.equal(settle(s,'f33','aid').ok,false);assert.equal(s.resources.san,100);
});

test('An earlier departure cannot be recycled as the ending of later aid', () => {
  const s=make();declare(s,'f33','F33',{visitor:'v',aid:'a'});
  must(fact(s,'f33','aid','same_visitor_departed',['v']));must(fact(s,'f33','aid','visitor_first_aid_actually_delivered',['v','a']));
  assert.equal(settle(s,'f33','aid').reason,'actual_fact_order_mismatch');assert.equal(s.resources.san,50);
});

test('Wrong roots, undeclared child keys and a second encounter reusing one root cannot create rewards', () => {
  const s=make();declare(s,'f33','F33',{visitor:'v',aid:'a'});
  assert.equal(fact(s,'f33','aid','same_visitor_departed',['v'],{rootRewardId:'invented-root'}).ok,false);
  assert.equal(settle(s,'f33','aid_extra').ok,false);
  assert.equal(registerBenefitEncounter(s,{id:'copy',monsterId:'F33',rootRewardId:'root:f33',bindings:{visitor:'v2',aid:'a2'}}).ok,false);
  assert.equal(s.resources.san,50);
});

test('F35 reuses the same actual work credit, requires its broom back and adds no coins or token', () => {
  const s=make();declare(s,'f35','F35',{garbage:'g',broom:'b',work:'work-1'});
  must(completeExistingCleaningWork(s,{receiptId:'work-r1',encounterId:'f35',rootRewardId:'root:f35',workId:'work-1',garbageId:'g'}));
  assert.equal(settle(s,'f35','cleaning').ok,false);
  assert.equal(fact(s,'f35','cleaning','same_broom_returned',['wrong-broom']).ok,false);
  must(fact(s,'f35','cleaning','same_broom_returned',['b']));const result=must(settle(s,'f35','cleaning'));
  assert.equal(result.receiptId,'work-r1');assert.equal(result.addedWorkCredits,0);assert.equal(result.addedCoins,0);
  assert.equal(Object.keys(s.workCredits).length,1);assert.equal(s.coins,0);assert.equal(Object.keys(s.inventory).length,0);
  assert.equal(completeExistingCleaningWork(s,{receiptId:'work-r2',encounterId:'f35',rootRewardId:'root:f35',workId:'work-1',garbageId:'g'}).ok,false);
});

function lease36(s) {declare(s,'f36','F36',{slot:'leased-slot'});must(fact(s,'f36','rent','actual_lease_granted',['leased-slot']));}
test('F36 automatically revokes its twenty-world-second lease and pays six only after actual clear', () => {
  const s=make();lease36(s);tick(s,19.9);
  assert.equal(fact(s,'f36','rent','same_leased_slot_actually_cleared',['leased-slot']).ok,false);tick(s,0.1);
  assert.equal(s.encounters.f36.lease.state,'revoked_on_time');assert.equal(s.encounters.f36.lease.revokedAt,20);
  assert.equal(settle(s,'f36','rent').ok,false);must(fact(s,'f36','rent','same_leased_slot_actually_cleared',['leased-slot']));
  assert.equal(must(settle(s,'f36','rent')).amount,6);assert.equal(s.coins,6);assert.equal(settle(s,'f36','rent').ok,false);
});

test('Early lease revocation remains unpaid even if time later passes twenty seconds', () => {
  const s=make();lease36(s);tick(s,10);must(revokeLeaseEarly(s,'f36'));tick(s,15);
  assert.equal(s.encounters.f36.lease.state,'revoked_early');assert.equal(settle(s,'f36','rent').ok,false);assert.equal(s.coins,0);
});

test('F36 cannot use budget-only time or an asserted timer receipt to satisfy world duration', () => {
  const s=make();lease36(s);must(advanceConsumerClock(s,{budgetCost:20}));
  assert.equal(s.encounters.f36.lease.state,'active');
  assert.equal(fact(s,'f36','rent','full_lease_elapsed',['leased-slot']).ok,false);assert.equal(settle(s,'f36','rent').ok,false);
  tick(s,25);assert.equal(s.encounters.f36.lease.revokedAt,20);
});

function song47(s) {declare(s,'f47','F47',{segment1:'seg-1',segment2:'seg-2',segment3:'seg-3'});}
function songSegment(s,n) {const key=`segment_${n}`,ids=[`seg-${n}`];
  must(fact(s,'f47',key,'same_segment_actually_completed',ids));must(fact(s,'f47',key,'same_segment_sealed_and_claimed',ids));
  return must(settle(s,'f47',key));}
test('F47 gives its three, five and eight coins only for successive sealed claims of the same segments', () => {
  const s=make();song47(s);
  assert.equal(fact(s,'f47','segment_2','same_segment_actually_completed',['seg-2']).ok,false);
  const a=songSegment(s,1),b=songSegment(s,2),c=songSegment(s,3);
  assert.deepEqual([a.amount,b.amount,c.amount],[3,5,8]);assert.equal(s.coins,16);
  assert.equal(settle(s,'f47','segment_1').ok,false);assert.equal(b.fragmentSource,undefined);assert.equal(c.fragmentSource,undefined);
});

test('F47 wrong-segment and reversed completion/claim facts cannot mint a payout', () => {
  const s=make();song47(s);
  assert.equal(fact(s,'f47','segment_1','same_segment_actually_completed',['seg-2']).ok,false);
  must(fact(s,'f47','segment_1','same_segment_sealed_and_claimed',['seg-1']));must(fact(s,'f47','segment_1','same_segment_actually_completed',['seg-1']));
  assert.equal(settle(s,'f47','segment_1').reason,'actual_fact_order_mismatch');assert.equal(s.coins,0);
});

test('F47 first cashout and E065 use one root in the existing fragment ledger while later coins remain', () => {
  const s=make();song47(s);const first=songSegment(s,1),source=first.fragmentSource;
  const ledger=createRewardState(items,{jobs:[
    {id:'first-cashout',kind:source.kind,nightId:source.nightId,rootRewardId:source.rootRewardId},
    {id:'E065-wrapper',kind:source.kind,nightId:source.nightId,rootRewardId:source.rootRewardId},
    {id:'another-work',kind:'optional_work_completed',nightId:source.nightId,rootRewardId:'different-root'}]});
  must(claimFragmentReward(ledger,must(completeRewardWork(ledger,'first-cashout')).receiptId));
  assert.equal(claimFragmentReward(ledger,must(completeRewardWork(ledger,'E065-wrapper')).receiptId).ok,false);
  assert.equal(claimFragmentReward(ledger,must(completeRewardWork(ledger,'another-work')).receiptId).ok,false);
  assert.equal(ledger.fragments,1);songSegment(s,2);songSegment(s,3);assert.equal(s.coins,16);
});

test('Cancelling F47 after one cashout preserves its three coins without paying unfinished segments', () => {
  const s=make();song47(s);songSegment(s,1);must(cancelConsumerEncounter(s,'f47'));
  assert.equal(settle(s,'f47','segment_2').ok,false);assert.equal(s.coins,3);
});

function promise53(s) {
  declare(s,'f53','F53',{bottle1:'b1',bottle2:'b2',container:'water-container'},
    {saleableBottleIds:['b3','b4','b5','b6'],storageSlots:['shelf','water-container']});
  must(fact(s,'f53','dawn','actual_promise_accepted',['b1','b2','water-container']));
}
function sealBoth(s) {for(const bottleId of ['b1','b2']) must(movePromisedBottle(s,{encounterId:'f53',bottleId,slotId:'water-container'}));must(setPromiseContainerSeal(s,'f53',true));}
function handover(s,extra={}) {return recordVerifiedHandover(s,{receiptId:'handover-r',runId:s.runId,
  managerId:'MANAGER',settlementMode:'handover_only',panicActive:false,...extra});}
test('F53 reservations block unrelated sale and consumption of its exact two originals', () => {
  const s=make();promise53(s);
  assert.equal(sellUnreservedBottle(s,'b1').ok,false);assert.equal(consumeVerifiedFood(s,'b2').ok,false);
  assert.equal(movePromisedBottle(s,{encounterId:'f53',bottleId:'b3',slotId:'water-container'}).ok,false);
  must(sellUnreservedBottle(s,'b3'));assert.equal(s.inventory.b3.owned,false);
  assert.equal(s.inventory.b1.owned,true);assert.equal(s.inventory.b2.owned,true);assert.equal(Object.keys(s.inventory).length,6);
});

test('F53 qualifies at true six but grants SAN5 only after an actual eligible handover receipt', () => {
  const s=make();promise53(s);sealBoth(s);tick(s,719);
  assert.equal(settle(s,'f53','dawn').ok,false);assert.equal(handover(s).ok,false);tick(s,1);
  assert.equal(s.encounters.f53.dawnSnapshot.qualified,true);assert.equal(s.inventory.b1.reservedBy,null);
  assert.equal(settle(s,'f53','dawn').ok,false);assert.equal(s.resources.san,50);
  must(handover(s));assert.equal(must(settle(s,'f53','dawn')).actualDelta,5);assert.equal(s.resources.san,55);
  assert.equal(settle(s,'f53','dawn').ok,false);
});

test('F53 reward cannot clear active panic or override failed settlement before handover', () => {
  const s=make({resources:{san:0}});promise53(s);sealBoth(s);tick(s,720);
  assert.equal(handover(s,{panicActive:true}).ok,false);assert.equal(handover(s,{settlementMode:'failed_shift'}).ok,false);
  assert.equal(settle(s,'f53','dawn').ok,false);assert.equal(s.resources.san,0);
});

test('A missing original at true six cannot be supplied or sealed later to claim F53 reward', () => {
  const s=make();promise53(s);must(movePromisedBottle(s,{encounterId:'f53',bottleId:'b1',slotId:'water-container'}));must(setPromiseContainerSeal(s,'f53',true));
  tick(s,720);assert.equal(s.encounters.f53.dawnSnapshot.qualified,false);
  assert.equal(movePromisedBottle(s,{encounterId:'f53',bottleId:'b2',slotId:'water-container'}).ok,false);
  assert.equal(setPromiseContainerSeal(s,'f53',true).ok,false);must(handover(s));
  assert.equal(settle(s,'f53','dawn').ok,false);assert.equal(s.resources.san,50);
});

test('Cancelling F53 releases existing stock without new bottles, SAN loss or a dawn reward', () => {
  const s=make();promise53(s);must(sellUnreservedBottle(s,'b3'));must(cancelConsumerEncounter(s,'f53'));
  assert.equal(s.inventory.b1.reservedBy,null);assert.equal(s.inventory.b3.owned,false);
  assert.equal(Object.keys(s.inventory).length,6);assert.equal(s.resources.san,50);
  tick(s,720);must(handover(s));assert.equal(settle(s,'f53','dawn').ok,false);assert.equal(s.resources.san,50);
});

test('F53 true-six snapshots and handover facts cannot be supplied as arbitrary reward predicates', () => {
  const s=make();promise53(s);
  for(const predicate of ['true_six_reached','same_two_bottles_sealed_in_reserved_container','verified_handover_completed']) {
    assert.equal(fact(s,'f53','dawn',predicate,['b1','b2','water-container']).ok,false);
  }
  assert.equal(settle(s,'f53','dawn').ok,false);
});

test('F55 requires the same escort and return before SAN4 without a next-night token or order credit', () => {
  const s=make();declare(s,'f55','F55',{route:'route-1',player:'PLAYER',item:'parcel-1'});
  must(fact(s,'f55','escort','actual_escort_accepted',['route-1','PLAYER','parcel-1']));
  assert.equal(fact(s,'f55','escort','same_registered_route_completed',['route-2','PLAYER','parcel-1']).ok,false);
  must(fact(s,'f55','escort','same_registered_route_completed',['route-1','PLAYER','parcel-1']));
  assert.equal(settle(s,'f55','escort').ok,false);
  must(fact(s,'f55','escort','player_and_remaining_item_returned_to_store',['PLAYER','parcel-1']));
  assert.equal(must(settle(s,'f55','escort')).actualDelta,4);assert.equal(s.resources.san,54);
  assert.equal(s.coins,0);assert.equal(Object.keys(s.inventory).length,0);assert.equal(Object.keys(s.workCredits).length,0);
});

test('F23 transfers one declared I21 only after actual coat return, departure and gift claim', () => {
  const s=make();declare(s,'f23','F23',{coat:'coat',claimant:'claimant',gift:'charm'});
  must(presentDeclaredGift(s,{encounterId:'f23',itemInstanceId:'charm',itemId:'I21',productClass:'known_nonfood_item'}));
  must(fact(s,'f23','gift','matched_coat_actually_returned',['coat','claimant']));
  must(fact(s,'f23','gift','claimant_departed',['claimant']));must(fact(s,'f23','gift','declared_gift_actually_claimed',['charm']));
  assert.equal(must(settle(s,'f23','gift')).itemId,'I21');assert.equal(settle(s,'f23','gift').ok,false);
  assert.equal(consumeVerifiedFood(s,'charm').ok,false);
});

function restState(pet={id:'P08',prepared:true,cared:true,charges:2}, options={}) {
  const s=make({pet,...options});must(registerRestEpisode(s,{encounterId:'f31',rootRewardId:'root:f31'}));return s;
}
// These are explicit finite test-adapter facts, not a precision controller. The
// paid helper commits the eight budget seconds separately before settlement.
function restInput(s,id,outcome,extra={}) {
  const scope={runId:s.runId,nightId:s.nightId,encounterId:'f31',rootRewardId:'root:f31',
    attemptNumber:s.restEpisodes.f31.attempts.length+1};
  return {receiptId:id,encounterId:'f31',rootRewardId:'root:f31',outcome,actualAttemptCommitted:true,
    precisionAdmissionReceipt:{id:`admission:${id}`,...scope,admitted:true,reservationId:`reservation:${id}`,
      reservedBudgetSeconds:8,sanAtAdmission:s.resources.san,admittedAtBudget:s.budget},
    budgetCostReceipt:{id:`cost:${id}`,...scope,precisionAdmissionReceiptId:`admission:${id}`,
      reservationId:`reservation:${id}`,committed:true,budgetSeconds:8,budgetBefore:s.budget,budgetAfter:s.budget+8},...extra};
}
function rest(s,id,outcome,extra={}) {
  const input=restInput(s,id,outcome,extra);must(advanceConsumerClock(s,{budgetCost:8}));
  return settleRestAttempt(s,input);
}
function rejectRest(s,id,outcome,extra={}) {return settleRestAttempt(s,restInput(s,id,outcome,extra));}

test('P08 permits one separately charged local retry: first failure energy2, second success only two more', () => {
  const s=restState();const first=must(rest(s,'attempt1','failed'));
  assert.equal(first.energyDelta,2);assert.equal(first.sanDelta,-6);assert.equal(first.petChargeSpent,true);
  assert.deepEqual(first.retry,{localWindowSeconds:1.5,clock:'local_qte',targetScale:1,existingPrecisionAdmissionStillRequired:true});
  assert.equal(s.budget,8);assert.equal(s.world,0);assert.equal(s.restEpisodes.f31.state,'RETRY_AVAILABLE');
  const second=must(rest(s,'attempt2','success'));assert.equal(second.energyDelta,2);assert.equal(second.sanDelta,0);
  assert.equal(second.petChargeSpent,false);assert.equal(second.attemptNumber,2);assert.equal(second.chargedBudgetSeconds,8);
  assert.equal(s.resources.energy,54);assert.equal(s.resources.san,44);assert.equal(s.pet.charges,1);
  assert.equal(s.budget,16);assert.equal(s.world,0);assert.equal(rejectRest(s,'attempt3','success').ok,false);
});

test('Cancelling an actually started first attempt still costs eight, gives no compensation, and ends this encounter', () => {
  const s=restState();const result=must(rest(s,'cancel','cancelled'));
  assert.equal(result.energyDelta,0);assert.equal(result.sanDelta,0);assert.equal(s.pet.charges,2);
  assert.equal(result.chargedBudgetSeconds,8);assert.equal(s.budget,8);
  assert.equal(rejectRest(s,'later','failed').ok,false);assert.equal(s.resources.energy,50);
});

test('Cancelling a started second attempt costs its own eight and preserves only the first compensation', () => {
  const s=restState();must(rest(s,'first','failed'));const result=must(rest(s,'exit','cancelled'));
  assert.equal(result.energyDelta,0);assert.equal(result.petChargeSpent,false);assert.equal(s.resources.energy,52);
  assert.equal(s.budget,16);assert.equal(s.pet.charges,1);assert.equal(rejectRest(s,'late','success').ok,false);
});

test('Leaving the prepared view or declining an unstarted retry adds no attempt, cost, or compensation', () => {
  for(const failedFirst of [false,true]) {
    const s=restState();if(failedFirst)must(rest(s,'first','failed'));
    const result=must(exitUnstartedRest(s,{encounterId:'f31',rootRewardId:'root:f31'}));
    assert.equal(result.energyDelta,0);assert.equal(result.chargedBudgetSeconds,0);
    assert.equal(s.budget,failedFirst?8:0);assert.equal(s.resources.energy,failedFirst?52:50);
    assert.equal(s.restEpisodes.f31.attempts.length,failedFirst?1:0);assert.equal(rejectRest(s,'late','success').ok,false);
  }
});

test('A missing, unprepared, uncared, or chargeless P08 cannot grant a retry after the first failure', () => {
  for(const pet of [{id:'P01',prepared:true,cared:true,charges:2},{id:'P08',prepared:false,cared:true,charges:2},
    {id:'P08',prepared:true,cared:false,charges:2},{id:'P08',prepared:true,cared:true,charges:0}]) {
    const s=restState(pet);const first=must(rest(s,'first','failed'));
    assert.equal(first.energyDelta,0);assert.equal(first.retry,null);assert.equal(s.restEpisodes.f31.state,'FAILED');
    assert.equal(rejectRest(s,'second','success').ok,false);assert.equal(s.pet.charges,pet.charges);
    assert.equal(s.budget,8);assert.equal(s.resources.energy,50);
    const fresh=restState(pet);assert.equal(must(rest(fresh,'only','success')).energyDelta,4);
    assert.equal(rejectRest(fresh,'extra','success').ok,false);
  }
});

test('A second actual failure ends the episode; a third success is rejected even with remaining pet charges', () => {
  const s=restState();must(rest(s,'first','failed'));const second=must(rest(s,'second','failed'));
  assert.equal(second.energyDelta,0);assert.equal(second.sanDelta,0);assert.equal(second.petChargeSpent,false);
  assert.equal(second.retry,null);assert.equal(s.restEpisodes.f31.state,'FAILED');
  assert.equal(rejectRest(s,'third','success').ok,false);assert.equal(s.resources.energy,52);
  assert.equal(s.resources.san,44);assert.equal(s.pet.charges,1);assert.equal(s.budget,16);
});

test('Zero, wrong, uncommitted, or mismatched cost receipts and the former boolean cannot settle an attempt', () => {
  const changes=[x=>({...x,budgetSeconds:0}),x=>({...x,budgetSeconds:7}),x=>({...x,budgetSeconds:9}),
    x=>({...x,committed:false}),x=>({...x,budgetAfter:x.budgetAfter+1}),x=>({...x,budgetBefore:x.budgetBefore+1}),
    x=>({...x,runId:'another-run'}),x=>({...x,attemptNumber:2}),x=>({...x,precisionAdmissionReceiptId:'another-admission'}),
    x=>({...x,reservationId:'another-reservation'}),()=>null];
  for(const change of changes) {
    const s=restState(), input=restInput(s,'bad','failed');input.budgetCostReceipt=change(input.budgetCostReceipt);
    input.budgetCostCommitted=true;must(advanceConsumerClock(s,{budgetCost:8}));
    assert.equal(settleRestAttempt(s,input).ok,false);assert.equal(s.restEpisodes.f31.attempts.length,0);
    assert.equal(s.resources.energy,50);assert.equal(s.resources.san,50);assert.equal(s.pet.charges,2);
  }
});

test('Each attempt needs actual positive-SAN precision admission and a currently committed budget interval', () => {
  const changes=[x=>({...x,admitted:false}),x=>({...x,reservationId:''}),x=>({...x,reservedBudgetSeconds:0}),
    x=>({...x,sanAtAdmission:0}),x=>({...x,sanAtAdmission:99}),x=>({...x,nightId:'another-night'}),
    x=>({...x,encounterId:'another-encounter'}),()=>null];
  for(const change of changes) {
    const s=restState(), input=restInput(s,'bad','failed');input.precisionAdmissionReceipt=change(input.precisionAdmissionReceipt);
    must(advanceConsumerClock(s,{budgetCost:8}));assert.equal(settleRestAttempt(s,input).ok,false);
    assert.equal(s.resources.energy,50);assert.equal(s.resources.san,50);
  }
  const uncharged=restState();assert.equal(rejectRest(uncharged,'future-cost','failed').ok,false);
  assert.equal(uncharged.budget,0);assert.equal(uncharged.restEpisodes.f31.attempts.length,0);
});

test('A first failure reaching SAN0 retains earned P08 energy2 but grants no retry and returns to normal panic', () => {
  for(const san of [1,6]) {
    const s=restState(undefined,{resources:{san}});const first=must(rest(s,'first','failed'));
    assert.equal(first.energyDelta,2);assert.equal(first.sanDelta,-san);assert.equal(first.petChargeSpent,true);
    assert.equal(first.normalPanicRequired,true);assert.equal(first.retry,null);assert.equal(s.resources.san,0);
    assert.equal(s.restEpisodes.f31.state,'FAILED');assert.equal(rejectRest(s,'retry','success').ok,false);
    assert.equal(s.resources.energy,52);assert.equal(s.pet.charges,1);assert.equal(s.budget,8);
  }
});

test('SAN0 forbids both initial admission and a later retry despite a caller asserting old positive SAN', () => {
  const initial=restState(undefined,{resources:{san:0}});assert.equal(rejectRest(initial,'first','success').ok,false);
  const s=restState();must(rest(s,'first','failed'));s.resources.san=0;
  const input=restInput(s,'retry','success');input.precisionAdmissionReceipt.sanAtAdmission=44;
  assert.equal(settleRestAttempt(s,input).ok,false);assert.equal(s.budget,8);assert.equal(s.resources.energy,52);
  assert.equal(s.pet.charges,1);assert.equal(s.restEpisodes.f31.attempts.length,1);
});

test('The one retry cannot reuse a prior cost receipt, admission receipt, or precision reservation', () => {
  for(const field of ['cost','admission','reservation']) {
    const s=restState();must(rest(s,'first','failed'));const input=restInput(s,'second','success');
    if(field==='cost')input.budgetCostReceipt.id='cost:first';
    if(field==='admission') {input.precisionAdmissionReceipt.id='admission:first';input.budgetCostReceipt.precisionAdmissionReceiptId='admission:first';}
    if(field==='reservation') {input.precisionAdmissionReceipt.reservationId='reservation:first';input.budgetCostReceipt.reservationId='reservation:first';}
    must(advanceConsumerClock(s,{budgetCost:8}));assert.equal(settleRestAttempt(s,input).ok,false);
    assert.equal(s.resources.energy,52);assert.equal(s.restEpisodes.f31.attempts.length,1);assert.equal(s.pet.charges,1);
  }
});

test('Rest receipt replays, wrong roots, missing actual attempts, and duplicate episode declarations cannot create effects', () => {
  for(const patch of [{rootRewardId:'another-root'},{actualAttemptCommitted:false}]) {
    const s=restState();assert.equal(rest(s,'bad','failed',patch).ok,false);
    assert.equal(s.resources.energy,50);assert.equal(s.resources.san,50);assert.equal(s.pet.charges,2);
  }
  const s=restState();must(rest(s,'first','failed'));assert.equal(rejectRest(s,'first','failed').ok,false);
  assert.equal(registerRestEpisode(s,{encounterId:'f31',rootRewardId:'another-root'}).ok,false);
  assert.equal(registerRestEpisode(s,{encounterId:'copy',rootRewardId:'root:f31'}).ok,false);
});

console.log(JSON.stringify({status:'PASS',scenarioCount:passed.length,scenarios:passed,
  scope:'Finite declared receipts, same-object food inspection, predeclared benefit keys, F53 dawn qualification/payment ordering and P08 rest settlement. Fragment deduplication reuses the existing reward reference. No physical authentication, full AI, item-use restrictions beyond these consumers, RNG, production persistence, daytime engine, complete precision controller or handover identity verification.'},null,2));
