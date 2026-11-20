#!/usr/bin/env python3
"""Ad callback, pause and real SQLite transaction counterexamples.

One real BC01 routed reference night supplies the base settlement; separate
week/invalid-provider fixtures are deliberately NOT a seven-night ad economy run.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile

from bc01_campaign_reference import (NightLedger, RunStore, canonical, level_for_xp, logical_night,
    new_campaign, open_night, settle_night)
from bc01_joint_reference import JointNight
from bc02_ad_reference import AdsBC02, CONTRACT, DOUBLE, DRAW, PauseClock

ROOT = Path(__file__).resolve().parents[1]
checks = []
repos = {}
repo_directory = None


def check(name, ok):
    checks.append({'name': name, 'passed': bool(ok)})
    if not ok:
        raise AssertionError(name)


def rejects(name, fn):
    try:
        fn()
    except (ValueError, KeyError):
        check(name, True)
    else:
        check(name, False)


def durable_show(ad, nonce, clock):
    if ad not in repos:
        repos[ad] = [RunStore(Path(repo_directory.name) / f'provider-{len(repos)}.sqlite'), 0]
    db, revision = repos[ad]
    result = ad.persist_request(nonce, db, expected_revision=revision)
    repos[ad][1] = result['revision']
    return ad.loaded_and_shown(nonce, clock)


def run():
    global repo_directory
    repo_directory = tempfile.TemporaryDirectory()
    state = new_campaign('bc02-ad-reference')
    night_id = logical_night(state)
    joint = JointNight(seed=7, night_id=night_id)
    open_night(state, joint.campaign_attempt())
    ads = AdsBC02(state)
    rejects('failed/unsettled night cannot mint ad offer', lambda: ads.offer(night_id, DOUBLE))
    clock = PauseClock()
    joint.advance(clock.tick(60))
    before_pause = canonical(joint.snapshot())
    clock.acquire('manual_menu')
    clock.acquire('ad:pause-sponsor')
    joint.advance(clock.tick(300))
    check('300 real ad seconds leave full actual joint snapshot unchanged', canonical(joint.snapshot()) == before_pause)
    clock.release('ad:pause-sponsor')
    joint.advance(clock.tick(10))
    check('ad closed does not release manual pause', canonical(joint.snapshot()) == before_pause)
    clock.acquire('background')
    clock.resume()
    joint.advance(clock.tick(20))
    check('manual resume does not release background owner', canonical(joint.snapshot()) == before_pause)
    clock.release('background')
    joint.advance(clock.tick(.25))
    check('resume advances only new world delta, never wall catchup', joint.director.now == 60.25 and clock.world == 60.25)
    result = joint.run()
    check('base night has actual customers/routes and real root terminals', result['summary']['settled'] and result['summary']['paid_orders'] > 0 and result['summary']['resolved_raids'] > 0)
    settlement = settle_night(state, joint.ledger, actual_time=joint.director.now,
        player_alive=joint.player.alive, san_safe=joint.player.san > 0,
        all_roots_terminal=joint.director.state['raid'] is None,
        customers_outside=joint.director.state['customer'] is None)['receipt']
    baseline = deepcopy(state)
    check('normal income already paid before optional ad', state['week']['coin'] == 120 + settlement['coin'])
    offer = ads.offer(night_id, DOUBLE)
    check('double means one extra original earned coin, not wallet', offer['reward']['coin'] == settlement['coin'] and offer['reward']['coin'] != state['week']['coin'])
    rejects('SDK cannot initiate rewarded show without explicit user choice', lambda: ads.begin(offer['id'], user_initiated=False))
    nonce1 = ads.begin(offer['id'], user_initiated=True)
    check('uncommitted show request cannot call the provider', not ads.loaded_and_shown(nonce1, clock))
    check('onLoad alone does not mint reward', not ads.close(nonce1, clock, is_ended=True)['applied'])
    check('cancelled loading cannot show after delayed onLoad', ads.fail_or_cancel(nonce1, clock, reason='cancelled') and not ads.loaded_and_shown(nonce1, clock))
    nonce2 = ads.begin(offer['id'], user_initiated=True)
    check('retry uses distinct show nonce, same immutable offer', nonce1 != nonce2 and ads.data['shows'][nonce2]['offer_id'] == offer['id'])
    check('old completion cannot claim newly retried show', not ads.close(nonce1, clock, is_ended=True)['applied'])
    durable_show(ads, nonce2, clock)
    before = deepcopy(state['permanent'])
    check('early close does not debit base rewards', not ads.close(nonce2, clock, is_ended=False)['applied'] and state['week']['coin'] == baseline['week']['coin'] and state['permanent'] == before)
    for invalid in (None, 1, 'true'):
        nonce = ads.begin(offer['id'], user_initiated=True)
        durable_show(ads, nonce, clock)
        check('only boolean true proves completion: ' + repr(invalid), not ads.close(nonce, clock, is_ended=invalid)['applied'])
    nonce = ads.begin(offer['id'], user_initiated=True)
    durable_show(ads, nonce, clock)
    rewards_before = deepcopy(state['permanent'])
    spirit_before = state['week']['spirit']
    awarded = ads.close(nonce, clock, is_ended=True)
    check('completed ad grants precisely original earned coin once', awarded['applied'] and state['week']['coin'] == 120 + 2 * settlement['coin'])
    check('XP, tickets, spirit, pity and equipment are not doubled', state['permanent'] == rewards_before and state['week']['spirit'] == spirit_before)
    check('duplicate completion returns original receipt without adding', not ads.close(nonce, clock, is_ended=True)['applied'] and state['week']['coin'] == 120 + 2 * settlement['coin'])
    rejects('same logical night cannot show another completed coin ad', lambda: ads.begin(offer['id'], user_initiated=True))
    rejects('missing lottery consumers hide rewarded draw', lambda: ads.offer(night_id, DRAW))
    rejects('pending real draw cannot be overwritten by ad', lambda: ads.offer(night_id, DRAW, lottery_ready=True, pending_draw=True))
    lottery_offer = ads.offer(night_id, DRAW, lottery_ready=True)
    rejects('lottery readiness must still hold at actual show', lambda: ads.begin(lottery_offer['id'], user_initiated=True))
    nonce = ads.begin(lottery_offer['id'], user_initiated=True, lottery_ready=True)
    durable_show(ads, nonce, clock)
    wallet_before = deepcopy(state['week'])
    old_tickets = state['permanent']['tickets']
    old_pity = deepcopy(state['permanent']['pity'])
    check('rewarded draw gives one ticket without rolling or changing pity', ads.close(nonce, clock, is_ended=True)['applied'] and state['permanent']['tickets'] == old_tickets + 1 and state['permanent']['pity'] == old_pity and state['week'] == wallet_before)
    rejects('extra draw cap is one per completed logical night', lambda: ads.begin(lottery_offer['id'], user_initiated=True, lottery_ready=True))
    check('max first-week tickets is 8 ordinary plus 7 optional', CONTRACT['placements'][2]['first_week_total_with_all_seven_optional_ads'] == 15)
    for phase in ('open', 'failed'):
        bad = deepcopy(baseline); bad['phase'] = phase
        rejects('cannot watch earned coin ad in phase ' + phase, lambda: AdsBC02(bad).offer(night_id, DOUBLE))
    closed = deepcopy(baseline); closed_ads = AdsBC02(closed)
    expired = closed_ads.offer(night_id, DOUBLE)
    closed_ads.leave_results(night_id)
    rejects('leaving results expires unstarted coin offer', lambda: closed_ads.begin(expired['id'], user_initiated=True))
    check('extra draw stays available in subsequent safe preparation', closed_ads.offer(night_id, DRAW, lottery_ready=True)['reward']['tickets'] == 1)
    next_id = logical_night(closed)
    next_joint = JointNight(seed=8, night_index=closed['night_index'], night_id=next_id,
        attempt_id=closed['attempt_id'] + 1,
        level=level_for_xp(closed['permanent']['total_xp']))
    open_night(closed, next_joint.campaign_attempt())
    open_snapshot = canonical(closed)
    check('stale repeated result close cannot revert new open night', not closed_ads.leave_results(night_id)['applied'] and canonical(closed) == open_snapshot)
    rejects('old draw invitation stays expired after next night starts', lambda: closed_ads.offer(night_id, DRAW, lottery_ready=True))
    check('unknown result navigation also leaves the new night intact', not closed_ads.leave_results('["unknown",1,1]')['applied'] and canonical(closed) == open_snapshot)
    loading_next = deepcopy(baseline); loading_ads = AdsBC02(loading_next)
    loading_ads.leave_results(night_id)
    loading_offer = loading_ads.offer(night_id, DRAW, lottery_ready=True)
    loading_nonce = loading_ads.begin(loading_offer['id'], user_initiated=True, lottery_ready=True)
    with tempfile.TemporaryDirectory() as tmp:
        provider_db = RunStore(Path(tmp) / 'loading.sqlite')
        loading_ads.persist_request(loading_nonce, provider_db, expected_revision=0)
        next_world = JointNight(seed=8, night_index=loading_next['night_index'], night_id=logical_night(loading_next),
            attempt_id=loading_next['attempt_id'] + 1, level=level_for_xp(loading_next['permanent']['total_xp']))
        open_night(loading_next, next_world.campaign_attempt())
        check('delayed onLoad cannot display an old draw ad after next night opens',
            not loading_ads.loaded_and_shown(loading_nonce, clock) and loading_ads.data['active_nonce'] is None and loading_next['phase'] == 'open')
        provider_db.close()
    # Deliberate boundary fixture: no claim of seven nights being played here.
    week7 = new_campaign('week-boundary-fixture'); week7.update({'night_index': 7, 'attempt_id': 1, 'phase': 'open'})
    ledger7 = NightLedger(logical_night(week7), 1)
    settle7 = settle_night(week7, ledger7, actual_time=720, player_alive=True,
        san_safe=True, all_roots_terminal=True, customers_outside=True)['receipt']
    a7 = AdsBC02(week7)
    rejects('night7 does not offer immediately erased old-week double coin', lambda: a7.offer(settle7['night_id'], DOUBLE))
    seventh = a7.offer(settle7['night_id'], DRAW, lottery_ready=True)
    n7 = a7.begin(seventh['id'], user_initiated=True, lottery_ready=True)
    durable_show(a7, n7, clock); a7.close(n7, clock, is_ended=True)
    check('night7 extra ticket persists while new week coin stays 120', week7['week_id'] == 2 and week7['week']['coin'] == 120 and week7['permanent']['tickets'] == 3)
    impression_state = deepcopy(baseline); ia = AdsBC02(impression_state)
    check('background pause cannot trigger sponsor ad', not ia.pause_impression(night_id, 60, manual=False, ready=True))
    check('no-fill pause does not consume impression cap', not ia.pause_impression(night_id, 60, manual=True, ready=False))
    check('early first minute is ad free', not ia.pause_impression(night_id, 59, manual=True, ready=True))
    check('manual pause after sixty actual seconds can show one ready ad', ia.pause_impression(night_id, 60, manual=True, ready=True))
    check('repeated pause does not repeatedly show ads', not ia.pause_impression(night_id, 720, manual=True, ready=True))
    check('active-world cooldown applies across logical nights', not ia.pause_impression('["next",1,2]', 200, manual=True, ready=True))
    check('cooldown expires by active play rather than ad wall time', ia.pause_impression('["next",1,2]', 240, manual=True, ready=True))
    pending = deepcopy(baseline); pa = AdsBC02(pending); po = pa.offer(night_id, DOUBLE)
    pn = pa.begin(po['id'], user_initiated=True)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'ads.sqlite'
        db = RunStore(path)
        pa.persist_request(pn, db, expected_revision=0)
        db.close(); db = RunStore(path)
        before_show_restart = db.load(state['campaign_id'])['state']
        restart_ads = AdsBC02(before_show_restart); restart_ads.recover_after_process_restart()
        restarted_nonce = restart_ads.begin(po['id'], user_initiated=True)
        check('committed request survives real reopen and cannot reuse shown nonce', restarted_nonce != pn and before_show_restart['ad_rewards_bc02']['sequence'] > pending['ad_rewards_bc02']['sequence'])
        check('restarted request must also be committed before showing', not restart_ads.loaded_and_shown(restarted_nonce, clock))
        # Continue the original live provider; the independent restart fixture
        # above was not persisted over it.
        pa.loaded_and_shown(pn, clock)
        db.save(pending, command_id='show-started', expected_revision=1)
        changed = deepcopy(pending); ca = AdsBC02(changed); ca.close(pn, clock, is_ended=True)
        try:
            db.save(changed, command_id='claim-completed', expected_revision=2, fault='after_snapshot')
        except RuntimeError:
            pass
        else:
            raise AssertionError('expected pre-commit interruption')
        db.close(); db = RunStore(path)
        restored = db.load(state['campaign_id'])
        check('real SQLite interrupted claim rolls back wallet and claim together', restored['revision'] == 2 and restored['state']['week']['coin'] == baseline['week']['coin'] and not restored['state']['ad_rewards_bc02']['claims'])
        recovered = restored['state']; ra = AdsBC02(recovered)
        ra.close(pn, clock, is_ended=True)
        db.save(recovered, command_id='claim-completed', expected_revision=2)
        db.close(); db = RunStore(path)
        loaded = db.load(state['campaign_id'])
        check('committed claim and full wallet survive actual file reopen', loaded['revision'] == 3 and loaded['state']['week']['coin'] == 120 + 2 * settlement['coin'] and len(loaded['state']['ad_rewards_bc02']['claims']) == 1)
        check('lost acknowledgement cannot duplicate claim after reopen', not AdsBC02(loaded['state']).close(pn, clock, is_ended=True)['applied'])
        check('same-command retry is idempotent', not db.save(recovered, command_id='claim-completed', expected_revision=2)['applied'])
        modified = deepcopy(recovered); modified['week']['coin'] += 1
        rejects('same command with changed wallet rejected', lambda: db.save(modified, command_id='claim-completed', expected_revision=3))
        rejects('parallel stale campaign revision rejected', lambda: db.save(recovered, command_id='stale-write', expected_revision=2))
        db.close()
    crash = deepcopy(pending); ac = AdsBC02(crash); ac.recover_after_process_restart()
    check('unknown interrupted video cannot infer completion from wall time', not ac.close(pn, clock, is_ended=True)['applied'] and crash['week']['coin'] == baseline['week']['coin'])
    check('unknown video interruption keeps unclaimed retry entitlement', ac.begin(po['id'], user_initiated=True) != pn)
    for invalidation in ('phase', 'receipt', 'week', 'offer_amount'):
        broken = deepcopy(baseline); ba = AdsBC02(broken); local_clock = PauseClock()
        bo = ba.offer(night_id, DOUBLE); bn = ba.begin(bo['id'], user_initiated=True)
        durable_show(ba, bn, local_clock)
        local_clock.acquire('manual_menu')
        if invalidation == 'phase':
            broken['phase'] = 'open'
        elif invalidation == 'receipt':
            broken['settlement_receipts'][night_id]['coin'] += 1
        elif invalidation == 'week':
            broken['week_id'] += 1
        else:
            ba.data['offers'][bo['id']]['reward']['coin'] += 1
        before_wallet = deepcopy(broken['week'])
        rejected = ba.close(bn, local_clock, is_ended=True)
        check('invalid completed show rejects reward and always releases own ad pause: ' + invalidation,
            not rejected['applied'] and broken['week'] == before_wallet and ba.data['active_nonce'] is None
            and 'ad:' + bn not in local_clock.tokens and 'manual_menu' in local_clock.tokens)
        local_clock.resume()
        check('invalid completed show remains resumable: ' + invalidation, local_clock.tick(10) == 10)
    dependencies = ['content/ad_contracts_bc02.json', 'scripts/bc02_ad_reference.py', 'scripts/check_bc02_ads.py',
        'scripts/bc01_campaign_reference.py', 'scripts/bc01_joint_reference.py', 'scripts/bc01_director_reference.py',
        'scripts/bc01_facility_reference.py', 'scripts/bc01_map_reference.py', 'content/campaign_bc01.json',
        'content/director_bc01.json', 'content/facilities_bc01.json', 'content/map_composition_bc01.json',
        'content/maps.json', 'content/map_mechanics_v05.json', 'content/lottery_rewards_eq01.json']
    report = {'version': 'BC02', 'status': 'PASS', 'runtime_integrated': False,
        'passed': len(checks), 'failed': 0, 'checks': checks,
        'actual_base_night': {'source': 'BC01 JointNight actual customer/route/reference terminal outputs',
            'seed': 7, 'summary': result['summary'], 'settlement': settlement},
        'scope': 'one routed BC01 base night + simulated SDK callbacks, ownership pause + actual local SQLite interruptions; no ad SDK/server authentication/client integration or ad-enabled weekly balance claim',
        'inputs_sha256': {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in dependencies}}
    (ROOT / 'docs/bc02_ad_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'BC02 ads PASS: {len(checks)} checks; one actual routed base night; live ads false')
    for db, _ in repos.values():
        db.close()
    repo_directory.cleanup()


if __name__ == '__main__':
    run()
