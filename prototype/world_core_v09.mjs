/**
 * Browser-compatible F12/F13 world slice on the authored store map.
 * Real four-neighbour routes, continuous movement, bounded world actions and
 * shared blueprint transitions. No director, full night, NPC, economy or WeChat
 * adapter is implied. The owning session applies passive resource changes.
 */
import {stepF12, stepF13, scatterPaperclips, storeTaskMeat, applySharedHit} from './rule_core.mjs';

const EPS = 1e-8;
const copy = x => JSON.parse(JSON.stringify(x));
const pos = p => Array.isArray(p) ? {x:p[0],y:p[1]} : {x:p?.x,y:p?.y};
const dist = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);
const key = (x,y) => `${x},${y}`;
const finitePoint = p => p && Number.isFinite(p.x) && Number.isFinite(p.y);
const cache = new WeakMap();
const ok = extra => ({ok:true,...extra});
const no = reason => ({ok:false,reason});
const interior = (s,p,r=0) => {const [x,y,w,h]=s.scene.interior_rect;return p.x-r>=x-EPS&&p.y-r>=y-EPS&&p.x+r<=x+w+EPS&&p.y+r<=y+h+EPS;};
const inRect = (p,r) => p.x>=r[0]&&p.y>=r[1]&&p.x<r[0]+r[2]&&p.y<r[1]+r[3];
const rectDistance = (p,r) => Math.hypot(Math.max(r[0]-p.x,0,p.x-r[0]-r[2]),Math.max(r[1]-p.y,0,p.y-r[1]-r[3]));
function cells(rect,fn) {for(let x=rect[0];x<rect[0]+rect[2];x++)for(let y=rect[1];y<rect[1]+rect[3];y++)fn(x,y);}
function emit(s,type,data={}) {const e={id:`${s.instanceId}:event-${++s.sequence}`,type,at:s.now,encounterInstanceId:s.instanceId,...data};s.events.push(e);return e;}
function grid(s,potential=false) {
  const signature=Object.values(s.doors).map(d=>`${d.id}:${d.open||potential&&d.operable&&!d.locked}`).join('|');
  let c=cache.get(s);if(c?.signature===signature)return c.walk;
  const walk=new Set();for(const f of s.scene.walk_surfaces)cells(f.rect,(x,y)=>walk.add(key(x,y)));
  for(const f of [...s.scene.walls,...s.scene.fixtures.filter(f=>f.blocks_navigation!==false)])cells(f.rect,(x,y)=>walk.delete(key(x,y)));
  for(const d of Object.values(s.doors))if(!(d.open||potential&&d.operable&&!d.locked))cells(d.rect,(x,y)=>walk.delete(key(x,y)));
  cache.set(s,{signature,walk});return walk;
}
function allowedCell(s,x,y,scope='all',potential=false) {
  const p={x:x+.5,y:y+.5};
  return grid(s,potential).has(key(x,y))&&(scope!=='interior'||interior(s,p,s.radius))&&
    (scope!=='lure'||interior(s,p)||inRect(p,s.lureCorridorRect));
}
export function canOccupyWorld(s,point,{scope='all',potential=false,radius=s.radius}={}) {
  const p=pos(point);if(!finitePoint(p)||scope==='interior'&&!interior(s,p,radius))return false;
  const walk=grid(s,potential);
  for(let x=Math.floor(p.x-radius);x<=Math.floor(p.x+radius);x++)for(let y=Math.floor(p.y-radius);y<=Math.floor(p.y+radius);y++) {
    if((!walk.has(key(x,y))||scope==='lure'&&!allowedCell(s,x,y,scope,potential))&&rectDistance(p,[x,y,1,1])<radius-EPS)return false;
  }
  return walk.has(key(Math.floor(p.x),Math.floor(p.y)));
}
function lineOpen(s,a,b,radius=0) {
  const length=dist(a,b),n=Math.max(1,Math.ceil(length/.1));
  for(let i=0;i<=n;i++)if(!canOccupyWorld(s,{x:a.x+(b.x-a.x)*i/n,y:a.y+(b.y-a.y)*i/n},{radius}))return false;
  return true;
}
export function findWorldPath(s,from,to,{scope='all',potential=false}={}) {
  const a=pos(from),b=pos(to);if(!finitePoint(a)||!finitePoint(b))return null;
  const ax=Math.floor(a.x),ay=Math.floor(a.y),bx=Math.floor(b.x),by=Math.floor(b.y);
  if(!allowedCell(s,ax,ay,scope,potential)||!allowedCell(s,bx,by,scope,potential))return null;
  const start=key(ax,ay),goal=key(bx,by),queue=[[ax,ay]],previous=new Map([[start,null]]);
  for(let i=0;i<queue.length;i++) {
    const [x,y]=queue[i],k=key(x,y);if(k===goal)break;
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){const nx=x+dx,ny=y+dy,nk=key(nx,ny);if(!previous.has(nk)&&allowedCell(s,nx,ny,scope,potential)){previous.set(nk,k);queue.push([nx,ny]);}}
  }
  if(!previous.has(goal))return null;
  const path=[];let k=goal;while(k!==null){const [x,y]=k.split(',').map(Number);path.push({x:x+.5,y:y+.5});k=previous.get(k);}path.reverse();
  if(path.length===1) return [b];
  if(dist(a,path[0])<EPS||path.length>1&&lineOpen(s,a,path[1],s.radius))path.shift();
  return path;
}
function nearestInteriorTarget(s,target) {
  let best=null,bestD=Infinity;
  for(const k of grid(s)){const [x,y]=k.split(',').map(Number),p={x:x+.5,y:y+.5};if(!interior(s,p,s.radius))continue;const d=dist(p,target);if(d<bestD-EPS){best=p;bestD=d;}}
  return best;
}
function inExit(s,p) {const [x,y,w,h]=s.exitRect,r=s.radius;return p.x-r>=x-EPS&&p.y-r>=y-EPS&&p.x+r<=x+w+EPS&&p.y+r<=y+h+EPS;}
function active(s){return s.status==='active'&&!s.paused;}

