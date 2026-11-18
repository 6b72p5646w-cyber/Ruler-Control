/**
 * V0.9 finite integration adapter. Condition owns world/budget/SAN; store and
 * consumer clocks only receive actual committed deltas. The two-bottle consumer
 * is the sole F53 truth; the old one-object condition example is not admitted.
 * World observations, duty completion and physical transfers remain trusted
 * engine-adapter receipts. Matching their scope is not physical authentication.
 */
import {createConditionState, advanceConditionWorld, setConditionPause,
  beginPrecisionAttempt, advancePrecisionLocal, finishPrecisionAttempt,
  applyConditionFear, beginPortableStabilization, beginRecordedWork, commitConditionSanDelta} from './condition_core_v06.mjs';
import {createStore, advanceStore, arriveOrder, customerEntered, beginService,
  finishService, phaseEnd, clearDebt, gradeShift, changeServiceMode} from './store_core_v05.mjs';
import {createConsumerState, advanceConsumerClock, registerBenefitEncounter,
  recordBenefitFact, movePromisedBottle, setPromiseContainerSeal,
  recordVerifiedHandover, settleFriendlyBenefit, consumeVerifiedFood,
  settleRestAttempt, registerRestEpisode} from './consumer_core_v08.mjs';

const copy = value => structuredClone(value);
const yes = value => ({ok: true, ...value});
const no = reason => ({ok: false, reason});
const named = x => typeof x === 'string' && x.length > 0;
const finite = x => typeof x === 'number' && Number.isFinite(x);
const TIME_EPS=1e-8;
const terminal = new Set(['RESOLVED','PREVENTED','DECLINED','SAFE_RETURNED',
  'FAILED_LOCAL','CANCELLED_UNAVAILABLE','WITHDRAWN']);
const methods = {private_arrangement: 'private_agreement', body_baseline: 'current_body_observation'};
const sameIds = (a,b) => Array.isArray(a) && a.length === b.length && new Set(a).size === a.length &&
  [...a].sort().every((x,i) => x === [...b].sort()[i]);
const next = (s,prefix) => prefix + ':' + s.scope.runId + ':' + (++s.sequence);
const activeThreat = s => Object.values(s.condition.encounters).some(e => e.critical && !terminal.has(e.state));
const working = s => s.condition.mode === 'night' && !s.condition.paused && !s.condition.precision;
function event(s,type,details={}) {s.events.push({type,world:s.condition.world,budget:s.condition.budget,...details});}
function scoped(s,r,kind,{historical=false}={}) {
  return r && named(r.id) && !s.receipts[r.id] && r.kind === kind && r.committed === true &&
    r.runId === s.scope.runId && r.nightId === s.scope.nightId && r.campaignId === s.scope.campaignId &&
    named(r.sourceActionId) && finite(r.worldAt) && finite(r.budgetAt) &&
    (historical ? r.worldAt <= 0 && r.budgetAt <= 0 :
      Math.abs(r.worldAt-s.condition.world)<1e-8 && Math.abs(r.budgetAt-s.condition.budget)<1e-8);
}
function record(s,r) {s.receipts[r.id]=copy(r);return r.id;}
function syncGuard(s) {
  if (Object.keys(s.condition.promises).length || Object.values(s.condition.encounters).some(e=>e.monsterId==='F53'))
    return no('legacy_single_object_f53_not_admitted_in_integrated_session');
  if (s.consumer.runId!==s.scope.runId || s.consumer.nightId!==s.scope.nightId ||
      Math.abs(s.consumer.world-s.condition.world)>1e-8 || Math.abs(s.consumer.budget-s.condition.budget)>1e-8 ||
      Math.abs(s.store.now-s.condition.world)>1e-8 || s.consumer.resources.san!==s.condition.san)
    return no('modules_changed_outside_shared_transaction');
  return yes({});
}

