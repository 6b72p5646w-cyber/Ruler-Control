import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import * as Session from './practice_session_core_v09.mjs';
import * as Cycle from './day_cycle_core_v09.mjs';

const read=n=>JSON.parse(readFileSync(fileURLToPath(new URL(`../content/${n}.json`,import.meta.url)),'utf8'));
const data={maps:read('maps'),blueprints:read('encounter_blueprints'),mechanics:read('map_mechanics_v05'),
  interactions:read('interactions'),condition:read('condition_lifecycle_v06'),balance:read('balance'),items:read('items'),integration:read('integration_v09')};
const coffeeSpec=data.items.items.find(x=>x.id==='I05'),mintSpec=data.items.items.find(x=>x.id==='I04');
const stabilizationSan=data.balance.resources.san.emergency_stabilization_target_san??data.balance.resources.san.safe_zone_stabilization_target_san;
const results=[],witnesses=[];let serial=0;
const test=(name,fn)=>{try{fn();results.push({name,status:'PASS'});}catch(error){results.push({name,status:'FAIL',error:error.message});}};
const must=r=>{assert.equal(r.ok,true,r.reason??JSON.stringify(r));return r;};
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} differs from ${b}`);
const bag=(id,itemId,extra={})=>({id,itemId,owned:true,consumed:false,foodStatus:'personal_verified',...extra});
const day=options=>Cycle.createDayCycleState(data.balance,data.items,{runId:'source-day',...options});
function make(caseId='F12',dayOptions={},options={}) {
  const source=day(dayOptions),sourceBefore=JSON.stringify(source);
  return {source,sourceBefore,s:Session.createPracticeSession(data,source,{caseId,runId:`practice-test-${++serial}`,paused:false,...options})};
}
function aligned(s){near(s.condition.san,s.resources.resources.san);near(s.condition.san,s.world.player.san);near(s.condition.world,s.world.now);near(s.condition.budget,s.resources.night.budget);}
function advance(s,seconds){let left=seconds;while(left>1e-8){const dt=Math.min(.05,left);Session.advancePractice(s,dt);left-=dt;aligned(s);}}
function walk(s,target){const p=Array.isArray(target)?{x:target[0],y:target[1]}:target;must(Session.movePracticeTo(s,p));let n=0;while(Math.hypot(s.world.player.x-p.x,s.world.player.y-p.y)>.001&&n++<4000){assert.equal(s.status,'active','session ended before arrival');Session.advancePractice(s,.05);aligned(s);}assert.ok(n<4000,'world path failed to finish');}
function act(s,type,extra={}){const result=must(Session.startPracticeAction(s,{type,...extra}));advance(s,result.seconds);assert.equal(s.world.action,null);return result;}
function lure(s){walk(s,s.world.anchors.metal_shelf);act(s,'take_clips');for(const point of s.world.scene.lure_route.bait_points){walk(s,point);act(s,'scatter',{point});}for(let n=0;n<500&&s.status==='active';n++){Session.advancePractice(s,.05);aligned(s);}assert.equal(s.status,'cleared');}
function meat(s){walk(s,s.world.meat);act(s,'take_meat');walk(s,s.world.freezer);act(s,'store_meat');}
function coffeePrepared(minutes=54,resources={san:50,energy:40,satiety:80,stamina:70}) {
  const source=day({absoluteGameMinute:1200,remainingDaySlots:0,resources,inventory:[bag('paid-coffee','I05')]});
  must(Cycle.consumePersonalItem(source,{commandId:'actual-coffee-drink',itemInstanceId:'paid-coffee'}));
  must(Cycle.advancePreparation(source,{commandId:'actual-preparation-time',minutes}));return source;
}

test('Practice starts from an isolated day copy and keeps its declared case, SAN and unique instance authority',()=>{
  const source=day({resources:{san:23}});const s=Session.createPracticeSession(data,source,{caseId:'F12',runId:'owned-instance',paused:false,
    worldOptions:{encounterId:'F13',instanceId:'foreign-instance',initialSan:99}});
  assert.equal(s.world.encounterId,'F12');assert.equal(s.world.instanceId,'owned-instance');assert.equal(s.condition.san,23);aligned(s);
});
test('F12 completes through actual shelf pickup and four casts, consuming time and passive resources exactly once',()=>{
  const {s,source,sourceBefore}=make('F12',{resources:{energy:60,san:80,satiety:80,stamina:0}});lure(s);const t=s.world.now;
  near(s.resources.resources.energy,60-data.balance.resources.energy.night_hour_drain*t/120);
  near(s.resources.resources.satiety,80-data.balance.resources.satiety.awake_hour_drain*t/120);
  assert.equal(s.world.inventory.paperclipCharges,2);assert.equal(s.world.receipts.filter(r=>r.actionType==='scatter').length,4);
  assert.equal(s.world.receipts.filter(r=>r.type==='encounter_cleared').length,1);assert.equal(s.condition.panic.active,false);assert.equal(s.officialRewardGranted,false);
  assert.equal(JSON.stringify(source),sourceBefore);assert.equal(s.resources.mode,'practice_done');
  witnesses.push({id:'integrated_F12',seconds:t,san:s.condition.san,casts:4,remainingClips:2,officialRewardGranted:false});
});
test('F13 completes with the same actual carried crate and a closed functional registered freezer at zero stamina',()=>{
  const {s,source,sourceBefore}=make('F13',{resources:{energy:30,san:50,satiety:50,stamina:0}});meat(s);
  assert.equal(s.status,'cleared');assert.equal(s.world.meat.storedIn,s.world.freezer.id);assert.equal(s.world.freezer.closed,true);
  assert.equal(s.world.deliveryReceipts.length,1);assert.equal(s.world.deliveryReceipts[0].encounterInstanceId,s.runId);
  assert.equal(JSON.stringify(source),sourceBefore);aligned(s);
  witnesses.push({id:'integrated_F13',seconds:s.world.now,san:s.condition.san,sameMeat:s.world.meat.id,officialRewardGranted:false});
});
test('An actual enemy hit changes all SAN copies once and records only one first-hit minor injury',()=>{
  const {s}=make('F12',{resources:{san:80}});advance(s,7);
  const hits=s.events.filter(e=>e.type==='hit');assert.ok(hits.length>=1);near(s.condition.san,80+hits.reduce((n,h)=>n+h.sanDelta,0));aligned(s);
  assert.equal(s.resources.ledger.filter(e=>e.type==='minor_injury_recorded').length,1);
  const effects=Object.values(s.condition.sanEffectReceipts).filter(r=>r.sourceKind==='actual_hit');assert.equal(effects.length,hits.filter(h=>h.sanDelta!==0).length);
});
test('Paused action, pursuit, panic, coffee and resource clocks all remain frozen',()=>{
  const source=coffeePrepared(),s=Session.createPracticeSession(data,source,{caseId:'F12',runId:'pause-coffee',paused:false});
  walk(s,s.world.anchors.metal_shelf);must(Session.startPracticeAction(s,{type:'take_clips'}));advance(s,.3);Session.setPracticePaused(s,true);
  const before=JSON.stringify(s);const r=Session.advancePractice(s,10);assert.equal(r.advancedSeconds,0);assert.equal(JSON.stringify(s),before);
  assert.equal(Session.usePracticeItem(s,'paid-coffee').ok,false);assert.equal(Session.startPracticeStabilization(s).ok,false);
  Session.setPracticePaused(s,false);advance(s,.7);assert.equal(s.world.inventory.paperclipCharges,6);aligned(s);
});
test('A real preparation coffee debt crossing into a practice settles once at its actual due minute',()=>{
  const source=coffeePrepared(),before=JSON.stringify(source),s=Session.createPracticeSession(data,source,{caseId:'F12',runId:'coffee-boundary',paused:false});
  lure(s);assert.ok(s.world.now>(coffeeSpec.delayed_effect.delay_game_minutes-54)*data.integration.calendar.night_budget_seconds_per_game_minute);assert.equal(s.resources.coffeeDebts[0].settled,true);near(s.condition.san,50+coffeeSpec.delayed_effect.resource_deltas.san);aligned(s);
  assert.equal(s.resources.ledger.filter(e=>e.type==='coffee_debt_settled').length,1);assert.equal(s.events.filter(e=>e.type==='coffee_debt_settled').length,1);
  assert.equal(Object.values(s.condition.sanEffectReceipts).filter(e=>e.sourceKind==='coffee_due').length,1);
  const snap=JSON.stringify(s);Session.advancePractice(s,5);assert.equal(JSON.stringify(s),snap);assert.equal(JSON.stringify(source),before);
});
test('Initial zero SAN can stabilize while really walking, then finish F13 without an invented recovery receipt',()=>{
  const {s}=make('F13',{resources:{san:0,energy:50,satiety:50,stamina:0}});assert.equal(s.condition.panic.active,true);
  must(Session.startPracticeStabilization(s));must(Session.movePracticeTo(s,s.world.anchors.freezer_main));
  let distance=0;for(let i=0;i<160;i++){distance+=Session.advancePractice(s,.05).actualMovedTiles;aligned(s);}
  assert.ok(distance>5);assert.equal(s.condition.panic.active,false);assert.equal(s.condition.panic.used,true);near(s.condition.san,stabilizationSan);
  meat(s);assert.equal(s.status,'cleared');assert.ok(s.condition.san>0);assert.equal(s.terminalReceipt.reason,'actual_objective_and_safe_state');
});
test('Only actual started work interrupts portable stabilization; an invalid distant action does not',()=>{
  const {s}=make('F12',{resources:{san:0}});must(Session.startPracticeStabilization(s));advance(s,.2);
  assert.equal(Session.startPracticeAction(s,{type:'take_clips'}).ok,false);assert.equal(s.condition.panic.stabilizing,true);
  walk(s,s.world.anchors.metal_shelf);const progress=s.condition.panic.progress;must(Session.startPracticeAction(s,{type:'take_clips'}));
  assert.equal(s.condition.panic.stabilizing,false);near(s.condition.panic.progress,progress);advance(s,1);
  must(Session.startPracticeStabilization(s));assert.equal(s.condition.panic.stabilizing,true);near(s.condition.panic.progress,progress);
});
test('Zero SAN without a recovery ends at the real panic deadline and stops all modules at that instant',()=>{
  const {s,source,sourceBefore}=make('F12',{resources:{san:0}});advance(s,25);
  assert.equal(s.status,'failed');assert.equal(s.terminalReceipt.reason,'panic_expired');near(s.world.now,data.balance.resources.san.panic_window_seconds);aligned(s);
  assert.equal(s.condition.panic.episode,1);assert.equal(s.officialRewardGranted,false);assert.equal(JSON.stringify(source),sourceBefore);
  assert.equal(s.paused,true);const frozen=JSON.stringify(s);Session.advancePractice(s,10);assert.equal(JSON.stringify(s),frozen);
});
test('A real eight-second stabilization ending at the panic deadline succeeds without adding a hidden frame',()=>{
  const {s}=make('F12',{resources:{san:0}});walk(s,s.world.anchors.front_exit);advance(s,12-s.world.now);
  must(Session.startPracticeStabilization(s));advance(s,8);near(s.world.now,20);aligned(s);
  assert.equal(s.status,'active');assert.equal(s.condition.panic.active,false);assert.equal(s.condition.panic.used,true);near(s.condition.san,stabilizationSan);
});
test('Starting stabilization genuinely 0.01 seconds too late cannot borrow time beyond the panic deadline',()=>{
  const {s}=make('F12',{resources:{san:0}});walk(s,s.world.anchors.front_exit);advance(s,12.01-s.world.now);
  must(Session.startPracticeStabilization(s));advance(s,8);near(s.world.now,20);aligned(s);
  assert.equal(s.status,'failed');assert.equal(s.condition.panic.active,true);assert.equal(s.condition.panic.used,false);near(s.condition.san,0);
});
test('An actual verified mint restores all SAN copies once and cannot be consumed or credited twice',()=>{
  const {s,source,sourceBefore}=make('F13',{resources:{san:0},inventory:[bag('mint-1','I04'),bag('mint-2','I04'),bag('mint-3','I04')]});
  must(Session.usePracticeItem(s,'mint-1'));near(s.condition.san,mintSpec.resource_deltas.san);aligned(s);assert.equal(s.condition.panic.active,false);
  assert.equal(Session.usePracticeItem(s,'mint-1').ok,false);must(Session.usePracticeItem(s,'mint-2'));near(s.condition.san,mintSpec.resource_deltas.san*2);
  assert.equal(Session.usePracticeItem(s,'mint-3').ok,false);assert.equal(s.resources.inventory['mint-3'].consumed,false);assert.equal(JSON.stringify(source),sourceBefore);
});
test('Unknown food and supplies needing their own world action cannot be used as instant practice recovery',()=>{
  const {s}=make('F13',{inventory:[bag('unverified','I04',{foodStatus:'sealed_unverified'}),bag('tea','I13'),bag('bento','I14')]});
  for(const id of ['unverified','tea','bento'])assert.equal(Session.usePracticeItem(s,id).ok,false);
  assert.equal(s.resources.inventory.unverified.consumed,false);assert.equal(s.resources.inventory.tea.consumed,false);assert.equal(s.resources.inventory.bento.consumed,false);
});
test('Actual store completion at an attack endpoint wins before that same-frame hit is applied',()=>{
  const {s}=make('F13',{resources:{san:80}});
  for(let i=0;i<600&&s.world.monster.state.mode==='SEEK_MEAT';i++)Session.advancePractice(s,.05);
  advance(s,1.6);walk(s,s.world.meat);act(s,'take_meat');walk(s,s.world.freezer);
  for(let i=0;i<600&&s.world.monster.attack.mode!=='windup';i++)Session.advancePractice(s,.05);
  assert.equal(s.world.monster.attack.mode,'windup');const storeSeconds=s.world.blueprint.parameters.store_and_close_seconds;
  const wait=s.world.monster.attack.remaining-storeSeconds;assert.ok(wait>=-1e-8);advance(s,Math.max(0,wait));
  const hitsBefore=s.events.filter(e=>e.type==='hit').length,sanBefore=s.condition.san;act(s,'store_meat');
  assert.equal(s.status,'cleared');assert.equal(s.events.filter(e=>e.type==='hit').length,hitsBefore);near(s.condition.san,sanBefore);aligned(s);
  witnesses.push({id:'actual_store_before_same_endpoint_attack',seconds:s.world.now,san:s.condition.san,deliveryReceipts:s.world.deliveryReceipts.length});
});
test('Objective completion with newly due zero-SAN debt stays active until real stabilization finishes',()=>{
  const source=coffeePrepared(54,{san:1,energy:40,satiety:80,stamina:70});
  const s=Session.createPracticeSession(data,source,{caseId:'F13',runId:'objective-plus-panic',paused:false});
  advance(s,2.1);meat(s);near(s.world.now,12);assert.equal(s.world.status,'cleared');assert.equal(s.status,'active');assert.equal(s.condition.panic.active,true);near(s.condition.san,0);aligned(s);
  must(Session.startPracticeStabilization(s));advance(s,data.balance.resources.san.emergency_stabilization_seconds);assert.equal(s.status,'cleared');assert.equal(s.condition.panic.active,false);aligned(s);
  assert.equal(s.resources.ledger.filter(x=>x.type==='practice_finished').length,1);assert.equal(s.officialRewardGranted,false);
});
test('Completing, re-entering pause and repeated ticking never mints a second terminal result or campaign reward',()=>{
  const {s,source,sourceBefore}=make('F13');meat(s);const terminal=JSON.stringify(s.terminalReceipt),coins=s.resources.coins;
  assert.equal(Session.practiceSnapshot(s).paused,true);assert.equal(Session.movePracticeTo(s,s.world.anchors.front_door).ok,false);assert.equal(Session.startPracticeAction(s,{type:'store_meat'}).ok,false);
  for(let i=0;i<5;i++)Session.advancePractice(s,2);assert.equal(JSON.stringify(s.terminalReceipt),terminal);assert.equal(s.resources.coins,coins);
  assert.equal(s.resources.ledger.filter(x=>x.type==='practice_finished').length,1);assert.equal(s.world.receipts.filter(x=>x.type==='encounter_cleared').length,1);
  assert.equal(s.resources.ledger.some(x=>x.wageAwarded>0||x.ticketsAwarded>0),false);assert.equal(JSON.stringify(source),sourceBefore);
});
test('An unavailable world setup never advances any of the three clocks or consumes the day inventory',()=>{
  const {s,source,sourceBefore}=make('F12',{}, {worldOptions:{doors:{DOOR_FRONT:{open:false,operable:false}}}});
  assert.equal(s.status,'unavailable');const before=JSON.stringify(s);assert.equal(Session.advancePractice(s,5).advancedSeconds,0);assert.equal(JSON.stringify(s),before);assert.equal(JSON.stringify(source),sourceBefore);
});
test('Cancelling an actual store retains the original meat and cannot complete either the encounter or exercise',()=>{
  const {s}=make('F13');walk(s,s.world.meat);act(s,'take_meat');walk(s,s.world.freezer);must(Session.startPracticeAction(s,{type:'store_meat'}));advance(s,.2);must(Session.cancelPracticeAction(s));
  assert.equal(s.status,'active');assert.equal(s.world.meat.carrierId,'player');assert.equal(s.world.player.carriedId,s.world.meat.id);assert.equal(s.world.deliveryReceipts.length,0);
  act(s,'store_meat');assert.equal(s.status,'cleared');assert.equal(s.world.deliveryReceipts.length,1);
});

const errors=results.filter(x=>x.status==='FAIL');
console.log(JSON.stringify({status:errors.length?'FAIL':'PASS',scenarioCount:results.length,scenarios:results,witnesses,errors,
  scope:'Integrated isolated F12/F13 practice with actual world movement/actions, synchronized SAN and panic, exact dated resource debt and no campaign reward writes. Does not prove a full six-wave night, all monsters, mobile UI, production persistence or arbitrary simultaneous events.'},null,2));
process.exitCode=errors.length?1:0;
