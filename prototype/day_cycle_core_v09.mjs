/**
 * V0.9 finite day/night resource adapter. Browser-safe ES module.
 * A practice night is an isolated copy: it never awards campaign wages, tickets,
 * knowledge, or rollback-safe production currency. World collisions, real item
 * use duration, current safe stations, and panic handling remain client inputs.
 */
import {createDayKnowledgeState, settleStudyAction, settleCaseReview} from './day_knowledge_core_v08.mjs';

const clone=x=>JSON.parse(JSON.stringify(x));
const EPS=1e-8;
const named=x=>typeof x==='string'&&x.length>0;
const finite=x=>Number.isFinite(x);
const no=reason=>({ok:false,reason});
const clamp=(x,min,max)=>Math.max(min,Math.min(max,x));
const period=m=>((m%1440)+1440)%1440;
const supplyDay=m=>Math.floor((m+1080)/1440);
function phaseAt(minute) {
  const m=period(minute);
  if(m<360)return 'night_ready';
  if(m<480)return 'morning';
  if(m<1200)return 'day';
  if(m<1320)return 'preparation';
  return 'commute';
}
function syncCaps(s) {
  for(const k of ['energy','san','satiety'])s.resources[k]=clamp(s.resources[k],0,100);
  s.staminaMax=50+0.5*s.resources.energy;
  s.resources.stamina=clamp(s.resources.stamina,0,s.staminaMax);
}
function delta(s,values) {
  const before=clone(s.resources);
  for(const [key,value] of Object.entries(values))if(key in s.resources)s.resources[key]+=value;
  syncCaps(s);
  return Object.fromEntries(Object.keys(s.resources).map(k=>[k,s.resources[k]-before[k]]));
}
function append(s,type,fields={}) {
  const r={id:`${s.runId}:resource:${++s.sequence}`,type,absoluteGameMinute:s.absoluteGameMinute,
    worldSeconds:s.worldSeconds,...clone(fields)};
  s.ledger.push(r);return r;
}
function settleDebts(s) {
  for(const debt of s.coffeeDebts.filter(x=>!x.settled&&x.dueAbsoluteGameMinute<=s.absoluteGameMinute+EPS)) {
    const beforeSan=s.resources.san;
    debt.settled=true;
    debt.receiptId=append(s,'coffee_debt_settled',{debtId:debt.id,itemInstanceId:debt.itemInstanceId,
      actualResourceDeltas:delta(s,debt.resourceDeltas)}).id;
    if(beforeSan>0&&s.resources.san===0)append(s,'san_reached_zero',{sourceId:debt.id,night:['night','practice_night'].includes(s.mode)});
  }
}
function nextDebtMinute(s) {
  return Math.min(Infinity,...s.coffeeDebts.filter(x=>!x.settled&&x.dueAbsoluteGameMinute>s.absoluteGameMinute+EPS).map(x=>x.dueAbsoluteGameMinute));
}
function refreshCalendar(s) {
  if(['night','practice_night','failed','practice_done'].includes(s.mode))return;
  const day=supplyDay(s.absoluteGameMinute);
  if(day!==s.dayIndex) {
    s.dayIndex=day;s.remainingDaySlots=s.balance.day_action_slots;s.preparationUsedMinutes=0;
    s.knowledge.dayId=`${s.runId}:day:${day}`;s.knowledge.remainingSlots=s.remainingDaySlots;
  }
  s.mode=phaseAt(s.absoluteGameMinute);
}
function advanceDayMinutes(s,minutes,{sleeping=false}={}) {
  const target=s.absoluteGameMinute+minutes;
  settleDebts(s);
  while(s.absoluteGameMinute<target-EPS) {
    const end=Math.min(target,nextDebtMinute(s));const dt=end-s.absoluteGameMinute;
    const rate=sleeping?s.balance.resources.satiety.sleep_hour_drain:s.balance.resources.satiety.awake_hour_drain;
    delta(s,{satiety:-dt*rate/60});s.absoluteGameMinute=end;settleDebts(s);
  }
  refreshCalendar(s);
}
function commitClone(s,d) {for(const k of Object.keys(s))delete s[k];Object.assign(s,d);}
function commandGuard(s,id) {return named(id)&&!s.commandReceipts[id]?null:no('command_already_committed_or_invalid');}
function commitCommand(s,id,type,data={}) {
  const r=append(s,type,{commandId:id,...data});s.commandReceipts[id]=r.id;return {ok:true,receipt:clone(r)};
}