export function createSettlementLedger({coins=0,tickets=0}={}) {
  if (![coins,tickets].every(x=>Number.isSafeInteger(x)&&x>=0)) throw new RangeError('invalid_ledger_balance');
  return {schemaVersion:'0.9',coins,tickets,nightAwards:{}};
}
export function serializeSettlementLedger(ledger) {validateLedger(ledger);return JSON.stringify(ledger);}
function validateLedger(ledger) {
  if (ledger?.schemaVersion!=='0.9' || ![ledger.coins,ledger.tickets].every(x=>Number.isSafeInteger(x)&&x>=0) ||
      !ledger.nightAwards || Array.isArray(ledger.nightAwards)) throw new Error('invalid_settlement_ledger');
  for (const [key,award] of Object.entries(ledger.nightAwards)) {
    if (!named(key)||award.key!==key||key!==JSON.stringify([award.campaignId,award.nightId])||!named(award.receiptId)||!named(award.runId)||!named(award.nightId)||
        !named(award.campaignId)||award.budget!==720||!Number.isSafeInteger(award.wage)||award.wage<0||
        !['A','B','C'].includes(award.grade)||typeof award.ticket!=='boolean'||
        !finite(award.sanBonus)||award.sanBonus<0) throw new Error('invalid_night_award');
  }
}
export function restoreSettlementLedger(text) {const ledger=JSON.parse(text);validateLedger(ledger);return ledger;}

export function createShiftSettlementSession(configs,options={}) {
  const {conditionContract,storeConfig,consumerContract,itemData,balance}=configs;
  const scope={campaignId:options.campaignId,nightId:options.nightId,runId:options.runId};
  if (Object.values(scope).some(x=>!named(x))) throw new Error('stable_campaign_night_and_attempt_run_required');
  const ledger=options.ledger ?? createSettlementLedger();validateLedger(ledger);
  const orderPlan=Array.from({length:6},(_,phase)=>['pickup','browse'].map(type=>({
    id:'order:'+scope.runId+':'+phase+':'+type,markerId:'base_order:'+phase+':'+type,
    phase,type,at:phase*120+storeConfig.service.base_order_mix[type==='pickup'?'pickup_default_second':'browse_default_second'],
    requiresEntry:type==='browse',dispatched:false}))).flat();
  const orderMarkerIds=new Set(orderPlan.map(x=>x.markerId));
  const condition=createConditionState(conditionContract,{balance,initialSan:options.initialSan,
    objects:options.objects??[],reservedSlots:options.reservedSlots??[],markers:[
      ...(options.markers??[]).filter(x=>!orderMarkerIds.has(x.id)),
      ...orderPlan.map(x=>({id:x.markerId,at:x.at}))]});
  const consumer=createConsumerState(consumerContract,itemData,{...scope,
    resources:{...(options.resources??{}),san:condition.san},
    resourceCaps:options.resourceCaps,transferItemIds:options.transferItemIds,
    foodInspectionImplemented:options.foodInspectionImplemented,pet:options.pet});
  const handoverObjectIds=options.handoverObjectIds??['shift-keys','shift-records'];
  if (!sameIds(handoverObjectIds,[...new Set(handoverObjectIds)])||handoverObjectIds.length!==2||
      handoverObjectIds.some(x=>!named(x))) throw new Error('two_existing_handover_objects_required');
  return {schemaVersion:'0.9',scope,configs:copy(configs),condition,store:createStore(storeConfig),consumer,
    ledger,sequence:0,receipts:{},events:[],completedDuties:{},phaseEnds:[],pendingSeals:{},orderPlan,
    precisionAdmissions:{},closed:false,handoverReceiptId:null,
    handoverObjectIds:[...handoverObjectIds],manager:{baselines:{},presence:null,observations:{},verification:null},
    sourceBoundary:'Receipt scope and declared comparisons are checked; the engine must supply real physical observations and transfers.'};
}

export function setSettlementPause(s,paused) {setConditionPause(s.condition,paused);return yes({paused:s.condition.paused});}
function mirrorSan(s) {s.consumer.resources.san=s.condition.san;}
function applyConsumerSan(s,before,receiptId,sourceKind) {
  const after=s.consumer.resources.san;
  if (after===before) return;
  const result=commitConditionSanDelta(s.condition,{receiptId:'consumer:'+s.scope.runId+':'+receiptId,
    delta:after-before,sourceKind});
  if(!result.ok)throw new Error('shared_san_commit_rejected:'+result.reason);
  event(s,'shared_san_committed',{before,after,receiptId});
}
export function applySettlementFear(s,command) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  const result=applyConditionFear(s.condition,command);mirrorSan(s);return result;
}
export function commitSettlementSanDelta(s,command) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  const result=commitConditionSanDelta(s.condition,command);mirrorSan(s);return result;
}
export function beginSettlementStabilization(s) {
  const guard=syncGuard(s);return guard.ok?beginPortableStabilization(s.condition):guard;
}

