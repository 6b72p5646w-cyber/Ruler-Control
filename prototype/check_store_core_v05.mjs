import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createStore,buyAssist,rechargeReserve,changeServiceMode,setGreeting,orderDuration,
  arriveOrder,customerEntered,beginService,finishService,advanceStore,recordLocalBreach,phaseEnd,clearDebt,
  gradeShift,publicEvidence,independentFactCount,admitEncounter} from './store_core_v05.mjs';
import {storeTaskMeat,stepF13} from './rule_core.mjs';

const config = JSON.parse(readFileSync(new URL('../content/store_systems_v05.json', import.meta.url)));
let tests = 0;
const check = (name, fn) => { fn(); tests++; process.stdout.write('PASS ' + name + '\n'); };

check('12-unit spending examples reconcile', () => {
  for (const row of config.emergency_power.budget_examples) {
    let state = createStore(config), counter = 0;
    for (const [id,count] of Object.entries(row.uses)) {
      for (let n=0;n<count;n++) {
        const result = buyAssist(state,config,id,'cost:'+counter++);
        assert.equal(result.ok,true); state=result.state;
      }
    }
    assert.equal(state.reserve,12-row.total_units);
    assert.equal(buyAssist(state,config,'snapshot','one-too-many').ok,false);
  }
});

check('power transactions commit once and pause produces no benefit', () => {
  const one=buyAssist(createStore(config),config,'snapshot','snap1');
  assert.equal(one.state.reserve,11);
  assert.equal(buyAssist(one.state,config,'snapshot','snap1').state.reserve,11);
  const paused=buyAssist(one.state,config,'snapshot','snap2',{paused:true});
  assert.equal(paused.reason,'world_paused'); assert.equal(paused.state.reserve,11);
});

check('battery cannot recharge both lamp and reserve or twice per night', () => {
  const s={...createStore(config),reserve:10};
  assert.equal(rechargeReserve(s,config,'b1',{batteryAvailable:true,usedForLamp:true}).ok,false);
  const r=rechargeReserve(s,config,'b1',{batteryAvailable:true});
  assert.equal(r.state.reserve,12); assert.equal(r.consumedBatteryId,'b1');
  assert.equal(rechargeReserve({...r.state,reserve:4},config,'b2',{batteryAvailable:true}).ok,false);
});

check('shutter cannot block required exit; free manual mode remains at zero reserve', () => {
  const s=createStore(config);
  const rejected=changeServiceMode(s,config,'shutter','brace',{blocksRequiredExit:true});
  assert.equal(rejected.reason,'required_exit'); assert.equal(rejected.state.reserve,12);
  const empty={...s,reserve:0};
  assert.equal(changeServiceMode(empty,config,'window','manual').ok,true);
  assert.equal(changeServiceMode(empty,config,'shutter','powered').ok,false);
});

check('shutter expires on world clock and does not resolve an admitted monster', () => {
  const s=createStore(config);s.encounters['F12:1']={episodes:0,active:true};
  const r=changeServiceMode(s,config,'shutter','brace').state;
  assert.equal(r.reserve,10);
  assert.equal(advanceStore(r,config,99,{paused:true}).mode,'shutter');
  const after=advanceStore(r,config,12);
  assert.equal(after.mode,'window');assert.deepEqual(after.encounters,s.encounters);
});

check('quiet greeting and window cost one manual confirmation, not two', () => {
  const s=createStore(config);assert.equal(orderDuration(s,config),1.5);
  const quiet=setGreeting(s,config,'silent');assert.equal(orderDuration(quiet,config),3.5);
  const window=changeServiceMode(quiet,config,'window','manual').state;
  assert.equal(orderDuration(window,config),3.5);
  assert.equal(setGreeting(s,config,'silent',{paused:true}).greeting,'voice');
});