export function createDayCycleState(balance,itemData,options={}) {
  const absolute=options.absoluteGameMinute??480;
  if(!finite(absolute)||absolute<0)throw new Error('Absolute game minute must be nonnegative');
  const resources={energy:50,san:70,satiety:70,stamina:75,...options.resources};
  if(Object.values(resources).some(x=>!finite(x)))throw new Error('Resources must be finite');
  const mode=options.mode??phaseAt(absolute),nightBudget=options.nightBudget??0;
  if(mode==='night'&&(period(absolute)>=360||Math.abs(period(absolute)-nightBudget/2)>EPS))throw new Error('Formal night must match its actual absolute minute');
  const inventory={};
  for(const item of options.inventory??[]) {
    if(!named(item.id)||inventory[item.id]||!named(item.itemId))throw new Error('Item instances need unique IDs');
    inventory[item.id]=clone(item);
  }
  const s={schemaVersion:9,runId:options.runId??'resource-run',balance:clone(balance),itemData:clone(itemData),
    items:Object.fromEntries(itemData.items.map(x=>[x.id,clone(x)])),mode,absoluteGameMinute:absolute,
    dayIndex:supplyDay(absolute),remainingDaySlots:options.remainingDaySlots??balance.day_action_slots,
    resources,coins:options.coins??balance.economy.starting_coins,staminaMax:0,worldSeconds:options.worldSeconds??0,
    lastExertionWorldSeconds:options.lastExertionWorldSeconds??-balance.resources.stamina.regen_delay_seconds,
    minorInjuryUntilWorldSeconds:options.minorInjuryUntilWorldSeconds??0,injuryIncidents:{},
    preparationUsedMinutes:0,inventory,coffeeDebts:clone(options.coffeeDebts??[]),dailySupplyClaims:clone(options.dailySupplyClaims??{}),
    itemUseCounts:{},commandReceipts:{},sequence:0,ledger:[],night:mode==='night'?{id:options.nightId??'night-1',budget:nightBudget,startAbsoluteGameMinute:absolute-nightBudget/2}:null,
    knowledge:createDayKnowledgeState(balance,{initialEnergy:resources.energy,availableSlots:options.remainingDaySlots??balance.day_action_slots,
      dayId:`${options.runId??'resource-run'}:day:${supplyDay(absolute)}`,unlockedPageIds:options.unlockedPageIds??[],sourceRecords:options.sourceRecords??[]})};
  if(!Number.isInteger(s.remainingDaySlots)||s.remainingDaySlots<0||s.remainingDaySlots>6||!finite(s.coins)||s.coins<0)throw new Error('Invalid resource initialization');
  syncCaps(s);settleDebts(s);return s;
}

export function createPracticeNightState(dayState,{practiceId='practice',initialBudget=0}={}) {
  if(!named(practiceId)||!finite(initialBudget)||initialBudget<0||initialBudget>=720)throw new Error('Invalid practice clock');
  const s=clone(dayState);s.mode='practice_night';s.practice=true;s.practiceSourceRunId=dayState.runId;
  s.runId=`${dayState.runId}:${practiceId}`;
  s.night={id:practiceId,budget:initialBudget,startAbsoluteGameMinute:s.absoluteGameMinute-initialBudget/2,officialSettlementAllowed:false};
  append(s,'practice_forked',{sourceRunId:dayState.runId,sourceAbsoluteGameMinute:dayState.absoluteGameMinute});return s;
}