function applyCommittedSeals(s,conditionDraft,consumerDraft) {
  const updates=[];
  for (const [actionId,pending] of Object.entries(s.pendingSeals)) {
    if (pending.settled) continue;
    const a=conditionDraft.actions[actionId];
    if (a?.state==='completed') {
      const e=consumerDraft.encounters[pending.encounterId], b=e?.bindings;
      const exact=e&&!e.cancelled&&a.objectId===b.container&&a.receiptId&&
        [b.bottle1,b.bottle2].every(id=>consumerDraft.inventory[id]?.slot===b.container&&consumerDraft.inventory[id].reservedBy===e.id);
      const result=exact?setPromiseContainerSeal(consumerDraft,e.id,true):no('original_bottles_changed');
      updates.push({actionId,settled:true,qualifiedSeal:result.ok,receiptId:a.receiptId});
    } else if (a?.state==='cancelled') updates.push({actionId,settled:true,qualifiedSeal:false});
  }
  return updates;
}
function finishClockTransaction(s,conditionDraft,oldBudget,oldWorld,preparedConsumer=null) {
  const consumerDraft=preparedConsumer??copy(s.consumer), worldDelta=conditionDraft.world-oldWorld,
    budgetDelta=conditionDraft.budget-oldBudget, rawCost=budgetDelta-worldDelta,
    cost=Math.abs(rawCost)<=TIME_EPS?0:rawCost;
  if (worldDelta < -1e-8 || cost < -1e-8 || (worldDelta>1e-8&&cost>1e-8)) return no('mixed_clock_transaction');
  const sealUpdates=applyCommittedSeals(s,conditionDraft,consumerDraft);
  consumerDraft.resources.san=conditionDraft.san;
  if(preparedConsumer) {
    if(Math.abs(consumerDraft.world-conditionDraft.world)>TIME_EPS||Math.abs(consumerDraft.budget-conditionDraft.budget)>TIME_EPS)return no('prepared_consumer_clock_mismatch');
  } else {
    // Within the same finite time tolerance, use the master's exact schedule
    // endpoint so the consumer's strict 720 snapshot cannot miss by 1e-12.
    const tick=worldDelta>0&&cost===0
      ?advanceConsumerClock(consumerDraft,{worldSeconds:Math.max(0,budgetDelta)})
      :advanceConsumerClock(consumerDraft,{worldSeconds:Math.max(0,worldDelta),budgetCost:Math.max(0,budgetDelta-worldDelta)});
    if (!tick.ok) return tick;
  }
  if(Math.abs(consumerDraft.world-conditionDraft.world)>TIME_EPS||Math.abs(consumerDraft.budget-conditionDraft.budget)>TIME_EPS)return no('consumer_clock_step_disagrees_with_master');
  consumerDraft.world=conditionDraft.world;consumerDraft.budget=conditionDraft.budget;
  let storeDraft=advanceStore(s.store,s.configs.storeConfig,Math.max(0,worldDelta));
  const serviceReceipts=[];
  for(const o of storeDraft.orders)if(o.status==='serving'&&storeDraft.now+TIME_EPS>=o.finishesAt) {
    const actualNow=storeDraft.now;
    if(Math.abs(storeDraft.now-o.finishesAt)<=TIME_EPS)storeDraft.now=o.finishesAt;
    const result=finishService(storeDraft,o.id);
    storeDraft.now=actualNow;
    if(result.ok){storeDraft=result.state;storeDraft.now=actualNow;serviceReceipts.push({orderId:o.id,receiptId:result.receiptId});}
  }
  // Drafts are private until both consumers have committed. F53's exact-six
  // snapshot therefore precedes publication of the shared critical verdict.
  s.condition=conditionDraft;s.consumer=consumerDraft;s.store=storeDraft;
  for(const r of serviceReceipts)event(s,'ordinary_order_completed',r);
  for(const plan of s.orderPlan)if(!plan.dispatched&&conditionDraft.markers.find(m=>m.id===plan.markerId)?.dispatched) {
    plan.dispatched=true;
    if(conditionDraft.mode==='night') {
      s.store=arriveOrder(s.store,s.configs.storeConfig,plan.id,{requiresEntry:plan.requiresEntry});
      event(s,'scheduled_order_arrived',{orderId:plan.id,requiresEntry:plan.requiresEntry,phase:plan.phase});
    }
  }
  for (const row of sealUpdates) {Object.assign(s.pendingSeals[row.actionId],row);event(s,'actual_container_seal_committed',row);}
  if (oldBudget<720&&conditionDraft.budget===720) {
    for (const e of Object.values(consumerDraft.encounters)) if(e.monsterId==='F53')
      event(s,'dawn_qualification_frozen',{encounterId:e.id,qualified:e.dawnSnapshot?.qualified===true});
    event(s,'shared_critical_verdict',{mode:conditionDraft.mode,panicActive:conditionDraft.panic.active});
  }
  for(let phase=0;phase<6;phase++)if(conditionDraft.budget>=(phase+1)*120&&!s.phaseEnds.includes(phase)) {
    const duty=s.configs.storeConfig.duties.find(x=>x.phase==='N0'+(phase+1));
    s.store=phaseEnd(s.store,s.configs.storeConfig,phase,s.completedDuties[duty?.id]?null:duty?.id);
    s.phaseEnds.push(phase);
  }
  if(conditionDraft.mode!=='night') {
    for(const o of s.store.orders)if(o.status==='serving') {o.status='waiting';o.cancelReason='night_closed';}
  }
  return yes({advancedWorld:worldDelta,advancedBudget:budgetDelta,mode:conditionDraft.mode});
}
export function advanceSettlementWorld(s,seconds) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  if(!finite(seconds)||seconds<0)return no('invalid_world_delta');
  let remaining=seconds,advancedWorld=0,advancedBudget=0;
  do {
    const serviceEnds=s.store.orders.filter(o=>o.status==='serving'&&o.finishesAt>s.store.now)
      .map(o=>o.finishesAt-s.store.now);
    const nextMarker=s.condition.markers.filter(m=>!m.dispatched&&m.at>s.condition.budget)
      .reduce((v,m)=>Math.min(v,m.at-s.condition.budget),Infinity);
    const step=Math.min(remaining,nextMarker,...serviceEnds),c=copy(s.condition),oldWorld=c.world,oldBudget=c.budget;
    const r=advanceConditionWorld(c,step);if(!r.ok)return r;
    const result=finishClockTransaction(s,c,oldBudget,oldWorld);if(!result.ok)return result;
    advancedWorld+=result.advancedWorld;advancedBudget+=result.advancedBudget;
    remaining=Math.max(0,remaining-result.advancedWorld);
    if(result.advancedWorld<=1e-9||s.condition.mode!=='night')break;
  } while(remaining>1e-9);
  return yes({advancedWorld,advancedBudget,mode:s.condition.mode});
}
export function beginSettlementPrecision(s,{costSeconds,tag=null}) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  if(tag?.kind==='F31') {
    const episode=s.consumer.restEpisodes[tag.encounterId];
    if(costSeconds!==s.configs.consumerContract.f31_p08_rest.attempt_cost_budget_seconds||
        !episode||episode.rootRewardId!==tag.rootRewardId||!['OPEN','RETRY_AVAILABLE'].includes(episode.state))
      return no('one_open_rest_or_single_retry_required');
  }
  const r=beginPrecisionAttempt(s.condition,{costSeconds});
  if(r.ok)s.precisionAdmissions[r.attemptId]={attemptId:r.attemptId,tag,world:s.condition.world,
    budget:s.condition.budget,san:s.condition.san,costSeconds,settled:false};
  return r;
}
export function advanceSettlementPrecisionLocal(s,seconds) {return advancePrecisionLocal(s.condition,seconds);}
export function finishSettlementPrecision(s,{attemptId,outcome,sanOutcome=null}) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  const start=s.precisionAdmissions[attemptId];if(!start||start.settled)return no('not_actual_pending_precision');
  if(start.tag?.kind==='F31')return no('rest_requires_atomic_outcome_and_cost_commit');
  const c=copy(s.condition),oldWorld=c.world,oldBudget=c.budget;
  const r=finishPrecisionAttempt(c,{attemptId,outcome,sanOutcome});if(!r.ok)return r;
  const transaction=finishClockTransaction(s,c,oldBudget,oldWorld);if(!transaction.ok)return transaction;
  start.settled=true;start.outcome=outcome;start.receiptId=r.receiptId;
  return yes({...transaction,attemptId,receiptId:r.receiptId,
    ...(r.sanResult?{sanResult:r.sanResult}:{}),
    committedCost:{worldBefore:oldWorld,worldAfter:c.world,budgetBefore:oldBudget,budgetAfter:c.budget,seconds:start.costSeconds}});
}

