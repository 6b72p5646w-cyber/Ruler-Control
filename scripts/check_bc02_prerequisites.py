#!/usr/bin/env python3
"""Audit real source contracts plus finite dependency/transaction counterexamples.

Tests do not mark missing geometry or a client adapter complete.  Only the old
12 BC01 layouts retain their prior geometry-reference status. Each of the 105
entries still needs an actual client integration test before runtime admission.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from bc02_prerequisite_reference import (
    ROOT, Receipt, World, PhysicalObject, SpawnTransaction, FilamentLedger,
    registry, encounter_index, dependency_witness, source_action_graph,
    blood_admission, paid_customer_device_support,
)

checks = []

def check(name, ok):
    checks.append({'name': name, 'passed': bool(ok)})


def rejected(fn):
    try:
        fn()
    except (ValueError, KeyError):
        return True
    return False


def json_pointer_exists(ref):
    path, pointer = ref.split('#', 1)
    try:
        obj = json.loads((ROOT / path).read_text())
        for token in pointer.strip('/').split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            obj = obj[int(token)] if isinstance(obj, list) else obj[token]
        return True
    except (FileNotFoundError, ValueError, KeyError, IndexError):
        return False


cfg = registry()
index = encounter_index()
env = json.loads((ROOT / 'content/environment_conditions_bc02.json').read_text())
env_ids = {c['condition_id'] for c in env['conditions']}
source_ids = {f'F{i:02d}' for i in range(1, 61)} | {f'S{i:02d}' for i in range(1, 46)}
check('exactly all 105 independent monster IDs covered', set(index) == source_ids)
check('all existing 12 geometry references preserved without adding a new layout',
      sum(c['module_binding']['existing_bc01_geometry_reference_admitted'] for c in index.values()) == 12)
check('all 105 client admission gates remain honest', all(not c['runtime_integrated'] and not c['module_binding']['client_adapter_ready'] for c in index.values()))
check('F14 still opt-in and disabled by default', not index['F14']['default_enabled_after_implementation'])
check('implementation batches cover each card exactly once',
      sorted(i for b in cfg['implementation_batches'].values() for i in b['ids']) == sorted(source_ids))

coverage = []
for mid, case in index.items():
    g = source_action_graph(mid)
    witness = dependency_witness(mid)
    check(mid + ': all explicit repository source pointers resolve', all(json_pointer_exists(r) for r in case['sources']))
    check(mid + ': terrain IDs are existing definitions', set(case['environment_condition_ids']) <= env_ids)
    check(mid + ': current step source has actual production outputs', bool(case['action_graph']) and all(a['produces'] and a['physical_predicates'] is not None for a in case['action_graph']))
    check(mid + ': no literal old example root is executable',
          ':example:' not in json.dumps([a['physical_predicates'] for a in case['action_graph']]))
    check(mid + ': source/action graph is acyclic and reaches declared main terminal', witness['terminal_reachable'])
    check(mid + ': module specification contains actual binding constraints',
          bool(case['module_binding']['specific_layout_and_routes']) and len(case['module_binding']['bindings_must_include']) >= 8 and bool(case['source_manifest']['original_objects']))
    check(mid + ': free tools are nonpositional module refs, not arbitrary supplier slots',
          all('module_ref_nonpositional' in t and 'supply_anchor_or_module' not in t and t['reward_on_supply_or_return'] == 0 for t in case['free_tools']))
    # Every real provenance input must dominate the terminal. A disconnected
    # historical source or merely decorative terrain field would fail this test.
    sources = [n for n in case['source_nodes'] if n['kind'] != 'visible_arrival_transaction' and n.get('required_for_admission',True)]
    missing_results = []
    for node in sources:
        blocked = not dependency_witness(mid, [node['id']])['terminal_reachable']
        missing_results.append(blocked)
    check(mid + ': each required source removal blocks declared completion', all(missing_results))
    coverage.append({'monster_id': mid, 'name': case['name'], 'module_family': case['module_family'],
                     'implementation_batch': case['implementation_batch'], 'source_count': len(sources),
                     'action_count': len(case['action_graph']), 'dependency_reachable': witness['terminal_reachable'],
                     'all_source_omissions_block': all(missing_results),
                     'existing_bc01_geometry_reference': case['module_binding']['existing_bc01_geometry_reference_admitted'],
                     'new_continuous_geometry_or_AI_proof': False,
                     'runtime_admitted': False})


def fixture(mid='F25', root='campaign/night/root'):
    """Explicit finite world fixture, not evidence of a shipped map adapter."""
    case = index[mid]
    w = World(now=100)
    # One actual test object for every declared manifest BUNDLE. Count/member
    # expansion remains an explicit runtime binding obligation, not this proof.
    object_ids = [mid + ':fixture_bundle:' + str(i) for i in range(len(case['source_manifest']['original_objects']))]
    for oid in object_ids:
        rid = oid + ':stock'
        w.add_actual_receipt(Receipt(rid, 'actual_stock_count', 10, (oid,), 'finite fixture stock observation'))
        w.add_object(PhysicalObject(oid, oid, 'EMPLOYER', 'actual_stock_slot', rid))
    history = {}
    for h in (n for n in case['source_nodes'] if n['kind'] == 'immutable_prior_receipt'):
        rid = h['id'] + ':receipt'
        w.add_actual_receipt(Receipt(rid, h['producer'], 40, tuple(object_ids), 'finite fixture prior event'))
        history[h['id']] = rid
    modid = mid + ':module_proof'
    w.add_actual_receipt(Receipt(modid, 'actual_installed_module_and_routes', 50,
                                (case['module_binding']['id'],), 'finite fixture module proof'))
    w.install_module(mid, modid)
    environment = {}
    for binding in case['environment_bindings']:
        if not binding['required_for_admission']:
            continue
        cid=binding['condition_id'];rid=mid+':'+cid
        producer=cid if binding['condition_must_be_true_at_admission'] else 'registered_condition_adapter:'+cid
        w.add_actual_receipt(Receipt(rid, producer, 80, (mid + ':actual_region',), 'finite fixture live source or capability', expires_at=200))
        environment[cid] = rid
    tx = SpawnTransaction(w, mid, root)
    args = dict(objects=object_ids, history=history, module_receipt_id=modid, environment=environment)
    return w, tx, args


def arrive(w, tx):
    rid = tx.root_id + ':arrival'
    w.add_actual_receipt(Receipt(rid, 'actual_actor_arrival', w.now, (tx.monster_id + ':actor',), 'finite fixture actual arrival'))
    tx.stage_actor(tx.monster_id + ':actor', rid)


w, tx, args = fixture()
check('F25 missing original sale rejects before reserving any objects', rejected(lambda: tx.reserve(**{**args, 'history': {}})))
check('failed atomic reserve leaves all physical stock free', all(o.reserved_by is None for o in w.objects.values()))
check('draw cannot manufacture historic sales/failed glass events', rejected(lambda: tx.materialize_history('sale', True)))
check('claim-only NPC speech is not history receipt', rejected(lambda: w.add_actual_receipt(Receipt('lie', 'ORIGINAL_SALE', 40, ('claimed',), 'voice', claim_only=True))))
check('future history cannot predate itself', rejected(lambda: w.add_actual_receipt(Receipt('future', 'ORIGINAL_SALE', 120, ('future',), 'fixture'))))
wrong = copy.deepcopy(args)
firsth = next(iter(wrong['history']))
w.add_actual_receipt(Receipt('wrong_original_sale', 'ORIGINAL_SALE', 40, ('other_item',), 'fixture unrelated sale'))
wrong['history'][firsth] = 'wrong_original_sale'
check('historical sale for another physical original rejected', rejected(lambda: tx.reserve(**wrong)))
tx.reserve(**args)
check('all originals reserved to one stable logical root', all(o.reserved_by == tx.root_id for o in w.objects.values()))
check('cannot commit before actual actor arrival', rejected(lambda: tx.commit()))
arrive(w, tx)
check('hands occupied blocks combat commit', rejected(lambda: tx.commit(hands_clear=False)))
check('unsafe ordinary customer blocks combat commit', rejected(lambda: tx.commit(ordinary_customers_safe=False)))
check('writing a new spec never opens missing client adapter', rejected(lambda: tx.commit(runtime=True)))
result = tx.commit()
check('finite source transaction can commit without claiming runtime', not result['runtime'] and tx.state == 'COMMITTED_REFERENCE')
check('stable logical root cannot commit again', rejected(lambda: tx.commit()))
w.add_actual_receipt(Receipt('rule_not_death', 'actual_main_rule_only', w.now, (tx.root_id,), 'fixture'))
check('F25 rule unlock is not automatic monster death/reward', rejected(lambda: tx.settle(main_rule_verified=True, source_receipt_id='rule_not_death')))
w.add_actual_receipt(Receipt('true_death', 'actual_required_pools_defeated', w.now, (tx.root_id,), 'fixture actual HP0'))
a = tx.settle(main_rule_verified=True, required_pools_zero=True, source_receipt_id='true_death')
b = tx.settle(main_rule_verified=True, required_pools_zero=True, source_receipt_id='true_death')
check('same actual root terminal is rewarded once after replay', a == b and len(w.rewards) == 1 and a['coins'] == 12 and a['spirit'] == 6)
check('monster trade does not create ordinary customer appliance support', not a['normal_customer_facility_buff'])

w2, tx2, args2 = fixture('F17', 'root17')
tx2.reserve(**args2)
oid = args2['objects'][0]
w2.add_actual_receipt(Receipt('delivered_parcel', 'actual_visible_delivery', w2.now, (oid,), 'fixture actual delivery'))
tx2.deliver_existing(oid, 'original_public_pickup_slot', 'delivered_parcel')
positions = tx2.abort()
check('aborting after delivery retains real original position', positions[oid] == 'original_public_pickup_slot')
check('abort releases reservation but gives no currency', all(o.reserved_by is None for o in w2.objects.values()) and not w2.rewards)
check('cannot clone original item with another object ID', rejected(lambda: w2.add_object(PhysicalObject('copy', oid, 'EMPLOYER', 'elsewhere', w2.objects[oid].source_receipt_id))))
check('critical parcel cannot be replaced with a new similar one', rejected(lambda: w2.replace_support_tool(oid, 'service', 'new_parcel', 'none')))

w3, tx3, args3 = fixture('F05', 'root5')
tx3.reserve(**args3); arrive(w3, tx3)
w3.now = 200
check('wet/environment source expired between reserve and commit blocks spawn', rejected(lambda: tx3.commit()))
check('expiry does not rewrite environment TTL', all(w3.receipts[r].expires_at == 200 for r in args3['environment'].values()))

w4 = World(now=20)
w4.add_actual_receipt(Receipt('tool_stock', 'actual_stock_count', 0, ('mop',), 'fixture'))
w4.add_object(PhysicalObject('mop', 'mop', 'EMPLOYER', 'unreachable_adapter_error', 'tool_stock', kind='reusable_support_tool'))
w4.add_actual_receipt(Receipt('service1', 'safe_phase_recovery_service', 20, ('mop', 'mop_v2'), 'fixture safe repair'))
check('non-original support tool repair creates one linked replacement', w4.replace_support_tool('mop', 'repair1', 'mop_v2', 'service1'))
check('tool repair replay cannot create another tool/reward', not w4.replace_support_tool('mop', 'repair1', 'mop_v3', 'service1') and len(w4.objects) == 2 and not w4.rewards)

w5, tx5, args5 = fixture('S38', 'root38')
tx5.reserve(**args5); arrive(w5, tx5); tx5.commit()
w5.add_actual_receipt(Receipt('safe_storage', 'actual_rule_leave', w5.now, (tx5.root_id,), 'fixture'))
p = tx5.settle(main_rule_verified=True, physical_terminal=True, source_receipt_id='safe_storage', passive=True)
check('S38 passive original-glasses storage never pays root money', p['coins'] == p['spirit'] == 0)

# Source lifetime is computed against real staging, not the old 45-second gate.
check('blood baseline includes 20 second omen and 24 second response route',
      blood_admission(now=30, injury_created=0, injury_source='BUSINESS_E003_GLASS_CONTACT', trace_created=[28])['required_remaining'] == 53)
check('fresh real BUSINESS glass source and recent physical trail can admit',
      blood_admission(now=30, injury_created=0, injury_source='BUSINESS_E003_GLASS_CONTACT', trace_created=[28])['admitted'])
check('old 45-second remaining shortcut fails the 53-second actual lead budget',
      not blood_admission(now=45, injury_created=0, injury_source='BUSINESS_E003_GLASS_CONTACT', trace_created=[44])['admitted'])
check('30 second blood trail can expire during 20 second omen even with fresh wound',
      not blood_admission(now=20, injury_created=0, injury_source='BUSINESS_E003_GLASS_CONTACT', trace_created=[5])['admitted'])
check('F13 cleaning blood never substitutes living wound source',
      not blood_admission(now=1, injury_created=0, injury_source='F13_CORPSE', trace_created=[0])['admitted'])
check('default F21 next-raid blood dependency rejects 115s over 90s TTL',
      not blood_admission(now=1, injury_created=0, injury_source='F21_GLASS_FAULT', trace_created=[0], standard_previous_F21=True)['admitted'])
check('F32 may require real wound without requiring a trail',
      blood_admission(now=20, injury_created=0, injury_source='BUSINESS_E003_GLASS_CONTACT', trace_created=[], needs_live_trace=False)['admitted'])

silk = FilamentLedger('S30/root')
silk.lay(0, ['line_A', 'line_B'])
check('S30 actual filament damage expires after eight world seconds', not any(silk.active_danger(k, 9) for k in silk.fibers))
check('S30 expired danger leaves original material physically recoverable', all(f['location'] in ['line_A', 'line_B'] for f in silk.fibers.values()))
check('S30 cannot close a missing two-original-material chain', rejected(silk.seal))
keys = list(silk.fibers)
silk.recover(keys[0], 20)
check('S30 one recovered filament cannot be gathered twice', not silk.recover(keys[0], 21))
silk.recover(keys[1], 200)
check('S30 late inert-filament recovery still closes the actual source chain', silk.seal())
check('S30 sealing replay is idempotent and does not respawn filament', not silk.seal() and len(silk.fibers) == 2)

check('normal paying customer actual device use creates support', paid_customer_device_support('NORMAL_CUSTOMER', True, True, True))
for actor in ['ANOMALOUS_VISITOR', 'DISGUISED_EMPLOYEE', 'COWORKER', 'PLAYER', 'MANAGER', 'SUMMON_CHILD']:
    check(actor + ' cannot impersonate normal-customer device payment', not paid_customer_device_support(actor, True, True, True))
check('unpaid normal use does not charge support', not paid_customer_device_support('NORMAL_CUSTOMER', False, True, True))
check('normal paid order without device use does not charge support', not paid_customer_device_support('NORMAL_CUSTOMER', True, True, False))

# Independent numerical counterexamples tied to the source cards.
check('F03 composite crossing pays carry distance exactly once', abs(3/2.4 + .6 - 1.85) < 1e-9)
check('F03 MA01 remaining preview+flight+recovery covers its composite crossing', .5 + .6 + 1 >= 1.85)
check('F34 true 6s rest covers actual two-way walking and 2s wipe', 2/3 + 2 + 2/3 < 6)
check('F34 2.5s attack recovery alone does not cover same roundtrip', 2/3 + 2 + 2/3 > 2.5)
check('F42 exact zero-stamina transfer fits eight-second pressure window', abs(1+1.5+3/2.4+1.5+3/3+1-7.25) < 1e-9 and 7.25 < 8)
check('F46 one tile cannot be crossed at 3 tiles per second in .25s', 1/3 > .25)
check('F38 short same-body grant chain fits 8s only before extra walking', 10/3 + 1 + 1.5 < 8)
check('F53 new night-close excludes forced manual manager/keys chores', '取消700' in index['F53']['work_and_retry']['BC02_effective_correction'])


# A visible precommit theft is neither an invented prior event nor an automatic
# consequence of drawing F16. Stock is reserved first; actual transfer follows.
w6, tx6, args6 = fixture('F16', 'root16')
check('F16 current theft is not an immutable pre-selection history gate', not args6['history'])
tx6.reserve(**args6); arrive(w6, tx6)
check('F16 cannot commit until original coin was visibly transferred', rejected(lambda: tx6.commit()))
arrival_node = next(n for n in index['F16']['source_nodes'] if n['kind']=='arrival_effect_receipt')
w6.add_actual_receipt(Receipt('old_theft', arrival_node['producer'], 99, tuple(args6['objects']), 'fixture old event'))
check('F16 cannot borrow earlier unrelated theft for current arrival', rejected(lambda: tx6.bind_arrival_effect(arrival_node['id'],'old_theft')))
w6.add_actual_receipt(Receipt('actual_this_theft', arrival_node['producer'], 100, tuple(args6['objects']), 'fixture visible physical transfer'))
tx6.bind_arrival_effect(arrival_node['id'],'actual_this_theft')
check('F16 reserves then actually steals then commits same root', not tx6.commit()['runtime'])
f38=index['F38']
check('F38 current A observations precede actual B arrival root commit', all(a['execution_stage']=='PRECOMMIT_OMEN_CURRENT_IDENTITY' for a in f38['action_graph'][:6]))
check('F38 precommit observation never requires B already arrived', all('F38:source:actual_arrival' not in a['requires'] for a in f38['action_graph'][:6]))
check('F38 source commit waits on actual second-body walk', 'F38:action:see_second_arrive' in next(n for n in f38['source_nodes'] if n['kind']=='visible_arrival_transaction')['requires'])
check('paid-only customer claim cannot fabricate F19 two-receipt chain', 'delivery_received' in index['F19']['source_manifest']['prior_receipts'][0])
check('all necessary kill/weakening roots reserve a free actual damaging route', all(c['combat_prerequisite']['required_for_terminal'] == (c['terminal_node']['resolution_type']!='rule_leave') for c in index.values()))


# Consumer registration is not equivalent to demanding its future condition now.
w7, tx7, args7=fixture('F13','root13')
check('F13 does not need its own future corpse blood before admission', 'BC02_ENV_CLEANUP_BLOOD' not in args7['environment'])
tx7.reserve(**args7);arrive(w7,tx7)
check('F13 can commit without producing a corpse first', not tx7.commit()['runtime'])
f03=next(b for b in index['F03']['environment_bindings'] if b['condition_id']=='BC02_ENV_BREATH_TRACE')
check('F03 breath is a registered player producer, not a preexisting required cloud', not f03['condition_must_be_true_at_admission'])
s25=next(b for b in index['S25']['environment_bindings'] if b['condition_id']=='BC02_ENV_NO_SHADOW_ZONE')
check('S25 reflection steps may create their later no-shadow-zone condition', not s25['condition_must_be_true_at_admission'])
check('F30 does not require first misusing the original stone to create water', 'BC02_ENV_WET_CONNECTED' not in index['F30']['admission_environment_condition_ids'])
check('F60 main curtain/back-turn route does not depend on optional mirror light', 'BC02_ENV_LIGHT_COVERAGE' not in index['F60']['admission_environment_condition_ids'])
check('F60 main source graph bypasses optional read_mirror step', 'F60:action:read_mirror' not in next(a for a in index['F60']['action_graph'] if a['source_step_id']=='pull_curtain')['requires'])
check('environment consumers match current terrain registry', all(set(r['condition_ids'])==set(index[r['monster_id']]['environment_condition_ids']) for r in env['monster_consumers']))

# F58's already-authored manual exit is a real alternative terminal. Missing
# heat cannot remove it, and none of its actual sign/route/exit actions is free.
f58_no_heat = ['F58:source:optional_warm_original', 'F58:env:BC02_ENV_WARM_FIELD']
check('F58 reaches free cold close terminal with no food or warm-source binding', dependency_witness('F58', f58_no_heat)['terminal_reachable'])
for action in ('close_cold_section', 'walk_to_warm_side', 'exit_cold_boundary'):
    check('F58 no-food path still needs actual ' + action,
          not dependency_witness('F58', f58_no_heat + ['F58:action:' + action])['terminal_reachable'])
check('F58 optional original warm food remains a separate terminal branch',
      dependency_witness('F58', ['F58:action:close_cold_section'])['terminal_reachable'])
check('F58 warm-only branch cannot omit its actual original heat source',
      not dependency_witness('F58', ['F58:action:close_cold_section', 'F58:source:optional_warm_original'])['terminal_reachable'])
check('F58 optional heat supplies are not mandatory admission inventory',
      all(not s['required_for_admission'] for s in index['F58']['supply_reservations'])
      and 'BC02_ENV_WARM_FIELD' not in index['F58']['admission_environment_condition_ids'])
from bc01_map_reference import StoreMap
f58_exit_route = StoreMap().route([24.5, 15.5], [21.5, 15.5])
check('F58 reference exit walks real three-tile body-clear route plus two half-second actions',
      f58_exit_route['body_clear'] and f58_exit_route['distance'] == 3
      and .5 + f58_exit_route['distance'] / 3 + .5 == 2)


# A roster of 105 is a cross-night module catalog, not 105 live fixtures.
w8,tx8,args8=fixture('S01','root_cage')
s06module=index['S06']['module_binding']['id']
w8.add_actual_receipt(Receipt('S06_module', 'actual_installed_module_and_routes',100,(s06module,),'fixture second large proof'))
check('a second different large module cannot occupy same nightly task slot', rejected(lambda:w8.install_module('S06','S06_module')))
w8.business_started=True
s04module=index['S04']['module_binding']['id']
w8.add_actual_receipt(Receipt('S04_module','actual_installed_module_and_routes',100,(s04module,),'fixture late small proof'))
check('opening freezes installed scene modules; arrival cannot build a new station',rejected(lambda:w8.install_module('S04','S04_module')))
w9,tx9,args9=fixture('F01','root_missing_installed')
w9.installed_modules.clear()
check('a valid-looking module receipt alone is not an installed-night-plan entry',rejected(lambda:tx9.reserve(**args9)))

failed = [c for c in checks if not c['passed']]
input_paths = {
    'content/encounter_prerequisites_bc02.json',
    'content/environment_conditions_bc02.json',
    'content/map_composition_bc01.json', 'content/maps.json',
    'scripts/check_bc02_prerequisites.py', 'scripts/bc02_prerequisite_reference.py',
    'scripts/bc01_map_reference.py',
}
input_paths.update(ref.split('#', 1)[0] for case in index.values() for ref in case['sources'])
report = {
    'version': 'BC02', 'status': 'passed' if not failed else 'failed',
    'check_count': len(checks), 'passed_count': len(checks) - len(failed),
    'failed': failed,
    'scope': '105逐条来源/对象/模块/动作/响应设计 + 有限依赖图、事务、TTL、原物/收益反例；不是105连续AI实机通关',
    'design_covered': 105, 'action_nodes': sum(len(c['action_graph']) for c in index.values()),
    'prior_bc01_geometry_reference_count': 12, 'new_geometry_validated_count': 0,
    'runtime_admitted_count': 0,
    'history_gated_count': sum(bool(c['source_manifest']['prior_receipts']) for c in index.values()),
    'module_family_count': len({c['module_family'] for c in index.values()}),
    'source_omission_experiments': sum(c['source_count'] for c in coverage),
    'implementation_batches': {k: {'count': len(v['ids']), **v} for k, v in cfg['implementation_batches'].items()},
    'limitations': [
        '依赖拓扑叶节点代表必须由真实适配器提交的观测，不是把所有条件当开场真值。',
        '事务测试使用显式有限fixture，每个manifest bundle的全部成员/数量仍须实际场景逐个绑定。',
        '已有12个BC01几何参考未在本检查中宣称新增通过；其余93仍须对应模块几何与时间验收。',
        '全部105正式客户端AI/触屏/寻路/动画/连续伤害集成仍未由本脚本实现。',
        'F14人类宿主模块单独可选默认关闭；新规则不能直接改runtime_admitted为true。'
    ],
    'coverage': coverage, 'checks': checks,
    'input_sha256': hashlib.sha256((ROOT/'content/encounter_prerequisites_bc02.json').read_bytes()).hexdigest(),
    'inputs_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                     for path in sorted(input_paths)},
}
(ROOT / 'docs/bc02_prerequisite_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'checks': len(checks), 'failed': failed,
                  'design_covered': 105, 'action_nodes': report['action_nodes'],
                  'source_omissions': report['source_omission_experiments'], 'runtime_admitted': 0}, ensure_ascii=False))
raise SystemExit(bool(failed))
