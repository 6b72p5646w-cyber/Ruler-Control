#!/usr/bin/env python3
"""P0 joint acceptance: real reference routes -> receipts -> support -> ledger.

This is a design acceptance suite. Full enemy AI and player survival are not
simulated; damage-required encounters use the explicitly conditional T02 lane.
"""
from copy import deepcopy
from pathlib import Path
from collections import Counter
import json
import statistics
import tempfile

from bc01_campaign_reference import (ROOT, RunStore, digest, logical_night,
    make_combat_resolver, new_campaign, open_night, retry_night)
from bc01_joint_reference import JointNight, run_week
from bc01_map_reference import StoreMap, encounter_catalog

checks = []


def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def run():
    nav = StoreMap()
    authority = json.loads((ROOT / 'content/system_authority_bc01.json').read_text())
    for override in authority['scoped_overrides']:
        source = override['source']
        path, _, fragment = source.partition('#/')
        obj = json.loads((ROOT / path).read_text())
        for component in fragment.split('/') if fragment else []:
            check('authority fragment exists: ' + source, component in obj)
            obj = obj[component]
    check('BC01 has one explicit current design profile', 'current_design_bc01' in authority['execution_profiles'])
    check('whole-game release is not asserted', authority['validation']['full_105_ai_or_mobile_playtest_proven'] is False)
    # Each admitted active root gets a real routed scenario, rather than a bare
    # parameter fixture that could skip time or teleport the enemy into a tower.
    encounter_results = []
    for plan in encounter_catalog(7):
        joint = JointNight(seed=4, night_index=7, navigation=nav, encounter_pool=[plan])
        while not joint.director.state['raids'] and joint.director.now < 500:
            joint.advance(.25)
            if joint.director.state['error']:
                raise ValueError(joint.director.state['error'])
        check(plan['monster_id'] + ': actual routed terminal, no timeout victory', len(joint.director.state['raids']) == 1)
        raid = joint.director.state['raids'][0]
        if plan['requires_combat_after_rule']:
            receipt = raid['terminal_receipt']
            check(plan['monster_id'] + ': damage consumer reached HP zero', receipt['hp_after'] == 0 and receipt['terminal_kind'] == 'defeated')
            log = raid['combat_result']['combat_log']
            check(plan['monster_id'] + ': finite actual damage not a fixed timer', bool(log) and log[-1]['hp_after'] == 0 and abs(sum(e.get('actual_damage', 0) for e in log) - plan['hp']) < 1e-7)
            bad = deepcopy(raid)
            bad['plan']['actor_positions']['monster'] = nav.position('receiving')
            check(plan['monster_id'] + ': empty valid lane cannot teleport target', make_combat_resolver(nav)(bad, {}) is None)
        else:
            check(plan['monster_id'] + ': actual original-object leave/container receipt', raid['terminal_receipt']['terminal_kind'] == 'left')
        encounter_results.append({'monster_id': plan['monster_id'], 'raid_started_at': raid['started_at'],
                                  'rule_completed_at': raid['rule_completed_at'], 'terminal_at': raid['ended_at'],
                                  'duration_s': raid['ended_at'] - raid['started_at'],
                                  'terminal_kind': raid['terminal_receipt']['terminal_kind'],
                                  'post_rule_combat_seconds': (raid.get('combat_result') or {}).get('duration_s', 0),
                                  'player_and_monster_routes_are_real_reference_paths': True})
    # One complete multi-module night is retained as a reviewable continuous trace.
    exemplar = JointNight(seed=7, night_index=7, navigation=nav)
    result = exemplar.run()
    s = result['summary']
    check('joint full night reaches actual settlement', s['settled'] and s['finished_at'] >= 720)
    check('all real customer-use requests accepted', s['facility_uses_rejected'] == 0 and s['facility_uses_accepted'] > 0)
    check('combat advances zero ordinary chore work', s['ordinary_work_during_raid_seconds'] == 0)
    check('support payout derives from finite alive raid time', s['survival_coin'] <= 12 and s['survival_coin'] * 15 <= s['survival_eligible_seconds'])
    check('no gift becomes inventory or leftover world trap', not exemplar.temporary_traps and not exemplar.facilities.state['active_trap'])
    check('customer cleared before each raid', all(not r.get('customer_present_at_activation', False) for r in result['raids']))
    check('every root reward has an actual terminal', exemplar.ledger.counts['root'] == len(result['raids']))
    # Real SQLite snapshots of the coupled state, then resume through the same
    # services/blackout/randomness. Dedupe, paid sources and partial work survive.
    resume_results = []
    for at in (35.25, 115.5, 188.75, 333.25):
        campaign = new_campaign(f'bc01-resume-{at}')
        campaign['night_index'] = 7
        original = JointNight(seed=1, night_index=7, night_id=logical_night(campaign), navigation=nav)
        open_night(campaign, original.campaign_attempt())
        original.advance(at)
        campaign['attempt'] = original.campaign_attempt()
        with tempfile.TemporaryDirectory(prefix='bc01-joint-save-') as tmp:
            path = Path(tmp) / 'night.sqlite'
            store = RunStore(path)
            store.save(campaign, command_id='world-save', expected_revision=0)
            store.close()
            store = RunStore(path)
            loaded = store.load(campaign['campaign_id'])['state']
            restored = JointNight.from_campaign(loaded, nav)
            store.close()
        check(f'joint durable snapshot at {at}: exact state', restored.snapshot() == original.snapshot())
        original.run()
        restored.run()
        check(f'joint durable resume at {at}: identical complete continuation', restored.snapshot() == original.snapshot())
        resume_results.append({'save_at': at, 'exact_snapshot_and_continuation': True,
                               'same_orders': original.ledger.counts['order'],
                               'same_survival_payouts': original.ledger.counts['survival']})
    # Death retry restores the actual opening scene and stable draws, with a new
    # attempt envelope rather than using XP or future goods from the failed run.
    campaign = new_campaign('bc01-retry')
    campaign['night_index'] = 7
    failed = JointNight(seed=2, night_index=7, night_id=logical_night(campaign), navigation=nav)
    open_night(campaign, failed.campaign_attempt())
    failed.advance(190)
    campaign['attempt'] = failed.campaign_attempt()
    campaign['phase'] = 'failed'
    campaign['attempt']['player']['hp'] = 0
    retry_night(campaign)
    retried = JointNight.from_campaign(campaign, nav)
    check('retry restores exact opening growth and currency', campaign['week']['coin'] == 120 and campaign['permanent']['total_xp'] == 0 and retried.player.hp == 100)
    check('retry rebinds actual director/facilities/ledger to new attempt', retried.director.state['attempt_id'] == 2 and retried.facilities.state['attempt_id'] == 2 and retried.ledger.attempt_id == 2)
    r1 = JointNight(seed=2, night_index=7, night_id=logical_night(campaign), navigation=nav).run()
    r2 = retried.run()
    check('retry cannot reroll encounters or normal sale schedule', [r['monster_id'] for r in r1['raids']] == [r['monster_id'] for r in r2['raids']] and [o['completed_at'] for o in r1['orders']] == [o['completed_at'] for o in r2['orders']])
    gifts1 = [(c['variant'], c['placement']) for c in r1['consumer_log'] if c['kind'] == 'actual_safe_temporary_trap_placed']
    gifts2 = [(c['variant'], c['placement']) for c in r2['consumer_log'] if c['kind'] == 'actual_safe_temporary_trap_placed']
    check('retry cannot reroll gift types or legal locations', gifts1 == gifts2)
    weeks = []
    for strategy in ('free', 'defense', 'balanced'):
        for seed in (1, 3, 7):
            week = run_week(seed, strategy, nav)
            weeks.append(week)
            prefix = f'{strategy}/seed{seed}'
            check(prefix + ': all seven nights settle from real routes', len(week['nights']) == 7 and all(n['settled'] for n in week['nights']))
            check(prefix + ': no future-wage borrowing/negative balance', all(n['opening_coin_after_purchase'] >= 0 and n['opening_spirit_after_purchase'] >= 0 for n in week['nights']))
            check(prefix + ': no ordinary work while chased', all(n['ordinary_work_during_raid_seconds'] == 0 for n in week['nights']))
            check(prefix + ': income follows actual bounded sources', all(n['settlement']['counts']['order'] == n['paid_orders'] and n['settlement']['counts']['root'] == n['resolved_raids'] and n['survival_coin'] <= 12 for n in week['nights']))
            check(prefix + ': level only applies at next opening', all(week['nights'][i]['level_at_open'] == week['nights'][i-1]['next_level'] for i in range(1, 7)))
            check(prefix + ': week resets coin but keeps XP/tickets', week['next_week_wallet'] == 120 and week['permanent_xp'] > 0 and week['tickets'] == 8)
    nights = [n for w in weeks for n in w['nights']]
    strategy_summary = []
    for strategy in ('free', 'defense', 'balanced'):
        rows = [w for w in weeks if w['strategy'] == strategy]
        strategy_summary.append({'strategy': strategy, 'weeks': len(rows),
                                 'permanent_xp_range': [min(w['permanent_xp'] for w in rows), max(w['permanent_xp'] for w in rows)],
                                 'next_level_range': [min(w['next_level'] for w in rows), max(w['next_level'] for w in rows)],
                                 'coin_at_close_range': [min(w['week_score']['coin_at_close'] for w in rows), max(w['week_score']['coin_at_close'] for w in rows)],
                                 'mean_orders_per_night': round(statistics.mean(n['paid_orders'] for w in rows for n in w['nights']), 3),
                                 'mean_active_raid_seconds': round(statistics.mean(n['active_raid_seconds'] for w in rows for n in w['nights']), 3)})
    report = {'version': 'BC01', 'design_p0_complete': True, 'production_client_integrated': False,
              'passed': len(checks), 'failed': 0, 'checks': checks,
              'scope': '首发设计与有限联合参考：真实路线/服务/主解脚本+有条件的T02实际HP伤害，无敌人攻击AI/躲避成功率。',
              'encounter_scenarios': encounter_results, 'full_joint_week_count': len(weeks),
              'full_joint_night_count': len(nights), 'durable_joint_resumes': resume_results,
              'aggregate': {'paid_orders_range': [min(n['paid_orders'] for n in nights), max(n['paid_orders'] for n in nights)],
                            'chore_range': [min(n['completed_chores'] for n in nights), max(n['completed_chores'] for n in nights)],
                            'raid_count_range': [min(n['resolved_raids'] for n in nights), max(n['resolved_raids'] for n in nights)],
                            'total_blackouts': sum(n['power_off_events'] for n in nights),
                            'total_accepted_customer_uses': sum(n['facility_uses_accepted'] for n in nights),
                            'rejected_real_customer_uses': sum(n['facility_uses_rejected'] for n in nights),
                            'ordinary_raid_chore_seconds': sum(n['ordinary_work_during_raid_seconds'] for n in nights)},
              'strategy_summary': strategy_summary, 'weeks': weeks,
              'not_proven': ['105个完整AI', '每次随机入侵的玩家生存胜率', '移动触控舒适性', '微信帧率与云存档部署'],
              'reference_adapter_limits': ['首次版实际NPC消费接通FR01/02/03/04/05/10；其余顾客服务有明确完整合同与消费者验证门禁，不能冒用玩家杂活触发。',
                                           '普通夜单主根；两种组合只有有条件的空间/规则准入证明，未伪装同时运行全套AI。',
                                           '有限伤害排程使用合法射界里的已显形、已解主机制目标，不能据此宣称免费T02实际必胜。']}
    trace = {'scope': report['scope'], 'summary': result['summary'], 'events': result['events'],
             'orders': result['orders'], 'chores': result['chores'], 'ledger': result['ledger'],
             'facility_use_results': result['facility_use_results'], 'consumer_log': result['consumer_log']}
    (ROOT / 'docs/bc01_full_night_trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2) + '\n')
    paths = [Path(__file__), ROOT / 'scripts/bc01_joint_reference.py', ROOT / 'scripts/bc01_campaign_reference.py',
             ROOT / 'scripts/bc01_map_reference.py', ROOT / 'scripts/bc01_director_reference.py', ROOT / 'scripts/bc01_facility_reference.py']
    paths += sorted((ROOT / 'content').glob('*bc01.json'))
    report['inputs_sha256'] = {str(p.relative_to(ROOT)): __import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in paths}
    (ROOT / 'docs/bc01_p0_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"BC01 P0: {len(checks)} passed; {len(weeks)} weeks / {len(nights)} routed nights; no full AI claim")
    print(json.dumps(report['aggregate'], ensure_ascii=False))
    return report


if __name__ == '__main__':
    run()