export function completeDayAction(s,{commandId,actionId,pageId,claimId=null,sourceRecordIds,noiseChoice=null,noiseEventId=null,studyRestAvailable=false}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(s.mode!=='day')return no('not_in_six_day_slots');
  const action=s.balance.day_actions.find(x=>x.id===actionId);
  if(!action||action.enabled===false||action.selectable===false)return no('day_action_unavailable');
  if(!['A01','A02','A03','A04','A05','A09'].includes(actionId))return no('actual_target_adapter_required');
  if(s.remainingDaySlots<1||period(s.absoluteGameMinute)+120>1200+EPS)return no('no_complete_day_slot');
  if(noiseChoice!==null&&(actionId!=='A01'||!['home','quiet'].includes(noiseChoice)||!named(noiseEventId)))return no('invalid_noise_sleep_choice');
  if(noiseChoice==='quiet'&&(!studyRestAvailable||s.coins<10))return no('quiet_place_or_payment_unavailable');
  if(noiseEventId&&s.commandReceipts[`noise:${noiseEventId}`])return no('noise_event_already_used');
  const d=clone(s);const before=clone(d.resources),start=d.absoluteGameMinute;
  advanceDayMinutes(d,120,{sleeping:actionId==='A01'});
  d.knowledge.energy=d.resources.energy;d.knowledge.remainingSlots=s.remainingDaySlots;
  let knowledgeResult=null;
  if(actionId==='A03')knowledgeResult=settleStudyAction(d.knowledge,{actionId:commandId,pageId});
  else if(actionId==='A04')knowledgeResult=settleCaseReview(d.knowledge,{actionId:commandId,claimId,sourceRecordIds});
  if(knowledgeResult&&!knowledgeResult.ok)return knowledgeResult;
  if(knowledgeResult)d.resources.energy=d.knowledge.energy;
  else {
    const energy=noiseChoice==='home'?8:(action.energy_delta??0),san=noiseChoice==='home'?0:(action.san_delta??0);
    delta(d,{energy,san});d.coins+=action.coins_delta??0;
  }
  if(noiseChoice==='quiet')d.coins-=10;
  d.remainingDaySlots=s.remainingDaySlots-1;d.knowledge.remainingSlots=d.remainingDaySlots;d.knowledge.energy=d.resources.energy;
  syncCaps(d);
  const result=commitCommand(d,commandId,'day_action_completed',{actionId,fromAbsoluteGameMinute:start,
    actualResourceDeltas:Object.fromEntries(Object.keys(before).map(k=>[k,d.resources[k]-before[k]])),
    noiseChoice,noiseEventId,knowledgeResult:knowledgeResult?clone(knowledgeResult):null});
  if(noiseEventId)d.commandReceipts[`noise:${noiseEventId}`]=result.receipt.id;
  commitClone(s,d);return result;
}

export function finishMorning(s,{commandId}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(s.mode!=='morning')return no('not_morning');
  advanceDayMinutes(s,480-period(s.absoluteGameMinute));return commitCommand(s,commandId,'morning_completed');
}
export function advancePreparation(s,{commandId,minutes}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(s.mode!=='preparation'||!finite(minutes)||minutes<=0||s.preparationUsedMinutes+minutes>60+EPS)return no('preparation_optional_budget_unavailable');
  if(period(s.absoluteGameMinute)+minutes>1260+EPS)return no('basic_preparation_minutes_reserved');
  s.preparationUsedMinutes+=minutes;advanceDayMinutes(s,minutes);return commitCommand(s,commandId,'optional_preparation_completed',{minutes});
}
export function finishPreparation(s,{commandId}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(s.mode!=='preparation')return no('not_preparation');
  advanceDayMinutes(s,1320-period(s.absoluteGameMinute));return commitCommand(s,commandId,'preparation_completed');
}
export function completeCommute(s,{commandId}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(s.mode!=='commute')return no('not_commute');
  advanceDayMinutes(s,1440-period(s.absoluteGameMinute));return commitCommand(s,commandId,'commute_completed');
}
export function beginNight(s,{nightId}={}) {
  if(s.mode!=='night_ready'||Math.abs(period(s.absoluteGameMinute))>EPS||!named(nightId)||s.remainingDaySlots!==0)return no('night_not_ready');
  if(s.commandReceipts[`night:${nightId}`])return no('night_already_started');
  s.mode='night';s.night={id:nightId,budget:0,startAbsoluteGameMinute:s.absoluteGameMinute,officialSettlementAllowed:true};
  s.minorInjuryUntilWorldSeconds=s.worldSeconds;s.injuryIncidents={};
  s.lastExertionWorldSeconds=s.worldSeconds-s.balance.resources.stamina.regen_delay_seconds;
  s.commandReceipts[`night:${nightId}`]=append(s,'night_started',{nightId}).id;
  return {ok:true,normalPanicRequired:s.resources.san===0};
}

