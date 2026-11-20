#!/usr/bin/env python3
"""Bounded S40/S43 response reference, not map navigation or production AI.

The caller proves physical identity, geometry and source facts.  This model only
executes the supplied lawful polyline, original work durations and one root's
response ledger. World combat damage remains explicit calls, as in MD01.
"""
from copy import deepcopy
from fractions import Fraction as F
from math import hypot, isfinite

from md01_reference import LifeState


def q(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a duration')
    answer = value if isinstance(value, F) else F(str(value))
    return answer


def point(value):
    if len(value) != 2 or not all(isfinite(float(v)) for v in value):
        raise ValueError('invalid point')
    return tuple(float(v) for v in value)


class ResponseReference:
    runtime_integrated = False
    runtime_enabled = False

    def __init__(self, record, root_id, attempt_id, actor_id, position, deadline,
                 *, maturities=(), timed_states=None, expected_source_id=None):
        self.life = LifeState(deepcopy(record), root=root_id)
        self.species = record['id']
        self.attempt_id, self.actor_id = attempt_id, actor_id
        self.position = point(position)
        self.deadline = q(deadline)
        self.plan = None
        self.phase = 'unstarted'
        self.protected = False
        self.actor_present = True
        self.source_hostility_revoked = False
        self.expected_source_id = expected_source_id
        self.source_open_receipt_id = None
        self.protection_used = F(0)
        self.route_done = F(0)
        self.work_done = F(0)
        self.latch_done = F(0)
        self.item_owner = 'tray' if self.species == 'S40' else None
        self.external_exit_at = None
        self.trace = []
        self.maturities = [dict(x, due=q(x['due']), amount=q(x['amount']), applied=False)
                           for x in maturities]
        if (len({x['id'] for x in self.maturities}) != len(self.maturities)
                or any(x['amount'] <= 0 or x['due'] < 0 for x in self.maturities)):
            raise ValueError('invalid paid maturity ledger')
        self.timed_states = {k:q(v) for k,v in (timed_states or {}).items()}
        self.rejected_reason = None

    @property
    def now(self):
        return self.life.now

    def _reject(self, reason):
        self.rejected_reason = reason
        return False

    def _proof_valid(self, proof):
        required = ('physical_verified', 'route_verified', 'position_verified',
                    'deadline_verified', 'hostility_verified', 'player_outside')
        if proof.get('evidence_origin') != 'world_adapter' or not all(proof.get(k) is True for k in required):
            return False
        if (proof.get('root_id') != self.life.root or proof.get('attempt_id') != self.attempt_id
                or proof.get('actor_id') != self.actor_id or proof.get('monster_id') != self.species
                or q(proof.get('original_deadline', -1)) != self.deadline
                or point(proof.get('actual_actor_position', (float('nan'),0))) != self.position):
            return False
        if not all(proof.get(k) for k in ('plan_id', 'route_id', 'destination_id', 'bound_source_id')):
            return False
        if self.species == 'S40':
            return proof.get('sound_muted') is True and proof.get('original_paper_in_tray') is True
        if self.species == 'S43':
            return (proof.get('external_mall_open') is True
                    and proof.get('exit_boundary_verified') is True
                    and q(proof.get('external_ack_elapsed_s', 0)) >= 3)
        return False

    def accept_source_open_receipt(self, proof):
        """Consume the actual S43 source fact independently of route admission.

        expected_source_id belongs to the already admitted root's world binding;
        a caller cannot invent a new source merely by putting its ID in a UI
        claim. The finite model still relies on the world adapter for evidence.
        """
        if (self.species != 'S43' or self.life.kind != 'rule_leave' or self.life.hp_max <= 0
                or self.life.state in ('left','defeated') or self.phase in ('complete','failed')
                or not self.expected_source_id or proof.get('normal_human') is True):
            return False
        try:
            valid = (proof.get('evidence_origin') == 'world_adapter'
                     and proof.get('physical_verified') is True
                     and proof.get('source_receipt_verified') is True
                     and proof.get('external_mall_open') is True
                     and proof.get('root_id') == self.life.root
                     and proof.get('attempt_id') == self.attempt_id
                     and proof.get('actor_id') == self.actor_id
                     and proof.get('monster_id') == self.species
                     and proof.get('bound_source_id') == self.expected_source_id
                     and q(proof.get('observed_world_time', -1)) == self.now
                     and q(proof.get('external_ack_elapsed_s', 0)) >= 3)
        except (ValueError,TypeError,ZeroDivisionError):
            valid = False
        if not valid:
            return False
        if not self.source_hostility_revoked:
            self.source_hostility_revoked = True
            self.source_open_receipt_id = self.expected_source_id
            self.trace.append({'event':'actual_source_open_revokes_hostility','at':str(self.now),
                               'cancel_owned_hostile_volumes':True})
        return True

    def enter(self, proof):
        """Only a verified actual response may acquire this root's protection."""
        if (self.species not in ('S40', 'S43') or self.life.kind != 'rule_leave'
                or self.life.hp_max <= 0 or proof.get('normal_human') is True):
            return self._reject('not_registered_rule_leave')
        # Source state is an independently owned fact. A missing route, current
        # suppression or insufficient response time must not undo an actual
        # open-mall receipt that already revokes this actor's hostility.
        if self.species == 'S43' and not self.accept_source_open_receipt(proof):
            return self._reject('missing_actual_open_source_receipt')
        if self.phase in ('complete','failed','awaiting_latch','latching') or self.protected:
            return self._reject('not_enterable')
        if self.life.state != 'active' or proof.get('control_active') is True:
            return self._reject('wait_for_original_control')
        try:
            valid = self._proof_valid(proof)
        except (ValueError, TypeError, ZeroDivisionError):
            valid = False
        if not valid:
            return self._reject('missing_actual_evidence')
        if self.plan is None:
            try:
                path = tuple(point(p) for p in proof['path'])
                if len(path) < 2 or path[0] != self.position:
                    return self._reject('invalid_route_start')
                distances = tuple(q(hypot(b[0]-a[0], b[1]-a[1])) for a,b in zip(path,path[1:]))
                distance = sum(distances, F(0))
                if distance < 0 or (distance == 0 and self.species == 'S43'):
                    return self._reject('exit_requires_actual_boundary_route')
                speed = q(self.life.record['stats']['move_speed'])
                route_seconds = distance/speed
                work_seconds = F(5,2) if self.species == 'S40' else F(0)
                latch_seconds = F(1) if self.species == 'S43' else F(0)
                if self.now+route_seconds+work_seconds+latch_seconds > self.deadline:
                    return self._reject('insufficient_original_time')
                plan = {k:proof[k] for k in ('plan_id','route_id','destination_id','bound_source_id')}
                plan.update(path=path, distances=distances, speed=speed,
                            route_seconds=route_seconds, work_seconds=work_seconds,
                            latch_seconds=latch_seconds,
                            protection_budget=route_seconds+work_seconds)
            except (KeyError,ValueError,TypeError,ZeroDivisionError):
                return self._reject('invalid_route')
            self.plan = plan
        else:
            if any(proof.get(k) != self.plan[k] for k in ('plan_id','route_id','destination_id','bound_source_id')):
                return self._reject('cannot_rebind_plan')
            if tuple(point(p) for p in proof.get('path', ())) != self.plan['path']:
                return self._reject('cannot_replace_route')
            remaining = self.plan['route_seconds']-self.route_done+self.plan['work_seconds']-self.work_done
            if (remaining+self.plan['latch_seconds'] > self.deadline-self.now
                    or self.protection_used+remaining > self.plan['protection_budget']):
                return self._reject('cannot_refresh_budget_or_deadline')
        self.protected = True
        self.phase = 'travel' if self.route_done < self.plan['route_seconds'] else 'collect'
        self.trace.append({'event':'response_enter_or_resume','at':str(self.now),
                           'protected_spent':str(self.protection_used),'cancel_owned_hostile_volumes':True})
        return True

    def interrupt(self, reason='actual_precondition_lost'):
        if not self.protected:
            return False
        self.protected = False
        self.phase = 'interrupted'
        self.trace.append({'event':'response_interrupted','at':str(self.now),'reason':reason})
        return True

    def attack_allowed(self):
        return (self.actor_present and self.life.state == 'active'
                and not self.protected and not self.source_hostility_revoked
                and self.phase not in ('complete','failed'))

    def damage(self, raw, channel='physical', **kwargs):
        if self.protected or not self.actor_present or self.source_hostility_revoked:
            return F(0)
        return self.life.apply_damage(raw, channel, **kwargs)

    def poison_tick(self, seconds=1):
        if q(seconds) <= 0:
            raise ValueError('invalid poison interval')
        return self.damage(self.life.poison*q(seconds)/2, 'spiritual')

    def _world(self, duration):
        self.life.advance(duration)
        for record in self.maturities:
            if not record['applied'] and record['due'] <= self.now:
                record['applied'] = True
                if self.life.state not in ('left','defeated'):
                    self.life.poison += record['amount']
        self.timed_states = {k:v for k,v in self.timed_states.items() if v > self.now}

    def _place_on_route(self):
        distance_left = self.route_done*self.plan['speed']
        for a,b,length in zip(self.plan['path'],self.plan['path'][1:],self.plan['distances']):
            if distance_left <= length and length:
                ratio=float(distance_left/length)
                self.position=(a[0]+(b[0]-a[0])*ratio,a[1]+(b[1]-a[1])*ratio)
                return
            distance_left-=length
        self.position=self.plan['path'][-1]

    def _finish(self):
        self.protected=False
        self.phase='complete'
        self.actor_present=False
        receipt={'verified':True,'root':self.life.root,'id':self.species+'_rule_complete:'+self.attempt_id}
        assert self.life.complete_rule(receipt)
        self.maturities=[]
        self.timed_states={}
        self.trace.append({'event':'actual_rule_terminal','at':str(self.now)})

    def start_latch(self, proof):
        if self.phase != 'awaiting_latch' or self.species != 'S43':
            return self._reject('actor_has_not_exited')
        required=('actual_control_position','held_input','door_binding_verified')
        if (proof.get('evidence_origin') != 'world_adapter'
                or proof.get('root_id') != self.life.root or proof.get('attempt_id') != self.attempt_id
                or proof.get('door_id') != self.plan['destination_id']
                or not all(proof.get(k) is True for k in required)):
            return self._reject('missing_actual_latch_action')
        if self.now+1 > self.deadline:
            return self._reject('late_latch')
        self.phase='latching'
        self.latch_done=F(0)
        return True

    def cancel_latch(self):
        if self.phase != 'latching':
            return False
        self.phase='awaiting_latch'
        self.latch_done=F(0)
        return True

    def elapse(self, seconds):
        """Actual world time; caller interrupts immediately if evidence fails.

        No poison damage is synthesized here. Explicit world damage ticks must
        still call poison_tick/damage, including while a response is protected.
        """
        remaining=q(seconds)
        if remaining < 0:
            raise ValueError('negative time')
        while remaining > 0:
            if self.phase in ('complete','failed'):
                self._world(remaining)
                return
            stage_left = remaining
            if self.protected:
                stage_left=(self.plan['route_seconds']-self.route_done if self.phase=='travel'
                            else self.plan['work_seconds']-self.work_done)
            elif self.phase=='latching':
                stage_left=1-self.latch_done
            delta=min(remaining,stage_left,max(F(0),self.deadline-self.now))
            if self.protected:
                self.protection_used+=delta
                if self.phase=='travel':
                    self.route_done+=delta
                    self._place_on_route()
                else:
                    self.work_done+=delta
            elif self.phase=='latching':
                self.latch_done+=delta
            self._world(delta)
            remaining-=delta
            # Real completion at an exact deadline precedes timeout.
            if self.protected and self.phase=='travel' and self.route_done==self.plan['route_seconds']:
                if self.species=='S40':
                    self.phase='collect'
                else:
                    self.actor_present=False
                    self.protected=False
                    self.phase='awaiting_latch'
                    self.external_exit_at=self.now
            if self.protected and self.phase=='collect' and self.work_done==self.plan['work_seconds']:
                self.item_owner=self.actor_id
                self._finish()
            if self.phase=='latching' and self.latch_done==1:
                self._finish()
            if self.phase!='complete' and self.now>=self.deadline:
                self.protected=False
                self.phase='failed'
                self.trace.append({'event':'original_deadline_without_terminal','at':str(self.now),
                                   'needs_original_timeout_handler':True})
            if delta==0 and self.phase not in ('complete','failed','collect','awaiting_latch'):
                raise AssertionError('nonprogressing reference state')

    def clone_saved_state(self):
        """Finite snapshot equivalent only; not a production save serializer."""
        return deepcopy(self)
