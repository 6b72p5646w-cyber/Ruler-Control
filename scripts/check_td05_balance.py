#!/usr/bin/env python3
"""Reproduce TD05 design checks and bounded reference measurements.

This is deliberately not a full playable simulation. Graph/LOS/hit inputs,
finite-health calibration bodies, nominal no-death integrals and actual static
map checks are labelled separately in the output.
"""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import math
import sys

from td05_reference import (q, clean, nodes, segment_spans, merge_sample_spans,
    normal_toll, phase_toll, actual_damage, repeat_events, offense, curse_expected,
    ElectricModel, complete_edges, run_electric, electric_reservation_fixture,
    susceptible_fixture, heat_susceptible_fixture, finite_direct_fixture,
    raw_primary_profile, StatusMeter)
from td05_economy_reference import (week_replay, command_counterexamples,
    depleted_sale_comparisons, repair_sale_comparisons, stock_pressure_replays,
    unused_stock_week_boundary_fixture)
from td05_geometry_reference import (geometry_examples, geometry_counterexamples,
    electric_store_fixture)
from td05_chase_reference import run_reference as chase_reference

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []


def locate(name):
    path = ROOT / name
    if path.exists():
        return path
    # Staging overlays use the already fetched source beside them. A normal
    # checkout always takes ROOT first and needs no network or sibling copy.
    for sibling in ('ruler-control-source', 'ruler-control-td04', 'ruler-control-td03', 'ruler-control-td02'):
        path = ROOT.parent / sibling / name
        if path.exists():
            return path
    raise FileNotFoundError(name)


def read(name):
    return json.loads(locate(name).read_text())


def check(name, condition, detail=None):
    CHECKS.append({'name': name, 'passed': bool(condition), 'detail': clean(detail)})


def brief(result):
    return {k: v for k, v in result.items() if k not in (
        'wave_trace', 'bounce_trace', 'reservation_trace', 'primary_trace', 'death_trace')}


def induction_inputs(pools, horizon=24, powered_by='AP1'):
    return [{'time': t, 'candidate_pools': pools, 'target_cap': 6,
             'damage': 2, 'charge': 1, 'requires_powered_appliance': powered_by,
             'source_id': 'T09.B1', 'phase_id': str(t)}
            for t in repeat_events(1.8, [0], horizon)]


def single_source_inputs(node, pool, horizon=24):
    p = node['parameters']
    charge = next(e['amount'] for e in node['effects'] if e['status'] == 'electric')
    cycle, damage = p.get('single_target_interval_s', p['interval_s']), p.get('single_target_damage', p['damage'])
    return [{'time': t, 'pool': pool, 'damage': damage, 'charge': charge,
             'source_id': node['id'], 'phase_id': str(t)} for t in repeat_events(cycle, [0], horizon)]