function nightPassive(s,budgetSeconds) {
  const r=s.balance.resources;
  return delta(s,{energy:-r.energy.night_hour_drain*budgetSeconds/120,satiety:-r.satiety.awake_hour_drain*budgetSeconds/120});
}
export function staminaRegenRate(s,{energy=s.resources.energy,satiety=s.resources.satiety,worldSeconds=s.worldSeconds}={}) {
  const p=s.balance.resources.stamina;
  let rate=p.base_regen_per_world_second;
  if(energy<p.low_energy_threshold)rate*=p.low_energy_regen_multiplier;
  if(satiety<p.low_satiety_threshold)rate*=p.low_satiety_regen_multiplier;
  if(worldSeconds<s.minorInjuryUntilWorldSeconds)rate*=0.85;
  return Math.max(p.minimum_regen_per_second,rate);
}
export function spendStamina(s,{commandId,amount}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(!['night','practice_night'].includes(s.mode)||!finite(amount)||amount<=0||s.resources.stamina+EPS<amount)return no('stamina_action_unavailable');
  delta(s,{stamina:-amount});s.lastExertionWorldSeconds=s.worldSeconds;
  return commitCommand(s,commandId,'stamina_spent',{amount,actionCostIsSuppliedByWorldAdapter:true});
}
export function recordMinorInjury(s,{incidentId}={}) {
  if(!['night','practice_night'].includes(s.mode)||!named(incidentId)||s.injuryIncidents[incidentId])return no('injury_incident_invalid_or_duplicate');
  s.injuryIncidents[incidentId]=true;s.minorInjuryUntilWorldSeconds=Math.max(s.minorInjuryUntilWorldSeconds,s.worldSeconds+30);
  return {ok:true,receipt:append(s,'minor_injury_recorded',{incidentId,expiresAtWorld:s.minorInjuryUntilWorldSeconds})};
}
export function advanceNightResources(s,{worldSeconds=0,budgetCost=0,paused=false,exerting=false}={}) {
  if(!['night','practice_night'].includes(s.mode))return no('night_resource_clock_inactive');
  if(!finite(worldSeconds)||!finite(budgetCost)||worldSeconds<0||budgetCost<0||worldSeconds>0&&budgetCost>0)return no('separate_world_and_precision_clock_steps_required');
  if(paused)return {ok:true,actualWorldSeconds:0,actualBudgetCost:0,events:[],normalPanicRequired:s.resources.san===0};
  if(budgetCost>720-s.night.budget+EPS)return no('precision_cost_passes_six');
  const logStart=s.ledger.length,startWorld=s.worldSeconds,startBudget=s.night.budget;
  const target=Math.min(worldSeconds||budgetCost,720-s.night.budget);let left=target;
  settleDebts(s);
  while(left>EPS) {
    let step=left;
    step=Math.min(step,(nextDebtMinute(s)-s.absoluteGameMinute)*2);
    if(worldSeconds>0) {
      const p=s.balance.resources.stamina,delayAt=s.lastExertionWorldSeconds+p.regen_delay_seconds;
      if(delayAt>s.worldSeconds+EPS)step=Math.min(step,delayAt-s.worldSeconds);
      if(s.minorInjuryUntilWorldSeconds>s.worldSeconds+EPS)step=Math.min(step,s.minorInjuryUntilWorldSeconds-s.worldSeconds);
      for(const [key,threshold,drain] of [['energy',p.low_energy_threshold,s.balance.resources.energy.night_hour_drain],['satiety',p.low_satiety_threshold,s.balance.resources.satiety.awake_hour_drain]]) {
        if(s.resources[key]>threshold+EPS)step=Math.min(step,(s.resources[key]-threshold)*120/drain);
      }
    }
    if(step<=EPS){settleDebts(s);step=Math.min(left,EPS*4);}
    const midEnergy=s.resources.energy-s.balance.resources.energy.night_hour_drain*step/240;
    const midSatiety=s.resources.satiety-s.balance.resources.satiety.awake_hour_drain*step/240;
    const regenAllowed=worldSeconds>0&&!exerting&&s.worldSeconds+EPS>=s.lastExertionWorldSeconds+s.balance.resources.stamina.regen_delay_seconds;
    const regen=regenAllowed?staminaRegenRate(s,{energy:midEnergy,satiety:midSatiety,worldSeconds:s.worldSeconds+step/2})*step:0;
    nightPassive(s,step);if(regen>0)delta(s,{stamina:regen});
    s.absoluteGameMinute+=step/2;s.night.budget+=step;
    if(worldSeconds>0){s.worldSeconds+=step;if(exerting)s.lastExertionWorldSeconds=s.worldSeconds;}
    left-=step;settleDebts(s);
  }
  return {ok:true,actualWorldSeconds:s.worldSeconds-startWorld,actualBudgetCost:budgetCost>0?s.night.budget-startBudget:0,
    events:clone(s.ledger.slice(logStart)),normalPanicRequired:s.resources.san===0,atTrueSix:s.night.budget>=720-EPS};
}

