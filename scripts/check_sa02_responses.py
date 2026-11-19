#!/usr/bin/env python3
"""Limited, reproducible SA02 evidence; no full-world gameplay claim."""
import hashlib
import json
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path

from md01_reference import LifeState
from sa02_response_reference import ResponseReference


ROOT=Path(__file__).resolve().parents[1]
BASELINE='aa7941aef0bfc82f4cef15337084b0a0ad3dbc59'
rows=[]


def check(name, condition):
    rows.append({'name':name,'passed':bool(condition)})


def fixture(species='S40',deadline=20,**kwargs):
    return ResponseReference(monsters[species], 'fixture:week1:night6:root1', 'attempt1',
                             'fixture:actor1', (0,0), deadline,
                             expected_source_id='fixture:original-paper-or-open-receipt',**kwargs)


def proof(r):
    return {'monster_id':r.species,'root_id':r.life.root,'attempt_id':r.attempt_id,'actor_id':r.actor_id,
            'evidence_origin':'world_adapter','physical_verified':True,'route_verified':True,
            'position_verified':True,'deadline_verified':True,'hostility_verified':True,
            'player_outside':True,'original_deadline':str(r.deadline),'actual_actor_position':r.position,
            'plan_id':'fixture:response1','route_id':'fixture:lawful-polyline1',
            'destination_id':'fixture:tray-or-exit','bound_source_id':'fixture:original-paper-or-open-receipt',
            'path':[(0,0),(3.3,0)],'sound_muted':True,'original_paper_in_tray':True,
            'external_mall_open':True,'exit_boundary_verified':True,'external_ack_elapsed_s':3,
            'source_receipt_verified':True,'observed_world_time':str(r.now)}


def latch(r):
    return {'evidence_origin':'world_adapter','root_id':r.life.root,'attempt_id':r.attempt_id,
            'door_id':r.plan['destination_id'],'actual_control_position':True,
            'held_input':True,'door_binding_verified':True}


monsters={m['id']:m for m in json.loads((ROOT/'content/monster_scp_b_md01.json').read_text())['monsters']}
contract=json.loads((ROOT/'content/rule_response_contracts_sa02.json').read_text())
specs={x['monster_id']:x for x in contract['registered_responses']}
check('only S40 and S43 are registered',set(specs)=={'S40','S43'})
check('runtime and universal proof gates remain closed',not contract['runtime_integrated']
      and not contract['runtime_enabled'] and not contract['validation_boundary']['all_gameplay_proven'])
check('baseline is explicit',contract['baseline_commit']==BASELINE)
check('S40 actual card has 2.5 second preparation','2.5s' in monsters['S40']['mechanism']['work_window']
      and specs['S40']['actor_work_seconds']==2.5)
check('S43 preserves actual one-second final latch',next(x for x in monsters['S43']['mechanism']['steps']
      if x['id']=='S43_step_3')['seconds']==specs['S43']['post_exit_player_action_seconds']==1)
check('S43 external state still requires three actual seconds','3s' in monsters['S43']['mechanism']['work_window'])
poison=json.loads((ROOT/'content/combat_contracts_td05.json').read_text())['statuses']['poison']
check('counterexample uses real unlimited spiritual poison',poison['unlimited_load'] and poison['max_load'] is None
      and poison['damage_per_second_per_load']==.5 and poison['damage_channel']=='spiritual')

# Original model: an admitted q state, not a proven acquisition/navigation trace.
old=LifeState(monsters['S40'],root='fixture:old-response')
old.add_poison(125)
old.apply_damage(10000,'physical')
legacy=[]
for cycle in range(3):
    old.advance(F(9,2))
    restored=(str(old.now),str(old.hp),str(old.poison))
    for _ in range(2):
        old.advance(1)
        old.poison_tick(1)
    legacy.append({'cycle':cycle+1,'restore_t_hp_q':restored,
                   'after_two_ticks_t_hp_state':[str(old.now),str(old.hp),old.state],
                   'uninterrupted_active_seconds':2,'s40_preparation_seconds':2.5})