def run():
    names = ['tower_defense', 'combat_contracts', 'traps_facilities', 'economy_week',
             'monster_matchups', 'chase_profiles', 'balance_scenarios']
    data = {name: read('content/' + name + '_td05.json') for name in names}
    towers, contract, traps, economy, matchups, chase, scenarios = [data[n] for n in names]
    maps = read('content/maps.json')
    for name, item in data.items():
        check('design_scope_' + name, item['version'] == 'TD05' and item['runtime_integrated'] is False)
    all_nodes = list(nodes(towers))
    by_id = {n['id']: n for n in all_nodes}
    check('tower_topology_10_20_40', len(towers['families']) == 10 and len(all_nodes) == len(by_id) == 70)
    for family in towers['families']:
        check('two_by_two_' + family['id'], len(family['l2']) == 2 and all(len(b['l3']) == 2 for b in family['l2']))
    for node in all_nodes:
        tier = node['tier']
        check('absolute_and_reviewed_' + node['id'], node['parameters']['parameters_are_absolute'] and bool(node['balance_profile']))
        check('tree_parent_' + node['id'], tier == 1 or node['parent'] in by_id and by_id[node['parent']]['tier'] == tier - 1)
        check('build_cost_' + node['id'], (tier == 1 and 35 <= node['cost']['coin'] <= 45) or
              (tier == 2 and node['cost'] == {'coin': 28, 'spirit': 4}) or
              (tier == 3 and node['cost'] == {'coin': 52, 'spirit': 12}))
        if node['id'].startswith('T10'):
            p = node['parameters']
            check('same_unit_toll_' + node['id'], p['cell_damage'] == p['phase_cell_damage'] and p['phase_damage_multiplier'] == 1)
        if node['id'].startswith('T05'):
            p = node['parameters']
            check('short_paper_' + node['id'], p['guard_max_hold_s'] == 1 and p['guard_target_reintercept_icd_s'] == 6 and p['respawn_s'] <= 4)
        for effect in node['effects']:
            if effect['status'] == 'electric':
                check('full_electric_' + node['id'], effect['overload_base_damage'] == 6 and effect['feedback_wave_charge_cap'] is None and effect['feedback_native_potency_multiplier'] == 1)
    trap_nodes = []
    for trap in traps['traps']:
        trap_nodes += [trap]
        for branch in trap['l2']:
            trap_nodes += [branch, branch['l3']]
    check('trap_topology_16_80', len(traps['traps']) == 16 and len(trap_nodes) == len({n['id'] for n in trap_nodes}) == 80)
    for node in trap_nodes:
        check('trap_resolved_and_reviewed_' + node['id'], bool(node['effective_parameters']) and bool(node['balance_profile']))
    s = contract['statuses']
    check('susceptible_thresholds', s['susceptible']['thresholds'] == {'heat': {'base': 8, 'susceptible': 7}, 'frost': {'base': 4, 'susceptible': 3}, 'curse': {'base': 4, 'susceptible': 3}, 'electric': {'base': 5, 'susceptible': 4}})
    check('only_three_susceptible_sources', {v['id'] for v in s['susceptible']['sources']} == {'T04.A2', 'T06.B2', 'R08.B3'})
    check('trap_susceptible_reference_exists', traps['shared_contract']['susceptibility']['contract_ref'].endswith('#/statuses/susceptible'))
    check('electric_no_feedback_budget', s['electric']['feedback']['per_wave_total_charge_cap'] is None and s['electric']['feedback']['feedback_source_overload_base_multiplier'] == 1)
    check('no_false_charge_dissipation_proof', 'chain_termination_proof' not in contract['electric_network'])

    # Eight behavioural baselines; no-death totals remain explicitly separate
    # from the new finite-health electric and sniper kill/overkill fixtures.
    nominal = {}
    for nid in ['T01.A1', 'T02.A1', 'T02.A2', 'T07.A1', 'T07.B1', 'T03.B1']:
        nominal[nid] = {}
        for horizon in [8, 24, 60]:
            nominal[nid][str(horizon)] = offense(by_id[nid], horizon)
            check('nonnegative_offense_' + nid + '_' + str(horizon), nominal[nid][str(horizon)]['damage'] >= 0)
    check('sniper_short_poison_long', nominal['T01.A1']['8']['damage'] > nominal['T02.A1']['8']['damage'] and nominal['T02.A1']['60']['damage'] > nominal['T01.A1']['60']['damage'])
    defense = {nid: {str(a): offense(by_id[nid], 24, armor=a, ward=a)['damage'] for a in [0, .35, .75]}
               for nid in ['T01.A1', 'T02.A1', 'T07.B1']}
    broad = offense(by_id['T07.A1'], 24, target_count=6, partner_dps_per_pool=10)
    broad_one = offense(by_id['T07.A1'], 24, target_count=1)
    broad_susceptible = offense(by_id['T07.A1'], 24, target_count=6, partner_dps_per_pool=10, susceptible=True)
    check('burn_team_utility_explicit', broad['partner_extra'] > 0 and broad['damage'] == broad_one['damage'] * 6)
    residence = {str(t): offense(by_id['T07.B1'], 8, windows=[(0, t)]) for t in [.75, 2.25, 6]}
    check('small_area_requires_residence', residence['0.75']['damage'] < residence['2.25']['damage'] < residence['6']['damage'])
    curse = curse_expected(by_id['T08.A1'])
    check('curse_has_real_defensive_value', 0 < curse['expected_prevented'] < curse['incoming_without_curse'])
    sniper_finite = {'single_180': finite_direct_fixture(48, 3.2, [180]),
                     'two_180': finite_direct_fixture(48, 3.2, [180, 180]),
                     'eight_45': finite_direct_fixture(48, 3.2, [45] * 8)}
    check('sniper_overkill_is_not_effective_damage', sniper_finite['eight_45']['actual_damage'] == 360 and sniper_finite['eight_45']['overkill'] == 24)
    check('sniper_single_180_time', sniper_finite['single_180']['kills'][0]['at_s'] == 9.6)
    all_profiles = {n['id']: raw_primary_profile(n) for n in all_nodes}
    check('paper_metric_not_continuous_melee', all_profiles['T05.A1']['one_pool_ideal_contact_windows'] == 4 and all_profiles['T05.A1']['raw_direct_damage_nominal_24s'] == 48)
    check('electric_solo_modes_use_actual_parameters', all_profiles['T09.A2']['raw_direct_damage_nominal_24s'] == 100)
    check('alternating_zones_only_three_active_at_arrival', all_profiles['T10.A2']['phase_full_corridor_damage'] == 18)

    fields = {(i, 0): 3 for i in range(4)}
    ledger, receipts = {}, set()
    forward = normal_toll('P', segment_spans((.2, .5), (3.8, .5), 0, 1), ledger, fields)
    backwards = normal_toll('P', segment_spans((3.8, .5), (.2, .5), 1, 1.5), ledger, fields)
    first = phase_toll('P', 'real-1', (.2, .5), (3.8, .5), 1.5, ledger, receipts, fields)
    after_first = dict(ledger)
    duplicate = phase_toll('P', 'real-1', (.2, .5), (3.8, .5), 1.6, ledger, receipts, fields)
    check('duplicate_does_not_retime', ledger == after_first)
    second = phase_toll('P', 'real-2', (3.8, .5), (.2, .5), 1.75, ledger, receipts, fields)
    totals = [sum(x[2] for x in part) for part in [forward, backwards, first, duplicate, second]]
    check('movement_frequency_without_bonus', totals == [12, 0, 12, 0, 12], totals)
    check('phase_refresh_deadlines', all(v == q(3.75) for v in ledger.values()))
    empty_receipts, empty_ledger = set(), {}
    check('zero_displacement_no_receipt', phase_toll('P', 'zero', (.2,.5), (.2,.5), 0, empty_ledger, empty_receipts, fields) == [] and not empty_receipts)
    check('canceled_phase_no_receipt', phase_toll('P', 'cancel', (.2,.5), (3.8,.5), 0, empty_ledger, empty_receipts, fields, committed=False) == [] and not empty_receipts)
    sparse = {cell: value for cell, value in fields.items() if cell != (1,0)}
    blocked = phase_toll('P', 'gap', (.2,.5), (3.8,.5), 0, {}, set(), sparse)
    check('solid_or_unprojected_cell_not_counted', sum(x[2] for x in blocked) == 9)
    for fps in [30,60,120]:
        samples = [(q(i)/fps, (q(.2)+q(3.6)*q(i)/fps, q(.5))) for i in range(fps+1)]
        result = normal_toll('P', merge_sample_spans(samples), {}, fields)
        check('trajectory_sampling_' + str(fps), sum(x[2] for x in result) == 12)
    phase = clean({'cell_damage': 3, 'four_cell_results': totals, 'last_deadlines': ledger,
                   'gap_total': sum(x[2] for x in blocked), 'no_phase_multiplier': True})

    electric = {'normal_and_crowd': {}, 'single_point_branch': {}, 'counterexamples': {}}
    for count in [1,2,3,6,8]:
        pools = ['M' + str(i) for i in range(count)]
        apps = ['AP1', 'AP2']
        result = run_electric(pools, apps, complete_edges(pools+apps), induction_inputs(pools),
                              health={p: 180 for p in pools}, ordinary_bounce=True)
        electric['normal_and_crowd'][str(count)] = result
        check('finite_electric_charge_ledger_' + str(count), result['charge_ledger_balances'])
        check('finite_electric_hp_bound_' + str(count), result['total_damage'] <= count * 180)
        check('finite_electric_no_dead_pending_' + str(count), set(result['ready_pool_ids']) <= set(result['living_pools']) and
              all(not any(w['at_s'] > at and p in w['local_counts'] for w in result['wave_trace']) for p, at in result['kill_times'].items()))
        check('electric_feedback_per_actual_hit_' + str(count), all(w['feedback_generated'] == sum(d > 0 for d in w['actual_damage'].values()) for w in result['wave_trace']))
    check('two_enemy_resonance_has_value', electric['normal_and_crowd']['2']['deaths'] == 2 and max(electric['normal_and_crowd']['2']['kill_times'].values()) < sniper_finite['two_180']['kills'][-1]['at_s'])
    mixed_health = {}
    for fragile in ['M0','M1']:
        hp = {p:45 if p == fragile else 180 for p in ['M0','M1']}
        result = run_electric(['M0','M1'], ['AP1','AP2'], complete_edges(['M0','M1','AP1','AP2']),
                              induction_inputs(['M0','M1']), health=hp, ordinary_bounce=True)
        mixed_health[fragile+'_fragile'] = result
        check('real_early_minion_death_shrinks_network_' + fragile,
              result['deaths'] == 1 and result['total_damage'] < 225 and result['charge_ledger_balances'] and
              any(w['local_counts'].get('M1' if fragile == 'M0' else 'M0') == [1,2] for w in result['wave_trace']))
    electric['mixed_finite_health'] = mixed_health
    for nid in ['T09', 'T09.A', 'T09.A1', 'T09.A2']:
        for appliance_count in [0,1,2]:
            apps = ['AP' + str(i) for i in range(appliance_count)]
            result = run_electric(['M'], apps, complete_edges(['M']+apps), single_source_inputs(by_id[nid], 'M'), health={'M': 180})
            electric['single_point_branch'][nid+'_'+str(appliance_count)+'AP'] = result
            check('single_branch_finite_' + nid + str(appliance_count), result['charge_ledger_balances'] and result['total_damage'] <= 180)
    check('single_point_upgrade_monotone', electric['single_point_branch']['T09.A_0AP']['total_damage'] >= electric['single_point_branch']['T09_0AP']['total_damage'] and electric['single_point_branch']['T09.A1_0AP']['total_damage'] >= electric['single_point_branch']['T09.A_0AP']['total_damage'])
    many = ['P'+str(i) for i in range(8)]
    uncapped = run_electric(many, [], complete_edges(many), initial={p: 5 if i == 0 else 1 for i,p in enumerate(many)}, horizon=.25, health={p: 10000 for p in many})
    check('eight_hits_return_eight_not_two', uncapped['wave_trace'][0]['feedback_generated'] == 8 and uncapped['remaining_charge'] == 15)
    check('crowd_charge_growth_is_allowed', uncapped['wave_trace'][0]['charge_after'] > uncapped['wave_trace'][0]['charge_before'])
    early = run_electric(['A','B','C'], ['AP1','AP2'], complete_edges(['A','B','C','AP1','AP2']), initial={'A':5,'B':5,'C':5}, horizon=3, health={'A':25,'B':180,'C':180})
    check('early_death_reduces_coefficient', early['wave_trace'][0]['local_counts']['B'] == [3,2] and early['wave_trace'][1]['local_counts']['B'] == [2,2])
    check('dead_seed_queue_removed', all(w['seed'] != 'A' for w in early['wave_trace'][1:]))
    bridge = run_electric(['A','B','C'], [], [('A','B'),('B','C')], initial={'A':5,'B':5,'C':5}, horizon=1, health={'A':180,'B':10,'C':180})
    check('dead_bridge_splits_next_graph', bridge['wave_trace'][0]['dead_after_wave'] == ['B'] and all(len(w['local_counts']) == 1 for w in bridge['wave_trace'][1:]))
    all_dead = run_electric(['A','B','C','D'], [], complete_edges(['A','B','C','D']), initial={p:5 for p in 'ABCD'}, horizon=2, health={p:10 for p in 'ABCD'})
    check('simultaneous_deaths_end_queued_cascade', all_dead['waves'] == 1 and all_dead['ready_requests'] == 0 and all_dead['remaining_charge'] == 0)
    off = run_electric(['A','B'], ['AP1','AP2'], complete_edges(['A','B','AP1','AP2']), induction_inputs(['A','B']), health={'A':180,'B':180}, powered=False, ordinary_bounce=True)
    check('unpowered_induction_no_invented_hits', off['total_damage'] == 0 and off['external_charge'] == 0)
    remote = run_electric(['A','B'], ['AP1','AP2'], [('A','AP1'),('AP1','AP2'),('AP2','B')], initial={'A':5,'B':1}, horizon=.25, health={'A':100,'B':100})
    check('full_component_reaches_remote_pool', set(remote['wave_trace'][0]['actual_damage']) == {'A','B'} and remote['wave_trace'][0]['local_counts']['B'] == [1,1])
    zero = run_electric(['A'], [], [], inputs=[(0,'A',0,1)], horizon=1, health={'A':100})
    check('zero_damage_no_free_charge', zero['external_charge'] == 0)
    source = ElectricModel(['A'], [], [], health={'A':100})
    source.add('A',3,0,source_d=6); source.add('A',2,0,source_d=4)
    check('mixed_potency_weighted_mean', source.consume('A') == q(5.2))
    receipt = ElectricModel(['A'], [], [], health={'A':100})
    receipt.primary('A',0,8,2,receipt=('tower','phase','A'))
    receipt.primary('A',0,8,2,receipt=('tower','phase','A'))
    check('electric_primary_receipt_dedupe', receipt.damage['A'] == 8 and receipt.load('A') == 2)
    generic = ElectricModel(['A'], [], [], health={'A':100})
    generic.primary('A',0,2,0)
    check('every_positive_electric_hit_still_grants_one', generic.load('A') == 1)
    reserve = electric_reservation_fixture()
    check('expired_reserved_lot_requeues', reserve['old_request_id'] != reserve['new_request_id'] and reserve['new_ready_at'] == 1 and reserve['A_load_after_reserved_expiry'] == 7 and reserve['first_seed_after_expiry'] == 'B')
    check('earliest_expiry_partial_lot', reserve['earliest_expiry_reserved_lots'] == [['inherited-earlier-deadline',4],['newer-deadline',1]] and reserve['post_consumption_surplus'] == 2)
    es = susceptible_fixture()
    check('electric_susceptible_gain_expiry', es['normal_four_not_ready'] and es['susceptible_four_ready_threshold'] == 4 and es['expired_four_cannot_emit'])
    check('susceptible_does_not_reduce_D', es['four_with_susceptible']['wave_trace'][0]['D'] == 6 and es['four_with_susceptible']['wave_trace'][0]['consumed_threshold'] == 4)
    hs = heat_susceptible_fixture()
    check('existing_seven_heat_ignite', hs['burns_before_susceptible'] == 0 and hs['burns_on_gain'] == 1 and hs['marks_added_by_susceptible'] == 0 and hs['consumed_on_gain'] == 7)
    check('full_burn_strength_from_seven', hs['result_DPS'] == 2 and hs['result_vulnerability'] == .25)
    check('susceptible_does_not_fake_four_curses', hs['curse_events'][0]['payload']['direct_attack_reduction'] == .12 and hs['curse_marks_after_fourth_real_hit'] == 4 and len(hs['curse_events']) == 1)
    check('freeze_cooldown_still_applies', len(hs['frost_events']) == 1 and hs['frost_reserve_during_cooldown'] == 2)
    check('poison_has_no_susceptible_threshold', hs['poison_threshold'] is None)
    electric['counterexamples'] = {'uncapped_eight':uncapped,'early_death':early,'dead_bridge':bridge,'all_dead':all_dead,'unpowered':off,'remote_relay':remote,'zero_damage':zero,'reservation':reserve,'susceptible':es}

    geometry = geometry_examples(traps, maps)
    geo_bad = geometry_counterexamples()
    for row in geometry['examples']:
        check('compensated_actual_anchor_' + row['anchor'], row['area_target_met'] and row['center_legal_and_connected'] and 1 <= row['effective_radius_tiles'] <= 1.5 and row['restored_target_fraction'] >= .98)
    check('free_floor_stays_nominal_radius', geo_bad['reference_body_does_not_expand_empty_circle'])
    check('bounded_compensation_rejects_narrow_dead_area', not geo_bad['narrow_insufficient_area_projection']['area_target_met'])
    check('compensation_never_sees_through_walls', geo_bad['cannot_compensate_through_wall'])
    actual_store = electric_store_fixture(traps, maps)
    check('real_store_two_pool_bodies_fit', all(actual_store['unit_body_clear_and_reachable'].values()))
    check('real_store_local_N2_E2', all(x['N_including_self'] == 2 and x['E_local_powered_devices'] == 2 and x['D6_raw_damage_per_overload'] == 24 for x in actual_store['local_formula_counts']))
    geometry['counterexamples'] = geo_bad
    geometry['electric_store'] = actual_store

    gates = command_counterexamples(economy, traps)
    for row in gates['open_rejections']:
        check('open_blocks_' + row['action'], row['denied'] and row['entire_state_unchanged'])
    for key in ['purchased_spare_open_deploy_denied','stale_week_rejected_without_mutation',
                'night_transition_preserved_empty_placed_item','next_preparation_can_load_prepaid_stock',
                'duplicate_load_rejected_without_mutation','paid_spare_remained_backpack',
                'fifth_trigger_rejected_without_mutation']:
        check('inventory_' + key, gates[key])
    weeks = [week_replay(economy,towers,traps,scenario) for scenario in economy['replay_assumptions']['scenarios']]
    for week in weeks:
        key = week['scenario']['id']
        check('weekly_plan_feasible_' + key, week['actual_stock_service_plan_feasible'])
        check('weekly_reset_real_assets_' + key, week['next_week_defense_instances'] == ['free_T02_L1'] and week['next_week_refill_stock'] == {} and not week['old_week_command_accepted_after_reset'])
        for row in week['before_night_rows']:
            check('nonnegative_cash_' + key + str(row['night']), row['before_night_coin'] >= 0 and row['before_night_spirit'] >= 0 and row['locked_phase'] == 'open')
    depleted = depleted_sale_comparisons(economy, traps)
    repair = repair_sale_comparisons(economy, traps)
    check('depleted_sale_does_not_beat_paid_refill', bool(depleted) and all(x['rebuild_not_cheaper'] for x in depleted), {'cases':len(depleted)})
    check('repair_then_sale_not_profitable', bool(repair) and all(x['repair_then_sale_not_profitable'] for x in repair), {'cases':len(repair)})
    pressure = stock_pressure_replays(economy,towers,traps)
    check('four_uses_changes_upgrade_tradeoff', pressure[0]['paid_stock_plan_feasible'] and pressure[1]['paid_stock_plan_feasible'] and pressure[1]['final_l3_traps'] < pressure[0]['final_l3_traps'])
    check('six_uses_cannot_replenish_midnight', not pressure[2]['paid_stock_plan_feasible'] and pressure[2]['unserved_trigger_count'] > 0)
    unused = unused_stock_week_boundary_fixture(economy,towers,traps)
    check('unused_stock_kept_all_seven_nights', len(unused['daily_carry']) == 7 and all(x['item_location'] == 'backpack' and x['paid_item_charges'] == 4 and x['loose_paid_refill_quantity'] == 4 for x in unused['daily_carry']))
    check('week_reset_clears_unused_paid_materials', unused['cleared_positive_refill_quantity'] == 4 and unused['cleared_unopened_spare'] and unused['next_week_only_free_job_tower'] and unused['next_week_loose_refill_quantity'] == 0)
    check('week_reset_idempotent', unused['repeated_reset_and_old_purchase_rejected_without_mutation'])
    # Detailed comparison keys are exported by the independent economy model.
    economy_results = {'weeks':weeks,'inventory_gate_cases':gates,'depleted_sale_comparisons':depleted,'repair_sale_comparisons':repair,'stock_pressure_replays':pressure,'unused_stock_week_boundary':unused}
    chase_results = chase_reference(chase, matchups, maps)
    CHECKS.extend(chase_results.pop('checks'))
    check('chase_reference_all_passed', chase_results['checks_failed'] == 0)

    inputs = {str(Path('content')/(n+'_td05.json')): hashlib.sha256(locate('content/'+n+'_td05.json').read_bytes()).hexdigest() for n in names}
    inputs['content/maps.json'] = hashlib.sha256(locate('content/maps.json').read_bytes()).hexdigest()
    scripts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'scripts').glob('*.py'))}
    report = clean({'version':'TD05','runtime_integrated':False,
        'scope':'finite reference checks and model calibration; no assertion of full AI, phone input, runtime persistence or seven-night playtest',
        'source_commit':'2de5054a12ee1655ad817dae73ce643d1db82047',
        'input_sha256':inputs,'script_sha256':scripts,
        'checks_passed':sum(c['passed'] for c in CHECKS),'checks_failed':sum(not c['passed'] for c in CHECKS),
        'nominal_no_death_offense':nominal,'defense_sensitivity':defense,
        'broad_burn':broad,'broad_burn_with_susceptible':broad_susceptible,
        'small_field_residence':residence,'group_curse':curse,'finite_sniper':sniper_finite,
        'all_70_tower_nominal_profiles':all_profiles,'phase_toll':phase,
        'electric_finite_health':electric,'susceptible_status_events':hs,
        'geometry':geometry,'economy':economy_results,'chase':chase_results,'checks':CHECKS})
    output = ROOT/'docs/td05_balance_report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':report['checks_passed'],'failed':report['checks_failed'],
                      'failed_checks':[c for c in CHECKS if not c['passed']],
                      'electric':{n:brief(v) for n,v in electric['normal_and_crowd'].items()},
                      'report':str(output)},ensure_ascii=False))
    return report


if __name__ == '__main__':
    result = run()
    sys.exit(1 if result['checks_failed'] else 0)