export function arriveSettlementOrder(s,{orderId,requiresEntry=false}) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  // The current integration owns the authored 6 pickup + 6 browse schedule.
  // Special replacements require their future reservation adapter, not a 13th
  // order or a browser silently changed into an extra pickup.
  const plan=s.orderPlan.find(x=>x.id===orderId&&x.requiresEntry===requiresEntry);
  return plan&&s.store.orders.some(o=>o.id===plan.id)?yes({alreadyScheduled:true,orderId}):no('base_orders_owned_by_fixed_schedule');
}
export function recordSettlementCustomerEntry(s,r) {
  if(!working(s)||!scoped(s,r,'actual_customer_threshold_crossing'))return no('actual_customer_entry_required');
  const result=customerEntered(s.store,r.orderId,{crossedDoor:true});
  if(result.ok){s.store=result.state;record(s,r);}return result.ok?yes({receiptId:r.id}):no(result.reason);
}
export function beginSettlementService(s,orderId) {
  if(!working(s))return no('night_world_not_available');
  const r=beginService(s.store,s.configs.storeConfig,orderId);if(r.ok)s.store=r.state;
  return r.ok?yes({duration:r.duration}):no(r.reason);
}
export function finishSettlementService(s,orderId) {
  if(!working(s))return no('no_new_service_commit_after_world_closed');
  const r=finishService(s.store,orderId);if(r.ok){s.store=r.state;event(s,'ordinary_order_completed',{orderId,receiptId:r.receiptId});}
  return r.ok?yes({receiptId:r.receiptId}):no(r.reason);
}
export function changeSettlementServiceMode(s,mode,commandId) {
  if(!working(s))return no('night_world_not_available');
  const r=changeServiceMode(s.store,s.configs.storeConfig,mode,commandId);if(r.ok)s.store=r.state;
  return r.ok?yes({requiredWorldSeconds:r.requiredWorldSeconds}):no(r.reason);
}
export function recordSettlementDuty(s,r) {
  const d=s.configs.storeConfig.duties.find(x=>x.id===r?.dutyId);
  if(!working(s)||!scoped(s,r,'actual_duty_completed')||!d||s.completedDuties[d.id]||
      !Array.isArray(r.objectIds)||!r.objectIds.length||r.objectIds.some(x=>!named(x)))return no('actual_uncredited_duty_required');
  const phase=Number(d.phase.slice(1))-1;
  if(s.condition.budget<phase*120||s.condition.budget>Math.min((phase+2)*120,720))return no('duty_outside_its_work_or_carryover_phase');
  record(s,r);s.completedDuties[d.id]=r.id;s.store=clearDebt(s.store,d.id);return yes({receiptId:r.id});
}