check('legacy poison permits repeated two-second activity windows',all(x['after_two_ticks_t_hp_state'][2]=='suppressed' for x in legacy))
check('legacy suppression is not a root success',not old.rule_done and not old.root_finished and old.ledger.coins==0)

for key in ('physical_verified','route_verified','position_verified','deadline_verified','hostility_verified','player_outside'):
    r=fixture(); p=proof(r); p[key]=False
    check('reject missing real prerequisite '+key,not r.enter(p) and r.plan is None and not r.protected)
for key,value in [('evidence_origin','ui'),('attempt_id','old_attempt'),('root_id','other_root'),
                  ('actor_id','other_actor'),('original_deadline','999'),('sound_muted',False),
                  ('original_paper_in_tray',False),('normal_human',True)]:
    r=fixture(); p=proof(r); p[key]=value
    check('reject mismatched or unsupported evidence '+key,not r.enter(p) and r.plan is None)
for kind in ('kill_unlocked','rule_weaken'):
    m=deepcopy(monsters['S40']); m['resolution']['type']=kind
    r=ResponseReference(m,'r','a','actor',(0,0),20)
    check('reject '+kind,not r.enter(proof(r)))
r=fixture('S38')
check('unregistered rule_leave does not acquire immunity',not r.enter(proof(r)))
r=fixture(); r.life.apply_damage(10000)
check('does not prematurely clear existing suppression',not r.enter(proof(r)) and r.life.state=='suppressed')
check('suppressed actor cannot start a new attack before response',not r.attack_allowed())
r=fixture(); p=proof(r); p['control_active']=True
check('does not prematurely clear existing freeze',not r.enter(p))
r=fixture(deadline=F(349,100))
check('reject insufficient original world time',not r.enter(proof(r)) and r.life.hp==200)

r=fixture(maturities=({'id':'paid-dose1','due':1,'amount':1},),timed_states={'old_buff':F(1,2)})
r.life.hp=F(50); r.life.add_poison(125)
check('actual S40 response starts',r.enter(proof(r)))
check('ordinary hostile attacks of this root stop',not r.attack_allowed())
check('repeat enter does not create another plan',not r.enter(proof(r)) and r.protection_used==0)
check('response has no HP damage or electric feedback',r.damage(100,'spiritual',electric_charge=1)==0
      and r.life.hp==50 and r.life.charge==0)
other=LifeState(monsters['S40'],root='other:unprotected')
check('other roots retain normal damage',other.apply_damage(10)>0)
r.elapse(1)
check('same real path is traversed',r.position==(3.3,0) and r.phase=='collect' and r.item_owner=='tray')
check('old mature dose matures once during response',r.life.poison==126 and r.maturities[0]['applied'])
check('timed effects expire without resetting world time',not r.timed_states and r.now==1)
check('permanent poison retained but no protected tick or charge',r.poison_tick(1)==0 and r.life.poison==126 and r.life.hp==50)
r.elapse(F(249,100))
check('no transfer or terminal before actual 2.5 second work',r.item_owner=='tray' and not r.life.rule_done and r.life.ledger.coins==0)
r.elapse(F(1,100))
check('actual same paper transfer completes root once',r.item_owner==r.actor_id and r.life.rule_done
      and r.life.ledger.coins==12 and r.life.ledger.spirit==6 and r.phase=='complete')
check('true terminal clears this pool original poison',r.life.poison==0 and not r.maturities)
check('terminal cannot be reentered for more rewards',not r.enter(proof(r)) and r.life.ledger.coins==12)

r=fixture(); r.life.hp=F(50); r.life.add_poison(125); r.enter(proof(r)); r.elapse(F(1,2))
position=r.position; hp=r.life.hp; poison_q=r.life.poison
check('real invalidation ends protection',r.interrupt() and not r.protected)
check('interruption preserves HP poison position and item',r.life.hp==hp and r.life.poison==poison_q
      and r.position==position and r.item_owner=='tray')
