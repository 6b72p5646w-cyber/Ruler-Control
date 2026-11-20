#!/usr/bin/env python3
"""BC02 prerequisite registry, typed source transactions and finite counterexamples.

This is not an implementation of 105 continuous monster AIs.  It never makes a
map adapter ready, creates a historical receipt because an encounter was drawn,
or converts a main-rule receipt into HP=0.  A manifest component is a binding
bundle; the runtime adapter must still validate every member/count written in
its original_manifest and the collision/time contract.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads((ROOT / 'content/encounter_prerequisites_bc02.json').read_text())


@lru_cache(maxsize=1)
def encounter_index() -> dict[str, dict]:
    return {r['monster_id']: r for r in registry()['encounters']}


def source_action_graph(monster_id: str) -> dict:
    """Return declared dependency edges; not a navigation or attack simulation."""
    r = encounter_index()[monster_id]
    nodes = copy.deepcopy(r['source_nodes'] + r['action_graph'] + [r['response_node'], r['terminal_node']])
    by_id = {n['id']: n for n in nodes}
    # Physical predicates are external typed observations, not synthesized by
    # a topological pass.  Their adapters remain explicitly unimplemented.
    def inputs(n):
        return n.get('requires', []) + [d for branch in n.get('requires_any', []) for d in branch]
    edges = [(d, n['id']) for n in nodes for d in inputs(n) if d in by_id]
    internal_inputs = {a for a, _ in edges}
    outputs = {b for _, b in edges}
    return {'monster_id': monster_id, 'nodes': nodes, 'edges': edges,
            'unproduced_semantic_inputs': sorted({d for n in nodes for d in inputs(n) if d not in by_id}),
            'physical_predicates_are_external': True,
            'source_ids': [n['id'] for n in nodes if n['id'] not in outputs],
            'terminal_id': r['terminal_node']['id']}


def dependency_witness(monster_id: str, omitted_sources=()) -> dict:
    """Check structural source reachability only, with external semantic guards.

    Starting leaves represent adapter observations required by the specification;
    this function does not claim those observations occurred in a playable map.
    Missing source tests are useful because they detect an accidental edge that
    allows root admission or a mechanism goal without its provenance dependency.
    """
    g = source_action_graph(monster_id)
    by_id = {n['id']: n for n in g['nodes']}
    omitted = set(omitted_sources)
    ready, pending = set(), set(by_id)
    order = []
    while pending:
        progressed = False
        for k in sorted(pending):
            n = by_id[k]
            if k in omitted:
                continue
            req = {x for x in n.get('requires', []) if x in by_id}
            alternatives = [{x for x in branch if x in by_id} for branch in n.get('requires_any', [])]
            if req <= ready and (not alternatives or any(branch <= ready for branch in alternatives)):
                ready.add(k)
                order.append(k)
                pending.remove(k)
                progressed = True
        if not progressed:
            break
    return {'monster_id': monster_id, 'terminal_reachable': g['terminal_id'] in ready,
            'topological_order': order, 'blocked_nodes': sorted(pending),
            'scope': 'declared_dependency_graph_not_actual_world'}


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    producer: str
    created_at: float
    subject_ids: tuple[str, ...]
    source_ref: str
    expires_at: float | None = None
    claim_only: bool = False

    def valid_at(self, now: float) -> bool:
        return not self.claim_only and bool(self.subject_ids) and self.created_at <= now and (self.expires_at is None or now < self.expires_at)


@dataclass
class PhysicalObject:
    object_id: str
    original_id: str
    owner: str
    location: str
    source_receipt_id: str
    kind: str = 'critical_original'
    quantity: int = 1
    reserved_by: str | None = None
    consumed: bool = False
    retired: bool = False


@dataclass
class World:
    now: float = 0
    objects: dict[str, PhysicalObject] = field(default_factory=dict)
    receipts: dict[str, Receipt] = field(default_factory=dict)
    module_receipts: dict[str, Receipt] = field(default_factory=dict)
    environment_receipts: dict[str, Receipt] = field(default_factory=dict)
    committed_roots: set[str] = field(default_factory=set)
    rewards: dict[str, dict] = field(default_factory=dict)
    replacement_keys: set[tuple[str, str]] = field(default_factory=set)
    source_claims_rejected: int = 0
    installed_modules: dict[str,str] = field(default_factory=dict)
    installed_large_module_id: str | None = None
    business_started: bool = False

    def add_actual_receipt(self, receipt: Receipt):
        """Only an adapter's actual event receipt enters this internal store.

        An SDK/UI must never expose this as a player input. The reference can
        reject impossible timestamps, empty subjects, claims, and ID rewrites;
        it cannot prove that an external engine correctly measured an event.
        """
        if not receipt.valid_at(self.now):
            self.source_claims_rejected += 1
            raise ValueError('Not an actual current source receipt')
        old = self.receipts.get(receipt.receipt_id)
        if old and old != receipt:
            raise ValueError('Immutable receipt ID cannot be rewritten')
        self.receipts[receipt.receipt_id] = receipt

    def install_module(self, monster_id: str, receipt_id: str):
        case = encounter_index()[monster_id]
        module_id = case['module_binding']['id']
        r = self.receipts.get(receipt_id)
        if self.business_started:
            raise ValueError('Module installation frozen after business opens')
        if not r or r.producer != 'actual_installed_module_and_routes' or module_id not in r.subject_ids or not r.valid_at(self.now):
            raise ValueError('Actual matching installation and route proof required')
        if case['module_binding']['installation_class']=='large_floor_module':
            if self.installed_large_module_id and self.installed_large_module_id != module_id:
                raise ValueError('Only one physically installed large module per night')
            self.installed_large_module_id = module_id
        self.installed_modules[module_id] = receipt_id

    def add_object(self, obj: PhysicalObject):
        if obj.object_id in self.objects or obj.quantity <= 0:
            raise ValueError('Object IDs and positive physical counts are unique')
        source = self.receipts.get(obj.source_receipt_id)
        if not source or not source.valid_at(self.now) or obj.original_id not in source.subject_ids:
            raise ValueError('Object requires a matching actual source receipt')
        if any(o.original_id == obj.original_id and not o.retired for o in self.objects.values()):
            raise ValueError('Original object cannot exist in two physical copies')
        self.objects[obj.object_id] = obj

    def move_original(self, object_id, source, destination, actor, seconds, *, path_receipt: Receipt):
        o = self.objects[object_id]
        if o.location != source or o.consumed or o.retired:
            raise ValueError('Same original must physically be at source')
        if seconds < 0 or path_receipt.producer != 'actual_body_clear_route' or not path_receipt.valid_at(self.now):
            raise ValueError('Missing actual movement route')
        if object_id not in path_receipt.subject_ids or actor not in path_receipt.subject_ids:
            raise ValueError('Route must bind this item and actor')
        self.now += seconds
        o.location = destination

    def replace_support_tool(self, old_id, service_id, replacement_id, source_receipt_id):
        o = self.objects[old_id]
        if o.kind != 'reusable_support_tool' or o.reserved_by or o.consumed:
            raise ValueError('Critical original/finite item/reserved item cannot be replaced')
        key = (old_id, service_id)
        if key in self.replacement_keys:
            return False
        source = self.receipts.get(source_receipt_id)
        if not source or source.producer != 'safe_phase_recovery_service' or old_id not in source.subject_ids:
            raise ValueError('Replacement needs actual safe recovery service')
        self.add_object(PhysicalObject(replacement_id, replacement_id, o.owner, 'service_cabinet', source_receipt_id,
                                       kind='reusable_support_tool'))
        o.retired = True
        self.replacement_keys.add(key)
        return True


class SpawnTransaction:
    """Atomic reservation/physical delivery/root-commit boundary.

    Runtime requires both an adapter capability receipt and actual module proof.
    A reference-mode transaction exercises provenance/atomicity without lifting
    the real runtime gate.
    """
    def __init__(self, world: World, monster_id: str, logical_root_id: str):
        self.world = world
        self.case = encounter_index()[monster_id]
        self.monster_id = monster_id
        self.root_id = logical_root_id
        self.state = 'NEW'
        self.history_bindings: dict[str, str] = {}
        self.original_ids: list[str] = []
        self.delivered_ids: list[str] = []
        self.module_receipt_id: str | None = None
        self.environment_bindings: dict[str, str] = {}
        self.arrival_effect_bindings: dict[str, str] = {}
        self.reserved_at: float | None = None
        self.actor_id: str | None = None
        self.normal_customer = False
        self.committed_at: float | None = None

    def reserve(self, *, objects: list[str], history: dict[str, str], module_receipt_id: str,
                environment: dict[str, str]):
        if self.state != 'NEW' or self.root_id in self.world.committed_roots:
            raise ValueError('Root cannot reserve twice')
        if len(objects) != len(set(objects)) or not objects:
            raise ValueError('A physical original bundle is required; duplicate IDs forbidden')
        required_hist = [n for n in self.case['source_nodes'] if n['kind'] == 'immutable_prior_receipt']
        for h in required_hist:
            receipt = self.world.receipts.get(history.get(h['id'], ''))
            if not receipt or receipt.producer != h['producer'] or not receipt.valid_at(self.world.now):
                raise ValueError('Missing actual prior history: ' + h['id'])
        for receipt_id in history.values():
            receipt = self.world.receipts.get(receipt_id)
            if receipt and not set(receipt.subject_ids).intersection(objects):
                raise ValueError('Historical receipt must bind original manifest subjects')
        for object_id in objects:
            o = self.world.objects.get(object_id)
            if not o or o.reserved_by or o.consumed or o.retired:
                raise ValueError('Original unavailable: ' + object_id)
        mod = self.world.receipts.get(module_receipt_id)
        if not mod or mod.producer != 'actual_installed_module_and_routes' or not mod.valid_at(self.world.now):
            raise ValueError('Module and routes not actually available')
        if self.world.installed_modules.get(self.case['module_binding']['id']) != module_receipt_id:
            raise ValueError('Candidate module is not in actual installed night plan')
        if self.case['module_binding']['id'] not in mod.subject_ids:
            raise ValueError('Wrong module binding')
        for binding in self.case['environment_bindings']:
            if not binding['required_for_admission']:
                continue
            cid = binding['condition_id']
            e = self.world.receipts.get(environment.get(cid, ''))
            expected = cid if binding['condition_must_be_true_at_admission'] else 'registered_condition_adapter:' + cid
            if not e or e.producer != expected or not e.valid_at(self.world.now):
                raise ValueError('Missing live source or registered condition adapter: ' + cid)
        # All predicates checked before any mutable stock reservation.
        for object_id in objects:
            self.world.objects[object_id].reserved_by = self.root_id
        self.history_bindings = dict(history)
        self.original_ids = list(objects)
        self.module_receipt_id = module_receipt_id
        self.environment_bindings = {b['condition_id']:environment[b['condition_id']] for b in self.case['environment_bindings'] if b['required_for_admission']}
        self.reserved_at = self.world.now
        self.state = 'RESERVED'

    def deliver_existing(self, object_id: str, destination: str, receipt_id: str):
        if self.state not in ('RESERVED', 'MATERIALIZED') or object_id not in self.original_ids:
            raise ValueError('Only reserved originals may be delivered')
        o = self.world.objects[object_id]
        r = self.world.receipts.get(receipt_id)
        if not r or r.producer != 'actual_visible_delivery' or object_id not in r.subject_ids or not r.valid_at(self.world.now):
            raise ValueError('Delivery is a physical event, not a candidate flag')
        o.location = destination
        if object_id not in self.delivered_ids:
            self.delivered_ids.append(object_id)
        self.state = 'MATERIALIZED'

    def bind_arrival_effect(self, source_node_id: str, receipt_id: str):
        if self.state not in ('RESERVED', 'MATERIALIZED'):
            raise ValueError('Reserve originals before visible arrival operations')
        node = next((n for n in self.case['source_nodes'] if n['id'] == source_node_id
                     and n['kind'] == 'arrival_effect_receipt'), None)
        r = self.world.receipts.get(receipt_id)
        if not node or not r or r.producer != node['producer'] or not r.valid_at(self.world.now):
            raise ValueError('No matching actual arrival operation')
        if self.reserved_at is None or r.created_at < self.reserved_at:
            raise ValueError('Current arrival operation cannot use a past unrelated event')
        if not set(r.subject_ids).intersection(self.original_ids + ([self.actor_id] if self.actor_id else [])):
            raise ValueError('Arrival operation must bind reserved originals or same actor')
        self.arrival_effect_bindings[source_node_id] = receipt_id

    def materialize_history(self, *args, **kwargs):
        raise ValueError('Selection/delivery cannot manufacture previous actions or injuries')

    def stage_actor(self, actor_id: str, arrival_receipt_id: str, *, actor_class='ANOMALOUS_VISITOR'):
        if self.state not in ('RESERVED', 'MATERIALIZED'):
            raise ValueError('Reserve all sources first')
        r = self.world.receipts.get(arrival_receipt_id)
        if not r or r.producer != 'actual_actor_arrival' or actor_id not in r.subject_ids or not r.valid_at(self.world.now):
            raise ValueError('Actor did not actually arrive')
        if actor_class in ('NORMAL_CUSTOMER', 'COWORKER', 'PLAYER', 'MANAGER'):
            raise ValueError('Anomalous root must not overwrite a normal human identity')
        self.actor_id = actor_id
        self.state = 'MATERIALIZED'

    def commit(self, *, runtime=False, adapter_receipt_id=None, hands_clear=True, ordinary_customers_safe=True):
        if self.state != 'MATERIALIZED' or not self.actor_id or not hands_clear or not ordinary_customers_safe:
            raise ValueError('Arrival, free hands, safe ordinary NPCs required')
        if self.root_id in self.world.committed_roots:
            raise ValueError('Root already committed')
        # Existing stationary originals need not be moved. They still must exist
        # and be exclusively reserved; a delivery event cannot clone them.
        for oid in self.original_ids:
            o = self.world.objects[oid]
            if o.reserved_by != self.root_id or o.consumed or o.retired:
                raise ValueError('Original lost before commit')
        required_arrival = {n['id'] for n in self.case['source_nodes'] if n['kind'] == 'arrival_effect_receipt'}
        if not required_arrival <= set(self.arrival_effect_bindings):
            raise ValueError('Visible arrival effects must actually happen before root commit')
        for rid in [self.module_receipt_id, *self.history_bindings.values(), *self.arrival_effect_bindings.values(), *self.environment_bindings.values()]:
            r = self.world.receipts.get(rid or '')
            if not r or not r.valid_at(self.world.now):
                raise ValueError('Source expired or module invalidated before commit')
        if runtime:
            a = self.world.receipts.get(adapter_receipt_id or '')
            if not self.case['module_binding']['client_adapter_ready'] or not a or a.producer != 'validated_runtime_adapter':
                raise ValueError('Design reference is not a validated client adapter')
        self.world.committed_roots.add(self.root_id)
        self.committed_at = self.world.now
        self.state = 'COMMITTED_REFERENCE' if not runtime else 'COMMITTED_RUNTIME'
        return {'logical_root_id': self.root_id, 'runtime': runtime, 'actor_id': self.actor_id}

    def abort(self):
        if self.state.startswith('COMMITTED'):
            raise ValueError('Committed root uses explicit root resolution, not preflight abort')
        for oid in self.original_ids:
            o = self.world.objects[oid]
            if o.reserved_by == self.root_id:
                o.reserved_by = None
        self.state = 'ABORTED'
        return {oid: self.world.objects[oid].location for oid in self.original_ids}

    def settle(self, *, main_rule_verified=False, required_pools_zero=False, physical_terminal=False,
               passive=False, source_receipt_id: str):
        if not self.state.startswith('COMMITTED'):
            raise ValueError('Uncommitted candidate cannot settle')
        receipt = self.world.receipts.get(source_receipt_id)
        if not receipt or not receipt.valid_at(self.world.now) or self.root_id not in receipt.subject_ids:
            raise ValueError('Terminal needs same-root actual world receipt')
        kind = self.case['terminal_node']['resolution_type']
        if kind == 'rule_leave':
            if not main_rule_verified or not physical_terminal or receipt.producer != 'actual_rule_leave':
                raise ValueError('Rule leave requires its real physical terminal')
        elif not required_pools_zero or receipt.producer != 'actual_required_pools_defeated':
            raise ValueError('Main rule never substitutes actual HP0')
        key = self.root_id + '/terminal'
        if key in self.world.rewards:
            return self.world.rewards[key]
        # Passive cases must be recognized by the admission adapter, not by a
        # player button. This reference deliberately defaults S38 to no reward.
        no_reward = passive or self.monster_id == 'S38'
        result = {'coins': 0 if no_reward else 12, 'spirit': 0 if no_reward else 4 + 2 * bool(main_rule_verified),
                  'normal_customer_facility_buff': False, 'root_id': self.root_id}
        self.world.rewards[key] = result
        for oid in self.original_ids:
            if self.world.objects[oid].reserved_by == self.root_id:
                self.world.objects[oid].reserved_by = None
        return result


def blood_admission(*, now: float, injury_created: float, injury_source: str, trace_created: list[float],
                    omen_seconds: float = 20, response_route_seconds: float = 24,
                    needs_live_trace=True, standard_previous_F21=False) -> dict:
    if injury_source not in ('BUSINESS_E003_GLASS_CONTACT', 'F21_GLASS_FAULT'):
        return {'admitted': False, 'reason': 'not_a_real_permitted_wound_source'}
    if standard_previous_F21:
        return {'admitted': False, 'reason': '115_second_standard_gap_exceeds_90_second_wound'}
    if omen_seconds < 20 or response_route_seconds < 0 or now < injury_created:
        raise ValueError('Invalid world clock budget')
    required_remaining = omen_seconds + response_route_seconds + 6 + 3
    wound_ok = injury_created + 90 - now >= required_remaining
    trace_ok = not needs_live_trace or bool(trace_created) and all(now + omen_seconds < t + 30 for t in trace_created)
    return {'admitted': bool(wound_ok and trace_ok), 'wound_remaining': injury_created + 90 - now,
            'required_remaining': required_remaining, 'trace_alive_at_commit': bool(trace_ok),
            'never_extended': True}


class FilamentLedger:
    """S30 eight-second danger is separate from two persistent original fibers."""
    def __init__(self, root_id: str):
        self.root_id = root_id
        self.fibers = {root_id + ':silk:' + str(n): {'location': 'on_body', 'danger_until': None} for n in (1, 2)}
        self.sealed = False

    def lay(self, now: float, locations: list[str]):
        if len(locations) != 2 or len(set(locations)) != 2:
            raise ValueError('Two distinct real line segments required')
        for f, loc in zip(self.fibers.values(), locations):
            if f['location'] == 'on_body':
                f.update(location=loc, danger_until=now + 8)

    def recover(self, fiber_id: str, now: float):
        f = self.fibers[fiber_id]
        if f['location'] in ('on_body', 'sealed'):
            raise ValueError('Fiber is not physically available at an exposed/source spool slot')
        if f['location'] == 'spool':
            return False
        f.update(location='spool', danger_until=None)
        return True

    def seal(self):
        if self.sealed:
            return False
        if not all(f['location'] == 'spool' for f in self.fibers.values()):
            raise ValueError('Cannot seal missing original fibers')
        for f in self.fibers.values():
            f['location'] = 'sealed'
        self.sealed = True
        return True

    def active_danger(self, fiber_id, now):
        f = self.fibers[fiber_id]
        return f['danger_until'] is not None and now < f['danger_until']


def paid_customer_device_support(actor_class: str, paid: bool, ordinary_order: bool, actual_device_use: bool) -> bool:
    return actor_class == 'NORMAL_CUSTOMER' and paid and ordinary_order and actual_device_use
