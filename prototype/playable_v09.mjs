import * as Session from './practice_session_core_v09.mjs';
import * as World from './world_core_v09.mjs';
import * as Cycle from './day_cycle_core_v09.mjs';
import {sanProfile} from './rule_core.mjs';

const D=window.MIDNIGHT_DATA,$=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cases={F12:{number:'01',title:'门外的金属声',hour:1,phase:'验货与补货',task:'让它自己走出去',
  intro:'先到文具架取回形针，再逐点洒向正门外。它追的是地上的金属声。',
  steps:['走到文具架，取一盒回形针。','每次洒少量，留出通往正门的路。','继续把金属声引向门外雨棚。'],
  omen:'金属碰撞声，正从货架另一侧传来。'},
 F13:{number:'02',title:'不要碰那箱生肉',hour:2,phase:'热食与冷链',task:'把原来的肉放回冷处',
  intro:'库房有一箱登记生肉。把它搬进主冰柜并关盖；提前处理也能安全结束。',
  steps:['沿过道前往库房，取登记生肉。','保持移动，运到熟食区的主冰柜。','存入同一箱肉，并真正关好柜盖。'],
  omen:'后门的铃响了一声。库房还有一箱生肉。'}};
const reasonText={too_far:'再靠近一点，距离需要在1格内。',target_blocked:'这里是货架或墙，请选择过道。',unreachable:'这条路目前不通，先检查门。',blocked_throw:'这片地面被挡住了，换一个能看见的空地。',no_paperclips:'先到文具架取回形针。',bait_limit:'场上最多保留3堆，等它处理一堆再洒。',supply_empty:'主盒与备用盒都已取完。',hands_occupied:'先放下手里的物件。',action_in_progress:'动作正在进行；移动可以中断。',not_carrying_meat:'需要先拿到那箱登记生肉。',freezer_unavailable:'冰柜现在无法接收这箱肉。',door_occupied:'有人正在门槛上，请先让开。',world_not_running:'先开始或继续练习。',exercise_not_running:'先开始或继续练习。',no_active_panic:'SAN归零后，才需要使用这次应急安定。',night_stabilization_spent:'本轮免费安定已经使用。',actual_world_action_in_progress:'先结束手中的工作，再安定呼吸。',daily_bundle_already_claimed:'今天的工作餐已经领过了。',not_in_six_day_slots:'当前已经不在白天行动时段。',shop_item_unavailable:'20:00进入采购时段后，才能购买补给。',insufficient_coins:'金币不足。',mint_encounter_limit:'同一遭遇最多使用两份薄荷糖。',actual_verified_unreserved_item_required:'需要一份已核验、未使用且未被任务占用的原物。',item_needs_its_own_safe_world_action:'这份物品需要自己的安全工位操作，本练习快捷栏暂不使用。',no_new_case_or_source:'没有新的实际记录可整理。'};
let saved=false,saveBlocked=false,sequence=0,session,day,aim=false,currentCase='F12',dialogKind=null,resumeAfterDialog=false;
let camera={x:7.5,y:12},lastFrame=0,lastHud=0,toastUntil=0,terminalShown=false,activeCommand=null;
const pointerDirs=new Map(),keys=new Set(),canvas=$('world'),ctx=canvas.getContext('2d'),mini=$('minimap'),mctx=mini.getContext('2d');
const STORAGE='midnight-mart-v09-day-plan';
function command(prefix){return `${prefix}-${Date.now()}-${++sequence}`;}
function newDay(){return Cycle.createDayCycleState(D.balance,D.items,{runId:'personal-day-plan',absoluteGameMinute:480});}
try{const data=localStorage.getItem(STORAGE);day=data?Cycle.restoreDayCycle(data):newDay();saved=Boolean(data);}catch{day=newDay();saveBlocked=true;}
function saveDay(){try{localStorage.setItem(STORAGE,Cycle.serializeDayCycle(day));saved=true;}catch{saveBlocked=true;}}
function toast(message){$('toast').textContent=message;$('toast').classList.add('show');toastUntil=performance.now()+2600;}
function report(r){if(!r?.ok){toast(reasonText[r?.reason]??'当前条件还不满足，请检查物件、距离和时间。');return false;}return true;}
function remainingInventory(state){return Object.values(state.inventory).filter(i=>i.owned&&!i.consumed&&!i.reservedBy);}
function startCase(id){
  currentCase=id;aim=false;terminalShown=false;pointerDirs.clear();keys.clear();
  session=Session.createPracticeSession(D,day,{caseId:id,runId:command(`exercise-${id}`),paused:true});
  camera={x:session.world.player.x-6,y:session.world.player.y-7.5};
  document.querySelectorAll('[data-case]').forEach(b=>b.classList.toggle('selected',b.dataset.case===id));
  $('task-title').textContent=cases[id].task;$('task-steps').innerHTML=cases[id].steps.map(s=>`<li>${esc(s)}</li>`).join('');
  $('omen').textContent=cases[id].omen;$('omen').classList.remove('danger');$('aim-note').hidden=true;
  showOverlay('ready');renderHud();draw();lastFrame=0;
}
function showOverlay(kind){
  const c=cases[currentCase];$('overlay').hidden=false;
  $('overlay-kicker').textContent=kind==='ready'?`夜班培训 / ${c.number}`:kind==='paused'?'PAUSED / 暂停':'值班记录';
  $('overlay-title').textContent=kind==='ready'?c.title:kind==='paused'?'稍作停留':kind==='cleared'?'这一次，平安收场。':'本轮练习结束';
  $('overlay-text').textContent=kind==='ready'?c.intro:kind==='paused'?'店内时间已暂停。准备好了，就继续刚才的操作。':kind==='cleared'?`实际操作完成，用时${session.world.now.toFixed(1)}秒。${currentCase==='F12'?'它已经完整走进门外区域。':'同一箱生肉已经存入冰柜，柜盖关闭。'}`:session.terminalReceipt?.reason==='panic_expired'?'恐慌没有及时缓解。下次SAN归零后，可边走边完成8秒安定。':'本轮时间已经用尽。可以查看店规，再试一次。';
  $('overlay-start').innerHTML=kind==='cleared'?`${currentCase==='F12'?'练习冷链搬运':'再试一次'} <span>→</span>`:kind==='failed'?'重新开始 <span>↻</span>':'继续实操 <span>→</span>';
  if(kind==='ready')$('overlay-start').innerHTML='开始实操 <span>→</span>';
  $('overlay-start').dataset.kind=kind;
  $('overlay-hint').textContent=kind==='cleared'?'练习不发放正式工资，也不改变日间资产。':'点击地面 / 方向键移动 · E交互 · F投放 · 空格暂停';
}
function resume(){if(session.status!=='active')return;Session.setPracticePaused(session,false);$('overlay').hidden=true;lastFrame=0;}
function togglePause(){if(dialogKind||session.status!=='active')return;if(session.paused)resume();else{Session.setPracticePaused(session,true);showOverlay('paused');}renderHud();}
$('overlay-start').onclick=()=>{const kind=$('overlay-start').dataset.kind;if(kind==='cleared'){startCase(currentCase==='F12'?'F13':currentCase);resume();}else if(kind==='failed'){startCase(currentCase);resume();}else resume();};
$('pause').onclick=togglePause;$('retry').onclick=()=>startCase(currentCase);
document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>startCase(b.dataset.case));
function objective(){const w=session.world;if(currentCase==='F12')return w.inventory.paperclipCharges>0?w.anchors.front_exit:w.anchors.metal_shelf;return w.player.carriedId?w.freezer:w.meat;}
function zone(){const p=session.world.player;return session.world.scene.zones.find(z=>p.x>=z.rect[0]&&p.x<z.rect[0]+z.rect[2]&&p.y>=z.rect[1]&&p.y<z.rect[1]+z.rect[3])?.name??(p.y>=30?'门店前空地':p.y<0?'后门垃圾区':'东侧装卸通道');}
function renderHud(){
  const p=Session.practiceSnapshot(session),w=session.world,c=cases[currentCase],r=p.resources;
  $('shift-label').textContent=`${String(c.hour+Math.floor(p.budget/120)).padStart(2,'0')}:${String(Math.floor(p.budget/2)%60).padStart(2,'0')}`;
  $('shift-name').textContent=c.phase;$('pause').textContent=session.paused?'▷':'Ⅱ';$('pause').setAttribute('aria-label',session.paused?'继续':'暂停');
  $('resources').innerHTML=[['energy','精力'],['san','SAN'],['satiety','饱腹'],['stamina','体力']].map(([k,n])=>`<div class="resource ${k} ${r[k]<25?'low':''}"><div><span>${n}</span><b>${Math.max(0,Math.round(r[k]))}</b></div><i><span style="width:${Math.max(0,Math.min(100,r[k]))}%"></span></i></div>`).join('');
  $('zone-label').textContent=zone();$('remaining').textContent=`本轮余时 ${Math.ceil(p.remaining)}秒`;
  $('carry').textContent=w.player.carriedId?'手持：登记生肉 · 搬运中':currentCase==='F12'?`回形针 ${w.inventory.paperclipCharges}份 · 双手空闲`:'双手空闲';
  const choices=World.worldInteractionOptions(w).filter(x=>x.type!=='scatter'&&x.type!=='drop_meat');
  activeCommand=choices.find(x=>x.enabled&&!(x.type==='take_clips'&&w.inventory.paperclipCharges>0))??null;
  $('interact').textContent=w.action?'操作中…':activeCommand?.label??(currentCase==='F12'?(w.inventory.paperclipCharges?'走向正门外':'靠近文具架'):(w.player.carriedId?'靠近主冰柜':'靠近登记生肉'));
  $('interact').disabled=!activeCommand||session.paused||session.status!=='active';
  $('secondary').textContent=currentCase==='F12'?(aim?'点选地面':'洒回形针'):'放下生肉';$('secondary').classList.toggle('active',aim);
  $('secondary').disabled=session.paused||session.status!=='active'||Boolean(w.action)||(currentCase==='F12'?w.inventory.paperclipCharges<=0:!w.player.carriedId);
  $('facing').classList.toggle('active',w.player.facingLocked);$('facing').setAttribute('aria-pressed',String(w.player.facingLocked));
  $('stabilize').disabled=!p.panic.active||p.panic.used||session.paused||session.status!=='active';
  $('stabilize').textContent=p.panic.stabilizing?`安定 ${Math.floor(p.panic.progress)}/8秒`:'安定呼吸';
  $('bag-count').textContent=String(remainingInventory(session.resources).length);
  $('work-progress').hidden=!w.action&&!p.panic.stabilizing;
  if(w.action){$('work-label').textContent=({take_clips:'取出回形针',scatter:'洒下回形针',take_meat:'拿起登记生肉',drop_meat:'放下原物',store_meat:'入柜并合盖',toggle_door:'操作门'}[w.action.type]??'操作中');$('work-fill').style.width=`${100*(1-w.action.remaining/w.action.seconds)}%`;}
  else if(p.panic.stabilizing){$('work-label').textContent='保持呼吸 · 可以步行';$('work-fill').style.width=`${p.panic.progress/8*100}%`;}
  const lis=$('task-steps').children;
  if(currentCase==='F12'){lis[0]?.classList.toggle('done',w.supplies.main.remaining===0);lis[1]?.classList.toggle('done',w.receipts.filter(x=>x.actionType==='scatter').length>=2);lis[2]?.classList.toggle('done',w.status==='cleared');}
  else{lis[0]?.classList.toggle('done',Boolean(w.player.carriedId)||Boolean(w.meat.storedIn));lis[1]?.classList.toggle('done',Boolean(w.meat.storedIn)||Boolean(w.player.carriedId)&&Math.hypot(w.player.x-w.freezer.x,w.player.y-w.freezer.y)<1.1);lis[2]?.classList.toggle('done',w.status==='cleared');}
  if(p.panic.active){$('omen').textContent=`SAN归零：还剩${Math.max(0,Math.ceil(p.panic.deadline-p.world))}秒。可边走边安定，工作或受击会打断。`;$('omen').classList.add('danger');}
  else if(w.status==='cleared'){$('omen').textContent='危险已经解除。请确认自己的状态。';$('omen').classList.remove('danger');}
}
$('interact').onclick=()=>{if(activeCommand&&report(Session.startPracticeAction(session,activeCommand))){aim=false;$('aim-note').hidden=true;}renderHud();};
function secondary(){if(currentCase==='F12'){if($('secondary').disabled)return;aim=!aim;$('aim-note').hidden=!aim;}else report(Session.startPracticeAction(session,{type:'drop_meat'}));renderHud();}
$('secondary').onclick=secondary;$('aim-cancel').onclick=()=>{aim=false;$('aim-note').hidden=true;renderHud();};
$('facing').onclick=()=>{Session.setPracticeFacingLock(session,!session.world.player.facingLocked);renderHud();};
$('stabilize').onclick=()=>{report(Session.startPracticeStabilization(session));renderHud();};
function updateDirection(){let x=0,y=0;for(const d of pointerDirs.values()){x+=d.x;y+=d.y;}if(keys.has('ArrowLeft')||keys.has('a'))x--;if(keys.has('ArrowRight')||keys.has('d'))x++;if(keys.has('ArrowUp')||keys.has('w'))y--;if(keys.has('ArrowDown')||keys.has('s'))y++;if(session.status==='active'&&!session.paused)Session.directPracticeMovement(session,{x,y});}
document.querySelectorAll('[data-dir]').forEach(b=>{const [x,y]=b.dataset.dir.split(',').map(Number);b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);pointerDirs.set(e.pointerId,{x,y});b.classList.add('pressed');updateDirection();});const release=e=>{pointerDirs.delete(e.pointerId);b.classList.remove('pressed');updateDirection();};for(const event of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(event,release);});
document.addEventListener('keydown',e=>{if(dialogKind){if(e.key==='Escape')closeDialog();return;}const k=e.key.length===1?e.key.toLowerCase():e.key;if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','w','a','s','d'].includes(k)){e.preventDefault();keys.add(k);updateDirection();}else if(!e.repeat){if(k===' '){e.preventDefault();togglePause();}if(k==='e')$('interact').click();if(k==='f')secondary();if(k==='q')$('facing').click();if(k==='Escape')togglePause();}});
document.addEventListener('keyup',e=>{const k=e.key.length===1?e.key.toLowerCase():e.key;if(keys.delete(k))updateDirection();});
canvas.addEventListener('pointerdown',e=>{e.preventDefault();if(session.paused||session.status!=='active')return;const rect=canvas.getBoundingClientRect(),point={x:camera.x+(e.clientX-rect.left)/rect.width*12,y:camera.y+(e.clientY-rect.top)/rect.height*15};if(aim){if(report(Session.startPracticeAction(session,{type:'scatter',point}))){aim=false;$('aim-note').hidden=true;}}else report(Session.movePracticeTo(session,point));renderHud();});
window.addEventListener('blur',()=>{pointerDirs.clear();keys.clear();if(session?.status==='active'&&!session.paused){Session.setPracticePaused(session,true);showOverlay('paused');}});
document.addEventListener('visibilitychange',()=>{if(document.hidden){saveDay();pointerDirs.clear();keys.clear();if(session?.status==='active'){Session.setPracticePaused(session,true);showOverlay('paused');}}});

function rect(g,x,y,w,h,color){g.fillStyle=color;g.fillRect(x,y,w,h);}
function round(g,x,y,w,h,r,color){g.beginPath();g.roundRect(x,y,w,h,r);g.fillStyle=color;g.fill();}
function label(g,text,x,y,size,color='#bdcab5',align='center'){g.font=`500 ${size}px "Noto Sans CJK SC",sans-serif`;g.fillStyle=color;g.textAlign=align;g.textBaseline='middle';g.fillText(text,x,y);}
function drawScene(g,w,tile,origin,small=false){
  const X=x=>(x-origin.x)*tile,Y=y=>(y-origin.y)*tile;
  for(const surface of w.scene.walk_surfaces){const [x,y,a,b]=surface.rect;rect(g,X(x),Y(y),a*tile,b*tile,surface.id==='floor'?'#26392e':'#14281f');}
  for(const z of w.scene.zones){const [x,y,a,b]=z.rect;const colors={Z01:'#304532',Z02:'#293e2e',Z03:'#263f3d',Z04:'#3e4030',Z05:'#343c37'};rect(g,X(x),Y(y),a*tile,b*tile,colors[z.id]??'#30402e');}
  if(!small){g.strokeStyle='#cad4af09';g.lineWidth=1;g.beginPath();for(let x=Math.floor(origin.x);x<origin.x+12;x++){g.moveTo(X(x),0);g.lineTo(X(x),15*tile);}for(let y=Math.floor(origin.y);y<origin.y+15;y++){g.moveTo(0,Y(y));g.lineTo(12*tile,Y(y));}g.stroke();}
  for(const f of w.scene.fixtures){const [x,y,a,b]=f.rect;if(small){rect(g,X(x),Y(y),a*tile,b*tile,'#67725a');continue;}round(g,X(x)+1,Y(y)+3,a*tile-2,b*tile-1,2,'#17271e');const cold=/冰|冷/.test(f.name);round(g,X(x)+2,Y(y)+1,a*tile-4,b*tile-5,2,cold?'#647f73':'#626c4d');rect(g,X(x)+3,Y(y)+2,a*tile-6,3,'#b7b98a55');if(/货架|文具|食品|饮料/.test(f.name)){for(let ix=.25;ix<a-.15;ix+=.45)for(let iy=.3;iy<b-.1;iy+=.55){const palette=['#bfa270','#8c9f72','#9a6655','#79928a'];rect(g,X(x+ix),Y(y+iy),tile*.23,tile*.28,palette[(Math.round(ix*4+iy*3)+f.id.length)%4]);}}else{g.strokeStyle='#cad8b52b';g.strokeRect(X(x)+6,Y(y)+6,Math.max(2,a*tile-12),Math.max(2,b*tile-15));}}
  for(const wall of w.scene.walls){const [x,y,a,b]=wall.rect;rect(g,X(x),Y(y),a*tile,b*tile,'#112017');if(!small)rect(g,X(x),Y(y),a*tile,Math.min(4,b*tile),'#718263');}
  for(const door of Object.values(w.doors)){const [x,y,a,b]=door.rect;rect(g,X(x),Y(y),a*tile,b*tile,door.open?'#75865c33':'#855b45');g.strokeStyle=door.open?'#a1b38c':'#daa27d';g.lineWidth=small?1:2;g.strokeRect(X(x)+1,Y(y)+1,a*tile-2,b*tile-2);}
  if(!small){
    const er=w.exitRect;g.strokeStyle='#d3bd764d';g.setLineDash([tile*.22,tile*.25]);g.strokeRect(X(er[0]),Y(er[1]),er[2]*tile,er[3]*tile);g.setLineDash([]);label(g,'门 外 雨 棚',X(15),Y(35.4),tile*.27,'#aab994');
    for(const [role,name] of [['metal_shelf','文具架'],['warehouse_meat','库房'],['freezer_main','主冰柜'],['cashier','收银台'],['verification_desk','核验台']]){const p=w.anchors[role];if(p&&p.x>=origin.x-2&&p.x<=origin.x+14&&p.y>=origin.y-2&&p.y<=origin.y+17)label(g,name,X(p.x),Y(p.y-.65),tile*.29,'#cad5b0');}
  }
}
function draw(){
  if(!session)return;const w=session.world,player=w.player;
  camera={x:Math.max(-.6,Math.min(22.6,player.x-6)),y:Math.max(-8.5,Math.min(23.5,player.y-7.5))};
  const tile=canvas.width/12,X=x=>(x-camera.x)*tile,Y=y=>(y-camera.y)*tile;
  ctx.clearRect(0,0,canvas.width,canvas.height);rect(ctx,0,0,canvas.width,canvas.height,'#0b1711');drawScene(ctx,w,tile,camera);
  if(player.path.length){ctx.beginPath();ctx.moveTo(X(player.x),Y(player.y));for(const p of player.path)ctx.lineTo(X(p.x),Y(p.y));ctx.strokeStyle='#e2ca7d55';ctx.setLineDash([3,6]);ctx.lineWidth=2;ctx.stroke();ctx.setLineDash([]);}
  if(aim){ctx.beginPath();ctx.arc(X(player.x),Y(player.y),tile*1.5,0,Math.PI*2);ctx.fillStyle='#e7c68312';ctx.fill();ctx.strokeStyle='#e7c6839f';ctx.setLineDash([4,4]);ctx.stroke();ctx.setLineDash([]);}
  for(const b of w.baits.filter(b=>b.active&&b.expiresAt>w.now)){ctx.save();ctx.translate(X(b.x),Y(b.y));ctx.strokeStyle='#d7dbb6';ctx.lineWidth=1.8;for(let i=0;i<4;i++){ctx.beginPath();ctx.ellipse((i-1.5)*3,Math.sin(i)*3,2,4,i*.8,0,Math.PI*2);ctx.stroke();}ctx.restore();}
  if(currentCase==='F12'){const p=w.anchors.metal_shelf;round(ctx,X(p.x)-tile*.23,Y(p.y)-tile*.2,tile*.46,tile*.4,2,w.supplies.main.remaining||w.supplies.backup.remaining?'#c1b781':'#55664c');label(ctx,'⌁',X(p.x),Y(p.y),tile*.35,'#34452b');}
  else if(!w.meat.storedIn&&!w.meat.carrierId){round(ctx,X(w.meat.x)-tile*.34,Y(w.meat.y)-tile*.28,tile*.68,tile*.56,3,'#b48c69');rect(ctx,X(w.meat.x)-tile*.07,Y(w.meat.y)-tile*.28,tile*.14,tile*.56,'#d8cda1');label(ctx,'冷',X(w.meat.x),Y(w.meat.y),tile*.23,'#32432a');}
  const target=objective();ctx.beginPath();ctx.arc(X(target.x),Y(target.y),tile*.48,0,Math.PI*2);ctx.strokeStyle='#b4dbbd77';ctx.lineWidth=1;ctx.stroke();
  if(w.status!=='cleared'){
    const m=w.monster,mx=X(m.x),my=Y(m.y);ctx.save();ctx.translate(mx,my);ctx.shadowColor=currentCase==='F12'?'#c8a45c':'#c99c8d';ctx.shadowBlur=tile*.2;
    if(m.attack.mode==='windup'||m.state.mode==='RAGE_WINDUP'){ctx.beginPath();ctx.arc(0,0,tile*.8,0,Math.PI*2);ctx.strokeStyle='#e49b735e';ctx.lineWidth=3;ctx.stroke();}
    if(currentCase==='F12'){ctx.beginPath();ctx.ellipse(0,0,tile*.36,tile*.46,0,0,Math.PI*2);ctx.fillStyle='#322d1c';ctx.fill();ctx.strokeStyle='#8c8150';ctx.lineWidth=2;ctx.stroke();rect(ctx,-tile*.16,-tile*.15,tile*.075,tile*.07,'#e5ca77');rect(ctx,tile*.09,-tile*.15,tile*.075,tile*.07,'#e5ca77');ctx.strokeStyle='#a2a275';ctx.beginPath();ctx.moveTo(-tile*.24,-tile*.3);ctx.lineTo(-tile*.33,-tile*.55);ctx.moveTo(tile*.24,-tile*.3);ctx.lineTo(tile*.33,-tile*.55);ctx.stroke();}
    else{ctx.beginPath();ctx.ellipse(0,0,tile*.37,tile*.49,0,0,Math.PI*2);ctx.fillStyle='#1c211e';ctx.fill();ctx.beginPath();ctx.ellipse(0,-tile*.04,tile*.22,tile*.29,0,0,Math.PI*2);ctx.fillStyle='#d4c9a4';ctx.fill();rect(ctx,-tile*.12,-tile*.09,tile*.065,tile*.045,'#4b352c');rect(ctx,tile*.06,-tile*.09,tile*.065,tile*.045,'#4b352c');ctx.strokeStyle='#a66d56';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,tile*.3);ctx.bezierCurveTo(tile*.3,tile*.5,-tile*.25,tile*.65,0,tile*.8);ctx.stroke();}
    ctx.restore();
  }
  ctx.save();ctx.translate(X(player.x),Y(player.y));ctx.fillStyle='#0005';ctx.beginPath();ctx.ellipse(1,tile*.22,tile*.27,tile*.16,0,0,Math.PI*2);ctx.fill();ctx.rotate(Math.atan2(player.facing.y,player.facing.x)+Math.PI/2);round(ctx,-tile*.22,-tile*.07,tile*.44,tile*.44,3,'#cfc692');rect(ctx,-tile*.18,tile*.02,tile*.36,tile*.23,'#859f7a');ctx.beginPath();ctx.arc(0,-tile*.13,tile*.17,0,Math.PI*2);ctx.fillStyle='#e5d7ac';ctx.fill();ctx.strokeStyle='#ecddb3';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,-tile*.37);ctx.lineTo(-tile*.09,-tile*.26);ctx.moveTo(0,-tile*.37);ctx.lineTo(tile*.09,-tile*.26);ctx.stroke();if(player.carriedId)round(ctx,-tile*.26,-tile*.52,tile*.52,tile*.32,2,'#b8936b');ctx.restore();
  const band=sanProfile(session.condition.san,D.qte);if(band.outside_opacity>0){const radius=band.clear_radius_tiles*tile,gradient=ctx.createRadialGradient(X(player.x),Y(player.y),radius*.75,X(player.x),Y(player.y),radius);gradient.addColorStop(0,'#00000000');gradient.addColorStop(1,`rgba(2,9,5,${band.outside_opacity})`);ctx.fillStyle=gradient;ctx.fillRect(0,0,canvas.width,canvas.height);}
  drawMinimap();
}
function drawMinimap(){const w=session.world,scale=5.7,origin={x:-5.5,y:-11};mctx.clearRect(0,0,mini.width,mini.height);rect(mctx,0,0,mini.width,mini.height,'#142019');drawScene(mctx,w,scale,origin,true);mctx.strokeStyle='#d7c48b88';mctx.lineWidth=1;mctx.strokeRect((camera.x-origin.x)*scale,(camera.y-origin.y)*scale,12*scale,15*scale);for(const [p,color,r] of [[w.player,'#efd295',3.4],[objective(),'#a7d8c3',2.8]]){mctx.fillStyle=color;mctx.beginPath();mctx.arc((p.x-origin.x)*scale,(p.y-origin.y)*scale,r,0,Math.PI*2);mctx.fill();}}

