#!/usr/bin/env python3
"""Counterexamples for SA01's legacy deployment bridge; no full-map claim."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

from sa01_legacy_reference import (MANAGEMENT, management_allowed, capacity_allowed,
    geometry_admitted, TimedInstallation, install_i16, PreparedLauncher, GuardPad)


ROOT = Path(__file__).resolve().parents[1]


def run():
    checks=[]
    def check(name, result):
        checks.append({'name': name, 'passed': bool(result)})

    bridge=json.loads((ROOT/'content/legacy_deployment_bridge_sa01.json').read_text())
    entries={x['id']:x for x in bridge['entries']}
    check('all eight old B helpers and I16 remain enabled designs with runtime closed',set(entries)=={f'B{i:02}' for i in range(1,9)}|{'I16'} and all(x['design_enabled'] and not x['runtime_enabled'] for x in entries.values()))
    check('unknown authored footprints stay unknown instead of fabricated one-cell placements',all(x['floor_footprint_cells'] is None for x in entries.values()))
    check('B01 enemy field is1.5 but B08 player circle remains its original separate scope',bridge['geometry']['enemy_circle_override']['B01_radius_tiles']==1.5 and bridge['geometry']['B08_player_guard_radius_is_not_enemy_field'])
    check('Q08 two real lamp points participate in the same legacy subcap',bridge['capacity']['Q08_two_points_count']==2 and 'Q08_each_installed_point' in bridge['capacity']['legacy_counted_definitions'])

    for action in sorted(MANAGEMENT):
        check('open shift cannot '+action,not management_allowed('open',action))
    check('peaceful text cannot impersonate preparation',not management_allowed('peaceful_open','install'))
    check('actual preparation can load and recover hardware',management_allowed('pre_shift','reload') and management_allowed('pre_shift','recover'))
    check('unknown management action is rejected even in preparation',not management_allowed('pre_shift','invent_source'))
    check('three old helpers plus five R traps fit the shared eight object cap',capacity_allowed(3,5,16,6))
    check('three old helpers are not extra capacity beyond eight R traps',not capacity_allowed(3,8,16,6))
    check('a fourth legacy helper fails even below the overall cap',not capacity_allowed(4,0,4))
    check('physical footprint seventeen fails despite few objects',not capacity_allowed(2,1,17))
    check('negative or fractional capacity counts cannot mint space',not capacity_allowed(-1,8,1) and not capacity_allowed(1.5,0,1))
    check('unverified socket coordinates are not installable footprints',not geometry_admitted('floor',[(1,2)],verified=False) and not geometry_admitted('floor',None,verified=True))
    check('actual floor install needs a nonempty physical cell set',geometry_admitted('floor',[(1,2)],verified=True) and not geometry_admitted('floor',[],verified=True))
    check('verified wall mount counts zero floor cells rather than an invented area',geometry_admitted('wall',[],verified=True) and not geometry_admitted('wall',[(1,2)],verified=True))
    check('duplicate physical cells cannot fake a footprint budget',not geometry_admitted('floor',[(1,2),(1,2)],verified=True))

    personal={'stick-a':'I16','stick-b':'I16'}; defense={}
    before=deepcopy((personal,defense))
    check('I16 cannot be installed from inventory during business',install_i16(personal,defense,'stick-a','w1',phase='open',geometry_valid=True,capacity_valid=True) is None and (personal,defense)==before)
    check('failed geometry leaves the same personal I16 unconsumed',install_i16(personal,defense,'stick-a','w1',phase='pre_shift',geometry_valid=False,capacity_valid=True) is None and (personal,defense)==before)
    check('failed capacity leaves no partial installed instance',install_i16(personal,defense,'stick-a','w1',phase='pre_shift',geometry_valid=True,capacity_valid=False) is None and (personal,defense)==before)
    device=install_i16(personal,defense,'stick-a','w1',phase='pre_shift',geometry_valid=True,capacity_valid=True)
    check('I16 install atomically moves from personal ownership into a week-bound installation',device is not None and 'stick-a' not in personal and list(defense)==['installed:stick-a'] and device.week_id=='w1')
    check('replaying the same I16 installation cannot clone a second device',install_i16(personal,defense,'stick-a','w1',phase='pre_shift',geometry_valid=True,capacity_valid=True) is None and len(defense)==1)
    check('preinstalled I16 has not spent its twenty seconds before activation',not device.activation_spent and device.deadline is None)
    check('I16 activation spends no second personal item',device.activate(100,'n1') and personal=={'stick-b':'I16'} and device.deadline==120)
    check('timed light is active until but not at its exact expiry',device.live(119.99,'n1') and not device.live(120,'n1'))
    device.finish_night()
    check('night end does not revive an already used I16',not device.live(110,'n2') and not device.activate(110,'n2') and device.deadline==120 and device.activation_spent)
    defense.clear()
    check('week clearing installed hardware preserves genuinely unused personal I16',personal=={'stick-b':'I16'} and not defense)
    unopened=TimedInstallation('screen','B02','w1',F(20));unopened.finish_night()
    check('an unactivated paid screen may first activate on a later night',unopened.activate(200,'n2') and unopened.deadline==220)
    unopened.finish_night()
    check('early handover consumes a started finite screen budget without next-night renewal',not unopened.activate(205,'n3') and unopened.activation_spent)
    bad=TimedInstallation('mat','B07','w1',F(20));before=deepcopy(bad)
    check('invalid target or negative time cannot spend a prepared activation',not bad.activate(0,'n1',target_valid=False) and not bad.activate(-1,'n1') and bad==before)
    check('finite activation survives save as the same absolute deadline and spent budget',deepcopy(unopened)==unopened)

    ammo={'portion-a','portion-b'};box=PreparedLauncher('box')
    check('B05 loads only a real fetched portion during preparation',box.load('pre_shift',ammo,'portion-a','load-a') and ammo=={'portion-b'} and box.loaded==['portion-a'])
    before=deepcopy((ammo,box))
    check('B05 refuses business reload even when a free real portion is in hand',not box.load('open',ammo,'portion-b','load-b') and (ammo,box)==before)
    check('B05 invalid path leaves paid loaded ammo intact',box.fire('open','fire-bad',real_point_and_path=False) is None and box.loaded==['portion-a'])
    check('B05 business activation consumes exactly one preloaded original portion',box.fire('open','fire-a')=='portion-a' and not box.loaded and box.spent_portions=={'portion-a'})
    check('same B05 firing receipt and empty box cannot produce new bait',box.fire('open','fire-a') is None and box.fire('open','fire-empty') is None)
    check('blocked B05 refill leaves free native hand-scatter supply available',ammo=={'portion-b'} and '手动撒已亲取回形针' in bridge['phase_permissions']['native_rule_actions_unrestricted_by_deployment_lock'])

    for label,kwargs in [
        ('uncommitted',{'committed':False}),('no real collision',{'geometry_hit':False}),
        ('outside guard',{'player_in_guard':False}),('curse failure',{'curse_failed':True}),
        ('no pending positive damage',{'pending_positive_damage':False}),('existing grace',{'grace_until':2})]:
        pad=GuardPad();before=deepcopy(pad)
        check('B08 does not spend on '+label,pad.intercept(1,'a','F12:BASIC',**kwargs) is None and pad==before)
    pad=GuardPad()
    check('B08 does not widen to other melee or ordinary body touch',pad.intercept(1,'a','F01:BASIC') is None and pad.intercept(1,'body','F12:UNARMED_BODY') is None and pad.charges==1)
    result=pad.intercept(2,'accepted','F12:BASIC',grace_until=2)
    check('B08 intercepts a real F12 basic exactly at old grace expiry',result is not None and result['grace_until']==5 and pad.charges==0 and pad.broken)
    check('B08 collision does not grant I39 or invent blood',result['collision_recorded'] and not result['spatial_miss_reward'] and not result['new_blood'])
    check('broken B08 cannot intercept another attack or replay the same one',pad.intercept(6,'accepted','F12:BASIC') is None and pad.intercept(6,'new','F13:BASIC') is None)
    result=GuardPad(tier=2).intercept(10,'f13','F13:BASIC')
    check('B08 L2 preserves its original two-second grace tradeoff',result is not None and result['grace_until']==12)

    passed=sum(x['passed'] for x in checks)
    return {'version':'SA01','runtime_integrated':False,'passed':passed,'failed':len(checks)-passed,
            'scope':'Finite management, intersecting capacities, caller-verified geometry admission, I16 same-item ownership conversion, paid timed lifetime, prepared B05 ammunition and B08 hit migration. No all-device AI, map footprint proof, combat balance or playtest claim.','checks':checks}


if __name__=='__main__':
    report=run()
    inputs=['content/legacy_deployment_bridge_sa01.json','scripts/sa01_legacy_reference.py','scripts/check_sa01_legacy_bridge.py']
    report['input_hashes']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in inputs}
    (ROOT/'docs/sa01_legacy_validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','failed']}))
    if report['failed']:
        print(json.dumps([x['name'] for x in report['checks'] if not x['passed']]))
    raise SystemExit(bool(report['failed']))