check('changing service mode or greeting cancels work without resetting patience', () => {
  let s=arriveOrder(createStore(config),config,'c1');
  s=beginService(s,config,'c1').state;s=advanceStore(s,config,1);
  s=changeServiceMode(s,config,'window','switch').state;
  assert.equal(s.orders[0].status,'waiting');assert.equal(s.orders[0].expiresAt,24);
  assert.equal(finishService(advanceStore(s,config,.5),'c1').ok,false);
  const begun=beginService(s,config,'c1');assert.equal(begun.duration,3.5);
  const shutter=changeServiceMode(begun.state,config,'shutter','brace').state;
  const after=advanceStore(shutter,config,12);
  assert.equal(after.orders[0].status,'waiting');assert.equal(finishService(after,'c1').ok,false);
  const again=beginService(after,config,'c1').state;
  assert.equal(setGreeting(again,config,'silent').orders[0].status,'waiting');
});

check('mode toggling never resets waiting customer patience', () => {
  let s=arriveOrder(createStore(config),config,'c1');
  s=advanceStore(s,config,20);s=changeServiceMode(s,config,'window','toggle').state;
  assert.equal(s.orders[0].expiresAt,24);
  s=changeServiceMode(s,config,'open','toggle2').state;
  assert.equal(advanceStore(s,config,5).orders[0].status,'lost');
});

check('orders need actual world service and settle once', () => {
  let s=arriveOrder(createStore(config),config,'c1');
  s=beginService(s,config,'c1').state;
  assert.equal(finishService(s,'c1').ok,false);
  assert.equal(finishService(advanceStore(s,config,10,{paused:true}),'c1').ok,false);
  const done=finishService(advanceStore(s,config,1.5),'c1');
  assert.equal(done.ok,true);assert.equal(finishService(done.state,'c1').ok,false);
});

check('browse orders require observed entry; a permanently closed shop cannot take every order', () => {
  let s=changeServiceMode(createStore(config),config,'window','window').state;
  s=arriveOrder(s,config,'browse',{requiresEntry:true});
  assert.equal(beginService(s,config,'browse').reason,'needs_physical_entry');
  assert.equal(customerEntered(s,'browse',{crossedDoor:true}).ok,false);
  s=changeServiceMode(s,config,'open','open').state;
  assert.equal(customerEntered(s,'browse',{crossedDoor:false}).ok,false);
  s=customerEntered(s,'browse',{crossedDoor:true}).state;
  s=changeServiceMode(s,config,'window','close').state;
  assert.equal(beginService(s,config,'browse').ok,true);
  assert.equal(config.service.base_order_mix.pickup_per_night,6);
  assert.equal(config.service.base_order_mix.browse_per_night,6);
  assert.ok(config.completion.order_target_for_top_grade > config.service.base_order_mix.pickup_per_night);
});

check('one continuous violation is one episode; different monsters do not share strikes', () => {
  let s=createStore(config);
  for(let n=0;n<120;n++)s=recordLocalBreach(s,'F60:1',true).state;
  assert.equal(s.encounters['F60:1'].episodes,1);
  const other=recordLocalBreach(s,'F07:1',true);
  assert.equal(other.reaction,'first_warning');
  s=recordLocalBreach(s,'F60:1',false).state;
  const repeat=recordLocalBreach(s,'F60:1',true);
  assert.equal(repeat.reaction,'local_consequence');
  assert.equal(repeat.state.criticalBreach,false);
});

check('work debt stays at one and total wage deduction at 20', () => {
  let s=createStore(config);
  for(let phase=0;phase<6;phase++){
    s=phaseEnd(s,config,phase,'D0'+(phase+1));
    assert.ok(s.debts.length<=1);assert.ok(s.debtDeduction<=20);
  }
  assert.equal(s.debts.length,0);assert.equal(s.debtDeduction,20);
  assert.equal(phaseEnd(s,config,5,'D06').debtDeduction,20);
});

check('clearing a debt avoids deduction and cannot reproduce it', () => {
  let s=phaseEnd(createStore(config),config,0,'D01');s=clearDebt(s,'D01');
  s=phaseEnd(s,config,0,'D01');assert.equal(s.debts.length,0);
  s=phaseEnd(s,config,1);assert.equal(s.debtDeduction,0);
});

