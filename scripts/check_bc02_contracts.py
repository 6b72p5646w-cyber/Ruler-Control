#!/usr/bin/env python3
"""Cross-contract coverage and implementation-handoff gates, not a game client."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
checks = []


def read(name):
    return json.loads((ROOT / 'content' / (name + '_bc02.json')).read_text())


def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
    if not value:
        raise AssertionError(name)


def run():
    authority, facilities, routes, environment, prerequisites, player, ads, teaching, plan = [read(n) for n in (
        'system_authority', 'facilities', 'customer_routes', 'environment_conditions', 'encounter_prerequisites',
        'player_loop', 'ad_contracts', 'onboarding', 'implementation_plan')]
    for domain, ref in authority['authority_by_domain'].items():
        check('current authority source exists: ' + domain, (ROOT / ref.split('#')[0]).is_file())
    check('BC02 retains explicit BC01 inheritance', authority['previous_authority'] == 'content/system_authority_bc01.json')
    check('every current design honestly marks client integration false', all(d.get('runtime_integrated') is False for d in (
        authority, facilities, routes, environment, prerequisites, player, ads, teaching, plan)))
    roles = {r['id']: r for r in facilities['roles']}
    rewarded = {k for k, r in roles.items() if r['reward'] is not None}
    check('fourteen roles with exactly twelve genuine reward sources', len(roles) == 14 and len(rewarded) == 12 and set(roles) - rewarded == {'FR07', 'FR08'})
    check('24 independent bank slots match 12 sources times two', facilities['bank']['per_facility_max_tokens'] == 2 and facilities['bank']['whole_store_max_tokens'] == 2 * len(rewarded))
    for fid, role in roles.items():
        reward = role['reward']
        if reward is None:
            continue
        rewards = reward.get('variants', [reward])
        for r in rewards:
            if r['kind'] in ('temporary_trap_token', 'survival_credit_seconds', 'stamina_restore_fraction'):
                continue
            check('maintained effect lifetime is actual raid: ' + fid + ':' + r['kind'], r.get('lifetime') == 'actual_raid' and not r.get('duration_s'))
    check('FR06 uses dedicated public face', roles['FR06']['anchor'] == 'bc02_customer_verification')
    check('customer profiles cover twelve reward sources without inventing employee use',
          set().union(*[set(p['optional_services']) for p in routes['profiles']]) | {'FR01', 'FR10'} == rewarded)
    for p in routes['profiles']:
        check('per-order optional limit holds for ' + p['id'], len(p['optional_services']) <= 2 and len(set(p['optional_services'])) == len(p['optional_services']))
    all_ids = {f'F{i:02}' for i in range(1, 61)} | {f'S{i:02}' for i in range(1, 46)}
    records = {r['monster_id']: r for r in prerequisites['encounters']}
    check('all105 prerequisites without missing or duplicate monsters', len(prerequisites['encounters']) == len(records) == 105 and set(records) == all_ids)
    env_records = {r['monster_id']: r for r in environment['monster_consumers']}
    check('all105 environment consumers align with prerequisite roster', set(env_records) == set(records))
    conditions = {r['condition_id'] for r in environment['conditions']}
    check('23 explicit condition kinds, including optional mirror interface', len(conditions) == 23 and 'BC02_ENV_MIRROR_ENDPOINT_PAIR' in conditions)
    batch_ids = [x for b in prerequisites['implementation_batches'].values() for x in b['ids']]
    check('105 monsters have one and only one construction batch', len(batch_ids) == 105 and set(batch_ids) == all_ids and max(Counter(batch_ids).values()) == 1)
    binding_stages = {
        'live_source_before_commit': (True, True),
        'registered_condition_adapter': (True, False),
        'terminal_producer_output_only': (False, False),
        'misuse_producer_output_only': (False, False),
        'optional_rule_branch_adapter': (False, False),
    }
    for mid, record in records.items():
        check(mid + ' environment binding IDs resolve and each has a stage', set(record['environment_condition_ids']) <= conditions and all(
            binding_stages.get(b['requirement_type']) == (b['required_for_admission'], b['condition_must_be_true_at_admission'])
            for b in record['environment_bindings']))
        check(mid + ' no design record enables a missing runtime module', record['runtime_integrated'] is False and record['module_binding']['client_adapter_ready'] is False)
    f13_blood = next(b for b in records['F13']['environment_bindings'] if b['condition_id'] == 'BC02_ENV_CLEANUP_BLOOD')
    check('F13 does not need its future corpse to spawn', f13_blood['required_for_admission'] is False and f13_blood['condition_must_be_true_at_admission'] is False)
    s25_shadow = next(b for b in records['S25']['environment_bindings'] if b['condition_id'] == 'BC02_ENV_NO_SHADOW_ZONE')
    check('S25 can start before player builds shadowless solution', not s25_shadow['condition_must_be_true_at_admission'])
    f30_water = next(b for b in records['F30']['environment_bindings'] if b['condition_id'] == 'BC02_ENV_WET_CONNECTED')
    check('F30 misuse water is an actual future output, not a spawn prerequisite', f30_water['requirement_type'] == 'misuse_producer_output_only')
    f58_warmth = next(b for b in records['F58']['environment_bindings'] if b['condition_id'] == 'BC02_ENV_WARM_FIELD')
    check('F58 warmth is optional and cannot block its original free exit', f58_warmth['requirement_type'] == 'optional_rule_branch_adapter')
    for mid in ('F26', 'F32'):
        check(mid + ' actually requires live blood, not just a blood handler', any(
            b['condition_id'] == 'BC02_ENV_FRESH_BLOOD' and b['condition_must_be_true_at_admission']
            for b in records[mid]['environment_bindings']))
    check('F14 default opt-in protection remains', records['F14']['default_enabled_after_implementation'] is False)
    text = json.dumps(teaching, ensure_ascii=False)
    check('teaching no longer promises eight slots or timed twelve-second support', '最多8' not in text and '真实剩余秒' not in text and '12秒' not in text)
    placement = {p['id']: p for p in ads['placements']}
    check('all requested ad surfaces reserved', set(placement) == {'AD_PAUSE_SPONSOR', 'AD_RUN_DOUBLE_COIN', 'AD_EXTRA_DRAW'})
    check('pause ads are unrewarded and interstitial opt-in configured', placement['AD_PAUSE_SPONSOR']['reward'] is None and placement['AD_PAUSE_SPONSOR']['default_interstitial_enabled'] is False)
    check('night7 closed-week coins are not misleading ad rewards', placement['AD_RUN_DOUBLE_COIN']['eligible_nights'] == [1,2,3,4,5,6])
    check('optional ads do not multiply XP/spirit/base tickets', {'经验', '灵能', '基础奖券'} <= set(placement['AD_RUN_DOUBLE_COIN']['excluded']))
    check('extra draw is one ordinary ticket and 15 first-week ceiling', placement['AD_EXTRA_DRAW']['reward'] == {'standard_lottery_tickets': 1} and placement['AD_EXTRA_DRAW']['first_week_total_with_all_seven_optional_ads'] == 15)
    tasks = {t['id']: t for t in plan['tasks']}
    check('task IDs unique and implementation not falsely started', len(tasks) == len(plan['tasks']) and all(t['status'] == 'planned_not_implemented' for t in tasks.values()))
    resolved = {'D00'}
    while True:
        ready = {tid for tid, t in tasks.items() if set(t['depends_on']) <= resolved}
        if ready <= resolved:
            break
        resolved |= ready
    check('Codex task dependencies are complete and acyclic', resolved == set(tasks) | {'D00'})
    for tid, task in tasks.items():
        check('concrete deliverable and acceptance for ' + tid, bool(task['deliverables'] and task['acceptance'] and task['target_paths_to_create_or_modify']))
    for bid, batch in prerequisites['implementation_batches'].items():
        if bid == 'P0_existing_geometry':
            covered = plan['p0_content']['active_monsters'] + plan['p0_content']['passive_monsters']
        else:
            covered = tasks[bid]['deliverables'][0]['monster_ids']
        check('plan uses actual audited batch unchanged: ' + bid, set(covered) == set(batch['ids']) and len(covered) == len(batch['ids']))
    gear = json.loads((ROOT / 'content/equipment_eq01.json').read_text())['equipment']
    items = json.loads((ROOT / 'content/consumables_eq01.json').read_text())['items']
    catalog = {r['id']: (r['rarity'], 'equipment') for r in gear}
    catalog.update({r['id']: (r['rarity'], 'consumable') for r in items})
    initial_pool = plan['p0_content']['lottery_items']
    check('P0 six-item lottery has a real definition for every positive tier/class',
          len(initial_pool) == 6 and {catalog.get(i) for i in initial_pool} == {
            (tier, kind) for tier in ('common', 'uncommon', 'rare') for kind in ('equipment', 'consumable')})
    check('live ads not a prerequisite to finish playable P0', plan['p0_content']['live_ads_required_for_P0'] is False and 'C10' not in tasks['C09']['depends_on'])
    check('actual runtime implementation not fabricated by handoff', plan['implementation_strategy']['actual_client_files_created_in_this_design_commit'] is False)
    for doc in ['94_bc02_closure.md','95_bc02_facility_duration.md','96_bc02_environment_sources.md',
                '97_bc02_encounter_prerequisites.md','98_bc02_codex_delivery_plan.md','99_bc02_advertising.md',
                '100_bc02_codex_start.md','101_bc02_customer_routes.md']:
        check('deliverable entry exists: ' + doc, (ROOT / 'docs' / doc).is_file())
    dependencies = sorted((ROOT / 'content').glob('*bc02.json')) + [Path(__file__), ROOT / 'content/equipment_eq01.json', ROOT / 'content/consumables_eq01.json']
    report = {'version':'BC02', 'status':'PASS', 'runtime_integrated':False,
        'scope':'cross-contract and task-DAG validation; no additional live-gameplay claim',
        'passed':len(checks), 'failed':0, 'checks':checks,
        'inputs_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in dependencies}}
    (ROOT / 'docs/bc02_contract_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'BC02 cross-contracts PASS: {len(checks)} checks; 105 unique assignments; {len(tasks)} implementation tasks')


if __name__ == '__main__':
    run()