r.elapse(1)
check('unprotected world time does not generate fake response progress',r.route_done==F(1,2) and r.protection_used==F(1,2) and r.now==F(3,2))
check('no catch-up damage is synthesized',r.life.hp==50)
check('next ordinary poison tick still consumes original q',r.poison_tick(1)==25 and r.life.poison==125)
p=proof(r); p['bound_source_id']='replacement-paper'
check('cannot substitute a new item to reset response',not r.enter(p))
p=proof(r); p['plan_id']='new-plan'
check('cannot reset plan identity',not r.enter(p))
p=proof(r); p['path']=[(0,0),(6.6,0)]
check('cannot enlarge route for more protection',not r.enter(p))
saved=r.clone_saved_state()
check('finite saved copy preserves spent budget and deadline',saved.protection_used==r.protection_used and saved.deadline==r.deadline and saved.position==r.position)
check('same physical plan can resume within its original time',saved.enter(proof(saved)))
saved.elapse(3)
check('resume finishes only the remaining original protected seconds',saved.phase=='complete'
      and saved.protection_used==F(7,2) and saved.life.ledger.coins==12)
r=fixture(); r.enter(proof(r)); r.interrupt(); r.damage(10000)
check('interrupted then suppressed actor cannot start a new attack',r.life.state=='suppressed' and not r.attack_allowed())

r=fixture(deadline=F(7,2)); r.life.add_poison(125); r.enter(proof(r)); r.elapse(F(7,2))
check('S40 completion exactly at original deadline succeeds',r.phase=='complete' and r.life.ledger.coins==12)
r=fixture(deadline=F(5,2)); p=proof(r); p['path']=[(0,0),(0,0)]
check('already-at-tray S40 still requires real preparation',r.enter(p) and r.life.ledger.coins==0)
r.elapse(F(5,2))
check('zero-length lawful approach does not invent a teleport',r.phase=='complete' and r.position==(0,0)
      and r.protection_used==F(5,2))
r=fixture(deadline=4); r.enter(proof(r)); r.elapse(F(1,2)); r.interrupt(); r.elapse(1)
check('resume cannot extend original deadline',not r.enter(proof(r)) and r.protection_used==F(1,2))
r.elapse(F(5,2))
check('deadline without actual response yields no reward',r.phase=='failed' and r.life.ledger.coins==0 and r.item_owner=='tray')

r=fixture('S43',deadline=2); p=proof(r); p['external_ack_elapsed_s']=F(299,100)
check('S43 requires actual three-second upstream acknowledgement',not r.enter(p))
check('S43 cannot close gate before actual exit',not r.start_latch({}))
check('S43 valid upstream state starts real return',r.enter(proof(r)))
r.elapse(1)
check('S43 exit is a real boundary event and not root reward',not r.actor_present and r.external_exit_at==1
      and r.position==(3.3,0) and r.phase=='awaiting_latch' and r.life.ledger.coins==0)
check('S43 old damage cannot re-anger departed actor',r.damage(100)==0 and not r.attack_allowed())
lp=latch(r); lp['evidence_origin']='ui'
check('S43 UI latch claim is insufficient',not r.start_latch(lp))
lp=latch(r); lp['attempt_id']='old'
check('S43 old-attempt gate receipt is rejected',not r.start_latch(lp))
check('S43 actual held gate action starts',r.start_latch(latch(r)))
r.elapse(1)
check('S43 actual latch at exact deadline settles once',r.phase=='complete' and r.life.ledger.coins==12 and r.life.ledger.spirit==6)
check('S43 protection covers only travel not latch',r.protection_used==1)

