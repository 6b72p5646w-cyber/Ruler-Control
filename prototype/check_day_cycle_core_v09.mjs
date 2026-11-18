import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createDayCycleState,createPracticeNightState,completeDayAction,finishMorning,advancePreparation,
  finishPreparation,completeCommute,beginNight,advanceNightResources,finishNight,finishPractice,
  claimDailyJobFood,purchasePersonalItem,consumePersonalItem,spendStamina,recordMinorInjury,
  staminaRegenRate,serializeDayCycle,restoreDayCycle} from './day_cycle_core_v09.mjs';
const read=name=>JSON.parse(fs.readFileSync(fileURLToPath(new URL('../content/'+name+'.json',import.meta.url)),'utf8'));
const balance=read('balance'),items=read('items');
const passed=[];const test=(name,fn)=>{fn();passed.push(name);};
const must=r=>{assert.equal(r.ok,true,JSON.stringify(r));return r;};
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} differs from ${b}`);
const clone=x=>JSON.parse(JSON.stringify(x));
const bag=(id,itemId,extra={})=>({id,itemId,owned:true,consumed:false,foodStatus:'personal_verified',...extra});
const day=options=>createDayCycleState(balance,items,options);
const night=options=>day({mode:'night',absoluteGameMinute:1440,nightId:'night-1',remainingDaySlots:0,...options});
const handover=s=>({id:'verified-handover',nightId:s.night.id,committed:true,verified:true,settlementMode:'handover_only',panicActive:false});
const unchanged=(s,call)=>{const before=JSON.stringify(s);assert.equal(call().ok,false);assert.equal(JSON.stringify(s),before);};

test('Twenty-four actual hours with eight sleeping hours drain exactly 56 satiety, once',()=>{
 const s=day({absoluteGameMinute:360,resources:{energy:35,san:70,satiety:100,stamina:50}});
 must(finishMorning(s,{commandId:'morning'}));
 for(let i=0;i<4;i++)must(completeDayAction(s,{commandId:'sleep'+i,actionId:'A01'}));
 must(completeDayAction(s,{commandId:'study',actionId:'A03',pageId:'K05'}));
 must(completeDayAction(s,{commandId:'job',actionId:'A09'}));
 must(finishPreparation(s,{commandId:'prep'}));must(completeCommute(s,{commandId:'commute'}));must(beginNight(s,{nightId:'night-1'}));
 must(advanceNightResources(s,{worldSeconds:720}));must(finishNight(s,{outcome:'complete',handoverReceipt:handover(s)}));
 near(s.absoluteGameMinute,1800);near(s.resources.satiety,44);near(s.resources.energy,57);
 assert.equal(s.remainingDaySlots,6);assert.equal(s.mode,'morning');assert.equal(s.coins,150);
});
test('Six day slots advance to preparation; a seventh day action is unavailable',()=>{
 const s=day();for(let i=0;i<6;i++)must(completeDayAction(s,{commandId:'rest'+i,actionId:'A02'}));
 assert.equal(s.absoluteGameMinute,1200);assert.equal(s.remainingDaySlots,0);assert.equal(s.mode,'preparation');
 unchanged(s,()=>completeDayAction(s,{commandId:'seventh',actionId:'A01'}));
});
test('A completed day action cannot be replayed with the same command',()=>{
 const s=day();must(completeDayAction(s,{commandId:'sleep',actionId:'A01'}));unchanged(s,()=>completeDayAction(s,{commandId:'sleep',actionId:'A09'}));
});
test('Unavailable maintenance and unbound specialty procurement or pet targets consume nothing',()=>{
 const s=day();for(const actionId of ['A06','A07','A08'])unchanged(s,()=>completeDayAction(s,{commandId:actionId,actionId}));
});
test('Learning uses the existing knowledge module and charges one slot and one energy cost',()=>{
 const s=day({resources:{energy:50}});must(completeDayAction(s,{commandId:'learn',actionId:'A03',pageId:'K01'}));
 assert.equal(s.remainingDaySlots,5);assert.equal(s.knowledge.remainingSlots,5);near(s.resources.energy,44);
 assert.ok(s.knowledge.unlockedPages.K01);assert.equal(s.knowledge.studyPoints,0);
 unchanged(s,()=>completeDayAction(s,{commandId:'again',actionId:'A03',pageId:'K01'}));
});
test('Missing study or case targets cannot advance the day or apply coffee debts early',()=>{
 const s=day({inventory:[bag('coffee','I05')]});must(consumePersonalItem(s,{commandId:'coffee',itemInstanceId:'coffee'}));
 unchanged(s,()=>completeDayAction(s,{commandId:'bad-study',actionId:'A03',pageId:'missing'}));
 unchanged(s,()=>completeDayAction(s,{commandId:'bad-case',actionId:'A04',sourceRecordIds:[]}));
 assert.equal(s.coffeeDebts[0].settled,false);assert.equal(s.absoluteGameMinute,480);
});
test('One actual case review consumes one slot and one new root via the knowledge model',()=>{
 const r={id:'observed',rootSourceId:'root-1',runId:'old-night',sceneId:'MAP_STORE',subjectId:'item-1',evaluationWindow:'past',producerKind:'actual_observation_receipt',completed:true,visible:true,observations:[]};
 const s=day({sourceRecords:[r]});must(completeDayAction(s,{commandId:'case',actionId:'A04',sourceRecordIds:['observed']}));
 assert.equal(s.remainingDaySlots,5);near(s.resources.energy,47);assert.equal(Object.values(s.knowledge.cases)[0].status,'HYPOTHESIS');
 unchanged(s,()=>completeDayAction(s,{commandId:'reprint',actionId:'A04',sourceRecordIds:['observed']}));
});
test('Free noisy sleep consumes only two sleep satiety and grants energy8 SAN0',()=>{
 const s=day();must(completeDayAction(s,{commandId:'noise',actionId:'A01',noiseChoice:'home',noiseEventId:'event-1'}));
 near(s.resources.energy,58);near(s.resources.san,70);near(s.resources.satiety,68);assert.equal(s.coins,120);
 unchanged(s,()=>completeDayAction(s,{commandId:'repeat',actionId:'A01',noiseChoice:'home',noiseEventId:'event-1'}));
});
test('Paid quiet sleep uses an existing available place, costs10, and grants the ordinary sleep result only',()=>{
 const s=day();must(completeDayAction(s,{commandId:'quiet',actionId:'A01',noiseChoice:'quiet',noiseEventId:'noise',studyRestAvailable:true}));
 near(s.resources.energy,66);near(s.resources.san,74);near(s.resources.satiety,68);assert.equal(s.coins,110);
});
test('A missing quiet place or insufficient payment leaves the free noisy branch available',()=>{
 const s=day({coins:9});unchanged(s,()=>completeDayAction(s,{commandId:'pay',actionId:'A01',noiseChoice:'quiet',noiseEventId:'e',studyRestAvailable:true}));
 must(completeDayAction(s,{commandId:'free',actionId:'A01',noiseChoice:'home',noiseEventId:'e'}));assert.equal(s.coins,9);
});
test('Preparation optional actions share 60 minutes while basic preparation and commute still consume their real hours',()=>{
 const s=day({absoluteGameMinute:1200,remainingDaySlots:0,resources:{satiety:70}});
 for(let i=0;i<4;i++)must(advancePreparation(s,{commandId:'option'+i,minutes:15}));
 unchanged(s,()=>advancePreparation(s,{commandId:'fifth',minutes:15}));
 must(finishPreparation(s,{commandId:'finish'}));near(s.resources.satiety,64);assert.equal(s.absoluteGameMinute,1320);
 must(completeCommute(s,{commandId:'travel'}));near(s.resources.satiety,58);assert.equal(s.absoluteGameMinute,1440);
});
test('Formal departure cannot skip the six day slots or required preparation sequence',()=>{
 const s=day();unchanged(s,()=>beginNight(s,{nightId:'early'}));unchanged(s,()=>completeCommute(s,{commandId:'skip'}));
 const n=day({absoluteGameMinute:1440,remainingDaySlots:6});unchanged(n,()=>beginNight(n,{nightId:'unearned'}));
});
test('Practice is an isolated same-resource same-clock fork, retaining exact coffee debt and inventory',()=>{
 const s=day({inventory:[bag('coffee','I05')]});must(consumePersonalItem(s,{commandId:'coffee',itemInstanceId:'coffee'}));
 const before=serializeDayCycle(s),p=createPracticeNightState(s,{practiceId:'f12',initialBudget:120});
 assert.equal(p.absoluteGameMinute,s.absoluteGameMinute);assert.deepEqual(p.resources,s.resources);assert.deepEqual(p.coffeeDebts,s.coffeeDebts);
 must(advanceNightResources(p,{worldSeconds:120}));assert.equal(p.coffeeDebts[0].settled,true);assert.equal(serializeDayCycle(s),before);
 assert.equal(must(finishPractice(p)).officialRewardGranted,false);unchanged(p,()=>advanceNightResources(p,{worldSeconds:1}));
});
test('A whole night costs energy24 and satiety18 with or without precision budget time',()=>{
 const s=night({resources:{energy:70,satiety:70,stamina:0}});must(advanceNightResources(s,{budgetCost:120}));
 assert.equal(s.worldSeconds,0);near(s.resources.stamina,0);near(s.resources.energy,66);near(s.resources.satiety,67);
 must(advanceNightResources(s,{worldSeconds:600}));near(s.resources.energy,46);near(s.resources.satiety,52);assert.equal(s.night.budget,720);
});
test('Paused time grants no recovery, no hunger drain, no debt progress, and no night budget',()=>{
 const s=night({inventory:[bag('coffee','I05')],resources:{stamina:0}});must(consumePersonalItem(s,{commandId:'coffee',itemInstanceId:'coffee'}));
 const before=serializeDayCycle(s);must(advanceNightResources(s,{worldSeconds:500,paused:true}));assert.equal(serializeDayCycle(s),before);
});
test('World and precision deltas cannot be silently charged together',()=>{
 const s=night();unchanged(s,()=>advanceNightResources(s,{worldSeconds:2,budgetCost:8}));
 unchanged(s,()=>advanceNightResources(s,{budgetCost:721}));
});
test('World motion truncates at720 and never accounts an extra game minute',()=>{
 const s=night({absoluteGameMinute:1799.5,nightBudget:719,resources:{energy:50}});
 assert.equal(must(advanceNightResources(s,{worldSeconds:30})).actualWorldSeconds,1);assert.equal(s.night.budget,720);assert.equal(s.absoluteGameMinute,1800);
});
test('Stamina waits two actual world seconds after exertion and then recovers at the defined rate',()=>{
 const s=night({resources:{energy:70,satiety:70,stamina:50}});must(spendStamina(s,{commandId:'run',amount:20}));
 must(advanceNightResources(s,{worldSeconds:2}));near(s.resources.stamina,30);
 must(advanceNightResources(s,{worldSeconds:1}));near(s.resources.stamina,36);
});
test('Continued high-exertion time never simultaneously grants passive stamina',()=>{
 const s=night({resources:{stamina:10}});must(advanceNightResources(s,{worldSeconds:10,exerting:true}));near(s.resources.stamina,10);
 must(advanceNightResources(s,{worldSeconds:2}));near(s.resources.stamina,10);must(advanceNightResources(s,{worldSeconds:1}));near(s.resources.stamina,16);
});
test('Low energy, low satiety and actual minor injury respect the minimum stamina recovery floor',()=>{
 const s=night({resources:{energy:20,satiety:20,stamina:0}});must(recordMinorInjury(s,{incidentId:'actual-hit'}));
 near(staminaRegenRate(s),2);must(advanceNightResources(s,{worldSeconds:3}));near(s.resources.stamina,6);
 unchanged(s,()=>recordMinorInjury(s,{incidentId:'actual-hit'}));
});
test('Stamina is clamped to the real current energy-derived cap, and zero energy still permits resource progression',()=>{
 const s=night({resources:{energy:0,satiety:0,stamina:100}});assert.equal(s.resources.stamina,50);
 must(advanceNightResources(s,{worldSeconds:1}));assert.equal(s.resources.energy,0);assert.equal(s.resources.satiety,0);assert.equal(s.resources.stamina,50);
});
test('Resource thresholds, injury expiry and coffee debt are independent of frame partition',()=>{
 const a=night({resources:{energy:26,satiety:26,stamina:0},inventory:[bag('coffee','I05')]});
 must(recordMinorInjury(a,{incidentId:'hit'}));must(consumePersonalItem(a,{commandId:'coffee',itemInstanceId:'coffee'}));
 const b=clone(a);must(advanceNightResources(a,{worldSeconds:360}));
 for(let i=0;i<720;i++)must(advanceNightResources(b,{worldSeconds:0.5}));
 for(const k of Object.keys(a.resources))near(a.resources[k],b.resources[k]);near(a.absoluteGameMinute,b.absoluteGameMinute);
 assert.equal(a.coffeeDebts[0].settled,true);assert.equal(b.coffeeDebts[0].settled,true);
});
test('Coffee debt is due sixty minutes after actual consumption, not at the next rounded hour',()=>{
 const s=night({absoluteGameMinute:1455,nightBudget:30,resources:{energy:40,san:50},inventory:[bag('coffee','I05')]});
 must(consumePersonalItem(s,{commandId:'drink',itemInstanceId:'coffee'}));assert.equal(s.coffeeDebts[0].dueAbsoluteGameMinute,1515);
 must(advanceNightResources(s,{worldSeconds:119}));assert.equal(s.coffeeDebts[0].settled,false);
 must(advanceNightResources(s,{worldSeconds:1}));assert.equal(s.coffeeDebts[0].settled,true);near(s.resources.energy,40);near(s.resources.san,48);
});
test('Coffee due inside a two-hour sleep settles before completion gains and is charged once',()=>{
 const s=day({resources:{energy:40,san:50},inventory:[bag('coffee','I05')]});must(consumePersonalItem(s,{commandId:'drink',itemInstanceId:'coffee'}));
 must(completeDayAction(s,{commandId:'sleep',actionId:'A01'}));near(s.resources.energy,60);near(s.resources.san,52);
 assert.equal(s.ledger.filter(x=>x.type==='coffee_debt_settled').length,1);
});
test('A coffee debt due exactly at day-action completion settles before that action recovery',()=>{
 const s=day({resources:{energy:100,san:99},coffeeDebts:[{id:'prior-debt',itemInstanceId:'old-coffee',dueAbsoluteGameMinute:600,resourceDeltas:{energy:-8,san:-2},settled:false}]});
 must(completeDayAction(s,{commandId:'sleep',actionId:'A01'}));near(s.resources.energy,100);near(s.resources.san,100);
});
test('Coffee consumed at05:50 stays due through06:00 and settles in the actual morning',()=>{
 const s=night({absoluteGameMinute:1790,nightBudget:700,inventory:[bag('coffee','I05')]});must(consumePersonalItem(s,{commandId:'drink',itemInstanceId:'coffee'}));
 must(advanceNightResources(s,{worldSeconds:20}));assert.equal(s.coffeeDebts[0].settled,false);
 must(finishNight(s,{outcome:'complete',handoverReceipt:handover(s)}));must(finishMorning(s,{commandId:'morning'}));
 assert.equal(s.coffeeDebts[0].settled,true);assert.equal(s.ledger.find(x=>x.type==='coffee_debt_settled').absoluteGameMinute,1850);
});
test('Coffee SAN debt reaching zero requests the ordinary night panic rather than silently restoring SAN',()=>{
 const s=night({resources:{san:1},inventory:[bag('coffee','I05')]});must(consumePersonalItem(s,{commandId:'drink',itemInstanceId:'coffee'}));
 const r=must(advanceNightResources(s,{worldSeconds:120}));assert.equal(s.resources.san,0);assert.equal(r.normalPanicRequired,true);
 assert.equal(r.events.filter(x=>x.type==='san_reached_zero').length,1);
});
test('Daily food is two real verified items, remains available without a completed night, and cannot be claimed twice',()=>{
 const s=day();const r=must(claimDailyJobFood(s,{commandId:'food'}));assert.equal(r.receipt.itemInstanceIds.length,2);
 assert.equal(Object.values(s.inventory).filter(x=>x.itemId==='I01').length,1);assert.equal(Object.values(s.inventory).filter(x=>x.itemId==='I02').length,1);
 unchanged(s,()=>claimDailyJobFood(s,{commandId:'food-again'}));
});
test('Daily food reset follows actual06:00, not entering a new practice or restoring a save',()=>{
 const s=day();must(claimDailyJobFood(s,{commandId:'food'}));const p=createPracticeNightState(s,{practiceId:'copy'});
 unchanged(p,()=>claimDailyJobFood(p,{commandId:'copy-food'}));const r=restoreDayCycle(serializeDayCycle(s));unchanged(r,()=>claimDailyJobFood(r,{commandId:'restored-food'}));
});
test('Same-item food use updates resources once and never turns task inventory directly into satiety',()=>{
 const s=day({resources:{satiety:50},inventory:[bag('meal','I01'),bag('meat','TASK_MEAT')]});must(consumePersonalItem(s,{commandId:'eat',itemInstanceId:'meal'}));near(s.resources.satiety,75);
 unchanged(s,()=>consumePersonalItem(s,{commandId:'eat-again',itemInstanceId:'meal'}));unchanged(s,()=>consumePersonalItem(s,{commandId:'meat',itemInstanceId:'meat'}));
});
test('Unverified, unowned, reserved and already-consumed food never grants a resource effect',()=>{
 for(const extra of [{foodStatus:'sealed_unverified'},{owned:false},{reservedBy:'F53'},{consumed:true}]) {
  const s=day({inventory:[bag('meal','I01',extra)]});unchanged(s,()=>consumePersonalItem(s,{commandId:'eat',itemInstanceId:'meal'}));
 }
});
test('I03 and I14 use their existing numeric effects; safe bento is unavailable during a chase',()=>{
 const s=night({resources:{energy:50,satiety:20,stamina:0},inventory:[bag('sugar','I03'),bag('bento','I14')]});
 must(consumePersonalItem(s,{commandId:'glucose',itemInstanceId:'sugar'}));near(s.resources.stamina,35);
 unchanged(s,()=>consumePersonalItem(s,{commandId:'unsafe',itemInstanceId:'bento',safeStation:true,activeChase:true}));
 must(consumePersonalItem(s,{commandId:'eat',itemInstanceId:'bento',safeStation:true}));near(s.resources.satiety,55);near(s.resources.energy,54);
});
test('Tea requires the declared safe place and completed three-world-second use; I20 has no invented resource gain',()=>{
 const s=night({resources:{san:30},inventory:[bag('tea','I13'),bag('water','I20')]});
 unchanged(s,()=>consumePersonalItem(s,{commandId:'instant',itemInstanceId:'tea',safeStation:true,actualUseWorldSeconds:2}));
 must(consumePersonalItem(s,{commandId:'tea',itemInstanceId:'tea',safeStation:true,actualUseWorldSeconds:3}));near(s.resources.san,50);
 unchanged(s,()=>consumePersonalItem(s,{commandId:'water',itemInstanceId:'water'}));
});
test('Mint respects the two-use limit of the same actual encounter and leaves a rejected third item intact',()=>{
 const s=night({resources:{san:30},inventory:[bag('m1','I04'),bag('m2','I04'),bag('m3','I04')]});
 for(const id of ['m1','m2'])must(consumePersonalItem(s,{commandId:id,itemInstanceId:id,encounterId:'encounter-1'}));
 unchanged(s,()=>consumePersonalItem(s,{commandId:'m3',itemInstanceId:'m3',encounterId:'encounter-1'}));
 must(consumePersonalItem(s,{commandId:'new-encounter',itemInstanceId:'m3',encounterId:'encounter-2'}));near(s.resources.san,54);
});
test('Basic shop purchases spend actual coins once and grant one verified item without consuming the daily bundle',()=>{
 const s=day({absoluteGameMinute:1200,remainingDaySlots:0});const r=must(purchasePersonalItem(s,{commandId:'buy',itemId:'I05'}));
 assert.equal(s.coins,102);assert.equal(s.inventory[r.receipt.itemInstanceId].itemId,'I05');assert.deepEqual(s.dailySupplyClaims,{});
 unchanged(s,()=>purchasePersonalItem(s,{commandId:'buy',itemId:'I05'}));
});
test('Unavailable item effects, wrong shop phase and unaffordable shopping charge nothing',()=>{
 const a=day();unchanged(a,()=>purchasePersonalItem(a,{commandId:'early',itemId:'I05'}));
 const b=day({absoluteGameMinute:1200,remainingDaySlots:0,coins:1});unchanged(b,()=>purchasePersonalItem(b,{commandId:'poor',itemId:'I05'}));
 unchanged(b,()=>purchasePersonalItem(b,{commandId:'disabled',itemId:'I22'}));
});
test('True06:00 refuses new recovery or locker work before verified handover',()=>{
 const s=night({absoluteGameMinute:1799.5,nightBudget:719,inventory:[bag('mint','I04')]});must(advanceNightResources(s,{worldSeconds:1}));
 unchanged(s,()=>consumePersonalItem(s,{commandId:'late-eat',itemInstanceId:'mint'}));unchanged(s,()=>claimDailyJobFood(s,{commandId:'late-food'}));
 unchanged(s,()=>finishNight(s,{outcome:'complete'}));
});
test('An active panic or foreign handover cannot turn a night into day or issue rewards',()=>{
 const s=night({absoluteGameMinute:1799.5,nightBudget:719,resources:{san:0}});must(advanceNightResources(s,{worldSeconds:1}));
 unchanged(s,()=>finishNight(s,{outcome:'complete',handoverReceipt:handover(s)}));
 const p=night({absoluteGameMinute:1799.5,nightBudget:719});must(advanceNightResources(p,{worldSeconds:1}));
 unchanged(p,()=>finishNight(p,{outcome:'complete',handoverReceipt:{...handover(p),nightId:'other'}}));
});
test('Failure freezes further resource progression and gives no automatic retry reset, food or wage',()=>{
 const s=night();const coins=s.coins;must(finishNight(s,{outcome:'failed'}));assert.equal(s.coins,coins);
 unchanged(s,()=>advanceNightResources(s,{worldSeconds:500}));unchanged(s,()=>claimDailyJobFood(s,{commandId:'reset-food'}));
});
test('Serialization preserves unpaid and settled coffee debts, consumption, mint limits and daily claims',()=>{
 const s=night({inventory:[bag('coffee','I05'),bag('mint','I04')]});must(claimDailyJobFood(s,{commandId:'food'}));
 must(consumePersonalItem(s,{commandId:'coffee',itemInstanceId:'coffee'}));must(consumePersonalItem(s,{commandId:'mint',itemInstanceId:'mint',encounterId:'f'}));
 const r=restoreDayCycle(serializeDayCycle(s));must(advanceNightResources(r,{worldSeconds:120}));const after=restoreDayCycle(serializeDayCycle(r));
 assert.equal(after.coffeeDebts[0].settled,true);assert.equal(after.ledger.filter(x=>x.type==='coffee_debt_settled').length,1);
 unchanged(after,()=>consumePersonalItem(after,{commandId:'reuse',itemInstanceId:'coffee'}));unchanged(after,()=>claimDailyJobFood(after,{commandId:'again'}));
 assert.equal(after.itemUseCounts['f:I04'],1);
});
test('Completing the day clears old short-lived night injury on admission while preserving resources and coffee debt',()=>{
 const s=day({absoluteGameMinute:1200,remainingDaySlots:0,minorInjuryUntilWorldSeconds:100,inventory:[bag('coffee','I05')]});
 must(finishPreparation(s,{commandId:'prep'}));must(consumePersonalItem(s,{commandId:'drink',itemInstanceId:'coffee'}));
 must(completeCommute(s,{commandId:'commute'}));const before=clone(s.resources);must(beginNight(s,{nightId:'n'}));
 assert.deepEqual(s.resources,before);assert.equal(s.minorInjuryUntilWorldSeconds,s.worldSeconds);assert.equal(s.coffeeDebts.length,1);
});

console.log(JSON.stringify({status:'PASS',scenarioCount:passed.length,scenarios:passed,
 scope:'Finite 24-hour resource accounting, six-slot day actions, preparation, same-item personal use, persistent coffee debt and daily food, knowledge adapter, and isolated practice forks. Physical receipt authenticity, world collisions, full panic execution, production rollback protection and campaign wages are external.'},null,2));
