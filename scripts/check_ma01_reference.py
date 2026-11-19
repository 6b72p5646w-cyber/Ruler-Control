#!/usr/bin/env python3
"""Counterexamples for MA01's finite references, not 105 AI/playtest claims."""
import argparse
from copy import deepcopy
import hashlib
import json
from math import isclose
from pathlib import Path

from ma01_reference import (F,q,clean,swept_discs_time,segment_rectangle_entry,
    clipped_segment,fixed_beam_hits,preset_sweep_direction,AttackTimeline,
    WholeAttack,PlayerHits,AttackReservations,ritual_route_budget,RitualCycle,
    StoneLedger,TetherEpisode)


def run():
    checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
    def rejects(name,call):
        try:
            call()
        except (ValueError,TypeError):
            check(name,True)
        else:
            check(name,False)

    # Discrete-frame tunnelling, relative motion, clipping and beam side steps.
    t=swept_discs_time((0,0),(10,0),(5,0),(5,0))
    check('fast dash crossing a stationary player is caught between frame endpoints',isclose(t,.44))
    check('two moving bodies use relative sweep',swept_discs_time((0,0),(10,0),(5,2),(5,-2)) is not None)
    check('parallel separated trajectories remain a miss',swept_discs_time((0,0),(10,0),(0,1),(10,1)) is None)
    check('initial overlap is an actual collision',swept_discs_time((0,0),(1,0),(.5,0),(.5,0))==0)
    check('near miss outside sum of physical radii stays a miss',swept_discs_time((0,0),(10,0),(5,.61),(5,.61)) is None)
    wall=[(3,-1,4,1)]
    check('charge body stops before a solid wall',isclose(segment_rectangle_entry((0,0),(10,0),wall[0],.3),.27))
    end,_=clipped_segment((0,0),(10,0),wall,.3)
    check('clipped charge endpoint is the first physical wall',isclose(end[0],2.7))
    check('locked beam hits a genuinely intersecting player',fixed_beam_hits((0,0),(1,0),6,.6,(4,.5)))
    check('side step outside beam plus player radius is safe',not fixed_beam_hits((0,0),(1,0),6,.6,(4,.6)))
    check('opaque shelf blocks a fixed beam behind it',not fixed_beam_hits((0,0),(1,0),6,.6,(5,0),wall))
    check('player before the blocking shelf remains exposed',fixed_beam_hits((0,0),(1,0),6,.6,(2,0),wall))
    a=preset_sweep_direction(0,90,1,1)
    check('sweep follows its visible predetermined endpoint',abs(a[0])<1e-10 and isclose(a[1],1))
    rejects('nonfinite coordinates cannot enter collision math',lambda:swept_discs_time((float('nan'),0),(1,0),(0,0),(0,0)))

    # Existing 3-second basics and telegraph extension move all downstream times.
    a=AttackTimeline('F12:BASIC',0,1.5,0,1.5,3)
    check('canonical F12/F13 basic cannot commit before 1.5 seconds',not a.commit(1.49))
    check('canonical basic commits at 1.5 seconds',a.commit(1.5))
    check('canonical basic keeps 3 second total cadence',a.complete(1.5) and a.next_start==3)
    a=AttackTimeline('fixture:projectile',0,1.5,.5,2,3.5,autonomous_projectile=True)
    check('I37 grants one real second before commit',a.extend(1)==1 and a.deadline==q(2.5))
    check('same I37 family cannot extend same attack twice',a.extend(1.1)==0)
    check('old damage timer cannot fire after extended warning',not a.commit(1.5))
    check('new commit determines projectile and recovery timing',a.commit(2.5) and a.active_end==3 and a.complete(3) and a.next_start==5)
    check('already launched/completed attack cannot be extended',a.extend(3.1,'I21',3)==0)
    a=AttackTimeline('F50:DIVE',0,8,0,4,10)
    first=a.extend(.2,'I37',1);second=a.extend(.3,'I21',3);third=a.extend(.4,'other',1)
    check('I21 and I37 share a three second cap on the eligible F50 dive',first==1 and second==2 and third==0 and a.deadline==11)
    check('curse failure is one decision for whole payload',not a.commit(11,curse_failure=True) and a.curse_draws==1 and a.state=='canceled')
    check('curse failure cannot immediately retry same attack ID',not a.commit(11.1) and a.curse_draws==1 and a.next_start==15)
    a=AttackTimeline('F50:DIVE',0,8,0,4,10)
    first=a.extend(1,'B04',1);second=a.extend(2,'P05',2)
    check('legacy B04 and P05 share maximum total rather than adding one plus two',first==1 and second==1 and a.extension==2 and a.deadline==10)
    check('weaker legacy warning has no chargeable positive difference',a.extend(3,'B04.active',1)==0)
    check('I37 adds one real increment to the legacy maximum',a.extend(3,'I37',1)==1 and a.extension==3 and a.deadline==11)
    a=AttackTimeline('F50:DIVE',0,8,0,4,10)
    check('I37 then P05 gives the same final deadline as reverse order',a.extend(1,'I37',1)==1 and a.extend(2,'P05',2)==2 and a.deadline==11)
    check('P07 cannot extend F50 despite sharing the old warning consumer',a.extend(3,'P07',2)==0)
    a=AttackTimeline('F60:GAZE',0,8,3,3,10)
    check('F60 accepts its own P07 warning and not F50 P05 or B04',a.extend(1,'P05',2)==0 and a.extend(1,'B04',1)==0 and a.extend(1,'P07',2)==2)
    a=AttackTimeline('F50:BASIC',0,1.5,0,3,4.5)
    check('I21 cannot extend the same monster basic attack',a.extend(.5,'I21',3)==0 and a.extension==0)
    a=AttackTimeline('fixture:unknown',0,1.5,0,3,4.5)
    before=deepcopy(a)
    check('unknown or inflated extension sources change no attack ledger',a.extend(.5,'I21',3)==0 and a.extend(.5,'I37',3)==0 and a.extend(.5,'unknown',1)==0 and a==before)
    a=AttackTimeline('actual-root-instance:attack-7',0,8,0,4,10,definition_id='F50:DIVE')
    check('persistent attack identity uses a separate verified definition for old consumer matching',a.extend(1,'B04',.5)==q(.5) and a.extend(2,'I21',3)==q(2.5) and a.deadline==11)
    base=Path(__file__).resolve().parents[1]
    auxiliary={entry['id']:entry for entry in json.loads((base/'content/auxiliary_effects_v010.json').read_text())['entries']}
    old={item:{effect['effect_id']:effect for effect in auxiliary[item]['effects']} for item in ('I21','P05','P07','B04')}
    i21=old['I21']['I21.warning']['parameters']
    check('reference I21 whitelist matches its unchanged authoritative consumer',i21['allowed_monsters']==['F50','F60'] and i21['allowed_actions']==['roof_dive','turn_to_face'] and i21['requested_total_bonus_world_seconds']==3)
    check('pet warning amounts retain the correct original actions',old['P05']['P05.special']['parameters']['action_id']=='roof_dive' and old['P05']['P05.special']['parameters']['requested_total_bonus_world_seconds']==2 and old['P07']['P07.special']['parameters']['action_id']=='turn_to_face' and old['P07']['P07.special']['parameters']['requested_total_bonus_world_seconds']==2)
    b04=old['B04']['B04.active']['parameters']
    check('B04 keeps only F50 and its actual tier request amounts',b04['warning_monster_ids']==['F50'] and b04['warning_action_ids']==['roof_dive'] and b04['warning_total_bonus_by_tier_world_seconds']=={'L1':1,'L2':.5})
    i37=next(item for item in json.loads((base/'content/consumables_eq01.json').read_text())['items'] if item['id']=='I37')['parameters']
    check('I37 source budget is one second once while three seconds remains only the shared cap',i37['attack_telegraph_added_s']==1 and i37['same_attack_id_once_per_item_family'] and i37['all_source_extension_total_cap_s']==3)
    a=AttackTimeline('fixture:freeze',0,1.5,0,3,4.5)
    check('position root does not cancel a stationary pending attack',not a.interrupt(.5,'root') and a.state=='preparing')
    check('freeze cancels uncommitted attack without curse draw',a.interrupt(.6,'freeze') and not a.commit(1.5) and a.curse_draws==0)
    beam=AttackTimeline('fixture:beam',0,1.5,1,2,5,requires_live_channel=True)
    beam.commit(1.5)
    check('freeze ends an already active channel beam',beam.interrupt(1.7,'freeze'))
    projectile=AttackTimeline('fixture:launched',0,1.5,1,2,5,autonomous_projectile=True)
    projectile.commit(1.5)
    check('freeze cannot recall a launched autonomous projectile',not projectile.interrupt(1.7,'freeze') and projectile.state=='active')
    check('source pool death within an unfinished root preserves its independent shot',not projectile.interrupt(1.75,'source_pool_terminal') and projectile.state=='active')
    check('terminal encounter revokes its owned future projectile hazard',projectile.interrupt(1.8,'terminal'))
    for family in ('charge','contact'):
        embodied=AttackTimeline('fixture:'+family,0,1.5,2,2,7,requires_live_channel=True)
        embodied.commit(1.5)
        check('freeze closes active embodied damage: '+family,embodied.interrupt(1.7,'freeze') and embodied.state=='canceled')
    residual=AttackTimeline('fixture:ground-silk',0,1.5,8,3,8,
                            independent_payload=True,action_active=0)
    residual.commit(1.5)
    check('eight-second autonomous field does not add eight seconds to source recovery',residual.action_ready_at==q(4.5) and residual.active_end==q(9.5) and residual.next_start==8)
    check('freeze of source does not recall an independent ground field',not residual.interrupt(2,'freeze') and residual.state=='active')
    rejects('unwarned sub-1.5 second harmful attack is rejected',lambda:AttackTimeline('bad',0,1,0,3,4))

    # A collision blocked by global hit protection is not a geometric dodge.
    hp=PlayerHits()
    hit=hp.attempt(1.5,'charge-and-body',12)
    check('one charge uses one accepted SAN hit',hit['accepted'] and hp.san==88)
    other=hp.attempt(2,'other-ribbon',8,requests_tether=True)
    check('shared two second protection blocks damage AND new tether',not other['accepted'] and not other['tether_allowed'] and hp.san==88)
    check('blocked damage still records actual player collision','other-ribbon' in hp.collided_attack_ids)
    check('body component cannot re-hit after same charge even beyond grace',not hp.attempt(4,'charge-and-body',12)['accepted'])
    check('different attack is legal at exact shared grace expiry',hp.attempt(3.5,'next',10)['accepted'] and hp.san==78)
    hp=PlayerHits()
    check('unarmed body contact has no damage',not hp.attempt(1,'body',8,legal=False)['accepted'] and hp.san==100)
    check('armed body contact can damage once',hp.attempt(1.5,'body',8)['accepted'] and not hp.attempt(3.6,'body',8)['accepted'])
    hp=PlayerHits()
    check('fractional equipment mitigation is not repeatedly rounded',hp.attempt(0,'mitigated',9,mitigation=.08)['san_loss']==q(8.28))

    attack=WholeAttack('combo',{'first','second','last-zone'})
    attack.resolve_part('first',player_moved=True)
    check('first missed combo segment cannot award I39 early',not attack.take_spatial_miss(1,12))
    attack.resolve_part('second',player_moved=True)
    check('remaining ground zone also blocks premature whole-miss receipt',not attack.take_spatial_miss(2,12))
    attack.resolve_part('last-zone',player_moved=True)
    check('complete genuine positional avoidance grants one whole receipt',attack.take_spatial_miss(3,12))
    check('duplicate whole attack completion cannot award I39 twice',not attack.take_spatial_miss(3,12))
    attack=WholeAttack('grace-blocked',{'beam'})
    attack.resolve_part('beam',collision=True,player_moved=True)
    check('hit-protection collision never becomes I39 evasion',not attack.take_spatial_miss(3,12))
    for reason in ('curse_failure','freeze','paper_interception','terminal'):
        attack=WholeAttack('canceled:'+reason,{'one'},canceled_reason=reason)
        attack.resolve_part('one',player_moved=True)
        check('cancellation is not spatial evasion: '+reason,not attack.take_spatial_miss(3,12))
    attack=WholeAttack('facing-only',{'gaze'})
    attack.resolve_part('gaze',player_moved=False)
    check('back-facing without movement does not trigger I39',not attack.take_spatial_miss(3,12))
    attack=WholeAttack('not-aimed',{'one'},player_in_locked_geometry=False)
    attack.resolve_part('one',player_moved=True)
    check('standing outside original danger cannot farm a miss',not attack.take_spatial_miss(3,12))
    attack=WholeAttack('expired',{'one'});attack.resolve_part('one',player_moved=True)
    check('I39 buff must remain live at final subordinate resolution',not attack.take_spatial_miss(12,12))
    check('I39 cannot hit an already departed attacker',not attack.take_spatial_miss(3,12,attacker_legal=False))
    check('I39 cannot hit an invisible or distant attacker',not attack.take_spatial_miss(3,12,attacker_visible=False) and not attack.take_spatial_miss(3,12,attacker_distance=4.1))

    slots=AttackReservations()
    check('first ritual reserves a real actor and pressure slot',slots.reserve('r','body-A','RITUAL'))
    check('same actor cannot stack a melee over its ritual',not slots.reserve('a','body-A','MELEE'))
    check('second global ritual/tether threat is not admitted',not slots.reserve('t','body-B','TETHER'))
    check('a second ordinary attack still requires a verified full escape route',not slots.reserve('b','body-B','MELEE',complete_route_verified=False))
    check('one independent legal ordinary threat can coexist',slots.reserve('b','body-B','MELEE'))
    check('a third simultaneous harmful sequence waits',not slots.reserve('c','body-C','MELEE'))
    slots.release('b')
    check('active player binding prevents new dangerous sequence',not slots.reserve('c','body-C','MELEE',player_bound=True))
    check('native movement recovery cannot be bypassed with a new attack',not slots.reserve('c','body-C','MELEE',native_move_recovering=True))
    slots=AttackReservations()
    slots.reserve('silk','S30-body','AREA_PULSE',has_independent_residual=True)
    check('independent field cannot release actor before actual recovery',not slots.detach_actor('silk',4.49,residual.action_ready_at))
    check('source actor recovers while its silk sequence retains danger slot',slots.detach_actor('silk',4.5,residual.action_ready_at) and len(slots.active)==1)
    check('recovered source can take another attack in a genuinely free second slot',slots.reserve('silk-owner-melee','S30-body','MELEE'))
    check('autonomous residual still counts against global two-sequence pressure',not slots.reserve('third','other','MELEE'))
    check('second actor action still cannot overlap itself',not slots.reserve('duplicate-melee','S30-body','MELEE'))
    slots.release('silk-owner-melee');slots.release('silk')
    check('expired residual finally releases its independent danger slot',len(slots.active)==0)
    slots.reserve('beam','beam-body','BEAM')
    check('live beam cannot detach actor as a fake autonomous field',not slots.detach_actor('beam',10,4))
    pair=[{'attack_id':'pair-left','actor_id':'S18-left','family':'CHARGE'},
          {'attack_id':'pair-right','actor_id':'S18-right','family':'CHARGE'}]
    check('synchronized pair cannot reserve only its first member into one remaining slot',not slots.reserve_many(pair) and set(slots.active)=={'beam'})
    slots.release('beam')
    check('two synchronized charge actors atomically reserve both scene slots',slots.reserve_many(pair) and len(slots.active)==2)
    check('no third threat can slip into a synchronized charge',not slots.reserve('third','other','MELEE'))

    # Zero-stamina time budget uses actual route/speed, hands and flight.
    budget=ritual_route_budget([(9,3)],6)
    check('ordinary nine-tile route fits six seconds including pickup and throw',budget['eligible'] and budget['channel_seconds']==6 and budget['required_seconds']==q(5.65))
    slow=ritual_route_budget([(9,1.8)],6,hand_preparation=True)
    check('current slowdown and occupied hands lengthen public ritual warning',slow['eligible'] and slow['required_seconds']==q(7.9) and slow['channel_seconds']==q(7.9))
    check('route exceeding eight-second allowance defers ritual',not ritual_route_budget([(20,2.4)],6,hand_preparation=True)['eligible'])
    held=ritual_route_budget([],6,stone_held=True)
    check('held actual stone saves only actual pickup time',held['required_seconds']==q(2.2))
    for name,args in [('no physical stone',{'actual_stone_available':False}),('blocked route',{'path_valid':False}),('no firing LOS',{'firing_los_valid':False}),('anchored body',{'mobile_body':False})]:
        check('ritual defers with '+name,not ritual_route_budget([],4,**args)['eligible'])
    check('stone cannot reach a target beyond six tiles',not ritual_route_budget([],6.1)['eligible'])

    ritual=RitualCycle('r')
    check('six-second ritual begins only with admitted route',not ritual.begin(0,admitted=False) and ritual.begin(0))
    check('ritual cannot be interrupted before its actual start',not ritual.interrupt(-1,'stone',receipt='retroactive-hit',actual_focus_hit=True) and ritual.mode=='chanting' and not ritual.interruption_receipts)
    check('root does not cancel ritual',not ritual.interrupt(1,'root',receipt='root'))
    result=ritual.resolve_timestamp(6,stone_contacts=[('stone:actual-hit',True)])
    check('same-timestamp actual stone wins before ritual pulse',result=={'interrupted':True,'pulse':False} and ritual.pulses==0)
    check('interrupted ritual has visible .8 second recovery',ritual.state_at(6.79)=='recovery' and ritual.state_at(6.8)=='chase')
    check('interrupt commits eight seconds of ordinary chase',ritual.forced_chase_until==q(14.8))
    check('ritual cannot immediately replace its pursuit phase',not ritual.begin(10))
    check('original sixteen-second recast floor persists',not ritual.begin(15.99) and ritual.begin(16))
    check('same old stone receipt cannot cancel a later ritual',not ritual.interrupt(17,'stone',receipt='stone:actual-hit',actual_focus_hit=True))
    check('new physical throw may interrupt later ritual',ritual.interrupt(17,'stone',receipt='stone:new-throw',actual_focus_hit=True))
    ritual=RitualCycle('long');ritual.begin(0,8);ritual.interrupt(7.9,'stone',receipt='late',actual_focus_hit=True)
    check('late interruption extends pursuit beyond nominal recast',not ritual.begin(16) and ritual.begin(16.7))
    ritual=RitualCycle('freeze');ritual.begin(0)
    result=ritual.resolve_timestamp(3,control='freeze',control_until=5)
    check('freeze legitimately cancels ritual and preserves real control duration',result['interrupted'] and ritual.recovery_until==5 and ritual.forced_chase_until==13)
    ritual=RitualCycle('bad-seal');ritual.begin(0)
    check('unregistered generic seal cannot invent a ritual consumer',not ritual.interrupt(2,'seal',receipt='badseal',existing_sealable=False))
    check('missed focus does not interrupt ritual',not ritual.interrupt(2,'stone',receipt='miss',actual_focus_hit=False))
    check('uninterrupted completed channel emits one pulse',ritual.commit_pulse(6) and not ritual.commit_pulse(6) and ritual.pulses==1)
    ritual=RitualCycle('curse');ritual.begin(0)
    check('curse failure suppresses ritual payload',not ritual.commit_pulse(6,curse_failure=True) and ritual.pulses==0)
    check('already committed ritual cannot receive a delayed extension',ritual.extend(6.1,'I37',1)==0)
    ritual.terminate()
    check('resolved encounter cannot restart ritual',not ritual.begin(100))
    ritual=RitualCycle('extended');ritual.begin(0,8)
    check('eight second ritual baseline can accept a paid real extension',ritual.extend(1,'I37',1)==1 and ritual.pulse_at==9)
    check('ritual I37 cannot refresh the same attack twice',ritual.extend(2,'I37',1)==0)
    before=deepcopy(ritual)
    check('I21 and old monster-specific helpers cannot extend a ritual',all(ritual.extend(3,source,amount)==0 for source,amount in [('I21',3),('P05',2),('P07',2),('B04',1),('other',1)]) and ritual==before)
    check('ritual I37 cannot claim the unused general three second budget',ritual.extend(3,'I37',3)==0 and ritual.pulse_at==9)
    check('extended ritual cannot damage at its old eight second deadline',not ritual.commit_pulse(8) and ritual.mode=='chanting')
    ritual.interrupt(8.8,'stone',receipt='late-extended-hit',actual_focus_hit=True)
    check('late extended ritual interruption preserves full eight second pursuit',ritual.forced_chase_until==q(17.6) and not ritual.begin(16) and ritual.begin(17.6))
    check('new ritual sequence resets only its own extension allowance',ritual.extension_total==0 and ritual.extend(20,'I37',1)==1 and ritual.attempt_number==2)
    ritual=RitualCycle('F21:RITUAL');ritual.begin(0,8)
    check('original illegal ritual I21 counterexample now preserves the eight second deadline',ritual.extend(1,'I21',3)==0 and ritual.pulse_at==8)

    # Mission stones remain exactly the same three physical IDs through all actions.
    stones=StoneLedger({'p1':(0,0),'p2':(.2,0),'p3':(2,0)})
    check('heavy carry must be placed before picking stone',not stones.begin_pickup('p1',0,(0,0),heavy=True))
    check('actual pickup needs a free hand',not stones.begin_pickup('p1',0,(0,0),free_hands=0))
    check('pickup starts in .8 tile reach without stamina input',stones.begin_pickup('p1',0,(.8,0)))
    check('pickup cannot complete early',not stones.finish_pickup(.44,(.8,0)))
    check('pickup completion transfers same physical ID',stones.finish_pickup(.45,(.8,0)) and stones.held=='p1')
    check('one mission slot cannot carry a second stone',not stones.begin_pickup('p2',.45,(.2,0)))
    check('out-of-range throw cannot spend held stone',not stones.begin_throw(.45,(0,0),(6.1,0)) and stones.held=='p1')
    check('throw has real .35 second preparation',stones.begin_throw(.45,(0,0),(6,0)) and not stones.finish_throw(.79,(0,0)))
    check('throw creates one physical flight and vacates carry slot',stones.finish_throw(.8,(0,0)) and stones.held is None and len(stones.stones)==3)
    rejects('unverified inaccessible floor cannot fake a return to hand',lambda:stones.resolve_flight('p1',verified_floor=False))
    ritual=RitualCycle('blocked');ritual.begin(0)
    result=stones.resolve_flight('p1',wall,focus=(5,0),ritual=ritual)
    check('wall blocks actual stone before exposed focus',not result['focus_hit'] and not result['interrupted'] and ritual.mode=='chanting')
    check('wall-hit stone lands before wall under same ID',isclose(result['position'][0],2.9) and stones.stones['p1']['state']=='ground' and len(stones.stones)==3)
    check('same physical missed stone can be recovered',stones.begin_pickup('p1',2,(2.5,0)) and stones.finish_pickup(2.45,(2.5,0)))
    stones.begin_throw(2.45,(2.5,0),(5,0));stones.finish_throw(2.8,(2.5,0))
    result=stones.resolve_flight('p1',focus=(5,0),ritual=ritual)
    check('actual stone focus collision interrupts without monster HP damage',result['focus_hit'] and result['interrupted'] and result['monster_hp_damage']==0)
    check('resolved physical flight cannot be delivered twice',stones.resolve_flight('p1',focus=(5,0),ritual=ritual) is None)
    reloaded=deepcopy(stones)
    check('save restore preserves three IDs and physical locations',reloaded.stones==stones.stones and reloaded.held==stones.held and len(reloaded.stones)==3)
    stones=StoneLedger({'a':(0,0),'b':(1,0),'c':(2,0)})
    stones.begin_pickup('a',0,(0,0));stones.finish_pickup(.45,(0,0));stones.begin_throw(.45,(0,0),(4,0))
    check('moving during stationary throw cancels without duplicating stone',not stones.finish_throw(.8,(.1,0)) and stones.held=='a' and stones.stones['a']['state']=='held')

    # Tether is a finite channel, not a persistent stun lock or hand/tool gate.
    tether=TetherEpisode()
    check('grace-blocked ribbon cannot bind',not tether.bind(0,'ribbon',accepted_hit=False))
    check('accepted ribbon binds once',tether.bind(0,'ribbon',accepted_hit=True))
    check('initial player root ends at .6 second',tether.movement_multiplier(.59)==0 and tether.movement_multiplier(.6)==q(.65))
    check('second tether cannot replace or extend current binding',not tether.bind(.5,'other-ribbon',accepted_hit=True) and tether.release_at==2)
    check('struggle requires no stamina or free hand parameter',tether.struggle(.1))
    check('struggle ends binding after actual .6 second hold',tether.tick(.69) is None and tether.tick(.7)=='struggle')
    check('release gives six second global rebind immunity',not tether.bind(6.69,'other',accepted_hit=True) and tether.bind(6.7,'other',accepted_hit=True))
    check('hard timeout is two seconds even with a late tick',tether.tick(10)=='timeout' and tether.immune_until==q(14.7))
    tether=TetherEpisode();tether.bind(0,'ribbon',accepted_hit=True)
    check('brief occlusion does not immediately break tether',tether.tick(.2,los_clear=False) is None and tether.tick(.39,los_clear=False) is None)
    check('real .2 second occlusion releases tether',tether.tick(.4,los_clear=False)=='occlusion' and tether.immune_until==q(6.4))
    tether=TetherEpisode();tether.bind(0,'ribbon',accepted_hit=True);tether.tick(.1,los_clear=False)
    check('LOS return cannot erase a break deadline already elapsed',tether.tick(.4,los_clear=True)=='occlusion' and tether.immune_until==q(6.3))
    for reason,args in [('source_invalid',{'source_active':False}),('freeze',{'source_frozen':True}),('overlength',{'distance':4.01})]:
        tether=TetherEpisode();tether.bind(0,'ribbon',accepted_hit=True)
        check('tether releases on '+reason,tether.tick(.1,**args)==reason)
    tether=TetherEpisode();tether.bind(0,'ribbon',accepted_hit=True)
    check('within four tiles live channel remains bounded but valid',tether.tick(1,distance=4) is None and tether.movement_multiplier(1)==q(.65))
    check('tether timeout restores ordinary walking',tether.tick(2)=='timeout' and tether.movement_multiplier(2)==1)
    short=TetherEpisode(max_length_tiles=3);short.bind(0,'S12-spine',accepted_hit=True)
    check('shorter original three-tile tether breaks at its actual range',short.tick(.1,distance=3.01)=='overlength')

    passed=sum(x['passed'] for x in checks)
    return {'version':'MA01','runtime_integrated':False,'passed':passed,'failed':len(checks)-passed,
            'scope':'Finite 2-D sweep/beam fixtures, attack timing/whole-miss receipts, shared hit protection, pressure reservations, actual task-stone ledger, ritual interruption and bounded tether lifecycle. Not all105AI, map navigation, height layers, reflected beam geometry, whole-week outcomes or live playtesting.',
            'review_corrections':[
                'Root review found an unguarded lower time boundary. Replaying the pre-guard function confirmed that begin(0) then stone interrupt(-1) was accepted; the final now>=started_at guard and regression case reject it.',
                'Separated a recovered actor action from its still-live independent residual danger sequence; the latter retains a scene slot and delays whole-attack I39 resolution.',
                'Aligned the physical stone radius with the final shared contract: 0.1 tile, retaining actual wall clipping and zero monster HP damage.',
                'Clarified source-pool death versus full-root termination for already launched independent payloads.',
                'SA01 replay confirmed two cross-system defects: the old reference accepted I21 on a ritual despite its F50/F60-only consumer, and added B04+P05 instead of taking the legacy maximum. Source/attack-definition/amount matching now rejects these counterexamples. Legacy maximum L and the once-only I37 increment J share total min(3,L+J), with only positive differences committed.',
                'A ritual base warning may be 6..8 seconds. Current legal source I37 adds exactly one real second once, so the current maximum is9; the general3-second safety cap does not grant I21 or other old helpers a new ritual consumer. The prior positive test incorrectly treated the cap as source eligibility and has been replaced with negative cases.',
                'Recorded automated runs passed at each stage; scope/contract corrections above were made during review and are not presented as full-world verification.'
            ],
            'checks':checks}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/ma01_reference_report.json');args=parser.parse_args()
    report=run();base=Path(__file__).resolve().parents[1]
    report['input_hashes']={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ['scripts/ma01_reference.py','scripts/check_ma01_reference.py','content/auxiliary_effects_v010.json','content/consumables_eq01.json']}
    output=Path(args.output);output=output if output.is_absolute() else base/output
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(clean(report),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'output':str(output),'failures':[x['name'] for x in report['checks'] if not x['passed']]},ensure_ascii=False))
    raise SystemExit(bool(report['failed']))
