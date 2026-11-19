#!/usr/bin/env python3
"""Bounded cross-source SA01 audit, not a full-game simulation.

Checks current consumers, source pointers, authority gates and report freshness.
The independent MA/TD/lifecycle/legacy/store suites exercise the actual finite
counterexamples; their pass counts are not summed into a playtest claim.
"""
from pathlib import Path
import collections
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
BASE = '961ccdbcdc5e8fb81b6cae534ab0317e64de4da5'
PROTECTED_BLOBS = {
    'content/monster_folklore_md01.json': 'd3bbec91e4be2f2a7bc68e3079363c30ef5a6c76',
    'content/monster_scp_a_md01.json': 'fe3a69b4031345edc2f84d6b5fc7055e7e107145',
    'content/monster_scp_b_md01.json': '20cf76da654982ae8e95a337328896db44959a41',
    'content/equipment_eq01.json': '31cfd8892b300c3b43c1f8b38a21d1d06ca2b4cf',
    'content/consumables_eq01.json': 'f388739832983c4ed0c7203ded63315f81ae4d8d',
}
INPUTS = set()
CHECKS = []


def read(path):
    INPUTS.add(path)
    return json.loads((ROOT / path).read_text())


def check(name, condition, evidence=None):
    CHECKS.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def sha256(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def blob_sha(path):
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def resolves(ref):
    path, _, fragment = ref.partition('#')
    try:
        current = read(path)
        if fragment:
            if not fragment.startswith('/'):
                return False
            for part in fragment[1:].split('/'):
                part = part.replace('~1', '/').replace('~0', '~')
                current = current[int(part)] if isinstance(current, list) else current[part]
        return current is not None
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def current_report(path, hash_fields, failure_fields):
    report = read(path)
    errors = []
    for field in hash_fields:
        hashes = report.get(field, {})
        if not hashes:
            errors.append('missing ' + field)
        for dependency, expected in hashes.items():
            dependency = 'scripts/' + dependency if field == 'script_sha256' else dependency
            INPUTS.add(dependency)
            if not (ROOT / dependency).is_file() or sha256(dependency) != expected:
                errors.append(dependency)
    for field in failure_fields:
        if report.get(field) != 0:
            errors.append(field)
    check(path + ' current inputs and no recorded failures', not errors, errors)
    return report


def run():
    authority = read('content/system_authority_sa01.json')
    facilities = read('content/facility_roles_sa01.json')
    legacy = read('content/legacy_deployment_bridge_sa01.json')
    lifecycle = read('content/run_lifecycle_sa01.json')
    towers = read('content/tower_defense_td05.json')
    traps = read('content/traps_facilities_td05.json')
    contract = read('content/combat_contracts_td05.json')
    store = read('content/store_systems_v05.json')
    maps = read('content/maps.json')
    check('all four SA01 design contracts explicitly unintegrated', all(
        d['runtime_integrated'] is False and d['baseline_commit'] == BASE
        for d in (authority, facilities, legacy, lifecycle)))
    for domain, paths in authority['authority_by_domain'].items():
        check('authority source exists ' + domain, all((ROOT / p).is_file() for p in paths), paths)
        INPUTS.update(paths)
    for path, expected in PROTECTED_BLOBS.items():
        INPUTS.add(path)
        check('protected original catalog ' + path, blob_sha(path) == expected)
    monster_cards = [m for p in list(PROTECTED_BLOBS)[:3] for m in read(p)['monsters']]
    check('105 unique original monster definitions', len(monster_cards) == 105 and len({m['id'] for m in monster_cards}) == 105)
    check('three outcomes retained', collections.Counter(m['resolution']['type'] for m in monster_cards)
          == {'kill_unlocked': 22, 'rule_leave': 45, 'rule_weaken': 38})

    check('10 tower families with two L2 and four L3 each', len(towers['families']) == 10 and all(
        len(f['l2']) == 2 and all(len(b['l3']) == 2 for b in f['l2']) for f in towers['families']))
    check('16 trap families with original five-node paths', len(traps['traps']) == 16 and all(
        len(f['l2']) == 2 and all(isinstance(b['l3'], dict) for b in f['l2']) for f in traps['traps']))
    minimums = [contract['effective_floor_domain']['minimum_circular_radius_tiles'],
                contract['persistent_field']['minimum_circular_radius_tiles'],
                towers['shared_geometry']['minimum_positive_circular_damage_radius_tiles'],
                traps['shared_contract']['placement']['circular_effect_min_radius_tiles'],
                legacy['geometry']['enemy_circle_override']['B01_radius_tiles']]
    check('hostile circle authorities all honor user minimum 1.5', all(v == 1.5 for v in minimums), minimums)

    active_ap = {a['id'] for a in traps['appliances'] if a['design_enabled']}
    check('only three registered powered-appliance definitions', active_ap ==
          {'AP_HOT_FOOD', 'AP_FREEZER', 'AP_COLD_CABINET'} == set(facilities['active_appliance_ids']))
    pos = next(a for a in traps['appliances'] if a['id'] == 'AP_POS')
    check('POS without actual placement and wiring stays disabled', not pos['design_enabled'] and pos['rect'] is None and pos['circuit_id'] is None)
    fx = {f['id'] for s in maps['scenes'] for f in s.get('fixtures', [])}
    roles = {a['role'] for s in maps['scenes'] for a in s.get('anchors', [])}
    anchors = {a['tower_anchor_id'] for a in traps['map_constraints']['side_hung_projection_examples']}
    catalog = facilities['roles']
    check('fourteen distinct facility roles', len(catalog) == 14 and len({r['id'] for r in catalog}) == 14)
    source_count = 0
    for role in catalog:
        rid, proposal, binding = role['id'], role['proposal'], role['physical_bindings']
        check(rid + ' proposal stays disabled with no invented upgrade price',
              proposal['status'] == 'proposed_pending_balance' and proposal['enabled'] is False
              and proposal['runtime_integrated'] is False and proposal['cost']['upgrade_coin'] is None
              and proposal['cost']['upgrade_spirit'] is None)
        pending = {'LOTTERY_COUNTER_01_pending_exact_position'} if rid == 'FR14' else set()
        check(rid + ' real fixture anchor and AP references', set(binding['fixture_ids']) <= fx
              and set(binding['anchor_roles']) <= roles | pending
              and set(binding['tower_anchor_ids']) <= anchors
              and set(binding['active_appliance_ids']) <= active_ap)
        for ref in role['sources']:
            source_count += 1
            check(rid + ' source pointer ' + ref, resolves(ref))
        radius = proposal['geometry'].get('nominal_radius_tiles')
        if radius is not None:
            check(rid + ' candidate enemy circle minimum', radius >= 1.5)
        if rid in {'FR01', 'FR02', 'FR03', 'FR04'}:
            timing = proposal['business_timing_example']
            actual = timing['base_checkout_or_short_work_s'] * timing['work_multiplier'] + proposal['cost']['action_world_seconds']
            check(rid + ' work bonus has positive net time after activation',
                  proposal['cost']['action_world_seconds'] == 0 and proposal['cost']['emergency_power_units'] == 1
                  and 0.8 <= timing['work_multiplier'] < 1
                  and actual < timing['base_checkout_or_short_work_s']
                  and math.isclose(timing['net_saved_world_s'], timing['base_checkout_or_short_work_s'] - actual))
            check(rid + ' finite paid work opportunity', proposal['duration']['armed_window_world_seconds'] == 20
                  and proposal['duration']['local_rearm_cooldown_world_seconds'] == 30
                  and len(proposal['required_real_consumer_events']) > 0)
    check('facility sources use exact actual references', source_count == 52, source_count)
    check('facility catalog claims zero newly activated effects', facilities['review_summary']['new_enabled_effect_count'] == 0
          and facilities['review_summary']['new_upgrade_prices_defined'] is False)

    phases = authority['phase_permissions']
    enabled = {a['id'] for a in store['emergency_power']['actions'] if a['enabled_current'] is True}
    disabled = {a['id'] for a in store['emergency_power']['actions'] if a['enabled_current'] is False}
    check('emergency assist gate matches actual configuration', enabled == set(phases['emergency_power']['currently_enabled_actions'])
          and disabled == set(phases['emergency_power']['currently_disabled_actions']))
    check('zero reserve keeps all original free essentials', all(store['emergency_power'][key] is False for key in
          ('baseline_fridge_depends_on_reserve', 'baseline_manual_door_depends_on_reserve', 'baseline_task_materials_depend_on_reserve')))
    check('tower and trap asset management share pre-shift boundary',
          phases['tower_asset_management']['allowed_phase'] == phases['trap_asset_management']['allowed_phase'] == 'pre_shift'
          and towers['growth']['management_phase'] == 'pre_shift_only'
          and traps['shared_contract']['charge_and_repair']['allowed_phase'] == 'pre_shift_only')
    check('existing morning equipment and lottery windows retained', set(phases['equipment']['loadout_changes']) ==
          set(phases['lottery']['allowed_phase']) == {'settled', 'pre_shift'} and phases['lottery']['open_allowed'] is False)
    capacity = legacy['capacity']
    check('legacy three is a subset of total eight with actual shared floor budget',
          capacity['legacy_auxiliary_subcap'] == 3 and capacity['shared_with_R_traps_total_installed_objects'] == 8
          and capacity['R_and_legacy_floor_cells_total'] == 16 and capacity['R_barricade_cells_subcap'] == 6
          and capacity['Q08_two_points_count'] == 2 and capacity['slot_limits_use_intersection_not_separate_extra_allowance'])
    check('unknown legacy physical footprints stay runtime-disabled', all(
        e['runtime_enabled'] is False for e in legacy['entries'] if e['floor_footprint_cells'] is None))
    check('logical night distinguishes week and attempt', lifecycle['identity']['night_key_fields'] ==
          ['campaign_id', 'week_id', 'night_index'] and lifecycle['identity']['absolute_night_ordinal'] ==
          '7 * (week_ordinal - 1) + night_index')

    td = current_report('docs/td05_balance_report.json', ('input_sha256', 'script_sha256'), ('checks_failed',))
    geo = td['geometry']['examples']
    check('all twelve actual static projections meet bounded restored area', len(geo) == 12
          and {r['anchor'] for r in geo} == anchors and all(r['area_target_met'] and r['center_legal_and_connected']
          and r['nominal_radius_tiles'] == 1.5 and r['effective_radius_tiles'] <= 2.25
          and r['restored_target_fraction'] >= .98 and r['emitter_to_field_los_clear']
          and r['projection_within_minimum_4_5_cast_range'] for r in geo))
    indexed_geo = {r['tower_anchor_id']: r for r in traps['map_constraints']['side_hung_projection_examples']}
    check('published derived geometry matches recomputed report', all(
        indexed_geo[r['anchor']]['field_center'] == r['center']
        and math.isclose(indexed_geo[r['anchor']]['compensated_radius_tiles'], r['effective_radius_tiles'])
        and math.isclose(indexed_geo[r['anchor']]['estimated_compensated_body_center_area_tiles2'], r['effective_usable_body_center_area_tiles2']) for r in geo))
    ma = current_report('docs/ma01_validation_report.json', ('input_hashes',), ('structural_failed', 'finite_failed'))
    ma_finite = current_report('docs/ma01_reference_report.json', ('input_hashes',), ('failed',))
    life = current_report('docs/sa01_lifecycle_report.json', ('input_hashes',), ('failed',))
    bridge = current_report('docs/sa01_legacy_validation_report.json', ('input_hashes',), ('failed',))
    store_report = current_report('docs/sa01_store_guard_report.json', ('input_sha256',), ('failed', 'exit_code'))
    build = current_report('docs/playable_build_v09.json', ('source_sha256',), ())
    INPUTS.add(build['standalone_html'])
    check('existing standalone artifact matches current source build', build['status'] == 'PASS'
          and sha256(build['standalone_html']) == build['sha256']
          and (ROOT / build['standalone_html']).stat().st_size == build['bytes'])
    check('standalone build is not claimed to contain store guard', 'prototype/store_core_v05.mjs' not in build['source_sha256'])
    INPUTS.add('scripts/check_sa01_design.py')
    return {
        'version': 'SA01', 'baseline_commit': BASE, 'runtime_integrated': False,
        'all_gameplay_proven': False,
        'scope': 'Cross-source roles, exact references, authority gates, user radius policy, current finite reports and unchanged original catalogs; not AI, live pathfinding or full-week balance.',
        'passed': sum(c['passed'] for c in CHECKS), 'failed': sum(not c['passed'] for c in CHECKS),
        'upstream_results': {'TD05_finite_and_structure': td['checks_passed'], 'MA01_structure': ma['structural_passed'],
                             'MA01_finite': ma_finite['passed'], 'SA01_lifecycle': life['passed'],
                             'SA01_legacy_bridge': bridge['passed'], 'existing_store_scenarios': store_report['passed']},
        'not_covered': authority['validation_boundary']['not_proven'],
        'checks': CHECKS, 'input_hashes': {p: sha256(p) for p in sorted(INPUTS)},
    }


if __name__ == '__main__':
    result = run()
    (ROOT / 'docs/sa01_validation_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('passed', 'failed', 'upstream_results', 'all_gameplay_proven')}, ensure_ascii=False))
    failures = [c for c in CHECKS if not c['passed']]
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result['failed']))