export function createWorldState({maps,blueprints,mechanics,interactions,encounterId='F12',instanceId=`slice-${encounterId}`,playerStart,monsterStart,initialSan=80,doors={},freezer={}}) {
  if(!['F12','F13'].includes(encounterId))throw new RangeError('This world slice implements F12 and F13 only');
  if(typeof instanceId!=='string'||!instanceId.length)throw new TypeError('An encounter instance ID is required');
  const scene=copy(maps.scenes.find(x=>x.id==='MAP_STORE'));
  const blueprint=blueprints.encounters.find(x=>x.id===encounterId);
  if(!scene||!blueprint||!interactions?.work_templates?.find(x=>x.id==='W11'))throw new Error('Authored map, blueprint and W11 interaction are required');
  if(!Number.isFinite(initialSan)||initialSan<0||initialSan>100)throw new RangeError('SAN must be in 0..100');
  const anchors=Object.fromEntries(scene.anchors.map(a=>[a.role,pos(a.position)]));
  const entry=mechanics.entry_profiles.find(x=>x.id===(encounterId==='F12'?'EP_F12_RESERVED':'EP_F13_REAR'));
  const player=pos(playerStart??(encounterId==='F12'?scene.lure_route.tutorial_player_start:anchors.packing));
  const spawn=pos(monsterStart??entry.positions[0]);
  const s={version:'0.9',scope:'two_encounter_world_slice',scene,anchors,blueprint:copy(blueprint),baseline:copy(blueprints.baseline),attackConfig:copy(blueprints.shared_attack_proposal),
    radius:scene.rules.collision_radius_tiles,encounterId,instanceId,now:0,paused:false,status:'active',sequence:0,actionSequence:0,events:[],receipts:[],
    doorActionSeconds:interactions.work_templates.find(x=>x.id==='W11').base_operation_seconds,
    player:{...player,facing:{x:0,y:-1},facingLocked:false,path:[],direction:{x:0,y:0},carriedId:null,san:initialSan,collisionGraceUntil:0},
    monster:{...spawn,state:encounterId==='F12'?{mode:'CHASE_PLAYER',baitId:null,exitHold:0}:{mode:'SEEK_MEAT',instanceId,requiredMeatId:`${instanceId}:meat`,registeredFreezerId:`${instanceId}:freezer`},target:null,path:[],targetKey:null,nextDecisionAt:0,lastDecisionAt:0,nextReplanAt:0,attack:{mode:'idle',remaining:0,cooldownUntil:0}},
    doors:Object.fromEntries(scene.doors.map(d=>[d.id,{...d,open:d.default_open,operable:true,locked:false,...(doors[d.id]??{})}])),
    inventory:{paperclipCharges:0},supplies:{main:{id:`${instanceId}:clips-main`,position:copy(anchors.metal_shelf),remaining:1},backup:{id:`${instanceId}:clips-backup`,position:copy(anchors.metal_shelf),remaining:1}},
    baits:[],exitRect:copy(scene.lure_route.guaranteed_exit_rect),lureCorridorRect:null,action:null,
    meat:{id:`${instanceId}:meat`,...anchors.warehouse_meat,carrierId:null,storedIn:null},
    freezer:{id:`${instanceId}:freezer`,...anchors.freezer_main,functional:true,operable:true,reservedSpace:true,closed:false,...freezer},deliveryReceipts:[],admission:{ok:true,reasons:[]}};
  const frontRect=s.doors.DOOR_FRONT.rect,exitRect=s.exitRect;
  const left=Math.min(frontRect[0],exitRect[0]),top=Math.min(frontRect[1],exitRect[1]);
  s.lureCorridorRect=[left,top,Math.max(frontRect[0]+frontRect[2],exitRect[0]+exitRect[2])-left,Math.max(frontRect[1]+frontRect[3],exitRect[1]+exitRect[3])-top];
  const reasons=[];
  if(!canOccupyWorld(s,player)||!canOccupyWorld(s,spawn))reasons.push('blocked_start');
  if(!entry.positions.some(p=>dist(pos(p),spawn)<EPS))reasons.push('undeclared_spawn');
  if(dist(player,spawn)<entry.activation_min_distance_tiles-EPS)reasons.push('spawn_too_close');
  if(encounterId==='F12') {
    if(!findWorldPath(s,player,anchors.metal_shelf,{potential:true}))reasons.push('supply_unreachable');
    const front=s.doors.DOOR_FRONT;if(!front.open&&(!front.operable||front.locked))reasons.push('declared_exit_unavailable');
    if(!findWorldPath(s,anchors.metal_shelf,anchors.front_exit,{potential:true}))reasons.push('declared_exit_unreachable');
  }else{
    if(dist(spawn,s.meat)<=s.radius*2)reasons.push('spawn_overlaps_meat');
    if(s.freezer.id!==s.monster.state.registeredFreezerId)reasons.push('unregistered_freezer');
    if(!s.freezer.functional||!s.freezer.operable||!s.freezer.reservedSpace)reasons.push('required_freezer_unavailable');
    if(!findWorldPath(s,player,s.meat,{potential:true})||!findWorldPath(s,s.meat,s.freezer,{potential:true}))reasons.push('meat_route_unreachable');
  }
  if(reasons.length){s.status='unavailable';s.admission={ok:false,reasons};}
  return s;
}
export function setWorldPaused(s,paused){s.paused=Boolean(paused);return ok({paused:s.paused});}
export function setWorldFacingLock(s,locked){s.player.facingLocked=Boolean(locked);return ok({locked:s.player.facingLocked});}
export function setWorldResources(s,{san}){if(!Number.isFinite(san)||san<0||san>100)return no('invalid_san');s.player.san=san;return ok({san});}
export function cancelWorldAction(s,reason='player_cancelled') {if(!s.action)return no('no_action');emit(s,'action_cancelled',{actionId:s.action.id,actionType:s.action.type,reason});s.action=null;return ok({});}
export function setWorldMoveTarget(s,point) {
  if(s.paused||s.status==='unavailable')return no('world_not_running');
  const target=pos(point);if(!canOccupyWorld(s,target))return no('target_blocked');
  const path=findWorldPath(s,s.player,target);if(!path)return no('unreachable');
  if(s.action)cancelWorldAction(s,'movement');s.player.direction={x:0,y:0};s.player.path=path;return ok({path:copy(path)});
}
export function setWorldDirection(s,direction) {
  const d=pos(direction);if(!finitePoint(d))return no('invalid_direction');
  if(s.paused||s.status==='unavailable')return no('world_not_running');
  const length=Math.hypot(d.x,d.y);s.player.direction=length?{x:d.x/length,y:d.y/length}:{x:0,y:0};s.player.path=[];
  if(length&&s.action)cancelWorldAction(s,'movement');return ok({});
}
function actionCheck(s,cmd) {
  if(!active(s))return no('world_not_active');
  const p=s.player,range=s.baseline.interaction_distance;
  if(cmd.type==='take_clips') {
    if(s.encounterId!=='F12')return no('no_clip_task');if(p.carriedId)return no('hands_occupied');
    const which=s.supplies.main.remaining?'main':s.supplies.backup.remaining?'backup':null;
    if(!which)return no('supply_empty');const supply=s.supplies[which];
    if(dist(p,supply.position)>range+EPS||!lineOpen(s,p,supply.position))return no('too_far');
    return ok({seconds:which==='main'?s.blueprint.parameters.pickup_seconds:s.blueprint.parameters.backup_pickup_seconds,supplyKey:which});
  }
  if(cmd.type==='scatter') {
    if(s.encounterId!=='F12')return no('no_clip_task');if(p.carriedId)return no('hands_occupied');if(s.inventory.paperclipCharges<=0)return no('no_paperclips');
    if(s.baits.filter(b=>b.active&&b.expiresAt>s.now).length>=s.blueprint.parameters.max_active_bait_points)return no('bait_limit');
    if(!cmd.point)return no('choose_ground_point');const point=pos(cmd.point);
    if(!canOccupyWorld(s,point)||!lineOpen(s,p,point))return no('blocked_throw');
    if(dist(p,point)>s.blueprint.parameters.bait_place_distance+EPS)return no('too_far');
    if(!findWorldPath(s,s.monster,point,{scope:'lure'}))return no('bait_outside_declared_lure_route');
    return ok({seconds:s.blueprint.parameters.bait_place_seconds,point});
  }
  if(cmd.type==='take_meat') {
    if(s.encounterId!=='F13'||s.meat.storedIn||s.meat.carrierId)return no('meat_unavailable');if(p.carriedId)return no('hands_occupied');
    if(dist(p,s.meat)>range+EPS||!lineOpen(s,p,s.meat))return no('too_far');return ok({seconds:s.blueprint.parameters.pickup_seconds});
  }
  if(cmd.type==='drop_meat') {
    if(p.carriedId!==s.meat.id)return no('not_carrying_meat');const point=cmd.point?pos(cmd.point):{x:p.x,y:p.y};
    if(dist(p,point)>range+EPS||!canOccupyWorld(s,point)||!lineOpen(s,p,point))return no('invalid_drop');return ok({seconds:s.blueprint.parameters.drop_seconds,point});
  }
  if(cmd.type==='store_meat') {
    if(p.carriedId!==s.meat.id)return no('not_carrying_meat');if(dist(p,s.freezer)>range+EPS||!lineOpen(s,p,s.freezer))return no('too_far');
    if(!s.freezer.functional||!s.freezer.operable||!s.freezer.reservedSpace)return no('freezer_unavailable');return ok({seconds:s.blueprint.parameters.store_and_close_seconds});
  }
  if(cmd.type==='toggle_door') {
    const d=s.doors[cmd.doorId];if(!d)return no('unknown_door');if(!d.operable||d.locked)return no('door_unavailable');if(rectDistance(p,d.rect)>range+EPS)return no('too_far');
    if(d.open&&[p,s.monster].some(a=>rectDistance(a,d.rect)<s.radius+EPS))return no('door_occupied');return ok({seconds:s.doorActionSeconds,doorId:d.id,targetOpen:!d.open});
  }
  return no('unknown_action');
}
export function beginWorldAction(s,command) {
  if(s.action)return no('action_in_progress');const cmd=copy(command),check=actionCheck(s,cmd);if(!check.ok)return check;
  s.player.path=[];s.player.direction={x:0,y:0};s.action={...cmd,...check,id:`${s.instanceId}:action-${++s.actionSequence}`,remaining:check.seconds,startedAt:s.now,startPosition:{x:s.player.x,y:s.player.y}};
  emit(s,'action_started',{actionId:s.action.id,actionType:s.action.type,seconds:check.seconds});return ok({actionId:s.action.id,seconds:check.seconds});
}
function commitAction(s) {
  const a=s.action;if(!a)return;
  const check=actionCheck(s,a);if(!check.ok){cancelWorldAction(s,check.reason);return;}
  let detail={};
  if(a.type==='take_clips') {if(check.supplyKey!==a.supplyKey){cancelWorldAction(s,'source_changed');return;}s.supplies[a.supplyKey].remaining--;s.inventory.paperclipCharges+=s.blueprint.parameters.charges_per_box;detail={sourceId:s.supplies[a.supplyKey].id,charges:s.blueprint.parameters.charges_per_box};}
  if(a.type==='scatter') {
    const result=scatterPaperclips(s.inventory,{id:`bait-${a.id}`,now:s.now,player:s.player,point:a.point,legalCell:true,reachable:true,clearThrow:true,handsOccupied:false,activeBaitCount:s.baits.filter(b=>b.active&&b.expiresAt>s.now).length},s.blueprint.parameters);
    if(!result.ok){cancelWorldAction(s,result.reason);return;}s.inventory=result.inventory;s.baits.push(result.bait);detail={baitId:result.bait.id,point:copy(a.point)};
  }
  if(a.type==='take_meat'){s.meat.carrierId='player';s.meat.x=s.player.x;s.meat.y=s.player.y;s.player.carriedId=s.meat.id;detail={itemId:s.meat.id};}
  if(a.type==='drop_meat'){s.meat.carrierId=null;s.player.carriedId=null;Object.assign(s.meat,a.point);detail={itemId:s.meat.id,point:copy(a.point)};}
  if(a.type==='store_meat') {
    const result=storeTaskMeat({...s,encounterInstanceId:s.instanceId},s.meat.id,s.freezer.id);
    if(!result.ok){cancelWorldAction(s,result.reason);return;}
    s.meat=result.world.meat;s.freezer=result.world.freezer;s.deliveryReceipts=result.world.deliveryReceipts;s.player.carriedId=null;detail={itemId:s.meat.id,containerId:s.freezer.id};
  }
  if(a.type==='toggle_door') {s.doors[a.doorId].open=a.targetOpen;s.player.path=[];s.monster.path=[];s.monster.targetKey=null;detail={doorId:a.doorId,open:a.targetOpen};}
  s.action=null;const r=emit(s,'action_completed',{actionId:a.id,actionType:a.type,worldSeconds:a.seconds,...detail});s.receipts.push(r);
}
function stepActor(s,actor,path,speed,dt,scope='all') {
  let remaining=speed*dt,total=0;
  while(remaining>EPS&&path.length){const p=path[0],d=dist(actor,p);if(d<EPS){path.shift();continue;}const n=Math.min(remaining,d),next={x:actor.x+(p.x-actor.x)*n/d,y:actor.y+(p.y-actor.y)*n/d};
    if(!canOccupyWorld(s,next,{scope})){path.length=0;break;}
    if(actor===s.player&&!actor.facingLocked)actor.facing={x:(p.x-actor.x)/d,y:(p.y-actor.y)/d};actor.x=next.x;actor.y=next.y;remaining-=n;total+=n;if(n>=d-EPS)path.shift();}
  return total;
}
function movePlayer(s,dt) {
  if(s.action)return 0;const p=s.player,speed=p.carriedId===s.meat.id?s.baseline.carrying_meat_walk_speed:s.baseline.player_walk_speed;
  if(p.path.length)return stepActor(s,p,p.path,speed,dt);
  const d=p.direction;if(!d.x&&!d.y)return 0;
  const old={x:p.x,y:p.y};if(!p.facingLocked)p.facing={...d};
  for(const axis of ['x','y']){const n={x:p.x,y:p.y};n[axis]+=d[axis]*speed*dt;if(canOccupyWorld(s,n)){p.x=n.x;p.y=n.y;}}
  return dist(old,p);
}
function synchronizeMonster(s,dt) {
  const m=s.monster;if(s.status!=='active')return;
  let result;
  if(s.encounterId==='F12') {
    for(const b of s.baits)b.reachable=b.active&&!!findWorldPath(s,m,b,{scope:'lure'});
    const b=s.baits.find(x=>x.id===m.state.baitId&&x.active&&x.expiresAt>s.now);
    result=stepF12(m.state,{monster:m,player:s.player,now:s.now,baits:s.baits,wholeBodyInExitZone:inExit(s,m),reachedBaitId:b&&dist(m,b)<.05?b.id:null},s.blueprint.parameters,dt);
  } else result=stepF13(m.state,{...s,encounterInstanceId:s.instanceId,touchingMeat:!s.meat.storedIn&&dist(m,s.meat)<=s.radius*2+EPS},s.blueprint.parameters,dt);
  const oldTarget=m.target?`${m.target.kind}:${m.target.id??''}`:null,newTarget=result.target?`${result.target.kind}:${result.target.id??''}`:null;
  if(oldTarget!==newTarget){m.path=[];m.targetKey=null;}
  m.state=result.state;m.target=result.target;m.canAttack=result.canAttack;m.navigationScope=result.navigationScope;
  for(const e of result.events){if(e.type==='consume_bait'){const b=s.baits.find(x=>x.id===e.id);if(b)b.active=false;}if(e.type==='encounter_cleared'){s.status='cleared';s.action=null;m.path=[];m.attack={mode:'idle',remaining:0,cooldownUntil:0};}const receipt=emit(s,e.type,{monsterId:s.encounterId,...(e.type==='consume_bait'?{baitId:e.id}:{})});if(e.type==='encounter_cleared')s.receipts.push(receipt);}
}
function moveMonster(s,dt) {
  const m=s.monster;if(s.status!=='active'||!m.target)return;
  let scope=m.navigationScope==='store_interior_only'?'interior':s.encounterId==='F12'?'lure':'all';
  let target=m.target.kind==='player'?s.player:m.target.kind==='meat'?s.meat:s.baits.find(b=>b.id===m.target.id);
  if(!target)return;
  if(scope==='interior'&&!interior(s,m,s.radius)){target=s.anchors.front_door;scope='lure';}
  else if(scope==='interior'&&!interior(s,target,s.radius))target=nearestInteriorTarget(s,target);
  if(!target)return;
  const tk=`${m.target.kind}:${m.target.id??''}:${Math.floor(target.x)},${Math.floor(target.y)}:${scope}`;
  if(m.targetKey!==tk&&s.now+EPS>=m.nextReplanAt){m.path=findWorldPath(s,m,target,{scope})??[];m.targetKey=tk;m.nextReplanAt=s.now+1/s.baseline.max_path_replans_per_second;}
  if(!m.path.length&&dist(m,target)>.05&&s.now+EPS>=m.nextReplanAt){m.path=findWorldPath(s,m,target,{scope})??[];m.nextReplanAt=s.now+1/s.baseline.max_path_replans_per_second;}
  stepActor(s,m,m.path,s.baseline.monster_move_speed,dt,scope);
}
function updateAttack(s,dt) {
  const m=s.monster,a=m.attack,c=s.attackConfig;
  if(s.status!=='active'||!m.canAttack||s.encounterId==='F12'&&!interior(s,m,s.radius)){if(a.mode==='windup')emit(s,'attack_cancelled',{});a.mode='idle';return;}
  if(a.mode==='windup') {
    a.remaining-=dt;if(a.remaining>EPS)return;a.mode='idle';a.cooldownUntil=s.now+c.attack_cooldown_seconds;
    if(dist(m,s.player)<=c.hit_check_distance+EPS&&lineOpen(s,m,s.player)) {
      const before=s.player.san,result=applySharedHit(s.player,s.now,c);if(result.applied){s.player=result.actor;emit(s,'hit',{sanDelta:s.player.san-before,sanAfter:s.player.san,injury:'minor',collisionGraceUntil:s.player.collisionGraceUntil});}
    }else emit(s,'attack_missed',{});
  }else if(s.now+EPS>=a.cooldownUntil&&dist(m,s.player)<=c.windup_start_distance+EPS&&lineOpen(s,m,s.player)) {
    a.mode='windup';a.remaining=c.telegraph_seconds;emit(s,'attack_telegraph',{seconds:c.telegraph_seconds});
  }
}
export function advanceWorld(s,dt) {
  if(!Number.isFinite(dt)||dt<0||dt>10)throw new RangeError('World step must be in 0..10 seconds');
  if(s.paused||s.status==='unavailable')return {advancedSeconds:0,actualMovedTiles:0,events:[]};
  const start=s.events.length;let left=dt,moved=0;
  while(left>EPS){const h=Math.min(.05,left);s.now+=h;left-=h;
    for(const b of s.baits)if(b.active&&b.expiresAt<=s.now+EPS){b.active=false;emit(s,'bait_expired',{baitId:b.id});}
    moved+=movePlayer(s,h);if(s.meat.carrierId==='player'){s.meat.x=s.player.x;s.meat.y=s.player.y;}
    if(s.action){s.action.remaining-=h;if(s.action.remaining<=EPS)commitAction(s);}
    if(s.status==='active'&&s.encounterId==='F13'&&s.deliveryReceipts.length)synchronizeMonster(s,0);
    if(s.status==='active'&&s.now+EPS>=s.monster.nextDecisionAt){synchronizeMonster(s,s.now-s.monster.lastDecisionAt);s.monster.lastDecisionAt=s.now;s.monster.nextDecisionAt=s.now+1/s.baseline.ai_decision_hz;}
    moveMonster(s,h);updateAttack(s,h);
  }
  return {advancedSeconds:dt,actualMovedTiles:moved,events:s.events.slice(start)};
}
export function worldInteractionOptions(s) {
  const commands=s.encounterId==='F12'?[{type:'take_clips',label:s.supplies.main.remaining?'取回形针':'取备用回形针'},{type:'scatter',label:'洒回形针',requiresPoint:true}]:[{type:'take_meat',label:'取登记生肉'},{type:'drop_meat',label:'放下生肉'},{type:'store_meat',label:'存入并关柜'}];
  for(const d of Object.values(s.doors))if(rectDistance(s.player,d.rect)<=s.baseline.interaction_distance+EPS)commands.push({type:'toggle_door',doorId:d.id,label:(d.open?'关闭':'打开')+d.name});
  return commands.map(cmd=>{const r=actionCheck(s,cmd);return {...cmd,enabled:!s.action&&(r.ok||cmd.requiresPoint&&r.reason==='choose_ground_point'),reason:s.action?'action_in_progress':r.reason,seconds:r.seconds??(cmd.type==='scatter'?s.blueprint.parameters.bait_place_seconds:undefined)};});
}