export function finishNight(s,{outcome,handoverReceipt=null}={}) {
  if(!['night','practice_night'].includes(s.mode)||!['complete','failed'].includes(outcome))return no('night_outcome_unavailable');
  if(outcome==='complete'&&s.night.budget<720-EPS)return no('not_true_six');
  const practice=s.mode==='practice_night';
  if(!practice&&outcome==='complete'&&(!handoverReceipt||!named(handoverReceipt.id)||handoverReceipt.nightId!==s.night.id||
    handoverReceipt.committed!==true||handoverReceipt.verified!==true||handoverReceipt.settlementMode!=='handover_only'||
    handoverReceipt.panicActive!==false||s.resources.san<=0))return no('actual_verified_handover_required');
  s.mode=practice?'practice_done':outcome==='failed'?'failed':'morning';
  const verifiedHandoverReceiptId=!practice&&outcome==='complete'?handoverReceipt.id:null;
  append(s,'night_resources_finished',{outcome,practice,verifiedHandoverReceiptId,wageAwarded:0,ticketsAwarded:0});
  refreshCalendar(s);return {ok:true,officialRewardGranted:false,verifiedHandoverReceiptId};
}

export function finishPractice(s,{reason='encounter_resolved'}={}) {
  if(s.mode!=='practice_night'||!['encounter_resolved','withdrawn','failed'].includes(reason))return no('practice_finish_unavailable');
  s.mode='practice_done';return {ok:true,receipt:append(s,'practice_finished',{reason,wageAwarded:0,ticketsAwarded:0}),officialRewardGranted:false};
}

export function claimDailyJobFood(s,{commandId}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(['failed','practice_done'].includes(s.mode))return no('no_active_supply_access');
  if(['night','practice_night'].includes(s.mode)&&s.night.budget>=720-EPS)return no('six_am_world_work_closed');
  const day=supplyDay(s.absoluteGameMinute),key=`day:${day}`;
  if(s.dailySupplyClaims[key])return no('daily_bundle_already_claimed');
  const bundle=s.itemData.job_supply.daily_free_food,ids=[];
  for(const row of bundle.items)for(let i=0;i<row.quantity;i++) {
    const id=`${s.runId}:food:${day}:${row.item_id}:${i}`;
    if(s.inventory[id])return no('daily_food_instance_collision');
    ids.push(id);
  }
  let n=0;for(const row of bundle.items)for(let i=0;i<row.quantity;i++) {
    const id=ids[n++];s.inventory[id]={id,itemId:row.item_id,foodStatus:'personal_verified',owned:true,consumed:false,location:'job_supply_locker',origin:'daily_job_supply'};
  }
  const result=commitCommand(s,commandId,'daily_job_food_claimed',{dayIndex:day,itemInstanceIds:ids});s.dailySupplyClaims[key]=result.receipt.id;return result;
}

