#!/usr/bin/env python3
"""Validate MD01 designs and bounded terminal/electric/reward fixtures.

Run from a complete repository: python3 scripts/check_md01_design.py
Sibling-cache fallback only supports the authoring workspace; no downloads.
"""
import hashlib
import importlib.util
import itertools
import json
import math
import statistics
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from md01_reference import (ElectricGateFixture, EncounterGroup, LifeState, RewardLedger,
                            ShiftTicketLedger, clean, num, split_conserved)

ROOT = Path(__file__).resolve().parents[1]
BASES = [ROOT] + [ROOT.parent / n for n in (
    'ruler-control-td05', 'ruler-control-md01-source',
    'ruler-control-source', 'ruler-control-td02')]
INPUTS = {}
CHECKS = []


def resolve(path):
    for base in BASES:
        p = base / path
        if p.is_file():
            return p
    raise FileNotFoundError(path)


def read(path):
    p = resolve(path)
    raw = p.read_bytes()
    INPUTS[path] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def check(name, condition, detail=''):
    CHECKS.append({'id': name, 'passed': bool(condition), 'detail': detail})


def fixture_record(kind='kill_unlocked', hp=180, armor=0, ward=0):
    return {'resolution': {'type': kind},
            'stats': {'hp': hp, 'armor': armor, 'ward': ward},
            'post_rule': {'armor': armor / 2, 'ward': ward / 2}}


def receipt(s, name='main-rule'):
    return {'id': name, 'root': s.root, 'verified': True}


