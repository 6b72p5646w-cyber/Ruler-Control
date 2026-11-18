/** A complete, isolated F12/F13 exercise. It cannot pay official campaign rewards. */
import * as World from './world_core_v09.mjs';
import * as Cycle from './day_cycle_core_v09.mjs';
import * as Condition from './condition_core_v06.mjs';

const no=reason=>({ok:false,reason});
const copy=x=>JSON.parse(JSON.stringify(x));
function syncSan(s) {
  s.resources.resources.san=s.condition.san;
  World.setWorldResources(s.world,{san:s.condition.san});
}
function actualSan(s,receiptId,delta,sourceKind) {
  if(Math.abs(delta)<1e-10)return {ok:true,actualDelta:0};
  const result=Condition.commitConditionSanDelta(s.condition,{receiptId,delta,sourceKind});
  if(!result.ok)throw new Error(`Uncommitted actual SAN effect: ${result.reason}`);
  syncSan(s);return result;
}
export function createPracticeSession(data,dayState,{caseId='F12',runId='practice',paused=true,worldOptions={}}={}) {
  if(!data.integration.practice.encounter_ids.includes(caseId))throw new Error('Unsupported exercise');
  const resources=Cycle.createPracticeNightState(dayState,{practiceId:runId,initialBudget:0});
  const condition=Condition.createConditionState(data.condition,{balance:data.balance,initialSan:resources.resources.san});
  const world=World.createWorldState({maps:data.maps,blueprints:data.blueprints,mechanics:data.mechanics,
    interactions:data.interactions,...worldOptions,encounterId:caseId,instanceId:runId,initialSan:condition.san});
  const s={version:9,runId,caseId,resources,condition,world,paused:false,status:world.admission.ok?'active':'unavailable',
    budgetLimit:data.integration.practice.budget_seconds_per_practice,events:[],sequence:0,minorInjuryApplied:false,
    officialRewardGranted:false,terminalReceipt:null};
  setPracticePaused(s,paused);return s;
}
export function setPracticePaused(s,paused) {
  s.paused=Boolean(paused);World.setWorldPaused(s.world,s.paused);Condition.setConditionPause(s.condition,s.paused);
  if(s.paused){s.world.player.direction={x:0,y:0};s.world.player.path=[];}
  return {ok:true,paused:s.paused};
}
export function movePracticeTo(s,point) {
  if(s.status!=='active')return no('exercise_finished');return World.setWorldMoveTarget(s.world,point);
}
export function directPracticeMovement(s,direction) {
  if(s.status!=='active')return no('exercise_finished');return World.setWorldDirection(s.world,direction);
}
export function setPracticeFacingLock(s,locked){return World.setWorldFacingLock(s.world,locked);}
export function startPracticeAction(s,command) {
  if(s.status!=='active'||s.paused)return no('exercise_not_running');
  const result=World.beginWorldAction(s.world,command);
  if(result.ok)Condition.interruptPortableStabilization(s.condition,'actual_world_work');
  return result;
}
export function cancelPracticeAction(s) {return World.cancelWorldAction(s.world);}
export function startPracticeStabilization(s) {
  if(s.status!=='active'||s.paused)return no('exercise_not_running');
  if(s.world.action)return no('actual_world_action_in_progress');
  return Condition.beginPortableStabilization(s.condition);
}
export function usePracticeItem(s,itemInstanceId) {
  if(s.status!=='active'||s.paused||s.world.action)return no('exercise_not_available_for_item');
  // This quick-use adapter exposes only instantaneous, already-verified supplies.
  const item=s.resources.inventory[itemInstanceId];
  if(!item||!['I01','I02','I03','I04','I05'].includes(item.itemId))return no('item_needs_its_own_safe_world_action');
  const result=Cycle.consumePersonalItem(s.resources,{commandId:`${s.runId}:use:${++s.sequence}`,itemInstanceId,
    encounterId:s.world.instanceId,activeChase:s.world.monster.state.mode==='CHASE_PLAYER'});
  if(!result.ok)return result;
  Condition.interruptPortableStabilization(s.condition,'actual_item_use');
  actualSan(s,result.receipt.id,result.receipt.actualResourceDeltas.san,'verified_item');
  s.events.push({type:'personal_item_used',itemId:item.itemId,at:s.world.now,receiptId:result.receipt.id});
  return result;
}
function endPractice(s,status,reason) {
  if(s.status!=='active')return;
  s.status=status;s.paused=true;s.terminalReceipt={id:`${s.runId}:terminal`,caseId:s.caseId,status,reason,
    worldSeconds:s.world.now,budgetSeconds:s.condition.budget,san:s.condition.san,officialRewardGranted:false};
  Cycle.finishPractice(s.resources,{reason:status==='cleared'?'encounter_resolved':'failed'});
  World.setWorldPaused(s.world,true);Condition.setConditionPause(s.condition,true);
}
export function advancePractice(s,seconds) {
  if(!Number.isFinite(seconds)||seconds<0||seconds>10)throw new RangeError('Practice advance must be 0..10 seconds');
  if(s.paused||s.status!=='active')return {ok:true,advancedSeconds:0,actualMovedTiles:0,events:[]};
  let left=seconds,advanced=0,moved=0;const start=s.events.length;
  while(left>1e-8&&s.status==='active') {
    let dt=Math.min(left,.05,s.budgetLimit-s.condition.budget);
    if(dt<=1e-8){endPractice(s,'failed','practice_budget_exhausted');break;}
    // The condition clock bounds this step. Its portable stabilization is a
    // completed player action, so it resolves before this endpoint's AI hit.
    const time=Condition.advanceConditionWorld(s.condition,dt);dt=time.advanced;
    if(dt<=1e-8){endPractice(s,'failed','panic_or_terminal_condition');break;}
    syncSan(s);
    const frame=World.advanceWorld(s.world,dt);moved+=frame.actualMovedTiles;
    for(const event of frame.events) {
      s.events.push(copy(event));
      if(event.type==='hit'&&s.condition.mode==='night') {
        Condition.interruptPortableStabilization(s.condition,'actual_hit');
        actualSan(s,`${s.runId}:${event.id}`,event.sanDelta,'actual_hit');
      }
    }
    // No natural SAN regeneration exists; only actual dated debt events may
    // change SAN here. All other resources advance on the same elapsed slice.
    const resources=Cycle.advanceNightResources(s.resources,{worldSeconds:dt,budgetCost:0,paused:false,exerting:false});
    if(!resources.ok)throw new Error(resources.reason);
    for(const event of resources.events) {
      if(event.type==='coffee_debt_settled') {
        if(s.condition.mode==='night')actualSan(s,event.id,event.actualResourceDeltas.san,'coffee_due');
        s.events.push({type:'coffee_debt_settled',at:s.world.now,receiptId:event.id});
      }
    }
    if(!s.minorInjuryApplied&&frame.events.some(e=>e.type==='hit')) {
      Cycle.recordMinorInjury(s.resources,{incidentId:`${s.runId}:first_actual_hit`});s.minorInjuryApplied=true;
    }
    syncSan(s);advanced+=dt;left-=dt;
    if(s.condition.mode==='failed_shift')endPractice(s,'failed','panic_expired');
    else if(s.world.status==='cleared'&&!s.condition.panic.active)endPractice(s,'cleared','actual_objective_and_safe_state');
    else if(s.condition.budget>=s.budgetLimit-1e-8)endPractice(s,'failed','practice_budget_exhausted');
  }
  return {ok:true,advancedSeconds:advanced,actualMovedTiles:moved,events:s.events.slice(start)};
}
export function practiceSnapshot(s) {
  return {caseId:s.caseId,status:s.status,paused:s.paused,world:s.world.now,budget:s.condition.budget,
    remaining:Math.max(0,s.budgetLimit-s.condition.budget),resources:copy(s.resources.resources),
    panic:copy(s.condition.panic),player:copy(s.world.player),monsterMode:s.world.monster.state.mode,
    terminalReceipt:copy(s.terminalReceipt),officialRewardGranted:false};
}