function openDialog(kind){resumeAfterDialog=!session.paused&&session.status==='active';Session.setPracticePaused(session,true);dialogKind=kind;$('dialog-backdrop').hidden=false;if(kind==='rules')renderRules();if(kind==='day')renderDay();if(kind==='bag')renderBag();$('dialog-close').focus();}
function closeDialog(){const resumeIt=resumeAfterDialog;dialogKind=null;$('dialog-backdrop').hidden=true;pointerDirs.clear();keys.clear();if(resumeIt&&session.status==='active')resume();else if(session.status==='active')showOverlay($('overlay-start').dataset.kind==='ready'?'ready':'paused');lastFrame=0;renderHud();}
$('dialog-close').onclick=closeDialog;$('dialog-backdrop').addEventListener('click',e=>{if(e.target===$('dialog-backdrop'))closeDialog();});
$('rules-open').onclick=()=>openDialog('rules');$('day-open').onclick=()=>openDialog('day');$('bag-open').onclick=()=>openDialog('bag');
function setDialogHeader(kicker,title){$('dialog-kicker').textContent=kicker;$('dialog-title').textContent=title;}
function renderRules(){setDialogHeader('员工手册 / 基础操作','先检查，再动手');$('dialog-body').innerHTML=`<p class="notice">阅读会暂停所有计时。回到地图后，原有追逐与动作继续。</p><h3>门外的金属声</h3><ul><li>到文具架取回形针。主盒6份，另有一盒有限备用。</li><li>点击“洒回形针”，再点选1.5格内的可见空地；动作需要0.25秒。</li><li>逐点引向正门外雨棚。单纯跑到门外不会完成诱离。</li><li>同时最多3堆，每堆15秒。旧诱饵消失后，它可能回头。</li></ul><h3>不要碰那箱生肉</h3><ul><li>先去库房取登记生肉，再沿过道运到主冰柜。</li><li>它碰到肉后会转而追逐你；放下肉不会让怒态消失。</li><li>同一箱肉真正入柜并合盖，才能解除。提前入柜同样有效。</li><li>普通步行和关键取放不要求剩余体力，也不需要QTE。</li></ul><h3>低SAN与应急</h3><ul><li>低SAN会收窄可见范围，HUD和应急按钮始终清楚。</li><li>SAN归零后有20世界秒。每轮一次免费安定，累计8秒，可边走边进行。</li><li>受击或工作会打断安定，但保留已完成进度。已核验补给能正常恢复。</li></ul><p>操作：方向键或WASD移动，E交互，F投放或放下，Q锁朝向，空格暂停。手机使用左侧方向键，也可以点击地面寻路。</p>`;}
function renderBag(){setDialogHeader('个人补给 / 练习副本','随身补给');const list=remainingInventory(session.resources),canUse=session.status==='active'&&!session.world.action;
 const stateNotice=session.status!=='active'?'本轮练习已经结束，补给暂停使用。':session.world.action?'手中的操作还没完成。请先回到地图完成或取消操作，再使用补给。':'选用后将回到地图，时间恢复。';
 $('dialog-body').innerHTML=`<p class="notice">练习补给不写回正式日间资产。${stateNotice}</p><p id="bag-feedback" role="status"></p>${list.length?list.map(i=>`<div class="inventory-row"><div>${esc(session.resources.items[i.itemId]?.name??i.itemId)}<small>${esc(session.resources.items[i.itemId]?.effect??'')}</small></div><button data-use="${esc(i.id)}" ${canUse&&['I01','I02','I03','I04','I05'].includes(i.itemId)?'':'disabled'}>使用</button></div>`).join(''):'<p class="empty">当前没有可用的个人补给。可以到“白天安排”领取工作餐，或在20:00采购，然后重新进入练习。</p>'}<p class="save-note">定心茶与便当需要安全工位动作，本轮快捷栏暂不使用它们。</p>`;
 $('dialog-body').querySelectorAll('[data-use]').forEach(b=>b.onclick=()=>{
   if(session.status!=='active'||session.world.action)return;
   // Commit the item synchronously before dismissing the paused dialog. A
   // rejected use must not resume a chase or hide its own explanation.
   Session.setPracticePaused(session,false);const r=Session.usePracticeItem(session,b.dataset.use);
   if(!r.ok){Session.setPracticePaused(session,true);$('bag-feedback').textContent=reasonText[r.reason]??'这份补给暂时不能使用，原物仍在。';renderHud();return;}
   dialogKind=null;$('dialog-backdrop').hidden=true;$('overlay').hidden=true;toast('已经使用同一份已核验补给。');lastFrame=0;renderHud();
 });}
