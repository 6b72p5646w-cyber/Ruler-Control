import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import * as world from './world_core_v09.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const read=n=>JSON.parse(readFileSync(resolve(root,'content',n+'.json'),'utf8'));
const data={maps:read('maps'),blueprints:read('encounter_blueprints'),mechanics:read('map_mechanics_v05'),interactions:read('interactions')};
const make=(encounterId='F12',extra={})=>world.createWorldState({...data,encounterId,...extra});
const tests=[],witnesses=[];
const test=(name,fn)=>{fn();tests.push(name);};
const must=r=>{assert.equal(r.ok,true,r.reason);return r;};
const d=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
function advance(s,seconds){let left=seconds;while(left>1e-8){const t=Math.min(.05,left);world.advanceWorld(s,t);left-=t;}}
function walk(s,target){const p=Array.isArray(target)?{x:target[0],y:target[1]}:target;must(world.setWorldMoveTarget(s,p));let n=0;while(d(s.player,p)>.001&&n++<4000)world.advanceWorld(s,.05);assert.ok(n<4000,`route did not complete: ${JSON.stringify({target:p,player:s.player})}`);}
function act(s,type,extra={}){const r=must(world.beginWorldAction(s,{type,...extra}));advance(s,r.seconds);assert.equal(s.action,null);return r;}
function completeLure(s,{openFront=false}={}){
  walk(s,s.anchors.metal_shelf);act(s,'take_clips');
  for(const point of s.scene.lure_route.bait_points){
    if(openFront&&point[1]>=30&&!s.doors.DOOR_FRONT.open){walk(s,s.anchors.front_door);act(s,'toggle_door',{doorId:'DOOR_FRONT'});}
    walk(s,point);act(s,'scatter',{point});
  }
  for(let i=0;i<500&&s.status!=='cleared';i++)world.advanceWorld(s,.05);
  assert.equal(s.status,'cleared');assert.equal(s.inventory.paperclipCharges,2);
}
test('The authored five-screen store preserves real walls, fixtures and all 42 reachable anchors',()=>{
  const s=make();assert.equal(s.admission.ok,true);assert.equal(s.scene.anchors.length,42);
  for(const a of s.scene.anchors)assert.ok(world.findWorldPath(s,s.player,a.position),a.role);
  assert.equal(world.canOccupyWorld(s,{x:11.5,y:14.5}),false);
  assert.equal(world.setWorldMoveTarget(s,{x:11.5,y:14.5}).ok,false);
  assert.equal(world.canOccupyWorld(s,{x:-1,y:20}),false);
});
test('Manual movement uses swept small steps and cannot tunnel through a fixture or wall',()=>{
  const s=make('F12',{playerStart:[13.5,17.5]});must(world.setWorldDirection(s,{x:-1,y:0}));advance(s,2);
  assert.ok(s.player.x>=13.3-1e-8);assert.ok(world.canOccupyWorld(s,s.player));
  assert.throws(()=>world.advanceWorld(s,11),/0..10/);
});
test('Facing lock preserves avatar orientation while moving and interaction never rotates it',()=>{
  const s=make();world.setWorldFacingLock(s,true);const original={...s.player.facing};
  walk(s,s.anchors.metal_shelf);act(s,'take_clips');assert.deepEqual(s.player.facing,original);
  world.setWorldFacingLock(s,false);must(world.setWorldDirection(s,{x:1,y:0}));advance(s,.1);assert.equal(s.player.facing.x,1);
});
test('Paused world freezes player, monster, action, lure lifetime and clock together',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);must(world.beginWorldAction(s,{type:'take_clips'}));world.setWorldPaused(s,true);
  const snapshot=JSON.stringify(s);const result=world.advanceWorld(s,5);assert.equal(JSON.stringify(s),snapshot);assert.equal(result.advancedSeconds,0);
  world.setWorldPaused(s,false);advance(s,1);assert.equal(s.inventory.paperclipCharges,6);
});
test('Pickup and scatter require real proximity, clear ground, actual supply and their own elapsed action',()=>{
  const s=make();assert.equal(world.beginWorldAction(s,{type:'take_clips'}).ok,false);
  assert.equal(world.beginWorldAction(s,{type:'scatter',point:s.player}).ok,false);
  walk(s,s.anchors.metal_shelf);must(world.beginWorldAction(s,{type:'take_clips'}));advance(s,.5);assert.equal(s.inventory.paperclipCharges,0);
  world.cancelWorldAction(s);assert.equal(s.supplies.main.remaining,1);act(s,'take_clips');assert.equal(s.inventory.paperclipCharges,6);
  assert.equal(world.beginWorldAction(s,{type:'scatter',point:[30,30]}).ok,false);assert.equal(world.beginWorldAction(s,{type:'scatter',point:[12.5,17.5]}).ok,false);
  const before=s.inventory.paperclipCharges;must(world.beginWorldAction(s,{type:'scatter',point:s.player}));advance(s,.1);world.cancelWorldAction(s);assert.equal(s.inventory.paperclipCharges,before);
});
test('F12 dynamically follows four actual player baits to the existing outdoor zone with two charges left',()=>{
  const s=make();completeLure(s);assert.equal(s.receipts.filter(x=>x.type==='encounter_cleared').length,1);
  assert.ok(s.monster.y-s.radius>=s.exitRect[1]);assert.ok(s.now<35);
  witnesses.push({id:'F12_normal_actual_route',seconds:s.now,san:s.player.san,chargesLeft:s.inventory.paperclipCharges,actualScatterReceipts:s.receipts.filter(x=>x.actionType==='scatter').length,monsterPosition:{x:s.monster.x,y:s.monster.y}});
});
test('An initially closed but operable front door remains recoverable through a real half-second open',()=>{
  const s=make('F12',{doors:{DOOR_FRONT:{open:false}}});assert.equal(s.admission.ok,true);completeLure(s,{openFront:true});
  const receipt=s.receipts.find(x=>x.actionType==='toggle_door');assert.equal(receipt.worldSeconds,.5);assert.equal(receipt.open,true);
  witnesses.push({id:'F12_closed_front_recovery',seconds:s.now,chargesLeft:s.inventory.paperclipCharges,san:s.player.san});
});
test('The slice refuses an inoperable only-declared exit instead of inventing a rear victory zone',()=>{
  const s=make('F12',{doors:{DOOR_FRONT:{open:false,operable:false}}});assert.equal(s.status,'unavailable');assert.ok(s.admission.reasons.includes('declared_exit_unavailable'));assert.equal(world.advanceWorld(s,1).advancedSeconds,0);
});
test('Unbaited F12 chases only inside and cannot be won by simply walking outdoors',()=>{
  const s=make();walk(s,s.anchors.front_exit);advance(s,8);assert.equal(s.status,'active');assert.equal(s.monster.state.mode,'CHASE_PLAYER');assert.ok(s.monster.y+s.radius<=30+1e-8);
});
test('An intermediate outdoor lure can end without victory, return F12 inside, and still be recovered with two real replacement baits',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);act(s,'take_clips');
  for(const point of s.scene.lure_route.bait_points.slice(0,3)){walk(s,point);act(s,'scatter',{point});}
  advance(s,8);assert.equal(s.status,'active');assert.ok(s.monster.y+s.radius<=30+1e-8);assert.equal(s.monster.state.mode,'CHASE_PLAYER');
  act(s,'scatter',{point:[14.5,30.5]});walk(s,[14.5,33.5]);act(s,'scatter',{point:[14.5,33.5]});advance(s,8);
  assert.equal(s.status,'cleared');assert.equal(s.inventory.paperclipCharges,1);
});
test('Outdoor ground beyond the declared exit corridor cannot become a fake alternate victory route',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);act(s,'take_clips');walk(s,[18.5,30.5]);
  const before=s.inventory.paperclipCharges;assert.equal(world.beginWorldAction(s,{type:'scatter',point:[19.5,30.5]}).reason,'bait_outside_declared_lure_route');assert.equal(s.inventory.paperclipCharges,before);
});
test('The primary and backup boxes are finite same-shelf sources, not infinite refills',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);act(s,'take_clips');const backup=act(s,'take_clips');assert.equal(backup.seconds,2);assert.equal(s.inventory.paperclipCharges,12);
  assert.equal(s.supplies.main.remaining,0);assert.equal(s.supplies.backup.remaining,0);assert.equal(world.beginWorldAction(s,{type:'take_clips'}).ok,false);
});
test('A full live-bait set rejects new placement without consuming another charge',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);act(s,'take_clips');for(let i=0;i<3;i++)act(s,'scatter',{point:[13.5,17.5]});
  const remaining=s.inventory.paperclipCharges;assert.equal(world.beginWorldAction(s,{type:'scatter',point:s.player}).reason,'bait_limit');assert.equal(s.inventory.paperclipCharges,remaining);
});
test('F13 actual pickup, carry route and atomic store can prevent meat contact without sprint or a pet',()=>{
  const s=make('F13');s.player.stamina=0;walk(s,s.meat);act(s,'take_meat');walk(s,s.freezer);act(s,'store_meat');
  assert.equal(s.status,'cleared');assert.equal(s.meat.storedIn,s.freezer.id);assert.equal(s.freezer.closed,true);assert.equal(s.player.carriedId,null);
  assert.equal(s.events.some(e=>e.type==='rage_telegraph'),false);assert.equal(s.deliveryReceipts.length,1);
  witnesses.push({id:'F13_early_actual_delivery',seconds:s.now,san:s.player.san,deliveryReceipts:s.deliveryReceipts.length,zeroStamina:true});
});
test('F13 touching its real meat telegraphs, keeps the crate, and remains enraged after it is dropped',()=>{
  const s=make('F13');for(let i=0;i<600&&s.monster.state.mode==='SEEK_MEAT';i++)world.advanceWorld(s,.05);
  assert.equal(s.monster.state.mode,'RAGE_WINDUP');assert.equal(s.meat.storedIn,null);assert.equal(s.meat.carrierId,null);advance(s,1.6);assert.equal(s.monster.state.mode,'CHASE_PLAYER');
  walk(s,s.meat);act(s,'take_meat');act(s,'drop_meat');assert.equal(s.monster.state.mode,'CHASE_PLAYER');act(s,'take_meat');walk(s,s.freezer);act(s,'store_meat');assert.equal(s.status,'cleared');
  witnesses.push({id:'F13_contact_drop_repickup_recovery',seconds:s.now,san:s.player.san,meatId:s.meat.id,deliveryReceipts:s.deliveryReceipts.length});
});
test('A cancelled F13 store retains the original carried crate and creates no delivery receipt',()=>{
  const s=make('F13');walk(s,s.meat);act(s,'take_meat');walk(s,s.freezer);must(world.beginWorldAction(s,{type:'store_meat'}));advance(s,.2);world.cancelWorldAction(s);
  assert.equal(s.player.carriedId,s.meat.id);assert.equal(s.meat.storedIn,null);assert.equal(s.deliveryReceipts.length,0);act(s,'store_meat');assert.equal(s.status,'cleared');
});
test('Freezer unavailable before admission rejects F13, and failure at commit never swallows the meat',()=>{
  assert.equal(make('F13',{freezer:{functional:false}}).status,'unavailable');
  assert.ok(make('F13',{freezer:{id:'unregistered'}}).admission.reasons.includes('unregistered_freezer'));
  const s=make('F13');walk(s,s.meat);act(s,'take_meat');walk(s,s.freezer);must(world.beginWorldAction(s,{type:'store_meat'}));s.freezer.functional=false;advance(s,.6);
  assert.equal(s.player.carriedId,s.meat.id);assert.equal(s.deliveryReceipts.length,0);assert.equal(s.status,'active');s.freezer.functional=true;act(s,'store_meat');assert.equal(s.status,'cleared');
});
test('Successful delivery is terminal despite later opening or outage and never pays twice',()=>{
  const s=make('F13');walk(s,s.meat);act(s,'take_meat');walk(s,s.freezer);act(s,'store_meat');s.freezer.closed=false;s.freezer.functional=false;advance(s,3);
  assert.equal(s.status,'cleared');assert.equal(s.receipts.filter(e=>e.type==='encounter_cleared').length,1);assert.equal(world.beginWorldAction(s,{type:'store_meat'}).ok,false);
});
test('An actual chase hit has a visible windup, shared SAN delta and no task destruction',()=>{
  const s=make();advance(s,6);const first=s.events.find(e=>e.type==='hit'),warning=s.events.find(e=>e.type==='attack_telegraph');
  assert.ok(first&&warning);assert.ok(first.at-warning.at>=1.5-1e-8);assert.equal(first.sanDelta,-10);assert.equal(s.inventory.paperclipCharges,0);assert.equal(s.supplies.main.remaining,1);
});
test('World motion emits actual walked distance and never drains passive resources or moves while paused',()=>{
  const s=make('F13');const original=s.player.san;must(world.setWorldDirection(s,{x:-1,y:0}));const r=world.advanceWorld(s,.2);assert.ok(Math.abs(r.actualMovedTiles-.6)<1e-8);assert.equal(s.player.san,original);
  must(world.setWorldResources(s,{san:15}));assert.equal(s.player.san,15);assert.equal(world.setWorldResources(s,{san:200}).ok,false);
});
test('Serialized world continuation retains exact bait supply, actions, target and terminal receipts',()=>{
  const s=make();walk(s,s.anchors.metal_shelf);act(s,'take_clips');walk(s,[13.5,22.5]);act(s,'scatter',{point:s.player});
  const restored=JSON.parse(JSON.stringify(s));advance(s,1);advance(restored,1);assert.deepEqual(restored,s);
});
console.log(JSON.stringify({status:'PASS',scenarioCount:tests.length,scenarios:tests,witnesses,scope:'Deterministic authored-map F12/F13 physics and finite actions with moving enemies; no full-night director, all 60 monsters, dynamic multi-enemy combinations, production save system, mobile performance or WeChat runtime.'},null,2));