export function purchasePersonalItem(s,{commandId,itemId}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  const item=s.items[itemId];
  if(s.mode!=='preparation'||!item||!item.acquisition_enabled||!item.shop_enabled||!finite(item.shop_price)||item.shop_price<0)return no('shop_item_unavailable');
  if(!['I01','I02','I03','I04','I05','I13','I14'].includes(itemId))return no('item_effect_adapter_not_available');
  if(s.coins<item.shop_price)return no('insufficient_coins');
  const id=`${s.runId}:purchase:${commandId}`;if(s.inventory[id])return no('purchase_instance_exists');
  s.coins-=item.shop_price;s.inventory[id]={id,itemId,foodStatus:'personal_verified',owned:true,consumed:false,location:'personal_inventory',origin:'paid_shop',paidPrice:item.shop_price};
  return commitCommand(s,commandId,'personal_item_purchased',{itemId,itemInstanceId:id,paidPrice:item.shop_price});
}

export function consumePersonalItem(s,{commandId,itemInstanceId,encounterId=null,safeStation=false,activeChase=false,actualUseWorldSeconds=0}={}) {
  const guard=commandGuard(s,commandId);if(guard)return guard;
  if(['failed','practice_done'].includes(s.mode))return no('item_use_mode_inactive');
  if(['night','practice_night'].includes(s.mode)&&s.night.budget>=720-EPS)return no('six_am_recovery_closed');
  const instance=s.inventory[itemInstanceId],item=instance&&s.items[instance.itemId];
  if(!item||instance.owned!==true||instance.consumed||instance.foodStatus!=='personal_verified'||instance.reservedBy)return no('actual_verified_unreserved_item_required');
  if(!['I01','I02','I03','I04','I05','I13','I14'].includes(item.id)||!item.resource_deltas)return no('personal_resource_effect_not_declared');
  if(['I13','I14'].includes(item.id)&&(!safeStation||activeChase))return no('safe_station_required');
  if(item.id==='I13'&&(!finite(actualUseWorldSeconds)||actualUseWorldSeconds<3))return no('actual_three_second_tea_action_required');
  if(encounterId!==null&&!named(encounterId))return no('invalid_encounter_id');
  const limitKey=encounterId===null?null:`${encounterId}:${item.id}`;
  if(item.id==='I04'&&limitKey&&(s.itemUseCounts[limitKey]??0)>=2)return no('mint_encounter_limit');
  const effect=item.resource_deltas;
  if(Object.entries(effect).some(([k,v])=>!['energy','san','satiety','stamina'].includes(k)||!finite(v)))return no('invalid_declared_resource_effect');
  let delayed=null;
  if(item.id==='I05') {
    delayed=item.delayed_effect;
    if(!delayed||delayed.delay_game_minutes!==60||!delayed.resource_deltas||delayed.resource_deltas.energy!==-8||delayed.resource_deltas.san!==-2)return no('coffee_debt_contract_missing');
  }
  instance.consumed=true;
  const actualResourceDeltas=delta(s,effect);
  if(limitKey)s.itemUseCounts[limitKey]=(s.itemUseCounts[limitKey]??0)+1;
  let debtId=null;
  if(delayed) {
    debtId=`${s.runId}:coffee:${itemInstanceId}`;
    s.coffeeDebts.push({id:debtId,itemInstanceId,createdAbsoluteGameMinute:s.absoluteGameMinute,dueAbsoluteGameMinute:s.absoluteGameMinute+60,
      resourceDeltas:clone(delayed.resource_deltas),settled:false});
  }
  return commitCommand(s,commandId,'personal_item_consumed',{itemInstanceId,itemId:item.id,actualResourceDeltas,debtId});
}

export function serializeDayCycle(s) {return JSON.stringify(s);}
export function restoreDayCycle(serialized) {
  const s=JSON.parse(serialized);
  if(s.schemaVersion!==9||!s.balance||!s.items||!s.knowledge||!finite(s.absoluteGameMinute)||!Array.isArray(s.coffeeDebts)||!s.dailySupplyClaims)throw new Error('Invalid day-cycle save');
  if(Object.values(s.resources??{}).some(x=>!finite(x))||!['energy','san','satiety','stamina'].every(k=>finite(s.resources?.[k])))throw new Error('Invalid saved resources');
  if(new Set(s.coffeeDebts.map(x=>x.id)).size!==s.coffeeDebts.length||s.coffeeDebts.some(x=>!named(x.id)||!finite(x.dueAbsoluteGameMinute)))throw new Error('Invalid saved debt ledger');
  syncCaps(s);settleDebts(s);return s;
}
