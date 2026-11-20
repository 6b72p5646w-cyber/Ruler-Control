#!/usr/bin/env python3
"""BC01 routed-night/first-week design integration, never a full game client.

Actual reference customer movement issues receipts; fixtures consume those
receipts, the player owns HP, and one ledger owns all provisional rewards.
Combat is explicitly the conditional post-rule T02 finite-damage scenario.
"""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path

from bc01_campaign_reference import (CONTRACT, ROOT, ElectricGate, NightLedger,
    Player, digest, level_for_xp, level_stats, logical_night, make_combat_resolver,
    movement_speed, new_campaign, open_night, settle_night)
from bc01_director_reference import Director
from bc01_facility_reference import FacilitiesBC01
from bc01_map_reference import StoreMap, encounter_catalog


class JointNight:
    def __init__(self, seed=1, *, night_index=1, night_id=None, attempt_id=1, level=1,
                 tower_node='T02', navigation=None, encounter_pool=None):
        self.navigation = navigation or StoreMap()
        self.night_id = night_id or json.dumps(['joint', 1, night_index], separators=(',', ':'))
        self.attempt_id = attempt_id
        self.tower_node = tower_node
        self.player = Player(level, level_stats(level)['max_hp'])
        self.facilities = FacilitiesBC01(self.night_id, attempt_id, seed, design_simulation=True)
        self.electric = ElectricGate()
        self.ledger = NightLedger(self.night_id, attempt_id)
        self.temporary_traps = {}
        self.consumer_log = []
        self.facility_use_results = []
        self.handled_requests = []
        self.director = Director(seed, self.navigation, night_index=night_index, night_id=self.night_id,
                                 attempt_id=attempt_id, action_duration_factor=level_stats(level)['manual_duration_factor'],
                                 encounter_pool=encounter_pool if encounter_pool is not None else encounter_catalog(night_index),
                                 callbacks=self.callbacks())

    def callbacks(self):
        return {'on_event': self.on_event, 'before_tick': self.before_tick,
                'resolve_raid': make_combat_resolver(self.navigation, self.tower_node)}

    def clock_to(self, now):
        if now > self.facilities.state['now'] + 1e-9 and self.facilities.state['phase'] != 'ENDED':
            result = self.facilities.actual_world_tick(f'joint-world:{now:.9f}', now, self.player.alive,
                                                        eligibility_cutoff=720.)
            if not result['ok']:
                raise ValueError('facility world clock rejected: ' + result['reason'])
        self.electric.advance(now)
        self.consume_requests()

    def consume_requests(self):
        for request in self.facilities.pending_requests():
            request_id = request['request_id']
            if request_id in self.handled_requests:
                self.facilities.acknowledge(request_id)
                continue
            kind = request['request_type']
            if kind == 'spawn_temporary_trap':
                continue  # creation requires geometry + capacity acceptance, below
            log = {'at': self.facilities.state['now'], 'request_id': request_id, 'kind': kind}
            if kind == 'hp_regen_interval':
                budget = self.player.max_hp * request['fraction_max_hp_per_second'] * request['actual_alive_raid_seconds']
                log['potential_hp'] = budget
                log['actual_hp'] = self.player.heal(request_id, budget)
            elif kind == 'payout':
                ordinal = int(request_id.rsplit(':', 1)[1])
                receipt = {'event_id': request_id, 'night_id': self.night_id, 'attempt_id': self.attempt_id,
                           'verified': True, 'source': 'FR10', 'unit_index': ordinal,
                           'eligible_alive_raid_seconds': 15, 'completed_at': self.facilities.state['now']}
                log['reward'] = self.ledger.apply('survival', receipt)
                if not log['reward']['applied']:
                    raise ValueError('survival source/ledger mismatch: ' + str(log['reward']))
            elif kind == 'resource_restore':
                if request['resource'] != 'stamina':
                    raise ValueError('unregistered resource request')
                # No fabricated consumer in standard night: only a real FR13 use
                # could issue this, and the finite stamina owner clamps it.
                maximum = 50 + .5 * self.player.energy
                amount = maximum * request.get('fraction_max', request.get('fraction', .1))
                before = self.player.stamina
                self.player.stamina = min(maximum, self.player.stamina + amount)
                log['actual_stamina'] = self.player.stamina - before
            elif kind == 'remove_temporary_trap':
                self.temporary_traps.pop(request['actual_instance_id'], None)
            elif kind == 'electric_power_gate':
                self.electric.change_power(request_id, self.facilities.electric_overload_allowed(), self.facilities.state['now'])
            elif kind not in ('buff_started', 'buff_source_enabled', 'buff_ended'):
                # A target effect requires a real collision/LOS world consumer;
                # do not silently acknowledge unimplemented combat interactions.
                raise ValueError('world consumer missing for ' + kind)
            self.consumer_log.append(log)
            self.handled_requests.append(request_id)
            self.facilities.acknowledge(request_id)

    def on_event(self, event):
        self.clock_to(event['time'])
        kind = event['kind']
        if kind == 'order_paid':
            if not self.ledger.apply('order', event['receipt'])['applied']:
                raise ValueError('actual order failed unified ledger')
        elif kind == 'chore_completed':
            result = self.ledger.apply('chore', event['receipt'])
            if not result['applied']:
                raise ValueError('actual chore failed unified ledger: ' + str(result))
        elif kind == 'facility_use_committed':
            result = self.facilities.customer_use(**event['request'])
            self.facility_use_results.append({'at': event['time'], 'facility_id': event['request']['facility_id'],
                                              'event_id': event['request']['event_id'], **result})
            if not result['ok']:
                raise ValueError('real service rejected: ' + result['reason'])
        elif kind == 'raid_started':
            result = self.facilities.raid_started(event['raid_id'])
            if not result['ok']:
                raise ValueError('raid support activation rejected')
        elif kind == 'raid_ended':
            if not self.ledger.apply('root', event['receipt'])['applied']:
                raise ValueError('actual terminal failed unified ledger')
            self.facilities.raid_ended(event['raid_id'])
        elif kind == 'power_changed':
            self.facilities.power_changed(f"{event['outage_id']}:{event['power_on']}", 'MAIN', event['power_on'])
        elif kind == 'automatic_settlement_ready':
            self.facilities.night_ended()
        self.consume_requests()

    def before_tick(self, director, dt):
        self.clock_to(director.now)
        modifiers = self.facilities.active_modifiers()
        manual = min([1.] + [e['reward']['value'] for e in modifiers if e['reward']['kind'] == 'manual_interaction_multiplier'])
        has_haste = any(e['reward']['kind'] == 'move_speed_bonus' for e in modifiers)
        has_carry = any(e['reward']['kind'] == 'carrying_move_speed_bonus' for e in modifiers)
        director.state['action_duration_factor'] = max(.6, level_stats(self.player.level)['manual_duration_factor'] * manual)
        director.state['player_move_speed'] = movement_speed(facility_haste=has_haste)
        director.state['player_carry_multiplier'] = max(1.08 if has_haste else 1., 1.1 if has_carry else 1.)
        director.state['player_alive'] = self.player.alive
        if director.state['phase'] == 'RAID':
            self.try_trap(director)

    def try_trap(self, director):
        if self.facilities.state['active_trap']:
            return
        candidates = []
        actors = [director.state['player_position']]
        raid = director.state['raid']
        if raid:
            actors += list(raid['plan'].get('actor_positions', {}).values())
        occupied = [cell for trap in self.temporary_traps.values() for cell in trap['placement']['cells']]
        for shape in ((1, 1), (1, 2)):
            candidates += self.navigation.safe_trap_placements(footprint=shape, occupied=occupied, active_actors=actors,
                                                               object_count=len(self.temporary_traps), footprint_count=len(occupied))
        nav_revision = digest({'obstacles': self.navigation.obstacles, 'occupied': sorted(occupied)})
        result = self.facilities.propose_trap(candidates, object_count=len(self.temporary_traps),
                                             footprint_cells=len(occupied), nav_revision=nav_revision,
                                             safe_current_world=True)
        request = result.get('request')
        if not request:
            return
        # Candidate proof and world mutation occur in one same-frame reference
        # transaction; source token is consumed only after this acceptance.
        instance_id = 'world:' + request['request_id']
        placement = request['placement']
        valid = placement in candidates and all(tuple(cell) not in {tuple(c) for c in occupied} for cell in placement['cells'])
        ack = self.facilities.trap_placement_ack(request['request_id'], valid, actual_instance_id=instance_id,
                                                current_nav_revision=nav_revision, actual_safe_world_placement=valid,
                                                total_objects_after=len(self.temporary_traps) + 1,
                                                total_footprint_after=len(occupied) + len(placement['cells']))
        if ack['ok']:
            self.temporary_traps[instance_id] = deepcopy(ack['trap'])
            self.consumer_log.append({'at': director.now, 'kind': 'actual_safe_temporary_trap_placed',
                                      'instance_id': instance_id, 'variant': request['variant']['id'],
                                      'placement': placement, 'inventory_granted': 0})

    def advance(self, seconds):
        self.director.advance(seconds)
        self.clock_to(self.director.now)

    def run(self, max_seconds=1800):
        while not self.director.state['settled'] and self.director.now < max_seconds:
            self.advance(.25)
            raid = self.director.state['raid']
            if self.director.state['error'] or (raid and raid.get('unresolved_reason')):
                break
        return self.report()

    def snapshot(self):
        return {'night_id': self.night_id, 'attempt_id': self.attempt_id, 'tower_node': self.tower_node,
                'player': self.player.export(), 'director': self.director.snapshot(),
                'facilities': self.facilities.snapshot(), 'electric': self.electric.export(),
                'ledger': self.ledger.export(), 'temporary_traps': deepcopy(self.temporary_traps),
                'consumer_log': deepcopy(self.consumer_log), 'facility_use_results': deepcopy(self.facility_use_results),
                'handled_requests': list(self.handled_requests)}

    @classmethod
    def restore(cls, snapshot, navigation=None):
        obj = cls.__new__(cls)
        obj.navigation = navigation or StoreMap()
        obj.night_id, obj.attempt_id = snapshot['night_id'], snapshot['attempt_id']
        obj.tower_node = snapshot['tower_node']
        obj.player = Player(**deepcopy(snapshot['player']))
        obj.facilities = FacilitiesBC01.restore(snapshot['facilities'], design_simulation=True)
        obj.electric = ElectricGate.restore(snapshot['electric'])
        obj.ledger = NightLedger.restore(snapshot['ledger'])
        for key in ('temporary_traps', 'consumer_log', 'facility_use_results', 'handled_requests'):
            setattr(obj, key, deepcopy(snapshot[key]))
        obj.director = Director.from_snapshot(snapshot['director'], obj.navigation, callbacks=obj.callbacks())
        return obj

    def campaign_attempt(self):
        snapshot = self.snapshot()
        result = {'world_clock': {'owner_ref': 'director.now'}, 'player': snapshot['player'],
                  'director': snapshot['director'], 'facilities': snapshot['facilities'], 'electric': snapshot['electric'],
                  'pending_reward_ledger': snapshot['ledger'],
                  'projectiles': [], 'status_effects': {'owner_ref': 'facilities.buffs', 'temporary_traps': snapshot['temporary_traps']},
                  'mechanism_objects': {'owner_ref': 'director.raid.plan', 'scope': 'finite original-object action receipt scenario'},
                  'joint_adapter': {k: snapshot[k] for k in ('tower_node', 'consumer_log', 'facility_use_results', 'handled_requests')}}
        for key, path in CONTRACT['persistence']['reference_owner_index'].items():
            result.setdefault(key, {'owner_ref': path})
        return result

    @classmethod
    def from_campaign(cls, campaign, navigation=None):
        attempt = campaign['attempt']
        adapter = attempt['joint_adapter']
        snapshot = {'night_id': logical_night(campaign), 'attempt_id': campaign['attempt_id'],
                    'tower_node': adapter['tower_node'], 'player': attempt['player'],
                    'director': attempt['director'], 'facilities': attempt['facilities'],
                    'electric': attempt['electric'], 'ledger': attempt['pending_reward_ledger'],
                    'temporary_traps': attempt['status_effects']['temporary_traps'],
                    'consumer_log': adapter['consumer_log'], 'facility_use_results': adapter['facility_use_results'],
                    'handled_requests': adapter['handled_requests']}
        return cls.restore(snapshot, navigation)

    def report(self):
        result = self.director.report()
        kinds = Counter(row['kind'] for row in self.consumer_log)
        result.update({'ledger': self.ledger.export(), 'player': self.player.export(),
                       'facility_use_results': deepcopy(self.facility_use_results), 'consumer_log': deepcopy(self.consumer_log)})
        result['summary'].update({'level_at_open': self.player.level, 'tower_node': self.tower_node,
                                  'facility_uses_accepted': sum(x['ok'] for x in self.facility_use_results),
                                  'facility_uses_rejected': sum(not x['ok'] for x in self.facility_use_results),
                                  'survival_coin': self.ledger.counts['survival'],
                                  'temporary_traps_placed': kinds['actual_safe_temporary_trap_placed'],
                                  'power_off_events': sum(e['kind'] == 'power_changed' and not e['power_on'] for e in result['events']),
                                  'hp_regen_potential': round(sum(e.get('potential_hp', 0) for e in self.consumer_log), 6),
                                  'hp_restored_actual': round(sum(e.get('actual_hp', 0) for e in self.consumer_log), 6),
                                  'provisional_coin': self.ledger.coin, 'provisional_spirit': self.ledger.spirit,
                                  'provisional_xp': self.ledger.xp,
                                  'enemy_attack_AI_simulated': False,
                                  'combat_condition': 'post-rule legal exposed target on map-verified T02 firing loop'})
        return result