export function registerSettlementDawnPromise(s,command,acceptanceReceipt) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  if(!working(s)||s.condition.budget>=240||!scoped(s,acceptanceReceipt,'actual_dawn_promise_accepted')||
      acceptanceReceipt.encounterId!==command.id||acceptanceReceipt.rootRewardId!==command.rootRewardId||
      s.condition.objects[command.bindings?.container]?.kind!=='reserved_water')return no('actual_two_bottle_promise_required');
  if(!sameIds(acceptanceReceipt.objectIds,[command.bindings.bottle1,command.bindings.bottle2,command.bindings.container]))return no('promise_objects_differ');
  const draft=copy(s.consumer);const registration=registerBenefitEncounter(draft,{...command,monsterId:'F53'});
  if(!registration.ok)return registration;
  const fact=recordBenefitFact(draft,{receiptId:acceptanceReceipt.id,encounterId:command.id,
    rootRewardId:command.rootRewardId,rewardKey:'dawn',predicate:'actual_promise_accepted',objectIds:acceptanceReceipt.objectIds});
  if(!fact.ok)return fact;s.consumer=draft;record(s,acceptanceReceipt);return yes({encounterId:command.id});
}
export function placeSettlementPromisedBottle(s,r) {
  const e=s.consumer.encounters[r?.encounterId];
  if(!working(s)||!scoped(s,r,'actual_promised_bottle_placed')||!e||
      s.condition.actionLocks['object:'+e.bindings.container])return no('actual_unlocked_bottle_transfer_required');
  const result=movePromisedBottle(s.consumer,{encounterId:e.id,bottleId:r.bottleId,slotId:r.slotId});
  if(result.ok)record(s,r);return result;
}
export function beginSettlementDawnSeal(s,encounterId) {
  const e=s.consumer.encounters[encounterId],b=e?.bindings;
  if(!working(s)||!e||e.cancelled||e.containerSealed||
      ![b.bottle1,b.bottle2].every(id=>s.consumer.inventory[id]?.slot===b.container&&s.consumer.inventory[id].reservedBy===e.id))return no('both_originals_must_be_in_same_container');
  const r=beginRecordedWork(s.condition,{kind:'seal_water',objectId:b.container});
  if(r.ok)s.pendingSeals[r.actionId]={encounterId,settled:false};return r;
}
export function consumeSettlementFood(s,itemInstanceId) {
  const guard=syncGuard(s);if(!guard.ok)return guard;if(!working(s))return no('night_world_not_available');
  const before=s.condition.san,result=consumeVerifiedFood(s.consumer,itemInstanceId);
  if(result.ok)applyConsumerSan(s,before,result.receiptId??('food:'+itemInstanceId),'verified_item');return result;
}
export function registerSettlementRest(s,{encounterId,rootRewardId}) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  if(!working(s)||s.condition.budget<600)return no('rest_requires_its_actual_final_phase');
  return registerRestEpisode(s.consumer,{encounterId,rootRewardId});
}
export function finishSettlementRestPrecision(s,{attemptId,encounterId,rootRewardId,outcome}) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  const start=s.precisionAdmissions[attemptId],episode=s.consumer.restEpisodes[encounterId],
    cost=s.configs.consumerContract.f31_p08_rest.attempt_cost_budget_seconds;
  if(!start||start.settled||s.condition.precision?.id!==attemptId||start.costSeconds!==cost||
      start.tag?.kind!=='F31'||start.tag.encounterId!==encounterId||start.tag.rootRewardId!==rootRewardId||
      !episode||episode.rootRewardId!==rootRewardId)return no('same_reserved_rest_attempt_required');
  const consumer=copy(s.consumer),condition=copy(s.condition),oldBudget=condition.budget,oldWorld=condition.world;
  const tick=advanceConsumerClock(consumer,{budgetCost:cost});if(!tick.ok)return tick;
  const attemptNumber=episode.attempts.length+1,base={...s.scope,encounterId,rootRewardId,attemptNumber},
    admissionId='rest-admission:'+attemptId,reservationId='rest-reservation:'+attemptId,
    costId='rest-cost:'+attemptId,outcomeId='rest-outcome:'+attemptId;
  const settled=settleRestAttempt(consumer,{receiptId:outcomeId,encounterId,rootRewardId,outcome,
    actualAttemptCommitted:true,
    precisionAdmissionReceipt:{...base,id:admissionId,admitted:true,reservationId,
      reservedBudgetSeconds:cost,sanAtAdmission:start.san,admittedAtBudget:start.budget},
    budgetCostReceipt:{...base,id:costId,committed:true,precisionAdmissionReceiptId:admissionId,
      reservationId,budgetSeconds:cost,budgetBefore:start.budget,budgetAfter:start.budget+cost}});
  if(!settled.ok)return settled;
  const delta=consumer.resources.san-condition.san;
  const committed=finishPrecisionAttempt(condition,{attemptId,outcome,
    sanOutcome:delta?{receiptId:outcomeId+':san',delta,sourceKind:'rest_failure'}:null});
  if(!committed.ok)return committed;
  const clock=finishClockTransaction(s,condition,oldBudget,oldWorld,consumer);if(!clock.ok)return clock;
  start.settled=true;start.outcome=outcome;start.receiptId=committed.receiptId;
  return yes({...settled,...clock,precisionReceiptId:committed.receiptId});
}