check('low orders reduce grade and rewards, not safe shift completion', () => {
  const outcome={trueGameMinutes:360,verifiedHandover:true,completedDuties:2};
  const grade=gradeShift(createStore(config),config,outcome);
  assert.equal(grade.complete,true);assert.equal(grade.grade,'C');assert.equal(grade.ticket,false);
  assert.equal(gradeShift(createStore(config),config,{...outcome,unresolvedCriticalThreat:true}).complete,false);
  assert.equal(gradeShift(createStore(config),config,{...outcome,trueGameMinutes:359}).complete,false);
  assert.equal(gradeShift({...createStore(config),criticalBreach:true},config,outcome).complete,false);
});

check('player evidence excludes truth keys and one photo is one independent root', () => {
  const evidence={id:'photo1',kind:'snapshot',source:'CAM4',capturedAt:80,area:'warehouse',
    description:'两个人穿同样围裙',rootEvidenceId:'capture1',true_author:'F02',is_fake:true,
    correct_monster_id:'F02'};
  const visible=publicEvidence(evidence);
  assert.equal('true_author' in visible,false);assert.equal('correct_monster_id' in visible,false);
  const frames=[{directlyObserved:true,rootEvidenceId:'capture1',independenceDomain:'camera_appearance'},
    {directlyObserved:true,rootEvidenceId:'capture1',independenceDomain:'camera_appearance'},
    {directlyObserved:true,rootEvidenceId:'capture2',independenceDomain:'camera_appearance'},
    {directlyObserved:false,rootEvidenceId:'schedule',independenceDomain:'presence'}];
  assert.equal(independentFactCount(frames),1);
  assert.equal(independentFactCount([...frames,{directlyObserved:true,rootEvidenceId:'footprint1',
    independenceDomain:'physical_trace'}]),2);
});

check('design completeness cannot enable an unimplemented or unsafe encounter', () => {
  const p={allowed_phases:['N01'],implementation:{client_implemented:false,
    required_components:['MC01'],new_discrete_features:['note_provenance']}};
  const c={phase:'N01',features:{MC01:true,note_provenance:true},requiredCuesReachable:true,
    criticalRouteReachable:true,spawnSafe:true,requiredSeconds:80,remainingSeconds:120};
  assert.equal(admitEncounter(p,c).reason,'client_not_implemented');
  p.implementation.client_implemented=true;
  assert.equal(admitEncounter(p,{...c,features:{MC01:true}}).reason,'missing_feature');
  assert.equal(admitEncounter(p,{...c,requiredSeconds:121}).reason,'insufficient_budget');
  assert.equal(admitEncounter(p,{...c,spawnSafe:false}).reason,'unsafe_layout');
  assert.equal(admitEncounter(p,c).ok,true);
  p.admission_requirements=['real_same_shift_problem_receipt_exists'];
  assert.equal(admitEncounter(p,c).reason,'missing_world_fact');
  assert.equal(admitEncounter(p,{...c,facts:{real_same_shift_problem_receipt_exists:true}}).ok,true);
});

check('zero reserve does not block canonical F13 meat delivery or revive completion', () => {
  const store={...createStore(config),reserve:0};
  const world={player:{x:1,y:1},meat:{id:'meat',carrierId:'player'},
    freezer:{id:'freezer',x:1,y:1,functional:true,operable:true,reservedSpace:true},
    encounterInstanceId:'F13:1',touchingMeat:true};
  const receipt=storeTaskMeat({...world,emergencyReserve:store.reserve},'meat','freezer');
  assert.equal(receipt.ok,true);
  const prev={mode:'SEEK_MEAT',instanceId:'F13:1',requiredMeatId:'meat',registeredFreezerId:'freezer'};
  const done=stepF13(prev,receipt.world,{rage_windup_seconds:1.5},0);
  assert.equal(done.state.mode,'CLEARED');
  assert.equal(stepF13(done.state,{...receipt.world,deliveryReceipts:[]}, {}, 1).state.mode,'CLEARED');
});

process.stdout.write(JSON.stringify({suite:'V0.5 store contracts',scenarios:tests,
  scope:'headless invariants only; no client, navigation, touch or fun validation'})+'\n');