def prepare_strategy(state, strategy):
    """Explicit actual catalogue purchases, no assumed nightly tax/resupply."""
    purchases = []
    free_tower = state['week']['defense_instances'][0]
    if strategy in ('defense', 'balanced'):
        target = 'T02.A' if free_tower['node'] == 'T02' else 'T02.A1' if free_tower['node'] == 'T02.A' and strategy == 'defense' else None
        if target:
            from td05_reference import nodes
            node = next(n for n in nodes(json.loads((ROOT / 'content/tower_defense_td05.json').read_text())) if n['id'] == target)
            cost = node['cost']
            if state['week']['coin'] >= cost['coin'] and state['week']['spirit'] >= cost['spirit']:
                state['week']['coin'] -= cost['coin']
                state['week']['spirit'] -= cost['spirit']
                free_tower['node'] = target
                purchases.append({'kind': 'paid_tower_upgrade', 'node': target, **cost})
    if strategy == 'balanced' and 'Q09' not in state['permanent']['equipment']:
        q09 = next(q for q in json.loads((ROOT / 'content/equipment_eq01.json').read_text())['equipment'] if q['id'] == 'Q09')
        cost = q09['acquisition']['shop_price_week_coin']
        if state['week']['coin'] >= cost:
            state['week']['coin'] -= cost
            state['permanent']['equipment'].append('Q09')
            purchases.append({'kind': 'paid_personal_equipment', 'item': 'Q09', 'coin': cost, 'spirit': 0})
    for index, receipt in enumerate(purchases):
        state['week']['preparation_receipts'].append({'id': f'{logical_night(state)}:prepare:{index}', **receipt})
    return purchases