export function registerManagerBaseline(s,r) {
  if(s.condition.paused||s.condition.budget!==0||!scoped(s,r,'pre_shift_manager_baseline',{historical:true})||
      !(r.method in methods)||s.manager.baselines[r.method]||!named(r.value)||!named(r.rootEvidenceId))return no('actual_pre_shift_baseline_required');
  record(s,r);s.manager.baselines[r.method]={...copy(r),compromised:false};return yes({receiptId:r.id});
}
export function recordManagerPresence(s,r) {
  if(s.closed||s.condition.paused||!['night','handover_only'].includes(s.condition.mode)||!s.condition.managerArrived||
      s.condition.budget<700||!scoped(s,r,'actual_manager_body_presence')||!named(r.bodyId))return no('scheduled_and_actual_body_arrival_required');
  const old=s.manager.presence,ttl=s.configs.conditionContract.evidence.live_presence_snapshot_world_ttl_seconds;
  const continuous=old&&old.visible&&old.bodyId===r.bodyId&&s.condition.world-old.lastWorld<=ttl;
  const continuityId=continuous?old.continuityId:next(s,'body-continuity');
  if(!continuous)s.manager.verification=null;
  s.manager.presence={bodyId:r.bodyId,continuityId,visible:true,lastWorld:s.condition.world,
    lastBudget:s.condition.budget,receiptId:r.id};record(s,r);return yes({continuityId});
}
export function interruptManagerContinuity(s,reason='body_left_current_observation') {
  if(s.manager.presence)s.manager.presence.visible=false;s.manager.verification=null;
  event(s,'manager_continuity_interrupted',{reason});return yes({});
}
function currentBody(s,bodyId,continuityId) {
  const p=s.manager.presence;
  return p&&p.visible&&p.bodyId===bodyId&&p.continuityId===continuityId&&
    s.condition.world-p.lastWorld<=s.configs.conditionContract.evidence.live_presence_snapshot_world_ttl_seconds;
}
export function recordManagerObservation(s,r) {
  if(s.closed||s.condition.paused||!['night','handover_only'].includes(s.condition.mode)||!scoped(s,r,'actual_manager_counter_observation')||
      !(r.method in methods)||!currentBody(s,r.bodyId,r.continuityId)||!named(r.rootEvidenceId)||!named(r.value)||
      !s.manager.baselines[r.method]||s.manager.baselines[r.method].compromised)return no('current_bound_manager_observation_required');
  record(s,r);s.manager.observations[r.id]={...copy(r),independenceDomain:methods[r.method]};return yes({receiptId:r.id});
}
export function compromiseManagerBaseline(s,method) {
  if(!(method in s.manager.baselines))return no('baseline_missing');
  s.manager.baselines[method].compromised=true;s.manager.verification=null;return yes({});
}
export function completeManagerCheck(s,observationIds) {
  if(s.closed||s.condition.paused||!Array.isArray(observationIds)||observationIds.length!==2||new Set(observationIds).size!==2)return no('two_specific_comparisons_required');
  const rows=observationIds.map(id=>s.manager.observations[id]);
  if(rows.some(r=>!r)||!sameIds(rows.map(r=>r.method),Object.keys(methods))||new Set(rows.map(r=>r.rootEvidenceId)).size!==2)
    return no('independent_authored_comparisons_required');
  const p=s.manager.presence;
  if(!p||rows.some(r=>!currentBody(s,r.bodyId,r.continuityId)||r.bodyId!==p.bodyId||r.continuityId!==p.continuityId||
      s.manager.baselines[r.method].compromised||r.value!==s.manager.baselines[r.method].value))return no('baseline_mismatch_or_continuity_lost');
  const verification={id:next(s,'manager-check'),bodyId:p.bodyId,continuityId:p.continuityId,
    observationIds:[...observationIds],worldAt:s.condition.world,budgetAt:s.condition.budget};
  s.manager.verification=verification;event(s,'manager_check_completed',{verificationId:verification.id,bodyId:p.bodyId});
  return yes({verificationId:verification.id});
}
export function commitSettlementHandover(s,transferReceipt) {
  const guard=syncGuard(s);if(!guard.ok)return guard;
  if(s.closed)return no('handover_already_committed');
  if(s.condition.paused||s.condition.budget!==720||s.condition.mode!=='handover_only'||s.condition.panic.active||activeThreat(s)||s.store.criticalBreach)
    return no('true_six_safe_handover_required');
  const v=s.manager.verification;
  if(!v||!currentBody(s,v.bodyId,v.continuityId)||Object.values(s.manager.baselines).some(x=>x.compromised)||
      !scoped(s,transferReceipt,'actual_keys_and_records_handover')||transferReceipt.bodyId!==v.bodyId||
      transferReceipt.continuityId!==v.continuityId||transferReceipt.verificationId!==v.id||
      !sameIds(transferReceipt.objectIds,s.handoverObjectIds))return no('same_verified_body_and_actual_objects_required');
  const grade=gradeShift(s.store,s.configs.storeConfig,{trueGameMinutes:360,verifiedHandover:true,
    completedDuties:Object.keys(s.completedDuties).length,unresolvedCriticalThreat:false,
    panicActive:s.condition.panic.active,panicExpired:false,settlementMode:s.condition.mode,withdrawn:false});
  if(!grade.complete)return no('actual_grade_incomplete');
  const key=JSON.stringify([s.scope.campaignId,s.scope.nightId]),prior=s.ledger.nightAwards[key];
  if(prior) {record(s,transferReceipt);s.closed=true;s.handoverReceiptId=transferReceipt.id;
    event(s,'night_award_already_paid',{key,originalReceiptId:prior.receiptId});
    return yes({replayedNight:true,paidCoins:0,paidTickets:0,sanBonus:0,originalAward:copy(prior)});}
  const consumerDraft=copy(s.consumer),handover=recordVerifiedHandover(consumerDraft,
    {receiptId:transferReceipt.id,runId:s.scope.runId,managerId:'MANAGER',settlementMode:s.condition.mode,panicActive:false});
  if(!handover.ok)return handover;
  let sanBonus=0;const benefits=[];
  for(const e of Object.values(consumerDraft.encounters))if(e.monsterId==='F53'&&e.dawnSnapshot?.qualified&&!e.cancelled) {
    const r=settleFriendlyBenefit(consumerDraft,{encounterId:e.id,rootRewardId:e.rootRewardId,rewardKey:'dawn'});
    if(!r.ok)return r;sanBonus+=r.actualDelta??0;benefits.push({encounterId:e.id,receiptId:r.rewardReceiptId,actualSan:r.actualDelta??0});
  }
  const award={key,receiptId:next(s,'night-award'),...s.scope,budget:720,grade:grade.grade,
    wage:grade.wage,ticket:grade.ticket,orders:grade.orders,duties:grade.duties,sanBonus,
    handoverReceiptId:transferReceipt.id,benefits};
  // Publish in one synchronous transaction. A production storage adapter must
  // durably commit this ledger together with the campaign resource checkpoint.
  const conditionDraft=copy(s.condition);
  if(sanBonus) {
    const gain=commitConditionSanDelta(conditionDraft,{receiptId:award.receiptId+':san',delta:sanBonus,sourceKind:'earned_shift_reward'});
    if(!gain.ok)return gain;
  }
  record(s,transferReceipt);s.consumer=consumerDraft;s.condition=conditionDraft;
  s.ledger.coins+=award.wage;s.ledger.tickets+=award.ticket?1:0;s.ledger.nightAwards[key]=copy(award);
  s.closed=true;s.handoverReceiptId=transferReceipt.id;event(s,'verified_handover_committed',{receiptId:transferReceipt.id});
  event(s,'night_award_committed',{key,receiptId:award.receiptId,wage:award.wage,ticket:award.ticket,sanBonus});
  return yes({replayedNight:false,paidCoins:award.wage,paidTickets:award.ticket?1:0,sanBonus,award:copy(award)});
}
export function snapshotSettlement(s) {
  return {scope:copy(s.scope),world:s.condition.world,budget:s.condition.budget,
    mode:s.condition.mode,san:s.condition.san,panic:copy(s.condition.panic),
    ordersCompleted:s.store.orders.filter(o=>o.status==='complete').length,
    dutiesCompleted:Object.keys(s.completedDuties).length,debtDeduction:s.store.debtDeduction,
    manager:{scheduledArrival:s.condition.managerArrived,presence:copy(s.manager.presence),verification:copy(s.manager.verification)},
    closed:s.closed,ledger:{coins:s.ledger.coins,tickets:s.ledger.tickets},
    dawnPromises:Object.values(s.consumer.encounters).filter(e=>e.monsterId==='F53').map(e=>({id:e.id,snapshot:copy(e.dawnSnapshot),reward:e.rewards.dawn??null}))};
}