function dayTime(){const m=Math.floor(day.absoluteGameMinute)%1440;return `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;}
function dayResult(r,message){if(!r.ok){$('day-feedback').textContent=reasonText[r.reason]??'没有适用目标或时间，请选择当前可执行的活动。';return;}saveDay();renderDay();$('day-feedback').textContent=message;}
function renderDay(){
 setDialogHeader('白天 / 安排与准备','天亮以后');const r=day.resources,labels={day:'自由安排',preparation:'采购与整备',commute:'出勤与验岗',night_ready:'准备进入夜班',night:'夜班时段',morning:'交班与早餐',failed:'本班结束'};
 const methods=D.balance.knowledge.method_pages,unlocked=new Set(Object.keys(day.knowledge.unlockedPages??{})),available=methods.filter(m=>!unlocked.has(m.id));
 const canDay=day.mode==='day';const actions=D.balance.day_actions.filter(a=>['A01','A02','A05','A09'].includes(a.id));
 $('dialog-body').innerHTML=`<div class="day-time"><span>${dayTime()} · ${labels[day.mode]??'准备'}</span><span>${day.coins}金币</span></div><div class="day-summary">${[['energy','精力'],['san','SAN'],['satiety','饱腹'],['stamina','体力']].map(([k,n])=>`<div>${n}<b>${Math.round(r[k])}</b></div>`).join('')}</div><div class="day-progress"><i style="width:${(6-day.remainingDaySlots)/6*100}%"></i></div><p class="notice">剩余${day.remainingDaySlots}个白天行动格，每格2小时。20条基础店规按进度免费解锁。<br>当前练习的消耗不会带回这里。</p><p id="day-feedback" role="status"></p>
 <div class="dialog-grid">${actions.map(a=>`<button data-day-action="${a.id}" ${canDay?'':'disabled'}><strong>${esc(a.name)}</strong><span>精力${a.energy_delta>=0?'+':''}${a.energy_delta??0} · SAN${a.san_delta>=0?'+':''}${a.san_delta??0}${a.coins_delta?` · 金币+${a.coins_delta}`:''}</span></button>`).join('')}</div>
 <h3>学习方法页</h3><div class="dialog-grid">${available.map(p=>`<button data-study="${p.id}" ${canDay?'':'disabled'}><strong>${esc(p.id)} ${esc(p.title)}</strong><span>1格 · 精力−6 · 解锁一页</span></button>`).join('')||'<p>七个方法页均已学完，不再扣格。</p>'}</div>
 <h3>个人补给</h3><div class="mini-actions"><button id="claim-food">领取今日工作餐</button>${day.mode==='preparation'?'<button id="finish-prep">完成采购与整备</button>':''}${day.mode==='commute'?'<button id="finish-commute">完成出勤与验岗</button>':''}</div>
 ${remainingInventory(day).map(i=>`<div class="inventory-row"><div>${esc(day.items[i.itemId]?.name??i.itemId)}<small>${esc(day.items[i.itemId]?.effect??'')}</small></div><button data-day-use="${esc(i.id)}" ${['I01','I02','I03','I04','I05'].includes(i.itemId)?'':'disabled'}>现在使用</button></div>`).join('')}
 <h3>道具店 · 20:00开放</h3><div class="dialog-grid">${D.items.items.filter(i=>['I01','I02','I03','I04','I05'].includes(i.id)).map(i=>`<button data-buy="${i.id}" ${day.mode==='preparation'&&day.coins>=i.shop_price?'':'disabled'}><strong>${esc(i.name)} / ${i.shop_price}币</strong><span>${esc(i.effect)}</span></button>`).join('')}</div>
 ${day.coffeeDebts.some(d=>!d.settled)?`<h3>咖啡的延迟代价</h3><p>还有${day.coffeeDebts.filter(d=>!d.settled).length}份咖啡债务，到各自使用后60游戏分钟结算。离开页面或进入下一时段不会取消。</p>`:''}
 ${unlocked.size?`<h3>已经解锁的资料</h3>${methods.filter(p=>unlocked.has(p.id)).map(p=>`<div class="method-page"><strong>${esc(p.title)}</strong><p>${esc(Array.isArray(p.method_steps)?p.method_steps.join('；'):p.method_steps)}</p></div>`).join('')}`:''}
 <div class="mini-actions"><button id="day-practice" class="primary">带当前状态进入练习 →</button><button id="reset-plan">重新安排本地计划</button></div><p class="save-note">${saveBlocked?'当前环境无法保存本地进度，本页内仍可使用。':saved?'日间计划已保存在当前浏览器。':'完成活动后自动保存在当前浏览器。'}这是日间流程验证，完整七夜战役尚未接入。</p>`;
 $('dialog-body').querySelectorAll('[data-day-action]').forEach(b=>b.onclick=()=>dayResult(Cycle.completeDayAction(day,{commandId:command('day'),actionId:b.dataset.dayAction}),'已完成一格活动；饱腹按实际时段结算。'));
 $('dialog-body').querySelectorAll('[data-study]').forEach(b=>b.onclick=()=>dayResult(Cycle.completeDayAction(day,{commandId:command('study'),actionId:'A03',pageId:b.dataset.study}),'方法页已经解锁，可以在下方查阅。'));
 $('claim-food').onclick=()=>dayResult(Cycle.claimDailyJobFood(day,{commandId:command('food')}),'今日工作餐已领取，同一日不会重复发放。');
 $('dialog-body').querySelectorAll('[data-day-use]').forEach(b=>b.onclick=()=>dayResult(Cycle.consumePersonalItem(day,{commandId:command('day-use'),itemInstanceId:b.dataset.dayUse}),'已消费这份原物，实际资源变化已记录。'));
 $('dialog-body').querySelectorAll('[data-buy]').forEach(b=>b.onclick=()=>dayResult(Cycle.purchasePersonalItem(day,{commandId:command('buy'),itemId:b.dataset.buy}),'已支付金币，补给放入个人库存。'));
 if($('finish-prep'))$('finish-prep').onclick=()=>dayResult(Cycle.finishPreparation(day,{commandId:command('prep')}),'已进入出勤与验岗时段。');
 if($('finish-commute'))$('finish-commute').onclick=()=>dayResult(Cycle.completeCommute(day,{commandId:command('commute')}),'准备完成。可以带当前状态开始独立实操。');
 $('day-practice').onclick=()=>{resumeAfterDialog=false;dialogKind=null;$('dialog-backdrop').hidden=true;startCase(currentCase);};
 $('reset-plan').onclick=()=>{day=newDay();saveDay();renderDay();$('day-feedback').textContent='已建立新的本地日间计划。';};
}
function frame(now){if(lastFrame&&session.status==='active'&&!session.paused){const delta=Math.min(.1,(now-lastFrame)/1000);const result=Session.advancePractice(session,delta);for(const e of result.events){if(e.type==='rage_telegraph'){$('omen').textContent='它碰到了生肉。别丢下任务，把原肉送入冰柜！';$('omen').classList.add('danger');}if(e.type==='hit'){$('omen').textContent='你被碰到了。保持移动，关键物件还在。';$('omen').classList.add('danger');}if(e.type==='coffee_debt_settled')toast('咖啡延迟代价已到期：精力−8，SAN−2。');}}
  lastFrame=now;if(now-lastHud>110){renderHud();lastHud=now;}draw();
  if(toastUntil&&now>toastUntil){$('toast').classList.remove('show');toastUntil=0;}
  if(!terminalShown&&['cleared','failed','unavailable'].includes(session.status)){terminalShown=true;showOverlay(session.status==='cleared'?'cleared':'failed');}
  requestAnimationFrame(frame);
}
startCase('F12');requestAnimationFrame(frame);
// Read-only browser automation surface; actions still pass through actual UI or
// the same public session controller. No direct success/set-position shortcut.
window.__midnight={snapshot:()=>Session.practiceSnapshot(session),getDay:()=>JSON.parse(Cycle.serializeDayCycle(day)),
 getWorld:()=>JSON.parse(JSON.stringify(session.world)),version:'0.9',officialCampaignImplemented:false};