def run_week(seed=1, strategy='free', navigation=None):
    navigation = navigation or StoreMap()
    state = new_campaign(f'bc01-week-{seed}-{strategy}')
    nights = []
    for night_index in range(1, 8):
        state['phase'] = 'pre_shift'
        purchases = prepare_strategy(state, strategy)
        opening_coin, opening_spirit = state['week']['coin'], state['week']['spirit']
        node = state['week']['defense_instances'][0]['node']
        joint = JointNight(seed * 1009 + night_index, night_index=night_index,
                           night_id=logical_night(state), attempt_id=state['attempt_id'] + 1,
                           level=level_for_xp(state['permanent']['total_xp']), tower_node=node, navigation=navigation)
        open_night(state, joint.campaign_attempt())
        result = joint.run()
        if not result['summary']['settled']:
            raise ValueError('unresolved reference night: ' + json.dumps(result['summary']))
        # Successful reference scenario only; no input assumes an order count.
        settle = settle_night(state, joint.ledger, actual_time=joint.director.now, player_alive=joint.player.alive,
                              san_safe=joint.player.san > 0, no_active_panic=True,
                              all_roots_terminal=joint.director.state['raid'] is None,
                              customers_outside=joint.director.state['customer'] is None)
        nights.append({'night': night_index, 'purchases': purchases, 'opening_coin_after_purchase': opening_coin,
                       'opening_spirit_after_purchase': opening_spirit, **result['summary'],
                       'settlement': settle['receipt'], 'wallet_after': deepcopy(state['week']),
                       'permanent_xp_after': state['permanent']['total_xp'],
                       'next_level': level_for_xp(state['permanent']['total_xp'])})
    return {'seed': seed, 'strategy': strategy, 'nights': nights,
            'week_score': state['permanent']['week_scores'][-1], 'next_week_wallet': state['week']['coin'],
            'permanent_xp': state['permanent']['total_xp'], 'next_level': level_for_xp(state['permanent']['total_xp']),
            'equipment_kept': state['permanent']['equipment'], 'tickets': state['permanent']['tickets'],
            'all_orders_derived_from_movement_and_service': True,
            'scope': 'conditional successful finite encounter routes, not a survival probability or full AI simulation'}


if __name__ == '__main__':
    print(json.dumps(JointNight(seed=2, night_index=7).run()['summary'], ensure_ascii=False, indent=2))