def main():
    registry = read('content/monster_roster_md01.json')
    rows = []
    for path in registry['data_files']:
        rows += read(path)['monsters']
    by_id = {m['id']: m for m in rows}
    originals = {m['id']: m for m in read('content/monsters.json')['monsters']}
    towers = read('content/tower_defense_td05.json')
    source_traps = read('content/traps_facilities_td05.json')
    trap_ids = {t['id'] for t in source_traps['traps']}
    chase = read('content/chase_profiles_td05.json')
    shared = read('content/monster_contracts_md01.json')
    lottery = read('content/lottery_direction_md01.json')
    old_lottery = read('content/items.json')['lottery']
    scp_sources = read('content/scp_attribution_md01.json')
    spec = importlib.util.spec_from_file_location('td05_reference', resolve('scripts/td05_reference.py'))
    td05 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(td05)
    INPUTS['scripts/td05_reference.py'] = hashlib.sha256(resolve('scripts/td05_reference.py').read_bytes()).hexdigest()
    tower_nodes = {n['id']: n for n in td05.nodes(towers)}
    l3_ids = {k for k in tower_nodes if len(k.split('.')[-1]) == 2 and '.' in k}
    expected_ids = {f'F{i:02}' for i in range(1, 61)} | {f'S{i:02}' for i in range(1, 46)}
    check('roster.exact_105_unique', len(rows) == 105 and set(by_id) == expected_ids)
    check('roster.baseline_is_60', len(originals) == 60)
    check('roster.design_only', registry['runtime_integrated'] is False and shared['runtime_integrated'] is False)
    check('roster.origin_truth', sum(m['origin'] == 'existing_folklore' for m in rows) == 60 and
          sum(m['origin'] == 'new_scp_adaptation' for m in rows) == 45)
    categories = Counter(m['resolution']['type'] for m in rows)
    check('roster.three_real_outcomes', set(categories) == {'kill_unlocked', 'rule_leave', 'rule_weaken'})
    required = {'id','name','origin','default_enabled','source_refs','adaptation_note','encounter_role',
                'first_day','pressure_cost','resolution','mechanism','stats','post_rule','movement',
                'combat','abilities','children','matchups','reward','lottery_required'}
    all_phases = []
    for m in rows:
        mid = m['id']
        check(f'{mid}.schema', required <= set(m))
        stats, post = m['stats'], m['post_rule']
        check(f'{mid}.numeric_bounds', stats['hp'] >= 0 and
              all(0 <= side[k] <= .75 for side in (stats, post) for k in ('armor', 'ward')) and
              all(side['move_speed'] >= 0 and side['attack_damage'] >= 0 for side in (stats, post)))
        check(f'{mid}.response_never_numeric_buff', all(post[k] <= stats[k] for k in ('armor','ward','move_speed','attack_damage')))
        meaningful = any(post[k] < stats[k] for k in ('armor','ward','move_speed','attack_damage')) or bool(post['removed_abilities'])
        check(f'{mid}.weakening_has_effect', m['resolution']['type'] != 'rule_weaken' or meaningful)
        check(f'{mid}.no_health_reset_on_rule', post['hp_policy'] == 'preserve_current_no_heal')
        mechanism = m['mechanism']
        steps = mechanism['steps']
        check(f'{mid}.mechanism_complete', bool(mechanism['cue']) and bool(steps) and
              bool(mechanism['success_condition']) and bool(mechanism['failure_recovery']) and
              bool(mechanism['work_window']) and bool(mechanism['completion_receipt']) and
              len({s['id'] for s in steps}) == len(steps) and
              all(isinstance(s['seconds'], (int, float)) and s['seconds'] >= 0 and s['action'] and s['anchor'] for s in steps))
        check(f'{mid}.no_lottery_gate', m['lottery_required'] is False and bool(mechanism['free_tools']))
        match = m['matchups']
        referenced = match['favorable'] + match['conditional'] + match['unfavorable']
        check(f'{mid}.real_tower_branches', bool(referenced) and set(referenced) <= l3_ids and bool(match['explanation']))
        check(f'{mid}.real_trap_ids', all(t in trap_ids for t in match['traps']))
        check(f'{mid}.telegraphed_contact', stats['attack_damage'] == 0 or (stats['attack_telegraph'] >= 1.5 and stats['attack_cooldown'] >= 2.5))
        check(f'{mid}.admission_fields', 1 <= m['first_day'] <= 7 and .5 <= m['pressure_cost'] <= 3)
        check(f'{mid}.root_reward_only', m['reward']['ledger'] == 'encounter_root_once' and
              m['reward']['base_coins'] == 12 and m['reward']['base_spirit'] == 4 and m['reward']['rule_bonus_spirit'] == 2)
        check(f'{mid}.explicit_carrier_and_outcome', bool(m['combat']['hp_meaning']) and
              bool(m['combat']['target_policy']) and bool(m['combat']['pre_rule_zero_hp']) and
              bool(m['combat']['post_rule_zero_hp']))
        if mid.startswith('F'):
            check(f'{mid}.identity_retained', m['name'] == originals[mid]['name_zh'])
        else:
            urls = [s.get('url','') for s in m['source_refs']]
            check(f'{mid}.official_source', any(u.startswith('https://scp-wiki.wikidot.com/scp-') for u in urls))
        if m['movement']['actual_transition']:
            all_phases.append(mid)
            check(f'{mid}.phase_contract', bool(m['movement'].get('phase_audit')))
        if stats['hp'] == 0:
            check(f'{mid}.noncombat_not_dead', m['resolution']['type'] == 'rule_leave')
        # Lifecycle field checks are paired with actual finite transitions.
        has_dependents = m['children']['kind'] in ('split', 'summon')
        expected_rule_spirit = 0 if has_dependents else 6
        if stats['hp'] > 0:
            s = LifeState(m, root=mid, auto_finish=not has_dependents)
            if s.kind == 'kill_unlocked':
                s.add_poison(8)
                s.apply_damage(100000)
                no_death = s.hp == 1 and not s.root_finished and s.state == 'active'
                s.complete_rule(receipt(s))
                hp_kept = s.hp == 1 and s.poison == 8
                s.poison_tick()
                check(f'{mid}.gate_witness', no_death and hp_kept and s.state == 'defeated' and s.ledger.spirit == expected_rule_spirit)
            elif s.kind == 'rule_leave':
                s.apply_damage(100000)
                was_suppressed = s.state == 'suppressed' and not s.root_finished
                s.complete_rule(receipt(s))
                check(f'{mid}.leave_witness', was_suppressed and s.state == 'left' and s.ledger.spirit == expected_rule_spirit)
            else:
                a = LifeState(m, root=mid+':hard', auto_finish=not has_dependents)
                a.apply_damage(100000)
                s.apply_damage(max(1, stats['hp']/5))
                before = s.hp
                s.complete_rule(receipt(s))
                preserved = s.hp == before
                s.apply_damage(100000)
                check(f'{mid}.both_routes_witness', a.state == s.state == 'defeated' and
                      a.ledger.spirit == (0 if has_dependents else 4) and s.ledger.spirit == expected_rule_spirit and preserved)
        else:
            s = LifeState(m, root=mid, auto_finish=not has_dependents)
            check(f'{mid}.noncombat_witness', s.apply_damage(10000) == 0 and not s.targetable and
                  s.complete_rule(receipt(s)) and s.state == 'left')
        if has_dependents:
            check(f'{mid}.single_pool_does_not_auto_pay_root',not s.root_finished and s.ledger.coins==0)
    check('identity.F14_excluded', by_id['F14']['default_enabled'] is False)
    check('identity.F46_slow_body', by_id['F46']['post_rule']['move_speed'] == 1.2)
    check('identity.F10_F54_anchored', by_id['F10']['stats']['move_speed'] == by_id['F54']['stats']['move_speed'] == 0)
    check('identity.F60_no_mirror_travel', by_id['F60']['movement']['actual_transition'] is False)
    sources = scp_sources['sources']
    check('sources.45_distinct_original_articles', len(sources) == 45 and len({s['url'] for s in sources}) == 45)
    check('sources.credits_present', all(s['title'] and s['url'] and s['author'] for s in sources))

    dynamic = {}
    # Invalid/foreign completion cannot bypass a lethal gate.
    s = LifeState(fixture_record())
    s.apply_damage(10000)
    rejected = [s.complete_rule({'id':'x','root':'other','verified':True}),
                s.complete_rule({'id':'y','root':s.root,'verified':False}), s.complete_rule({})]
    check('gate.requires_verified_same_root', not any(rejected) and s.hp == 1 and not s.rule_done)
    s.charge = 23
    for i in range(10):
        s.apply_damage(20, 'spiritual', electric_charge=2, receipt=f'hit{i}')
    check('gate.no_fake_electric_feedback_at_floor', s.charge == 23)
    s.complete_rule(receipt(s))
    check('gate.rule_does_not_replay_old_damage', s.hp == 1 and s.state == 'active')
    s.apply_damage(1, 'spiritual', electric_charge=1)
    check('gate.next_hit_finishes_and_cleans', s.state == 'defeated' and s.charge == 0 and s.poison == 0)

    # Reformation is public, bounded, and never applied to kill-unlocked pools.
    s = LifeState(fixture_record('rule_leave', 200))
    s.add_poison(40)
    s.charge = 6
    s.apply_damage(10000)
    blocked_loss = s.poison_tick(4)
    s.advance(4)
    no_early = s.state == 'suppressed' and s.hp == 1
    s.advance(.5)
    check('leave.explicit_reformation_preserves_poison', blocked_loss == 0 and no_early and s.hp == 50 and s.poison == 40 and s.charge == 6)
    s.poison_tick(1)
    check('leave.no_catchup_ticks', s.hp == 30)
    s.complete_rule(receipt(s))
    check('leave.no_post_terminal_reformation_or_damage', s.state == 'left' and s.apply_damage(10000) == 0)
    s.advance(100)
    check('leave.timer_cancelled', s.state == 'left' and s.recover_at is None)
    check('leave.not_a_kill_proc', s.terminal_reason == 'withdrawal')
    ordinary = LifeState(fixture_record('rule_weaken', 20))
    ordinary.apply_damage(100)
    check('defeat.real_kill_proc', ordinary.terminal_reason == 'true_combat_defeat')
    suppressed = LifeState(fixture_record('rule_leave', 20))
    suppressed.apply_damage(100)
    check('suppression.not_a_kill_proc', suppressed.terminal_reason is None and not suppressed.root_finished)

    # One overkill receipt cannot create multiple damage/charge applications.
    s = LifeState(fixture_record('rule_weaken', 200))
    s.apply_damage(10, 'spiritual', electric_charge=2, receipt='native-double')
    s.apply_damage(10, 'spiritual', electric_charge=2, receipt='native-double')
    check('electric.native_two_not_three_deduped', s.hp == 190 and s.charge == 2)

    # All-floor graph drains any finite stored charge without a gameplay cap.
    for initial in (5, 100, 1001):
        s = LifeState(fixture_record())
        s.hp = num(1)
        s.charge = initial
        graph = ElectricGateFixture({'A':s})
        graph.drain()
        check(f'electric.floor_drain_{initial}', len(graph.waves) == initial//5 and s.charge == initial%5 and graph.feedback_total == 0)
        dynamic[f'floor_charge_{initial}'] = {'waves':len(graph.waves),'remaining':s.charge,'actual_damage':0}

    # Crowds keep uncapped positive feedback before actual deaths/floors.
    for kind in ('rule_weaken', 'kill_unlocked'):
        pools = {str(i): LifeState(fixture_record(kind), root=str(i)) for i in range(6)}
        for s in pools.values():
            s.charge = 5
        graph = ElectricGateFixture(pools, edges=list(itertools.combinations(pools, 2)))
        first = graph.wave('0')
        check(f'electric.{kind}.six_feedback_no_cap', first['feedback'] == 6 and set(first['losses'].values()) == {36})
        graph.drain()
        check(f'electric.{kind}.real_end_state', all(s.hp == (0 if kind=='rule_weaken' else 1) for s in pools.values()))
        dynamic[f'six_{kind}'] = {'waves':len(graph.waves),'feedback_total':graph.feedback_total,
                                  'total_actual_loss':sum(180-s.hp for s in pools.values()),'first_wave':first}
    s = LifeState(fixture_record('rule_leave'))
    s.charge=20
    s.apply_damage(10000)
    graph=ElectricGateFixture({'suppressed':s})
    check('electric.suppressed_not_a_node', not graph.eligible() and graph.wave('suppressed') is None)
    s.advance(4.5)
    check('electric.reformed_can_rejoin', graph.eligible()=={'suppressed'})
    s.complete_rule(receipt(s))
    check('electric.left_never_joins', not graph.eligible() and s.charge==0)

    # Three connected pools, different local coefficients; AP bridge reaches far.
    pools = {k:LifeState(fixture_record('rule_weaken',1000),root=k) for k in 'ABC'}
    for s in pools.values():s.charge=5
    graph=ElectricGateFixture(pools, ('P','Q'), [('A','P'),('B','P'),('P','Q'),('C','Q'),('A','B')])
    wave=graph.wave('A')
    check('electric.full_graph_local_counts', wave['coefficients']=={'A':3,'B':3,'C':2} and wave['losses']=={'A':18,'B':18,'C':12})
    dynamic['relay_graph']=wave
    # Split conservation plus same-root payout. No copied q on every child.
    for weights in ([1,1], [1,2,3], [1]*8):
        parts=split_conserved(179,37,13,weights)
        check('split.conservation_'+str(len(weights)), all(sum(p[k] for p in parts)==num(v) for k,v in [('hp',179),('poison',37),('charge',13)]))
    try:
        split_conserved(0,37,13,[1,1])
        check('split.dead_pool_cannot_escape',False)
    except ValueError:
        check('split.dead_pool_cannot_escape',True)
    try:
        split_conserved(1,37,13,[1,1],child_hp_floor=1)
        check('split.insufficient_hp_for_two_lethal_gates_cancels',False)
    except ValueError:
        check('split.insufficient_hp_for_two_lethal_gates_cancels',True)
    parts=split_conserved(2,37,13,[1,1],child_hp_floor=1)
    check('split.exact_two_gate_floors_no_heal',sum(p['hp'] for p in parts)==2 and all(p['hp']==1 for p in parts))
    ledger=RewardLedger()
    for child in range(8):ledger.settle('one-root',successful=True,rule_completed=True)
    check('reward.children_share_root', ledger.coins==12 and ledger.spirit==6 and len(ledger.entries)==1)
    ledger.settle('timeout',successful=False,rule_completed=False)
    check('reward.timeout_no_pay', ledger.coins==12 and ledger.spirit==6)
    ledger=RewardLedger()
    mother=LifeState(fixture_record('rule_weaken'),root='split-root',ledger=ledger,auto_finish=False)
    child=LifeState(fixture_record('rule_weaken'),root='split-root',ledger=ledger,auto_finish=False)
    mother.complete_rule(receipt(mother))
    mother.apply_damage(10000)
    child.apply_damage(10000)
    child.finish_root()
    mother.finish_root()
    check('reward.qualified_mother_before_last_child',ledger.coins==12 and ledger.spirit==6 and len(ledger.entries)==1)
    check('reward.root_qualification_not_child_rule_effect',not child.rule_done and child.parameters is child.record['stats'])
    group=EncounterGroup('producer-root')
    mother=group.add_pool('mother',fixture_record('rule_weaken',100))
    child=group.add_pool('child',fixture_record('rule_weaken',50))
    mother.complete_rule(receipt(mother))
    mother.apply_damage(10000)
    check('reward.no_pay_with_required_live_child',not group.try_finish()['new'] and group.ledger.coins==0)
    child.apply_damage(10000)
    check('reward.no_pay_while_future_births_possible',not group.try_finish()['new'])
    group.close_production()
    check('reward.closed_source_all_pools_ends_once',group.try_finish()['spirit']==6 and not group.try_finish()['new'] and group.ledger.coins==12)

    # New rule outcomes do not change the TD05 baseline coin economy.
    incomes={}
    for name,orders,roots,rules in [('cautious',6,3,1),('normal',8,4,3),('proficient',10,6,5)]:
        incomes[name]={'coins':80+6*orders+12*roots,'spirit':4*roots+2*rules}
    check('economy.td05_income_preserved', incomes=={'cautious':{'coins':152,'spirit':14},'normal':{'coins':176,'spirit':22},'proficient':{'coins':212,'spirit':34}})
    dynamic['income_profiles']=incomes

    tickets=ShiftTicketLedger()
    for night in range(1,8):
        tickets.complete_shift('campaign',1,night,handover_verified=True,grade='C')
        tickets.complete_shift('campaign',1,night,handover_verified=True,grade='A')
    check('lottery.seven_C_shifts_seven_tickets_no_replay',tickets.tickets==7)
    tickets.pity_common=4;tickets.pity_nonrare=9
    tickets.week_clear()
    check('lottery.week_clear_preserves_ticket_pity',tickets.tickets==7 and tickets.pity_common==4 and tickets.pity_nonrare==9)
    check('lottery.practice_no_ticket',tickets.complete_shift('campaign',2,1,handover_verified=True,practice=True)==0)
    check('lottery.failure_no_ticket',tickets.complete_shift('campaign',2,1,handover_verified=False)==0)
    check('lottery.next_week_unique',tickets.complete_shift('campaign',2,1,handover_verified=True)==1 and tickets.tickets==8)
    retained=lottery['retained_probability_and_pity']
    check('lottery.pity_unchanged',all(retained[k]==old_lottery[k] for k in retained))
    check('lottery.probability_sum',sum(num(v) for v in retained['base_tier_probabilities'].values())==1)
    check('lottery.closed_during_business',lottery['machine']['active_business_enabled'] is False)
    check('lottery.disabled_items_stay_disabled',set(lottery['reward_direction']['forbidden_pool_ids'])=={'I22','I23','Q03','Q11'})
    check('lottery.no_essential_gate',lottery['essential_mechanism_requires_draw'] is False)

    # Numerical comparisons use actual TD05 branch inputs. These are legal-hit
    # damage budgets, not claims of complete AI/pathing time-to-kill.
    snapshots=[]
    for mid in ('F02','F03','F12','F13','F46','F54','S05','S08','S15','S27','S28','S43'):
        m=by_id[mid]
        if m['stats']['hp']==0:continue
        before=m['stats'];after=m['post_rule']
        n=tower_nodes['T01.A1']['parameters']
        shot=td05.actual_damage(n['damage'],n['channel'],before['armor'],before['ward'],n.get('armor_penetration_pp',0))
        aftershot=td05.actual_damage(n['damage'],n['channel'],after['armor'],after['ward'],n.get('armor_penetration_pp',0))
        poison24=td05.offense(tower_nodes['T02.A1'],24,armor=before['armor'],ward=before['ward'])
        snapshots.append({'id':mid,'name':m['name'],'category':m['resolution']['type'],
          'hp':before['hp'],'armor':before['armor'],'ward':before['ward'],
          'sniper_actual_per_shot_before':shot,'sniper_actual_per_shot_after':None if m['resolution']['type']=='rule_leave' else aftershot,
          'sniper_hits_to_full_hp_equivalent':math.ceil(num(before['hp'])/shot),
          'poison24_legal_stationary_infinite_hp_budget':poison24,
          'limits':'门槛/离场不把此值当击杀时间；不包含射界、转场、身高、前摇和真实走位。'})
        check(f'{mid}.sniper_not_worse_after_rule',aftershot>=shot)
    dynamic['actual_branch_snapshots']=snapshots
    dynamic['eight_behavior_regression']={
      'sniper':td05.offense(tower_nodes['T01.A1'],24),
      'permanent_poison':{str(t):td05.offense(tower_nodes['T02.A1'],t) for t in (8,24,60)},
      'wide_burn':td05.offense(tower_nodes['T07.A1'],24,target_count=6,partner_dps_per_pool=10),
      'small_continuous':{str(t):td05.offense(tower_nodes['T07.B1'],t) for t in (.75,2.25,6)},
      'mass_curse':td05.curse_expected(tower_nodes['T08.A1'],24,pools=5,incoming_hit=12,enemy_interval=3),
      'electrical_resonance':'MD01固定合法图与floor/压制见上方；完整FIFO、实际电器与提前减员见TD05报告。',
      'continuous_zones':td05.raw_primary_profile(tower_nodes['T10.A1']),
      'real_phase':td05.raw_primary_profile(tower_nodes['T10.A2'])}
    check('tower.exact70_nodes40_leaves',len(tower_nodes)==70 and len(l3_ids)==40)
    check('tower.T10_A2_only_three_active_cells',dynamic['eight_behavior_regression']['real_phase']['phase_full_corridor_damage']==18)
    for path in ('scripts/md01_reference.py','scripts/check_md01_design.py'):
        INPUTS[path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    report=clean({'version':'MD01','runtime_integrated':False,
       'passed':sum(c['passed'] for c in CHECKS),'failed':sum(not c['passed'] for c in CHECKS),
       'coverage':{'total':len(rows),'origin_counts':dict(Counter(m['origin'] for m in rows)),
          'resolution_counts':dict(categories),'default_design_candidates':sum(m['default_enabled'] for m in rows),
          'noncombat_hp0': [m['id'] for m in rows if m['stats']['hp']==0],
          'actual_phase_ids':all_phases,'independent_scp_articles':len(sources)},
       'hp_summary':{'min_positive':min(m['stats']['hp'] for m in rows if m['stats']['hp']>0),
                     'max':max(m['stats']['hp'] for m in rows),'median_positive':statistics.median(m['stats']['hp'] for m in rows if m['stats']['hp']>0)},
       'input_sha256':INPUTS,'scenarios':dynamic,'checks':CHECKS,
       'limitations':['实际规则完成回执由fixture注入，未实现105个世界适配器。',
                      '未做SCP地图几何/完整AI/手机交互与真实随机周试玩。',
                      'damage预算使用明确合法命中或静止目标，不能当实际击杀用时。',
                      '电门槛fixture是固定合法图同D瞬时反应，只验证生命边界；全时序仍由TD05参考负责。',
                      '抽奖只检查方向与发券去重，不实现随机采样与完整奖池。']})
    target=ROOT/'docs/md01_validation_report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'coverage':report['coverage']},ensure_ascii=False))
    for c in CHECKS:
        if not c['passed']:print('FAIL',c['id'],c['detail'])
    return 1 if report['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