for key,value in [('evidence_origin','ui'),('attempt_id','old_attempt'),('root_id','other_root'),
                  ('actor_id','other_actor'),('bound_source_id','other_source'),
                  ('source_receipt_verified',False),('observed_world_time','1')]:
    r=fixture('S43'); p=proof(r); p[key]=value; p['route_verified']=False
    check('invalid open-source fact cannot revoke hostility: '+key,
          not r.accept_source_open_receipt(p) and not r.source_hostility_revoked
          and r.attack_allowed() and r.plan is None)
r=fixture('S43'); r.life.add_poison(125); p=proof(r); p['route_verified']=False
check('true S43 open source is accepted before any route exists',r.accept_source_open_receipt(p)
      and r.source_hostility_revoked and r.source_open_receipt_id==r.expected_source_id and r.plan is None)
check('first blocked route does not restore S43 attacks or poison',not r.enter(p) and not r.protected
      and not r.attack_allowed() and r.poison_tick(1)==0 and r.life.poison==125 and r.life.hp==240)
check('source receipt alone gives no exit no plan no reward',r.actor_present and r.position==(0,0)
      and r.external_exit_at is None and r.plan is None and r.life.ledger.coins==0)
check('same source receipt is idempotent',r.accept_source_open_receipt(p)
      and sum(x['event']=='actual_source_open_revokes_hostility' for x in r.trace)==1)
check('actual route can later start the still-bound response',r.enter(proof(r)) and r.plan is not None)
r.elapse(1); r.start_latch(latch(r)); r.elapse(1)
check('later actual return and latch settle after source-only state',r.phase=='complete' and r.life.ledger.coins==12)
r=fixture('S43'); p=proof(r); p['route_verified']=False
check('enter also consumes valid source before rejecting its first route',not r.enter(p)
      and r.source_hostility_revoked and not r.attack_allowed() and r.plan is None)

r=fixture('S43'); r.life.add_poison(125); r.enter(proof(r)); r.elapse(F(1,2)); r.interrupt('real_route_blocked')
check('S43 path interruption does not fabricate a new closed-mall hostility',not r.protected
      and not r.attack_allowed() and r.poison_tick(1)==0 and r.life.poison==125
      and r.actor_present and r.life.ledger.coins==0)

r=fixture('S43',deadline=3); r.enter(proof(r)); r.elapse(1); r.start_latch(latch(r)); r.elapse(F(1,2)); r.cancel_latch()
check('canceled uncommitted latch does not finish or respawn actor',r.phase=='awaiting_latch'
      and r.latch_done==0 and not r.actor_present and r.life.ledger.coins==0)
r.elapse(1)
check('late gate cannot use a fresh clock',not r.start_latch(latch(r)))
r.elapse(F(1,2))
check('departed-but-unlatched timeout has no root reward',r.phase=='failed' and not r.actor_present and r.life.ledger.coins==0)

files=['content/rule_response_contracts_sa02.json','content/monster_scp_b_md01.json',
       'content/monster_contracts_md01.json','content/combat_contracts_td05.json',
       'content/attack_contracts_ma01.json','scripts/md01_reference.py',
       'scripts/sa02_response_reference.py','scripts/check_sa02_responses.py']
report={'version':'SA02','baseline_commit':BASELINE,'runtime_integrated':False,'runtime_enabled':False,
        'all_gameplay_proven':False,'registered_monsters':['S40','S43'],
        'scope':'Finite source-bound response priorities on caller-verified fixture routes; no map or full AI proof.',
        'legacy_counterexample':{'scope':'q=125 is allowed by the source model; its gameplay acquisition route is not proven. A deadlock arises only if suppression restarts the undefined noncombat response.','cycles':legacy},
        'passed':sum(x['passed'] for x in rows),'failed':sum(not x['passed'] for x in rows),'checks':rows,
        'input_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        'not_proven':contract['validation_boundary']['not_proven']}
(ROOT/'docs/sa02_response_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('passed','failed','registered_monsters','runtime_integrated','all_gameplay_proven')},ensure_ascii=False))
if report['failed']:
    print(json.dumps([x for x in rows if not x['passed']],ensure_ascii=False,indent=2))
    raise SystemExit(1)
