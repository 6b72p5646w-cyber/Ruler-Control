#!/usr/bin/env python3
"""BC02 finite ad state/ledger adapter, NOT an ad SDK or anti-fraud server.

Uses actual BC01 successful settlement receipts and its atomic RunStore envelope.
The extra partition is reference-only. A production BC02 loader must implement
its own explicit schema migration; this is not permission to mix live modes.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'content/ad_contracts_bc02.json').read_text())
DOUBLE = 'AD_RUN_DOUBLE_COIN'
DRAW = 'AD_EXTRA_DRAW'


def key(parts):
    return json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class PauseClock:
    """Only the shared world delta is consumed by domain owners."""
    def __init__(self):
        self.world = 0.0
        self.wall = 0.0
        self.tokens = set()

    def acquire(self, owner):
        self.tokens.add(owner)

    def release(self, owner):
        self.tokens.discard(owner)

    def tick(self, seconds):
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0 <= seconds < 1e9:
            raise ValueError('invalid elapsed time')
        self.wall += seconds
        dt = 0.0 if self.tokens else seconds
        self.world += dt
        return dt

    def resume(self):
        self.release('manual_menu')
        self.release('resume_confirmation')
        # An active provider or background owner still prevents advancement.


class AdsBC02:
    """Mutable reference points at the same campaign wallet as settlement."""
    def __init__(self, campaign):
        self.campaign = campaign
        self._durable_nonces = set()
        self.data = campaign.setdefault('ad_rewards_bc02', {
            'version': 'BC02', 'offers': {}, 'claims': {}, 'sequence': 0,
            'active_nonce': None, 'shows': {}, 'pause_impressions': {},
            'last_pause_at_active_world': None, 'closed_result_nights': []})
        if self.data['version'] != 'BC02':
            raise ValueError('incompatible ad reference partition')

    def _settlement(self, night_id):
        result = self.campaign['settlement_receipts'].get(night_id)
        if (not result or night_id not in self.campaign['permanent']['settled_nights']
                or result.get('night_id') != night_id or result.get('ticket') != 1
                or not isinstance(result.get('coin'), int) or isinstance(result['coin'], bool) or result['coin'] < 0):
            raise ValueError('actual successful settlement required')
        cid, week, night = json.loads(night_id)
        if cid != self.campaign['campaign_id'] or type(week) is not int or type(night) is not int or not 1 <= night <= 7:
            raise ValueError('wrong settlement identity')
        return result, week, night

    def offer(self, night_id, placement, *, lottery_ready=False, pending_draw=False):
        receipt, week, night = self._settlement(night_id)
        if (self.campaign['phase'] not in ('settled', 'pre_shift') or
                self.campaign['permanent']['settled_nights'][-1] != night_id):
            raise ValueError('only latest successful safe interval is eligible')
        if placement == DOUBLE:
            if (night == 7 or week != self.campaign['week_id'] or self.campaign['phase'] != 'settled'
                    or night_id in self.data['closed_result_nights']):
                raise ValueError('coin offer closed or old week cleared')
            reward = {'coin': receipt['coin'], 'tickets': 0}
        elif placement == DRAW:
            if not lottery_ready or pending_draw:
                raise ValueError('actual complete lottery pool and no pending draw required')
            reward = {'coin': 0, 'tickets': 1}
        else:
            raise ValueError('unknown rewarded placement')
        oid = key([self.campaign['campaign_id'], week, night, placement])
        offer = {'id': oid, 'night_id': night_id, 'placement': placement,
                 'week_id': week, 'reward': reward,
                 'base_receipt_hash': sha256(key(receipt).encode()).hexdigest()}
        previous = self.data['offers'].get(oid)
        if previous is not None and previous != offer:
            raise ValueError('immutable reward offer changed')
        self.data['offers'][oid] = offer
        return deepcopy(offer)

    def begin(self, offer_id, *, user_initiated, lottery_ready=False, pending_draw=False):
        offer = self.data['offers'][offer_id]
        # Revalidate screen/phase with the fixed identity; an old offer is not
        # authority to display after the next night or week has started.
        self.offer(offer['night_id'], offer['placement'], lottery_ready=lottery_ready, pending_draw=pending_draw)
        if user_initiated is not True or offer_id in self.data['claims'] or self.data['active_nonce'] is not None:
            raise ValueError('one voluntary unclaimed show at a time')
        self.data['sequence'] += 1
        nonce = key([offer_id, self.data['sequence']])
        self.data['shows'][nonce] = {'nonce': nonce, 'offer_id': offer_id, 'state': 'loading'}
        self.data['active_nonce'] = nonce
        return nonce

    def loaded_and_shown(self, nonce, clock):
        show = self.data['shows'].get(nonce)
        if (not show or nonce not in self._durable_nonces or
                self.data['active_nonce'] != nonce or show['state'] != 'loading'):
            return False
        offer = self.data['offers'][show['offer_id']]
        latest = self.campaign['permanent']['settled_nights']
        if (self.campaign['phase'] not in ('settled', 'pre_shift') or not latest or
                latest[-1] != offer['night_id'] or
                (offer['placement'] == DOUBLE and (
                    self.campaign['phase'] != 'settled' or
                    offer['night_id'] in self.data['closed_result_nights'] or
                    offer['week_id'] != self.campaign['week_id']))):
            self._finish_show(nonce, clock, 'cancelled')
            return False
        show['state'] = 'showing'
        clock.acquire('ad:' + nonce)
        return True

    def persist_request(self, nonce, store, *, expected_revision):
        """Real repository commit is required BEFORE the provider may show.

        An allocated but uncommitted nonce must never leave this adapter. After
        a process restart, recover unknown requests and allocate a higher nonce
        from the committed sequence; do not replay a native show automatically.
        """
        show = self.data['shows'].get(nonce)
        if not show or self.data['active_nonce'] != nonce or show['state'] != 'loading':
            raise ValueError('no current prepared request')
        result = store.save(self.campaign, command_id='ad-request:' + nonce,
                            expected_revision=expected_revision)
        self._durable_nonces.add(nonce)
        return result

    def _finish_show(self, nonce, clock, state):
        self.data['shows'][nonce]['state'] = state
        if self.data['active_nonce'] == nonce:
            self.data['active_nonce'] = None
        clock.release('ad:' + nonce)
        clock.acquire('resume_confirmation')

    def fail_or_cancel(self, nonce, clock, *, reason='failed'):
        show = self.data['shows'].get(nonce)
        if not show or self.data['active_nonce'] != nonce:
            return False
        self._finish_show(nonce, clock, 'cancelled' if reason == 'cancelled' else 'failed')
        return True

    def close(self, nonce, clock, *, is_ended):
        show = self.data['shows'].get(nonce)
        if not show:
            return {'applied': False, 'reason': 'unknown_show'}
        oid = show['offer_id']
        if show['state'] == 'claimed':
            return {'applied': False, 'reason': 'duplicate', 'receipt': deepcopy(self.data['claims'][oid])}
        if self.data['active_nonce'] != nonce or show['state'] != 'showing':
            return {'applied': False, 'reason': 'stale_or_never_shown'}
        if is_ended is not True:
            self._finish_show(nonce, clock, 'early_close')
            return {'applied': False, 'reason': 'completion_not_proven'}
        offer = self.data['offers'][oid]
        try:
            original, week, night = self._settlement(offer['night_id'])
            if (self.campaign['phase'] not in ('settled', 'pre_shift') or
                    self.campaign['permanent']['settled_nights'][-1] != offer['night_id']):
                raise ValueError('cannot apply ad completion to a different gameplay interval')
            if sha256(key(original).encode()).hexdigest() != offer['base_receipt_hash']:
                raise ValueError('settlement changed during ad')
            if offer['placement'] == DOUBLE and (week != self.campaign['week_id'] or night == 7):
                raise ValueError('cannot credit a closed week')
            expected_reward = {'coin': original['coin'], 'tickets': 0} if offer['placement'] == DOUBLE else {'coin': 0, 'tickets': 1}
            if offer['placement'] not in (DOUBLE, DRAW) or offer['reward'] != expected_reward:
                raise ValueError('immutable offer reward changed')
            if oid in self.data['claims']:
                raise ValueError('duplicate claim from a different show')
        except (ValueError, KeyError, TypeError) as error:
            # The native view already closed. A reward validation failure must
            # not strand its pause token or clear another owner's pause.
            self._finish_show(nonce, clock, 'failed')
            return {'applied': False, 'reason': 'invalid_completed_show', 'detail': str(error)}
        receipt = {'offer_id': oid, 'show_nonce': nonce, 'night_id': offer['night_id'],
                   'reward': deepcopy(offer['reward']), 'source': 'simulated_completed_sdk_callback'}
        # Persist these mutations in ONE campaign/RunStore transaction, never
        # persist just the wallet or just the ad marker. UI sees it after commit.
        self.campaign['week']['coin'] += offer['reward']['coin']
        self.campaign['permanent']['tickets'] += offer['reward']['tickets']
        self.data['claims'][oid] = receipt
        self._finish_show(nonce, clock, 'claimed')
        return {'applied': True, 'receipt': deepcopy(receipt)}

    def leave_results(self, night_id):
        if night_id in self.data['closed_result_nights']:
            return {'applied': False, 'reason': 'already_closed'}
        latest = self.campaign['permanent']['settled_nights']
        if self.campaign['phase'] != 'settled' or not latest or latest[-1] != night_id:
            return {'applied': False, 'reason': 'stale_result_screen'}
        if self.data['active_nonce'] is not None:
            raise ValueError('first close/cancel the actual active provider')
        self.data['closed_result_nights'].append(night_id)
        self.campaign['phase'] = 'pre_shift'
        return {'applied': True, 'reason': 'result_screen_closed'}

    def pause_impression(self, night_id, active_world_seconds, *, manual, ready):
        if manual is not True or ready is not True or active_world_seconds < 60:
            return False
        if night_id in self.data['pause_impressions']:
            return False
        previous = self.data['last_pause_at_active_world']
        if previous is not None and active_world_seconds - previous < 180:
            return False
        self.data['pause_impressions'][night_id] = active_world_seconds
        self.data['last_pause_at_active_world'] = active_world_seconds
        return True

    def recover_after_process_restart(self):
        """No replayable completion is invented from elapsed wall time."""
        nonce = self.data['active_nonce']
        if nonce:
            self.data['shows'][nonce]['state'] = 'failed'
            self.data['active_nonce'] = None
