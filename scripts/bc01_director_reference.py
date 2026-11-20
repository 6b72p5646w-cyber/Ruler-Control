#!/usr/bin/env python3
"""BC01 bounded director: routed customers, interruptible work and explicit raid receipts.

This is a deterministic design reference. It does not implement monster AI or input.
Ordinary sales are outputs of actors walking and completing actions, never inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'content' / 'director_bc01.json'


def _clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seed(seed, stream):
    return int.from_bytes(hashlib.sha256(f'{seed}:{stream}'.encode()).digest()[:4], 'big') or 1


def _default_navigation():
    from bc01_map_reference import StoreMap
    return StoreMap()


def _default_pool(night_index=None):
    from bc01_map_reference import encounter_catalog
    # No invented combat victory: default demonstrates the actual leave-route subset.
    return [p for p in encounter_catalog(night_index) if not p.get('requires_combat_after_rule', False)]


class Director:
    """State ownership is entirely inside `state`; callbacks are external adapters."""
    def __init__(self, seed=1, navigation=None, *, action_duration_factor=1.0,
                 player_move_speed=3.0, encounter_pool=None, callbacks=None,
                 night_index=1, night_id=None, attempt_id=1):
        self.config = json.loads(CONTRACT.read_text())
        self.navigation = navigation or _default_navigation()
        self.callbacks = callbacks or {}
        pool = _clone(encounter_pool if encounter_pool is not None else _default_pool(night_index))
        if not pool:
            raise ValueError('an admitted encounter pool is required')
        self.state = {
            'version': 'BC01', 'seed': seed, 'night_index': night_index,
            'night_id': night_id or json.dumps(['bc01', 1, night_index], separators=(',', ':')), 'attempt_id': attempt_id,
            'now': 0.0, 'phase': 'BUSINESS', 'phase_started_at': 0.0,
            'phase_deadline': None, 'raid_due': None, 'next_customer_at': None,
            'closing': False, 'settled': False, 'power_on': True, 'player_alive': True,
            'action_duration_factor': max(0.6, min(1.0, action_duration_factor)),
            'player_move_speed': player_move_speed, 'player_carry_multiplier': 1.0, 'player_position': self.position('cashier'),
            'rng': {stream: _seed(seed, stream) for stream in ['raids', 'customers', 'chores', 'power', 'cosmetic']},
            'pool': pool, 'selected_monsters': [], 'raid': None, 'raids': [],
            'pending_raid_plan': None, 'pending_grid_surge': False, 'grid_surge_count': 0,
            'tactical_breaker': None, 'hands': None, 'paused_items': {}, 'pending_setdown': None,
            'customer': None, 'customer_count': 0, 'orders': [], 'facility_uses': [],
            'stock': {f'FR{n:02d}': 2 for n in [2, 3, 4, 5]},
            'warehouse_units': 12, 'returned_items': [], 'jobs': [], 'chore_receipts': [],
            'job_counter': 0, 'player_task': None, 'events': [], 'blackout_sources': [],
            'active_outage_id': None, 'truck_schedule': [], 'truck_offered': [],
            'eligible_survival_seconds': 0.0, 'active_raid_seconds': 0.0,
            'paid_reward_ids': [], 'route_distance_player': 0.0,
            'route_distance_customers': 0.0, 'work_seconds': 0.0,
            'ordinary_work_during_raid_seconds': 0.0, 'omen_extensions': [],
            'rejected_commands': [], 'error': None,
        }
        self.state['raid_due'] = self.randint('raids', 80, 100)
        self.state['next_customer_at'] = self.randint('customers', 3, 8)
        self.state['truck_schedule'] = [self.randint('chores', 150, 190), self.randint('chores', 455, 495)]
        self.emit('night_open', raid_due=self.state['raid_due'])

    @property
    def now(self):
        return self.state['now']

    def position(self, anchor_or_coordinate):
        if isinstance(anchor_or_coordinate, (list, tuple)):
            return list(anchor_or_coordinate)
        return list(self.navigation.position(anchor_or_coordinate))

    def randint(self, stream, lower, upper):
        # Portable, independent, serializable streams; not intended as cryptographic RNG.
        x = (1664525 * self.state['rng'][stream] + 1013904223) & 0xFFFFFFFF
        self.state['rng'][stream] = x
        return lower + (x >> 8) % (upper - lower + 1)

    def emit(self, kind, **payload):
        event = {'time': round(self.now, 6), 'kind': kind, 'phase': self.state['phase'], **payload}
        self.state['events'].append(event)
        callback = self.callbacks.get('on_event')
        if callback:
            callback(_clone(event))
        return event

    def _id(self, category, number):
        return f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:{category}:{number}"

    def _logical_id(self, category, ordinal):
        return json.dumps(['bc01', self.state['night_id'], category, ordinal], separators=(',', ':'), ensure_ascii=False)

    def _phase(self, phase, deadline=None):
        old = self.state['phase']
        self.state['phase'] = phase
        self.state['phase_started_at'] = self.now
        self.state['phase_deadline'] = deadline
        self.emit('phase_changed', previous=old, current=phase, deadline=deadline)

    def _plan(self, steps, start=None):
        return {'steps': _clone(steps), 'index': 0, 'remaining': None, 'path': None,
                'path_index': 0, 'actor_positions': {'player': list(start or self.state['player_position'])},
                'used_seconds': 0.0, 'action_receipts': [], 'travel_distance': 0.0, 'done': False}

    def _actor_key(self, step):
        return step.get('actor', 'player')

    def _prepare_step(self, plan, step):
        actor = self._actor_key(step)
        if actor not in plan['actor_positions']:
            source = step.get('from', step.get('start', step.get('from_role', step.get('start_role'))))
            if source is None:
                source = step.get('to', step.get('role', 'front_door'))
            plan['actor_positions'][actor] = self.position(source)
        pos = plan['actor_positions'][actor]
        if step['kind'] == 'travel':
            target = step.get('to', step.get('role'))
            route = self.navigation.route(pos, self.position(target), actor='customer' if actor == 'customer' else 'player')
            if not route or route.get('distance') is None:
                raise ValueError(f'unreachable actual route: {pos} -> {target}')
            plan['path'] = [list(p) for p in route['path']]
            if not plan['path']:
                plan['path'] = [self.position(target)]
            if _distance(pos, plan['path'][0]) > 1e-7:
                plan['path'].insert(0, list(pos))
            plan['path_index'] = 1
            plan['remaining'] = float(route['distance'])
        else:
            base = float(step.get('seconds', step.get('duration_s', 0.0)))
            # Only the player's authored manual action duration changes with proficiency.
            eligible = step['kind'] == 'action' and actor == 'player' and step.get('proficiency', True)
            # Persist remaining BASE work, so a buff expiring or blackout changes
            # the remainder immediately instead of gifting its old rate forever.
            plan['remaining'] = base
            plan['step_base_seconds'] = base
            plan['step_manual'] = eligible
            plan['step_elapsed_seconds'] = 0.0

    def _advance_plan(self, plan, seconds, *, owner, receipt_prefix):
        remaining_tick = seconds
        while remaining_tick > 1e-9 and not plan['done']:
            if plan['index'] >= len(plan['steps']):
                plan['done'] = True
                break
            step = plan['steps'][plan['index']]
            actor = self._actor_key(step)
            if plan['remaining'] is None:
                self._prepare_step(plan, step)
            if step['kind'] == 'travel':
                base_speed = float(step.get('speed', 3.0 if actor == 'player' else 2.4))
                speed = (base_speed * self.state.get('player_carry_multiplier', 1.0) if base_speed < 3.0 else base_speed * self.state['player_move_speed'] / 3.0) if actor == 'player' else base_speed
                budget = remaining_tick * speed
                moved = 0.0
                path = plan['path']
                while plan['path_index'] < len(path) and budget > 1e-9:
                    pos = plan['actor_positions'][actor]
                    target = path[plan['path_index']]
                    length = _distance(pos, target)
                    take = min(length, budget)
                    if length > 1e-9:
                        ratio = take / length
                        plan['actor_positions'][actor] = [pos[0] + (target[0] - pos[0]) * ratio,
                                                           pos[1] + (target[1] - pos[1]) * ratio]
                    budget -= take
                    moved += take
                    if take >= length - 1e-9:
                        plan['actor_positions'][actor] = list(target)
                        plan['path_index'] += 1
                used = moved / speed
                remaining_tick -= used
                plan['used_seconds'] += used
                plan['travel_distance'] += moved
                plan['remaining'] = max(0.0, plan['remaining'] - moved)
                if owner == 'customer':
                    self.state['route_distance_customers'] += moved
                elif actor == 'player':
                    self.state['route_distance_player'] += moved
                done = plan['path_index'] >= len(path)
            else:
                base = plan.get('step_base_seconds', 0.0)
                factor = max(0.6, self.state['action_duration_factor'], 0.25 / base) if plan.get('step_manual') and base > 0 else 1.0
                used = min(remaining_tick, plan['remaining'] * factor)
                plan['remaining'] = max(0.0, plan['remaining'] - used / factor)
                plan['step_elapsed_seconds'] = plan.get('step_elapsed_seconds', 0.0) + used
                plan['used_seconds'] += used
                remaining_tick -= used
                if owner == 'job':
                    self.state['work_seconds'] += used
                    if self.state['phase'] == 'RAID':
                        self.state['ordinary_work_during_raid_seconds'] += used
                done = plan['remaining'] <= 1e-9
            if not done:
                break
            ended_at = self.now - remaining_tick
            receipt = {'event_id': f'{receipt_prefix}:step:{plan["index"]}',
                       'action_id': step.get('action_id', step.get('reason', step['kind'])),
                       'kind': step['kind'], 'actor': actor,
                       'completed_at': round(ended_at, 6),
                       'position': list(plan['actor_positions'][actor]),
                       'actual_seconds': round(plan.get('step_elapsed_seconds', 0.0), 9) if step['kind'] != 'travel' else None}
            plan['action_receipts'].append(receipt)
            self._step_effect(owner, step, receipt)
            plan['index'] += 1
            plan['remaining'] = None
            plan['path'] = None
            plan['path_index'] = 0
            if plan['index'] >= len(plan['steps']):
                plan['done'] = True
        return seconds - remaining_tick

    def _step_effect(self, owner, step, receipt):
        if owner == 'customer':
            customer = self.state['customer']
            effect = step.get('effect')
            if effect == 'entered':
                customer['physical_entry_at'] = receipt['completed_at']
                self.emit('customer_enter', customer_id=customer['customer_id'], position=receipt['position'])
            elif effect == 'used':
                fid = customer['variant']['facility_id']
                if self.state['stock'][fid] < 1:
                    raise ValueError('reserved ordinary SKU disappeared before actual pickup')
                self.state['stock'][fid] -= 1
                customer['holding_item'] = True
                customer['used'] = {'facility_id': fid, 'actual_use_at': receipt['completed_at'],
                                    'usage_kind': customer['variant']['usage_kind'], 'source_item_id': customer['item_id']}
                self.emit('facility_used_unpaid', customer_id=customer['customer_id'], **customer['used'])
            elif effect == 'return':
                if customer.get('holding_item') and not customer.get('paid'):
                    self.state['returned_items'].append({'item_id': customer['item_id'], 'facility_id': customer['variant']['facility_id'], 'position': receipt['position']})
                    customer['holding_item'] = False
                    self.emit('unpaid_item_returned', customer_id=customer['customer_id'], item_id=customer['item_id'])
        if owner == 'job':
            task = self.state['player_task']
            job = next((j for j in self.state['jobs'] if task and j['chore_id'] == task.get('chore_id')), None)
            if job and step.get('action_id') in ['take_employer_box', 'verify_real_delivery', 'take_cleaning_kit', 'resume_same_original_cargo']:
                existing = job.get('carry_state')
                item_id = existing['source_item_id'] if existing else job['chore_id'] + ':original_employer_item'
                job['carry_state'] = {'source_item_id': item_id, 'owner': 'employer_store',
                                      'held': True, 'position': list(receipt['position'])}
                self.state['hands'] = {'chore_id': job['chore_id'], 'source_item_id': item_id}
                if job.get('carry_pause'):
                    job['carry_pause']['status'] = 'picked_up_same_item'
                    self.state['paused_items'].pop(item_id, None)
                self.emit('store_item_taken', chore_id=job['chore_id'], source_item_id=item_id,
                          position=receipt['position'], same_original=existing is not None)
        if owner == 'omen' and step.get('action_id') == 'set_down_store_item':
            job = next(j for j in self.state['jobs'] if j['chore_id'] == step['chore_id'])
            cargo = job['carry_state']
            cargo['held'] = False
            cargo['position'] = list(receipt['position'])
            job['carry_pause'] = {'status': 'stowed', 'source_item_id': cargo['source_item_id'],
                                  'position': list(receipt['position']), 'blocks_navigation': False,
                                  'released_hands': True, 'actual_setdown_seconds': receipt['actual_seconds']}
            self.state['paused_items'][cargo['source_item_id']] = _clone(job['carry_pause'])
            self.state['hands'] = None
            self.state['pending_setdown'] = None
            self.emit('store_item_safely_set_down', chore_id=job['chore_id'], carry_pause=_clone(job['carry_pause']))
        if owner == 'raid':
            self.emit('raid_action_completed', raid_id=self.state['raid']['raid_id'], receipt=receipt)

    def _spawn_customer(self):
        s = self.state
        if s['customer'] or s['phase'] != 'BUSINESS' or s['closing']:
            return
        if len(s['orders']) >= 12 or s['customer_count'] >= 20 or self.now >= 675:
            s['next_customer_at'] = None
            return
        candidates = [v for v in self.config['customers']['variants'] if s['stock'][v['facility_id']] > 0]
        s['customer_count'] += 1
        cid = self._id('customer', s['customer_count'])
        if not candidates:
            self.emit('customer_offer_no_stock', customer_id=cid)
            s['next_customer_at'] = self.now + self.randint('customers', 4, 10)
            return
        variant = candidates[self.randint('customers', 0, len(candidates) - 1)]
        steps = [
            {'kind': 'travel', 'actor': 'customer', 'from': 'street_boundary', 'to': 'front_door', 'speed': 2.4},
            {'kind': 'action', 'actor': 'customer', 'seconds': 0, 'action_id': 'cross_store_threshold', 'effect': 'entered'},
            {'kind': 'travel', 'actor': 'customer', 'to': variant['use_anchor'], 'speed': 2.4},
            {'kind': 'action', 'actor': 'customer', 'seconds': 1.5, 'action_id': variant['usage_kind'], 'effect': 'used'},
            {'kind': 'travel', 'actor': 'customer', 'to': 'customer_wait', 'speed': 2.4},
        ]
        plan = self._plan(steps)
        s['customer'] = {'customer_id': cid, 'order_id': self._id('order', s['customer_count']),
                         'logical_customer_id': self._logical_id('customer', s['customer_count']),
                         'logical_order_id': self._logical_id('order', s['customer_count']),
                         'item_id': self._id('store_item', s['customer_count']), 'variant': _clone(variant),
                         'plan': plan, 'state': 'shopping', 'arrived_at': self.now,
                         'physical_entry_at': None, 'holding_item': False, 'paid': False,
                         'safe_wait_seconds': 0.0, 'used': None}
        s['next_customer_at'] = None
        self.emit('customer_arrived', customer_id=cid, variant=variant['facility_id'])

    def _customer_exit(self, reason):
        customer = self.state['customer']
        if not customer or customer['state'] == 'exiting':
            return
        pos = customer['plan']['actor_positions'].get('customer', self.position('street_boundary'))
        steps = []
        if customer.get('holding_item') and not customer.get('paid'):
            steps.extend([
                {'kind': 'travel', 'actor': 'customer', 'from': pos, 'to': 'customer_return', 'speed': 2.4},
                {'kind': 'action', 'actor': 'customer', 'seconds': 1, 'action_id': 'return_unpaid_item', 'effect': 'return'},
            ])
        steps.append({'kind': 'travel', 'actor': 'customer', 'from': pos, 'to': 'street_boundary', 'speed': 2.4})
        plan = self._plan(steps)
        plan['actor_positions']['customer'] = list(pos)
        customer['plan'] = plan
        customer['state'] = 'exiting'
        customer['exit_reason'] = reason
        self.emit('customer_exit_started', customer_id=customer['customer_id'], reason=reason, paid=customer['paid'])
        task = self.state['player_task']
        if task and task['mode'] == 'checkout' and task['customer_id'] == customer['customer_id']:
            self.state['player_task'] = None

    def _advance_customer(self, dt):
        customer = self.state['customer']
        if not customer:
            return
        if customer['state'] in ('shopping', 'exiting'):
            self._advance_plan(customer['plan'], dt, owner='customer', receipt_prefix=customer['customer_id'])
            if customer['plan']['done']:
                if customer['state'] == 'shopping':
                    customer['state'] = 'waiting'
                    self.emit('customer_waiting', customer_id=customer['customer_id'])
                else:
                    self.emit('customer_exit_completed', customer_id=customer['customer_id'], paid=customer['paid'],
                              position=customer['plan']['actor_positions']['customer'])
                    if customer['paid']:
                        receipt = customer['paid_receipt']
                        use = {'event_id': f"{receipt['event_id']}:facility:FR10", 'customer_id': customer['customer_id'],
                               'facility_id': 'FR10', 'night_id': self.state['night_id'], 'attempt_id': self.state['attempt_id'],
                               'paid_order_receipt': _clone(receipt),
                               'facts': {'actual_use_completed': True, 'normal_customer': True,
                                         'customer_kind': 'normal', 'consumer_registered': True,
                                         'facility_geometry_bound': True, 'actual_use_at': self.now,
                                         'usage_kind': 'paid_customer_exit', 'source_item_id': customer['item_id'],
                                         'order_id': receipt['order_id'], 'use_duration_s': 0,
                                         'route_service_authorized': True, 'source_item_owner_customer': True,
                                         'same_order_service': True, 'exit_boundary_crossed': True,
                                         'actual_exit_position': list(customer['plan']['actor_positions']['customer'])}}
                        self.state['facility_uses'].append(use)
                        self.emit('facility_use_committed', request=use)
                    self.state['customer'] = None
                    if self.state['phase'] == 'BUSINESS' and not self.state['closing']:
                        self.state['next_customer_at'] = self.now + self.randint('customers', 4, 10)
        elif customer['state'] == 'waiting' and self.state['phase'] == 'BUSINESS':
            customer['safe_wait_seconds'] += dt
            if customer['safe_wait_seconds'] >= 45:
                self._customer_exit('safe_wait_patience_expired')

    def _checkout(self, customer, plan):
        if customer.get('paid') or not customer.get('used') or customer['physical_entry_at'] is None:
            raise ValueError('checkout needs real entry, actual use and unpaid order')
        customer['paid'] = True
        used = [customer['used'], {'facility_id': 'FR01', 'actual_use_at': self.now,
                                  'usage_kind': 'checkout', 'source_item_id': customer['item_id']}]
        receipt = {'event_id': customer['order_id'] + ':paid', 'order_id': customer['order_id'],
                   'customer_id': customer['customer_id'], 'night_id': self.state['night_id'],
                   'logical_customer_id': customer['logical_customer_id'],
                   'logical_order_id': customer['logical_order_id'],
                   'attempt_id': self.state['attempt_id'], 'paid': True, 'verified': True, 'normal_customer': True,
                   'payment_kind': 'ordinary_store_sale', 'completed_at': self.now, 'coin': 6, 'xp': 8,
                   'items': [{'sku': customer['variant']['sku'], 'facility_id': customer['variant']['facility_id'],
                              'source_item_id': customer['item_id'], 'quantity': 1}],
                   'facilities_used': _clone(used), 'physical_entry_at': customer['physical_entry_at'],
                   'checkout_anchor': 'cashier', 'actual_action_receipts': _clone(plan['action_receipts'])}
        customer['paid_receipt'] = _clone(receipt)
        self.state['orders'].append(receipt)
        self.state['paid_reward_ids'].append(receipt['event_id'])
        self.emit('order_paid', receipt=receipt)
        for fact in used:
            use = {'event_id': f"{receipt['event_id']}:facility:{fact['facility_id']}",
                   'customer_id': customer['customer_id'], 'facility_id': fact['facility_id'],
                   'night_id': self.state['night_id'], 'attempt_id': self.state['attempt_id'],
                   'paid_order_receipt': _clone(receipt),
                   'facts': {'actual_use_completed': True, 'normal_customer': True,
                             'consumer_registered': True, 'actual_use_at': fact['actual_use_at'],
                             'customer_kind': 'normal', 'facility_geometry_bound': True,
                             'route_service_authorized': True, 'source_item_owner_customer': True,
                             'same_order_service': True, 'progress_complete': True, 'use_duration_s': (plan['action_receipts'][-1]['actual_seconds'] if fact['facility_id'] == 'FR01' else 1.5),
                             'usage_kind': fact['usage_kind'], 'source_item_id': fact['source_item_id'],
                             'order_id': receipt['order_id']}}
            self.state['facility_uses'].append(use)
            self.emit('facility_use_committed', request=use)
        self._offer_stock_job(customer['variant']['facility_id'])
        if self.randint('chores', 0, 2) == 0:
            self._offer_clean(receipt['event_id'])
        self._customer_exit('paid_order_complete')

    def _job_count(self, kind):
        return sum(j['kind'] == kind for j in self.state['jobs'])

    def _offer_job(self, kind, source_id, steps, **extra):
        if any(j['kind'] == kind and j['source_id'] == source_id for j in self.state['jobs']):
            return None
        spec = next(x for x in self.config['chores']['jobs'] if x['kind'] == kind)
        if self._job_count(kind) >= spec['maximum_paid_per_night']:
            return None
        self.state['job_counter'] += 1
        job = {'chore_id': self._id('chore', self.state['job_counter']), 'kind': kind,
               'source_id': source_id, 'steps': steps, 'plan': None, 'status': 'pending',
               'coin': spec['coin'], 'xp': spec['xp'], 'started_at': None, 'carry_state': None, 'carry_pause': None, 'resume_seconds': 0.0, 'resume_receipts': [], **extra}
        self.state['jobs'].append(job)
        self.emit('chore_offered', chore_id=job['chore_id'], chore_kind=kind,
                  source_id=source_id, deferred=self.state['phase'] not in ['BUSINESS', 'RECOVERY'])
        return job

    def _offer_stock_job(self, fid):
        if self.state['stock'][fid] > 1 or any(j['kind'] == 'restock' and j.get('facility_id') == fid and j['status'] != 'completed' for j in self.state['jobs']):
            return
        variant = next(v for v in self.config['customers']['variants'] if v['facility_id'] == fid)
        source_id = self._id('stock_need', f'{fid}-{self._job_count("restock") + 1}')
        self._offer_job('restock', source_id, [
            {'kind': 'travel', 'to': 'storage_shelf'},
            {'kind': 'action', 'role': 'storage_shelf', 'seconds': 1.5, 'action_id': 'take_employer_box'},
            {'kind': 'travel', 'to': variant['use_anchor'], 'speed': 2.4},
            {'kind': 'action', 'role': variant['use_anchor'], 'seconds': 3, 'action_id': 'place_two_store_items'},
        ], facility_id=fid)

    def _offer_clean(self, source_id, *, source_kind='normal_customer_use', biological_owner=None, allow_blood=False):
        types = self.config['chores']['random_floor_types']
        kind = types[self.randint('chores', 0, len(types) - 1)]
        if kind == 'blood' and not allow_blood:
            kind = 'trash'
        if allow_blood:
            kind = 'blood'
        job = self._offer_job('clean', source_id, [
            {'kind': 'travel', 'to': 'mop_station'},
            {'kind': 'action', 'role': 'mop_station', 'seconds': 1, 'action_id': 'take_cleaning_kit'},
            {'kind': 'travel', 'to': 'floor_markers'},
            {'kind': 'action', 'role': 'floor_markers', 'seconds': 3, 'action_id': 'clean_registered_patch'},
            {'kind': 'travel', 'to': 'waste_sort', 'speed': 2.4},
            {'kind': 'action', 'role': 'waste_sort', 'seconds': 1.5, 'action_id': 'bag_registered_waste'},
        ], patch_type=kind, source_kind=source_kind, biological_owner=biological_owner,
           is_player_wound=False, can_activate_blood_conditional_encounters=False)
        if job:
            self.emit('registered_floor_patch_created', chore_id=job['chore_id'], source_id=source_id,
                      patch_type=kind, source_kind=source_kind, biological_owner=biological_owner,
                      is_player_wound=False, can_activate_blood_conditional_encounters=False)
        return job

    def _queue_due_jobs(self):
        if self.state['phase'] not in ['BUSINESS', 'RECOVERY'] or self.state['closing']:
            return
        for index, at in enumerate(self.state['truck_schedule']):
            if at <= self.now and index not in self.state['truck_offered']:
                self.state['truck_offered'].append(index)
                self._offer_job('receive_truck', self._id('truck', index + 1), [
                    {'kind': 'travel', 'to': 'loading_bay'},
                    {'kind': 'action', 'role': 'loading_bay', 'seconds': 2, 'action_id': 'verify_real_delivery'},
                    {'kind': 'travel', 'to': 'receiving', 'speed': 2.4},
                    {'kind': 'action', 'role': 'receiving', 'seconds': 2, 'action_id': 'accept_box'},
                    {'kind': 'travel', 'to': 'storage_shelf', 'speed': 2.4},
                    {'kind': 'action', 'role': 'storage_shelf', 'seconds': 3, 'action_id': 'store_employer_box'},
                ])
        for fid in sorted(self.state['stock']):
            self._offer_stock_job(fid)

    def monster_blackout(self, source_id, monster_id):
        raid = self.state['raid']
        if self.state['phase'] != 'RAID' or not raid or raid['monster_id'] != monster_id:
            return False
        if source_id in self.state['blackout_sources'] or not self.state['power_on']:
            return False
        self.state['blackout_sources'].append(source_id)
        self.state['power_on'] = False
        outage = self._id('outage', len(self.state['blackout_sources']))
        self.state['active_outage_id'] = outage
        self.emit('power_changed', power_on=False, outage_id=outage, actual_monster_source=source_id)
        self._offer_job('restore_power', outage, [
            {'kind': 'travel', 'to': 'power_panel'},
            {'kind': 'action', 'role': 'power_panel', 'seconds': 2, 'action_id': 'reset_breaker'},
        ])
        return True


    def request_tactical_breaker(self):
        # This opt-in combat input is separate from the ordinary-work dispatcher.
        # Travel must already have happened; the method never teleports the player.
        if self.state['phase'] != 'RAID' or self.state['power_on'] or self.state['tactical_breaker']:
            return False
        if _distance(self.state['player_position'], self.position('power_panel')) > 1.25:
            return False
        job = next((j for j in self.state['jobs'] if j['kind'] == 'restore_power' and j['source_id'] == self.state['active_outage_id'] and j['status'] != 'completed'), None)
        if not job:
            return False
        plan = self._plan([{'kind': 'action', 'role': 'power_panel', 'seconds': 1, 'action_id': 'tactical_breaker_reset'}])
        self.state['tactical_breaker'] = {'chore_id': job['chore_id'], 'plan': plan}
        self.emit('tactical_breaker_requested', outage_id=job['source_id'], user_opt_in=True)
        return True

    def start_chore(self, chore_id):
        if self.state['phase'] not in ['BUSINESS', 'RECOVERY'] or self.state['closing']:
            self.state['rejected_commands'].append({'time': self.now, 'command': 'start_chore', 'reason': 'unsafe_phase'})
            return False
        if self.state['player_task']:
            return False
        job = next((j for j in self.state['jobs'] if j['chore_id'] == chore_id), None)
        if not job or job['status'] == 'completed':
            return False
        if job['kind'] == 'restock' and self.state['warehouse_units'] < 2:
            return False
        if job['plan'] is None:
            job['plan'] = self._plan(job['steps'])
            job['started_at'] = self.now
        resume = None
        saved_position = job['plan']['actor_positions']['player']
        if _distance(saved_position, self.state['player_position']) > 1e-7 or (job.get('carry_pause') and job['carry_pause']['status'] == 'stowed'):
            steps = [{'kind': 'travel', 'to': saved_position, 'action_id': 'return_to_paused_job_object'}]
            if job.get('carry_pause') and job['carry_pause']['status'] == 'stowed':
                steps.append({'kind': 'action', 'seconds': 0.5, 'action_id': 'resume_same_original_cargo'})
            resume = self._plan(steps)
        job['status'] = 'active'
        self.state['player_task'] = {'mode': 'job', 'chore_id': chore_id, 'resume_plan': resume}
        self.emit('chore_started_or_resumed', chore_id=chore_id)
        return True

    def _finish_job(self, job):
        if job['status'] == 'completed':
            return False
        if job['kind'] == 'restock':
            if self.state['warehouse_units'] < 2:
                raise ValueError('warehouse stock transaction cannot go negative')
            fid = job['facility_id']
            amount = min(2, 4 - self.state['stock'][fid])
            self.state['warehouse_units'] -= amount
            self.state['stock'][fid] += amount
        elif job['kind'] == 'receive_truck':
            self.state['warehouse_units'] += 8
        elif job['kind'] == 'restore_power':
            if self.state['active_outage_id'] != job['source_id']:
                raise ValueError('breaker job must resolve its same actual outage')
            self.state['power_on'] = True
            self.state['active_outage_id'] = None
            self.emit('power_changed', power_on=True, outage_id=job['source_id'])
        receipt = {'event_id': job['chore_id'] + ':complete', 'night_id': self.state['night_id'],
                   'attempt_id': self.state['attempt_id'], 'chore_id': job['chore_id'], 'kind': job['kind'],
                   'source_id': job['source_id'], 'completed_at': self.now, 'verified': True, 'completed': True,
                   'reward_kind': {'receive_truck': 'receive_delivery', 'restore_power': 'breaker_reset', 'clean': 'clean_floor', 'restock': 'restock'}[job['kind']],
                   'duration_s': round(job['plan']['used_seconds'] + job.get('resume_seconds', 0), 6), 'coin': job['coin'], 'xp': job['xp'],
                   'actual_action_receipts': _clone(job.get('resume_receipts', []) + job['plan']['action_receipts']),
                   'tactical_optional': job.get('tactical_optional', False)}
        if job['kind'] == 'restore_power':
            receipt.update({'outage_id': job['source_id'], 'monster_caused': True})
        if self.state['hands'] and self.state['hands']['chore_id'] == job['chore_id']:
            self.state['hands'] = None
        if job.get('carry_state'):
            job['carry_state']['held'] = False
            job['carry_state']['position'] = list(self.state['player_position'])
        job['status'] = 'completed'
        self.state['chore_receipts'].append(receipt)
        self.state['paid_reward_ids'].append(receipt['event_id'])
        self.emit('chore_completed', receipt=receipt)
        return True

    def _dispatch_player(self):
        s = self.state
        if s['player_task'] or s['phase'] not in ['BUSINESS', 'RECOVERY'] or s['closing']:
            return
        customer = s['customer']
        if customer and customer['state'] == 'waiting':
            s['player_task'] = {'mode': 'checkout', 'customer_id': customer['customer_id'],
                                'plan': self._plan([{'kind': 'travel', 'to': 'cashier'},
                                                   {'kind': 'action', 'seconds': 1.5, 'role': 'cashier', 'action_id': 'normal_checkout'}])}
            return
        priority = {'restore_power': 0, 'receive_truck': 1, 'restock': 2, 'clean': 3}
        candidates = sorted((j for j in s['jobs'] if j['status'] in ['pending', 'paused']), key=lambda j: (priority[j['kind']], j['chore_id']))
        for job in candidates:
            if self.start_chore(job['chore_id']):
                return

    def _pause_player_work(self):
        task = self.state['player_task']
        if task and task['mode'] == 'job':
            job = next(j for j in self.state['jobs'] if j['chore_id'] == task['chore_id'])
            job['status'] = 'paused'
            if self.state['hands'] and self.state['hands']['chore_id'] == job['chore_id']:
                job['carry_state']['position'] = list(self.state['player_position'])
                job['carry_pause'] = {'status': 'pending_setdown', 'source_item_id': job['carry_state']['source_item_id'],
                                      'position': list(self.state['player_position']), 'released_hands': False,
                                      'blocks_navigation': False}
                self.state['pending_setdown'] = job['chore_id']
            self.emit('chore_paused', chore_id=job['chore_id'], position=job['plan']['actor_positions']['player'],
                      remaining=job['plan']['remaining'], step_index=job['plan']['index'])
        self.state['player_task'] = None

    def _enter_omen(self):
        self._pause_player_work()
        self.state['next_customer_at'] = None
        self._phase('OMEN', self.now + 20)
        plan = self._choose_plan()
        self.state['pending_raid_plan'] = plan
        initial = plan.get('initial_actor_positions', {})
        minimum = plan.get('activation_gate', {}).get('minimum_player_distance_tiles', 5)
        positions = [self.position(v) for v in initial.values()]
        safety_steps = []
        if self.state['pending_setdown']:
            safety_steps.append({'kind': 'action', 'seconds': 0.5, 'proficiency': False,
                                 'action_id': 'set_down_store_item', 'chore_id': self.state['pending_setdown']})
        if any(_distance(self.state['player_position'], p) < minimum for p in positions):
            candidates = []
            for role in ['player_start', 'safe_counter', 'front_door', 'staff_desk', 'receiving']:
                candidate = self.position(role)
                if all(_distance(candidate, p) >= minimum for p in positions):
                    candidates.append((self.navigation.route(self.state['player_position'], candidate)['distance'], role))
            if not candidates:
                self.state['error'] = 'no_safe_raid_activation_retreat'
                return
            target = min(candidates)[1]
            safety_steps.append({'kind': 'travel', 'to': target})
            self.emit('omen_safe_retreat_started', target=target, minimum_spawn_distance=minimum)
        if safety_steps:
            self.state['player_task'] = {'mode': 'omen_retreat', 'plan': self._plan(safety_steps)}
        self.state['pending_grid_surge'] = (self.state['night_index'] >= 3 and self.state['grid_surge_count'] < 2 and self.randint('power', 1, 4) == 1)
        self._customer_exit('raid_evacuation')
        self.emit('raid_warning', minimum_seconds=20, customer_exit_required=True,
                  grid_surge_forecast=self.state['pending_grid_surge'])

    def _choose_plan(self):
        unseen = [p for p in self.state['pool'] if p['monster_id'] not in self.state['selected_monsters']]
        candidates = unseen or self.state['pool']
        result = _clone(candidates[self.randint('raids', 0, len(candidates) - 1)])
        self.state['selected_monsters'].append(result['monster_id'])
        return result

    def _start_raid(self):
        if self.state['hands'] is not None:
            raise ValueError('cannot activate a raid with ordinary store cargo occupying hands')
        if self.state['customer'] is not None:
            raise ValueError('cannot spawn a raid before real customer exit')
        plan = self.state['pending_raid_plan']
        if not plan:
            raise ValueError('raid requires its already announced immutable plan')
        minimum = plan.get('activation_gate', {}).get('minimum_player_distance_tiles', 5)
        if any(_distance(self.state['player_position'], self.position(p)) < minimum for p in plan.get('initial_actor_positions', {}).values()):
            return False
        self._pause_player_work()
        self.state['pending_raid_plan'] = None
        raid_id = f"bc01:{self.state['night_id']}:raid:{len(self.state['raids']) + 1}"
        self._phase('RAID')
        raid = {'raid_id': raid_id, 'logical_raid_id': self._logical_id('raid', len(self.state['raids']) + 1), 'monster_id': plan['monster_id'], 'night_id': self.state['night_id'],
                'attempt_id': self.state['attempt_id'], 'started_at': self.now,
                'rule_completed_at': None, 'player_position': list(self.state['player_position']),
                'requires_combat_after_rule': plan.get('requires_combat_after_rule', False),
                'terminal_kind': 'defeated' if plan.get('requires_combat_after_rule', False) else 'left',
                'source_resolution_kind': plan.get('terminal_kind', 'rule_leave'),
                'plan_source': plan.get('source', 'content/map_placements_bc01.json'),
                'actual_action_receipts': [], 'source_plan': plan, 'plan': self._plan(plan['steps']),
                'resolver_called': False, 'combat_remaining': None, 'combat_result': None,
                'terminal_receipt': None, 'unresolved_reason': None,
                'grid_surge_due': self.now + 6 if self.state['pending_grid_surge'] else None,
                'grid_surge_warned': False, 'grid_surge_done': False}
        raid['plan']['actor_positions'].update({actor: self.position(pos) for actor, pos in plan.get('initial_actor_positions', {}).items()})
        self.state['raid'] = raid
        self.emit('raid_started', raid_id=raid_id, logical_raid_id=raid['logical_raid_id'], monster_id=raid['monster_id'], ordinary_cargo_in_hands=False,
                  player_position=list(self.state['player_position']), initial_actor_positions=plan.get('initial_actor_positions', {}))
        callback = self.callbacks.get('on_raid_started')
        if callback:
            callback(self, _clone(raid))

    def _terminal_from_leave_plan(self, raid):
        plan = raid['source_plan']
        # Catalog admission asserts these are physical leave sequences, not HP unlocks.
        if plan.get('requires_combat_after_rule') or not any(step.get('real_exit_observed') for step in plan.get('steps', [])):
            return None
        return {'event_id': raid['raid_id'] + f":attempt:{self.state['attempt_id']}:terminal", 'night_id': self.state['night_id'],
                'attempt_id': self.state['attempt_id'], 'raid_id': raid['raid_id'],
                'monster_id': raid['monster_id'], 'terminal_kind': raid['terminal_kind'],
                'source': 'root_lifecycle', 'verified': True, 'actual_terminal': True,
                'physical_leave_script_completed': True, 'main_rule_completed': True,
                'action_receipt_ids': [r['event_id'] for r in raid['actual_action_receipts']]}

    def complete_raid(self, receipt):
        raid = self.state['raid']
        if self.state['phase'] != 'RAID' or not raid or not raid['plan']['done'] or raid['rule_completed_at'] is None:
            return False
        for field in ['night_id', 'attempt_id', 'raid_id', 'monster_id', 'terminal_kind']:
            if receipt.get(field) != raid.get(field):
                return False
        if not receipt.get('verified') or not receipt.get('actual_terminal') or receipt.get('source') != 'root_lifecycle':
            return False
        if raid['requires_combat_after_rule'] and receipt.get('hp_after') != 0:
            return False
        if raid['terminal_receipt'] is not None:
            return False
        raid['terminal_receipt'] = _clone(receipt)
        raid['ended_at'] = self.now
        raid['player_position'] = list(self.state['player_position'])
        self.state['raids'].append(_clone(raid))
        self.emit('raid_ended', raid_id=raid['raid_id'], monster_id=raid['monster_id'], receipt=receipt)
        actual_f13_body = raid['monster_id'] == 'F13' and receipt.get('hp_after') == 0 and receipt['terminal_kind'] == 'defeated'
        self._offer_clean(receipt['event_id'],
                          source_kind='post_raid_biological_body' if actual_f13_body else 'post_raid_ordinary_residue',
                          biological_owner=raid['raid_id'] if actual_f13_body else None, allow_blood=actual_f13_body)
        self.state['raid'] = None
        if not self.state['closing']:
            self._phase('RECOVERY', self.now + self.randint('raids', 35, 45))
        return True

    def _advance_raid(self, dt):
        raid = self.state['raid']
        if not raid:
            return
        tactical = self.state['tactical_breaker']
        if tactical:
            tplan = tactical['plan']
            self._advance_plan(tplan, dt, owner='tactical', receipt_prefix=tactical['chore_id'] + ':tactical')
            if tplan['done']:
                job = next(j for j in self.state['jobs'] if j['chore_id'] == tactical['chore_id'])
                job['plan'] = tplan
                job['tactical_optional'] = True
                self._finish_job(job)
                self.state['tactical_breaker'] = None
            # Monster-owned waits/travel and already running automatic tower combat
            # continue; the same player cannot perform two manual actions at once.
            if not raid['plan']['done']:
                step = raid['plan']['steps'][raid['plan']['index']]
                if step.get('actor', 'player') == 'player':
                    return
        if not raid['plan']['done']:
            self._advance_plan(raid['plan'], dt, owner='raid', receipt_prefix=raid['raid_id'] + f":attempt:{self.state['attempt_id']}")
            self.state['player_position'] = list(raid['plan']['actor_positions']['player'])
            if not raid['plan']['done']:
                return
            raid['rule_completed_at'] = self.now
            raid['actual_action_receipts'] = _clone(raid['plan']['action_receipts'])
            raid['player_position'] = list(self.state['player_position'])
            self.emit('raid_rule_plan_completed', raid_id=raid['raid_id'], requires_combat=raid['requires_combat_after_rule'])
            if not raid['requires_combat_after_rule']:
                receipt = self._terminal_from_leave_plan(raid)
                if receipt is None or not self.complete_raid(receipt):
                    raid['unresolved_reason'] = 'leave_route_terminal_observation_missing'
                return
        if not raid['resolver_called']:
            raid['resolver_called'] = True
            resolver = self.callbacks.get('resolve_raid')
            context = {'now': self.now, 'navigation': self.navigation, 'night_id': self.state['night_id'],
                       'attempt_id': self.state['attempt_id'], 'power_on': self.state['power_on'],
                       'action_duration_factor': self.state['action_duration_factor'],
                       'player_move_speed': self.state['player_move_speed']}
            result = resolver(_clone(raid), context) if resolver else None
            if not result:
                raid['unresolved_reason'] = 'combat_terminal_required_no_valid_resolver'
                self.emit('raid_unresolved', raid_id=raid['raid_id'], reason=raid['unresolved_reason'])
                return
            duration = float(result.get('duration_s', -1))
            if duration < 0 or not math.isfinite(duration) or not result.get('terminal_receipt'):
                raise ValueError('resolver must give a finite actual combat duration and terminal receipt')
            raid['combat_result'] = _clone(result)
            raid['combat_remaining'] = duration
            self.emit('finite_combat_reference_started', raid_id=raid['raid_id'], duration_s=duration,
                      combat_log=result.get('combat_log', []))
            return
        if raid['combat_remaining'] is not None:
            raid['combat_remaining'] = max(0.0, raid['combat_remaining'] - dt)
            if raid['combat_remaining'] <= 1e-9:
                result = raid['combat_result']
                if result.get('end_player_position') is not None:
                    self.state['player_position'] = self.position(result['end_player_position'])
                if not self.complete_raid(result['terminal_receipt']):
                    raid['unresolved_reason'] = 'invalid_combat_terminal_receipt'

    def _advance_player(self, dt):
        if self.state['phase'] == 'RAID':
            self._advance_raid(dt)
            return
        task = self.state['player_task']
        if task and task['mode'] == 'omen_retreat' and self.state['phase'] == 'OMEN':
            plan = task['plan']
            self._advance_plan(plan, dt, owner='omen', receipt_prefix=self._id('omen_retreat', len(self.state['raids']) + 1))
            self.state['player_position'] = list(plan['actor_positions']['player'])
            if plan['done']:
                self.emit('omen_safe_retreat_completed', position=list(self.state['player_position']))
                self.state['player_task'] = None
            return
        if not task or self.state['phase'] not in ['BUSINESS', 'RECOVERY']:
            return
        if task['mode'] == 'checkout':
            customer = self.state['customer']
            if not customer or customer['customer_id'] != task['customer_id'] or customer['state'] != 'waiting':
                self.state['player_task'] = None
                return
            plan = task['plan']
            self._advance_plan(plan, dt, owner='checkout', receipt_prefix=customer['order_id'])
            self.state['player_position'] = list(plan['actor_positions']['player'])
            if plan['done']:
                self._checkout(customer, plan)
                self.state['player_task'] = None
        elif task['mode'] == 'job':
            job = next(j for j in self.state['jobs'] if j['chore_id'] == task['chore_id'])
            resume = task.get('resume_plan')
            if resume and not resume['done']:
                self._advance_plan(resume, dt, owner='job', receipt_prefix=job['chore_id'] + ':resume')
                self.state['player_position'] = list(resume['actor_positions']['player'])
                if resume['done']:
                    job['resume_seconds'] += resume['used_seconds']
                    job['resume_receipts'].extend(_clone(resume['action_receipts']))
                    task['resume_plan'] = None
                return
            plan = job['plan']
            self._advance_plan(plan, dt, owner='job', receipt_prefix=job['chore_id'])
            self.state['player_position'] = list(plan['actor_positions']['player'])
            if job.get('carry_state') and job['carry_state']['held']:
                job['carry_state']['position'] = list(self.state['player_position'])
            if plan['done']:
                self._finish_job(job)
                self.state['player_task'] = None

    def _close(self):
        if self.state['closing']:
            return
        self.state['closing'] = True
        self.state['raid_due'] = None
        self.state['next_customer_at'] = None
        if self.state['phase'] != 'RAID':
            self._pause_player_work()
        self._customer_exit('night_closed')
        self.emit('night_arrivals_closed', actual_time=self.now)

    def _maybe_settle(self):
        s = self.state
        if not s['closing'] or s['raid'] or s['customer'] or s['settled']:
            return False
        s['settled'] = True
        s['player_task'] = None
        self._phase('SETTLED')
        bonus = min(40, 2 * min(12, len(s['orders'])) + 2 * min(8, len(s['chore_receipts'])))
        self.emit('automatic_settlement_ready', event_id=self._id('settlement', 1), base_wage=80,
                  performance_bonus=bonus, ticket=1, manager_or_key_ceremony=False)
        return True

    def advance(self, seconds, *, paused=False):
        if paused or seconds <= 0 or self.state['settled']:
            return
        remaining = seconds
        while remaining > 1e-9 and not self.state['settled']:
            dt = min(0.25, remaining)
            before_tick = self.callbacks.get('before_tick')
            if before_tick:
                before_tick(self, dt)
            old_time = self.now
            phase_before = self.state['phase']
            self.state['now'] = round(self.now + dt, 9)
            if not self.state['player_alive']:
                self.state['error'] = 'player_defeated'
                return
            if phase_before == 'RAID':
                self.state['active_raid_seconds'] += dt
                self.state['eligible_survival_seconds'] += max(0.0, min(self.now, 720) - min(old_time, 720))
            # An announced electrical pulse commits before this tick's actions.
            raid = self.state['raid']
            if raid and raid.get('grid_surge_due') is not None:
                due = raid['grid_surge_due']
                if not raid['grid_surge_warned'] and self.now >= due - 3:
                    raid['grid_surge_warned'] = True
                    self.emit('grid_surge_warning', raid_id=raid['raid_id'], seconds_until_pulse=max(0, due-self.now))
                if not raid['grid_surge_done'] and self.now >= due:
                    raid['grid_surge_done'] = True
                    if self.monster_blackout(raid['raid_id'] + ':BC01_GRID_SURGE', raid['monster_id']):
                        self.state['grid_surge_count'] += 1
            # World actions from the interval complete before its boundary changes phase.
            self._advance_customer(dt)
            self._advance_player(dt)
            if self.now >= 720:
                self._close()
            s = self.state
            if not s['closing']:
                if s['phase'] == 'BUSINESS' and s['raid_due'] is not None and self.now >= s['raid_due']:
                    if len(s['raids']) < 4 and self.now <= 620:
                        self._enter_omen()
                    else:
                        s['raid_due'] = None
                if s['phase'] == 'OMEN' and self.now >= s['phase_deadline']:
                    if s['customer'] is None and s['player_task'] is None:
                        extra = self.now - s['phase_started_at'] - 20
                        s['omen_extensions'].append(round(extra, 6))
                        self._start_raid()
                    elif self.now - s['phase_started_at'] > 35:
                        s['error'] = 'customer_evacuation_exceeded_admitted_geometry_budget'
                        return
                if s['phase'] == 'RECOVERY' and self.now >= s['phase_deadline']:
                    self._phase('BUSINESS')
                    due = self.now + self.randint('raids', 60, 80)
                    s['raid_due'] = due if due <= 620 and len(s['raids']) < 4 else None
                    s['next_customer_at'] = self.now + self.randint('customers', 3, 8)
                self._queue_due_jobs()
                if s['phase'] == 'BUSINESS' and s['next_customer_at'] is not None and self.now >= s['next_customer_at']:
                    self._spawn_customer()
                self._dispatch_player()
            self._maybe_settle()
            remaining -= dt

    def snapshot(self):
        return _clone(self.state)

    @classmethod
    def from_snapshot(cls, snapshot, navigation=None, callbacks=None):
        if snapshot.get('version') != 'BC01':
            raise ValueError('wrong snapshot schema')
        obj = cls.__new__(cls)
        obj.config = json.loads(CONTRACT.read_text())
        obj.navigation = navigation or _default_navigation()
        obj.callbacks = callbacks or {}
        obj.state = _clone(snapshot)
        return obj

    def report(self):
        s = self.state
        phases = []
        for event in s['events']:
            if event['kind'] == 'phase_changed':
                phases.append({'at': event['time'], 'phase': event['current']})
        summary = {'night_id': s['night_id'], 'seed': s['seed'], 'finished_at': self.now,
                   'settled': s['settled'], 'status': 'settled' if s['settled'] else 'unresolved',
                   'paid_orders': len(s['orders']), 'offered_customers': s['customer_count'],
                   'completed_chores': len(s['chore_receipts']), 'resolved_raids': len(s['raids']),
                   'order_coin': sum(x['coin'] for x in s['orders']),
                   'order_xp': sum(x['xp'] for x in s['orders']),
                   'chore_coin': sum(x['coin'] for x in s['chore_receipts']),
                   'chore_xp': sum(x['xp'] for x in s['chore_receipts']),
                   'active_raid_seconds': round(s['active_raid_seconds'], 6),
                   'survival_eligible_seconds': round(s['eligible_survival_seconds'], 6),
                   'ordinary_work_during_raid_seconds': s['ordinary_work_during_raid_seconds'],
                   'player_travel_tiles': round(s['route_distance_player'], 6),
                   'customer_travel_tiles': round(s['route_distance_customers'], 6),
                   'manual_work_seconds': round(s['work_seconds'], 6), 'phases': phases,
                   'grid_surge_count': s['grid_surge_count'],
                   'orders_are_simulation_outputs': True, 'full_game_ai_implemented': False,
                   'pending_chores': sum(j['status'] != 'completed' for j in s['jobs']),
                   'error': s['error']}
        return {'summary': summary, 'events': _clone(s['events']), 'orders': _clone(s['orders']),
                'facility_uses': _clone(s['facility_uses']), 'chores': _clone(s['chore_receipts']),
                'raids': _clone(s['raids']), 'snapshot': self.snapshot()}


def run_night(seed=1, navigation=None, *, action_duration_factor=1.0,
              player_move_speed=3.0, encounter_pool=None, callbacks=None,
              night_index=1, night_id=None, attempt_id=1, max_seconds=1800):
    director = Director(seed, navigation, action_duration_factor=action_duration_factor,
                        player_move_speed=player_move_speed, encounter_pool=encounter_pool,
                        callbacks=callbacks, night_index=night_index, night_id=night_id,
                        attempt_id=attempt_id)
    while not director.state['settled'] and director.now < max_seconds:
        director.advance(0.25)
        raid = director.state['raid']
        if director.state['error'] or (raid and raid.get('unresolved_reason')):
            break
    return director.report()


if __name__ == '__main__':
    result = run_night()
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
