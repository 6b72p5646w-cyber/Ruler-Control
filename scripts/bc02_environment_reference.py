#!/usr/bin/env python3
"""BC02 real source, geometry and lifecycle reference (not client enemy AI).

Public catalogue helpers are intentionally independent of the finite simulator.
EnvironmentWorld charges actual body-clear routes and world time for deployment;
selecting/reserving a monster never creates water, a mirror, a wound or history.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import copy
import json
import math
from pathlib import Path
import random

from bc01_map_reference import StoreMap, _segment_rect_intersects

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-8


def contract():
    return json.loads((ROOT / 'content/environment_conditions_bc02.json').read_text())


def condition_index():
    return {c['condition_id']: c for c in contract()['conditions']}


def consumer_bindings(monster_id):
    return copy.deepcopy(next(c['uses'] for c in contract()['monster_consumers'] if c['monster_id'] == monster_id))


def _centre(cell):
    return (cell[0] + .5, cell[1] + .5)


def _cell(point):
    return (math.floor(point[0]), math.floor(point[1]))


def _neighbours(cell):
    x, y = cell
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


@dataclass
class Actor:
    id: str
    position: tuple
    speed: float = 3.0
    layer: str = 'ground'
    carried: str | None = None
    bleeding_incident: str | None = None
    travelled_since_mark: float = 0.0


@dataclass
class Deployment:
    id: str
    item_id: str
    actor_id: str
    root_id: str
    kind: str
    target: tuple
    config: dict
    path: list
    route_distance: float
    action_seconds: float
    started_at: float
    edge_index: int = 0
    action_elapsed: float = 0.0
    status: str = 'travelling'
    receipt_id: str | None = None
    walked_distance: float = 0.0


@dataclass
class Transition:
    id: str
    root_id: str
    monster_id: str
    mode: str
    origin: tuple
    destination: tuple
    source_ids: tuple
    path: list
    warning_s: float
    transit_s: float
    recovery_s: float
    started_at: float
    locked_player_position: tuple
    status: str = 'warning'
    reason: str | None = None
    commits: int = 0
    recovery_until: float = 0.0
    phase_event_count: int = 0
    physical_ground_midpath_hits: int = 0


class EnvironmentWorld:
    """Finite world with actual routes, source ownership, graph topology and TTLs.

    A supplied real event (glass contact, root terminal, power fault) is an
    integration boundary; this module does not pretend to simulate the entire
    economic, combat, injury, or encounter-director engine.
    """
    def __init__(self, *, phase='BUSINESS', closed_doors=(), player_position=None):
        self.data = contract()
        self.regions = {x['id']: x for x in self.data['wet_regions']}
        self.closed_doors = set(closed_doors)
        self.nav = StoreMap(closed_doors=self.closed_doors)
        self.now = 0.0
        self.phase = phase
        self.paused = False
        self.power = {'MAIN': True, 'TASK_ISOLATED': True, 'PASSIVE_THERMAL': True}
        start = tuple(player_position or self.nav.position('player_start'))
        if not self.nav.point_clear(start):
            raise ValueError('player must have real body-clear starting position')
        self.actors = {'PLAYER': Actor('PLAYER', start)}
        self.items = {}
        self.deployments = {}
        self.receipts = []
        self.sources = {}
        self.surfaces = {}
        self.nodes = {}
        self.lamps = {}
        self.warm_sources = {}
        self.wounds = {}
        self.traces = {}
        self.cleanup_stains = {}
        self.hazards = {}
        self.roots = {}
        self.transitions = {}
        self.sounds = {}
        self.mirror_curtain_closed = False
        self.cleaned_episodes = set()
        self.blood_reservations = {}
        self._serial = 0
        # The fixed convex mirror is an actual map asset, not a phase endpoint.
        self.surfaces['FIXED_CONVEX_MIRROR'] = {
            'id': 'FIXED_CONVEX_MIRROR', 'item_id': 'MAP_STORE:ATT02:mirror_surface',
            'position': tuple(self.nav.position('convex_mirror')), 'normal': (0., 1.), 'reflectivity': .85,
            'phase_port': False, 'covered': False, 'broken': False,
            'root_id': 'world', 'layer': 'ground', 'version': 1,
            'source_ref': 'content/maps.json#/scenes/0/fixed_attachments/1',
            'source_event_id': self._receipt('MAP_ASSET_REGISTERED', 'world', 'MAP_STORE:ATT02:mirror_surface')}

    def _id(self, stem):
        self._serial += 1
        return f'{stem}:{self._serial}'

    def _receipt(self, event, root_id, item_id, **fields):
        rid = self._id('receipt')
        self.receipts.append({'id': rid, 'event': event, 'root_id': root_id,
                              'object_instance_id': item_id, 'world_at': self.now, **fields})
        return rid

    def reserve_root(self, root_id, monster_id):
        if root_id in self.roots:
            raise ValueError('root IDs cannot be reused')
        if monster_id not in {r['monster_id'] for r in self.data['monster_consumers']}:
            raise ValueError('unknown monster')
        self.roots[root_id] = {'monster_id': monster_id, 'state': 'reserved',
                              'body': None, 'layer': None, 'cooldown_until': 0.0}

    def declare_payload(self, item_id, *, kind, root_id='world', entry=(15.5, 32.5)):
        """Actual new arrival payload at a visible entrance; does not install it.

        The encounter adapter must have committed a declared-arrival manifest.
        No historical work receipt, employee wound or prior sale is accepted as
        a payload kind. Existing original items must use their existing IDs.
        """
        if kind not in {'water_module', 'mirror', 'lamp', 'phase_anchor', 'glass_return',
                        'sapling_return', 'warmed_pack'}:
            raise ValueError('not a legitimate declared payload kind')
        if item_id in self.items:
            raise ValueError('duplicate original item')
        if tuple(entry) not in {(15.5, 32.5), (27.5, -3.5)}:
            raise ValueError('arrival must use a real registered entrance')
        if not self.nav.point_clear(entry):
            raise ValueError('blocked entrance')
        actor_id = self._id('PORTER')
        self.actors[actor_id] = Actor(actor_id, tuple(entry), carried=item_id)
        receipt = self._receipt('DECLARED_PAYLOAD_ARRIVED', root_id, item_id,
                                entry=list(entry), kind=kind)
        self.items[item_id] = {'id': item_id, 'kind': kind, 'root_id': root_id,
                               'position': tuple(entry), 'held_by': actor_id,
                               'arrival_receipt': receipt, 'installed': False,
                               'removed': False, 'version': 1}
        return item_id

    def begin_deployment(self, item_id, *, kind, destination=None, **config):
        if self.phase not in {'SETUP', 'BUSINESS', 'OMEN', 'RECOVERY'}:
            raise ValueError('ordinary deployment cannot become a raid chore')
        item = self.items[item_id]
        if item['removed'] or item['installed']:
            raise ValueError('source item unavailable')
        if any(t.item_id == item_id and t.status in {'travelling', 'installing'} for t in self.deployments.values()):
            raise ValueError('one original item cannot be in two transactions')
        if kind != item['kind']:
            raise ValueError('cannot transmute a payload into another source')
        if kind=='phase_anchor':
            root=self.roots.get(item['root_id'])
            if not root or root['monster_id']!='S22' or config.get('subtype')!='same_three_task_dark_nodes':
                raise ValueError('finite reference deploys S22 physical nodes; other anchor subtypes require their actual original-item/history adapters')
        if kind == 'water_module':
            region = self.regions[config['region_id']]
            destination = _centre(region['source_cell'])
        if destination is None:
            raise ValueError('physical destination required')
        actor_id = item['held_by']
        if actor_id is None:
            raise ValueError('cancelled cargo must be physically picked up before retry')
        actor = self.actors[actor_id]
        route = self.nav.route(actor.position, destination)
        tx = Deployment(self._id('deployment'), item_id, actor_id, item['root_id'], kind,
                        tuple(destination), config, route['path'], route['distance'],
                        2.0 if kind == 'water_module' else 1.5, self.now)
        self.deployments[tx.id] = tx
        return tx

    def advance_deployment(self, tx, seconds):
        """Charge real body motion before stationary installation; .1s integration."""
        if seconds < 0:
            raise ValueError('negative time')
        left = seconds
        while left > EPS and tx.status in {'travelling', 'installing'}:
            if self.paused:
                return tx
            dt = min(.1, left)
            actor = self.actors[tx.actor_id]
            if tx.status == 'travelling':
                while tx.edge_index + 1 < len(tx.path) and math.dist(actor.position, tx.path[tx.edge_index+1]) < EPS:
                    tx.edge_index += 1
                if tx.edge_index + 1 == len(tx.path):
                    tx.status = 'installing'
                    continue
                dest = tuple(tx.path[tx.edge_index + 1])
                distance = math.dist(actor.position, dest)
                actual_dt = min(dt, distance / actor.speed)
                fraction = actor.speed * actual_dt / distance
                nxt = tuple(a + (b-a)*fraction for a, b in zip(actor.position, dest))
                if not self.nav.segment_clear(actor.position, nxt):
                    self.cancel_deployment(tx, reason='route_changed')
                    break
                self.advance(actual_dt)
                self._move_actor_segment(actor, nxt)
                tx.walked_distance += actor.speed * actual_dt
                self.items[tx.item_id]['position'] = actor.position
                left -= actual_dt
            else:
                actual_dt = min(dt, tx.action_seconds - tx.action_elapsed)
                self.advance(actual_dt)
                tx.action_elapsed += actual_dt
                left -= actual_dt
                if tx.action_elapsed + EPS >= tx.action_seconds:
                    self._commit_deployment(tx)
        return tx

    def complete_deployment(self, tx):
        return self.advance_deployment(tx, tx.route_distance / 3.0 + tx.action_seconds + 1)

    def cancel_deployment(self, tx, *, reason='cancelled'):
        if tx.status not in {'travelling', 'installing'}:
            return False
        tx.status = reason
        item = self.items[tx.item_id]
        item['position'] = self.actors[tx.actor_id].position
        item['held_by'] = None
        self.actors[tx.actor_id].carried = None
        self._receipt('DEPLOYMENT_CANCELLED', tx.root_id, tx.item_id,
                      actual_position=list(item['position']), no_condition_committed=True)
        return True

    def pickup_cancelled(self, item_id, actor_id='PLAYER'):
        item = self.items[item_id]
        actor = self.actors[actor_id]
        if actor.carried or item['held_by'] or math.dist(actor.position, item['position']) > 1.5:
            raise ValueError('actual free hand and local original item required')
        self.advance(.6)
        actor.carried = item_id
        item['held_by'] = actor_id

    def _commit_deployment(self, tx):
        item = self.items[tx.item_id]
        if not self.nav.point_clear(tx.target) or math.dist(self.actors[tx.actor_id].position, tx.target) > EPS:
            self.cancel_deployment(tx, reason='destination_invalid')
            return
        item.update(position=tx.target, installed=True, held_by=None)
        self.actors[tx.actor_id].carried = None
        tx.status = 'committed'
        tx.receipt_id = self._receipt('PHYSICAL_INSTALL_COMPLETED', tx.root_id, tx.item_id,
                                      kind=tx.kind, route_distance=tx.walked_distance,
                                      position=list(tx.target), action_seconds=tx.action_seconds)
        if tx.kind == 'water_module':
            self._create_water(tx.config['region_id'], tx.item_id, tx.root_id, tx.receipt_id,
                               supply_kind=tx.config.get('supply_kind', 'closed_loop'))
        elif tx.kind == 'mirror':
            normal = tuple(tx.config.get('normal', (0, 1)))
            if math.hypot(*normal) < EPS:
                raise ValueError('mirror needs physical normal')
            n = math.hypot(*normal)
            self.surfaces[tx.item_id] = {'id': tx.item_id, 'item_id': tx.item_id,
                'position': tx.target, 'normal': tuple(v/n for v in normal),
                'reflectivity': tx.config.get('reflectivity', .9),
                'phase_port': tx.config.get('phase_port', False), 'covered': False,
                'broken': False, 'root_id': tx.root_id, 'layer': 'ground', 'version': 1,
                'source_event_id': tx.receipt_id}
        elif tx.kind == 'lamp':
            self.lamps[tx.item_id] = {'id': tx.item_id, 'position': tx.target,
                'root_id': tx.root_id, 'intensity': tx.config.get('intensity', 1.),
                'radius': tx.config.get('radius', 3.), 'on': tx.config.get('on', True),
                'power_domain': tx.config.get('power_domain', 'TASK_ISOLATED'),
                'expires_at': self.now + 900, 'source_event_id': tx.receipt_id,
                'safe_control': tuple(tx.config.get('safe_control', (19.5,19.5))),
                'necessary_for_rule': tx.root_id in self.roots,
                'handcrank_same_original_module': True}
        elif tx.kind == 'phase_anchor':
            self.nodes[tx.item_id] = {'id': tx.item_id, 'position': tx.target,
                'root_id': tx.root_id, 'subtype': tx.config['subtype'],
                'layer': tx.config.get('layer', 'ground'), 'active': True, 'version': 1,
                'requires_dark': tx.config.get('requires_dark', False),
                'source_event_id': tx.receipt_id, 'expires_at': tx.config.get('expires_at')}
        elif tx.kind == 'glass_return':
            self.hazards[tx.item_id] = {'item_id': tx.item_id, 'position': tx.target,
                'warned_at': self.now, 'isolated': False, 'contacted': False,
                'source_event_id': tx.receipt_id}

    def _create_water(self, region_id, item_id, root_id, event_id, *, supply_kind='closed_loop', feed_until=None):
        if any(s['region_id'] == region_id and not s['ended'] for s in self.sources.values()):
            raise ValueError('one live source episode per wet region')
        region = self.regions[region_id]
        episode = self._id('water_episode')
        if supply_kind not in {'closed_loop','finite_pour','weather_flux','plumbed_channel'}:
            raise ValueError('unknown physical water supply')
        volume = len(region['wet_cells'])
        if supply_kind == 'finite_pour':
            feed_until = self.now + 3 + volume
        self.sources[episode] = {'id': episode, 'region_id': region_id,
            'item_id': item_id, 'root_id': root_id, 'source_event_id': event_id,
            'started_at': self.now, 'flowing': True, 'ended': False, 'cells': {},
            'cut_cells': set(), 'version': 1, 'feed_start_at': self.now+3,
            'feed_until': feed_until, 'supply_kind': supply_kind,
            'volume_cell_units': volume, 'ever_filled': set(),
            'detached_fast_drain': False, 'ready_at': self.now+3}
        self._update_water()
        return episode

    def weather_rain(self, seed):
        """Independent nightly weather draw; source only after actual 20s rain onset."""
        rng = random.Random(seed)
        rain = rng.random() < .2
        self._receipt('WEATHER_DRAW', 'world', 'weather', seed=seed, rain=rain)
        if rain:
            if self.now < 20:
                self.advance(20-self.now)
            receipt = self._receipt('RAIN_STARTED', 'world', 'front_rain')
            return self._create_water('WET_FRONT', 'front_rain', 'world', receipt,
                                      supply_kind='weather_flux',feed_until=140.)
        return None

    def _source_reachable(self, src):
        region = self.regions[src['region_id']]
        allowed = {tuple(c) for c in region['wet_cells']} - src['cut_cells']
        start = tuple(region['source_cell'])
        if start not in allowed or not self.nav.point_clear(_centre(start), .15):
            return {}
        distances = {start: 0}
        q = deque([start])
        while q:
            cell = q.popleft()
            for nxt in _neighbours(cell):
                if nxt not in allowed or nxt in distances:
                    continue
                if not self.nav.segment_clear(_centre(cell), _centre(nxt), .15):
                    continue
                distances[nxt] = distances[cell] + 1
                q.append(nxt)
        return distances

    def _update_water(self):
        for src in self.sources.values():
            if src['feed_until'] is not None and self.now+EPS >= src['feed_until']:
                src['flowing'] = False
            reachable = self._source_reachable(src) if src['flowing'] and not src['ended'] else {}
            for cell, distance in reachable.items():
                if self.now + EPS < src['feed_start_at'] + distance:
                    continue
                if cell not in src['cells']:
                    if src['supply_kind']=='finite_pour' and cell in src['ever_filled']:
                        continue
                    src['cells'][cell] = {'born_at': self.now, 'expires_at': self.now+180}
                    src['ever_filled'].add(cell)
                elif src['supply_kind']!='finite_pour':
                    src['cells'][cell]['expires_at'] = self.now+180
            for cell, v in list(src['cells'].items()):
                if cell not in reachable and src['detached_fast_drain']:
                    v['expires_at'] = min(v['expires_at'], self.now+2)
                if self.now + EPS >= v['expires_at']:
                    del src['cells'][cell]
                    src['version'] += 1

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError('cannot reverse world time')
        if self.paused:
            return
        end = self.now + seconds
        while self.now + EPS < end:
            self.now = min(end, self.now + .1)
            # Source/treatment/expiry changes happen before any movement commit.
            for incident in self.wounds.values():
                if incident['status'] == 'fresh' and self.now + EPS >= incident['expires_at']:
                    incident['status'] = 'dry'
            for trace in self.traces.values():
                if trace['alive'] and self.now + EPS >= trace['expires_at']:
                    trace['alive'] = False
            self._update_water()
            for rid,root in self.roots.items():
                window=root.get('task_recovery_window')
                if window and (self.now+EPS>=window['until'] or
                               math.dist(self.actors['PLAYER'].position,window['safe_control'])>1.5):
                    root.pop('environment_guard',None)
                if root['state']=='active' and self.now+EPS>=root.get('absolute_rule_deadline',float('inf')):
                    root['state']=root.get('deadline_terminal','failed')
                    root['rule_terminal_request']='original_absolute_deadline'
                    root.pop('environment_guard',None)
                    root['terminal_receipt']=self._receipt('ORIGINAL_RULE_DEADLINE_EXPIRED',rid,root['monster_id'],
                                                          outcome=root['state'],root_reward=0)
                f58=root.get('f58')
                if f58 and self.now+EPS>=f58['fog_deadline']:
                    f58['fog_present']=False

    def _move_actor_segment(self, actor, nxt):
        old = actor.position
        length = math.dist(old, nxt)
        actor.position = tuple(nxt)
        inc = self.wounds.get(actor.bleeding_incident)
        if not inc or inc['status'] != 'fresh' or self.now + EPS >= inc['expires_at']:
            return
        actor.travelled_since_mark += length
        if actor.travelled_since_mark + EPS >= 2:
            # Segments in walk() are <=.3 tiles; precise interpolated marker point.
            overshoot = actor.travelled_since_mark - 2
            frac = max(0, min(1, (length-overshoot)/length)) if length else 0
            point = tuple(a+(b-a)*frac for a,b in zip(old,nxt))
            actor.travelled_since_mark -= 2
            tid = self._id('blood_trace')
            live = [x for x in self.traces.values() if x['actor_id'] == actor.id and x['alive']]
            if len(live) >= 6:
                min(live, key=lambda x:x['born_at'])['alive'] = False
            self.traces[tid] = {'id':tid, 'actor_id':actor.id, 'incident_id':inc['id'],
                'position':point, 'born_at':self.now, 'expires_at':self.now+30,
                'alive':True, 'layer':actor.layer, 'owner_root_id':'world',
                'source_event_id':self._receipt('WOUNDED_BODY_TRAVELLED_TWO_TILES','world',inc['id'],position=list(point))}

    def walk(self, destination, *, actor_id='PLAYER'):
        actor = self.actors[actor_id]
        route = self.nav.route(actor.position, destination)
        for target in route['path'][1:]:
            while math.dist(actor.position, target) > EPS:
                if self.paused:
                    return {'completed':False, 'distance':route['distance']}
                distance = math.dist(actor.position, target)
                dt = min(.1, distance/actor.speed)
                nxt = tuple(a+(b-a)*actor.speed*dt/distance for a,b in zip(actor.position,target))
                if not self.nav.segment_clear(actor.position,nxt):
                    raise ValueError('route became blocked')
                self.advance(dt)
                self._move_actor_segment(actor,nxt)
        return {'completed':True, 'distance':route['distance'], 'path':route['path']}

    def live_wet_cells(self, root_id='world'):
        cells = set()
        for src in self.sources.values():
            if src['root_id'] not in {'world', root_id}:
                continue
            cells.update(c for c,v in src['cells'].items() if v['expires_at'] > self.now+EPS)
        return cells

    def wet_path(self, start, end, *, root_id='world', layer='ground'):
        if layer != 'ground':
            return None
        a,b = _cell(start),_cell(end)
        wet = self.live_wet_cells(root_id)
        if a not in wet or b not in wet:
            return None
        prev = {a:None}; q = deque([a])
        while q and b not in prev:
            c=q.popleft()
            for n in _neighbours(c):
                if n in wet and n not in prev and self.nav.segment_clear(_centre(c),_centre(n),.15):
                    prev[n]=c; q.append(n)
        if b not in prev:return None
        cells=[]; cur=b
        while cur is not None:cells.append(cur);cur=prev[cur]
        cells.reverse()
        return {'cells':cells,'path':[_centre(c) for c in cells], 'distance':max(0,len(cells)-1),
                'source_episode_ids':[s['id'] for s in self.sources.values() if s['root_id'] in {'world',root_id} and any(c in s['cells'] for c in cells)]}

    def control_flow(self, source_id, *, open_flow, actor_id='PLAYER'):
        src=self.sources[source_id];region=self.regions[src['region_id']]
        control=region.get('control_anchor') or ('water_valve' if region['id']=='WET_REAR' else region['dry_interact_position'])
        target=self.nav.position(control)
        if math.dist(self.actors[actor_id].position,target)>1.5:raise ValueError('physical valve/control required')
        self.advance(.5)
        src['flowing']=bool(open_flow);src['version']+=1
        if open_flow:src['feed_start_at']=self.now
        self._receipt('REAL_SOURCE_VALVE_CHANGED',src['root_id'],src['item_id'],source_episode_id=source_id,open=open_flow)
        self._update_water()

    def wipe_cut(self, source_id, *, actor_id='PLAYER', commit=True):
        src=self.sources[source_id];r=self.regions[src['region_id']]
        if math.dist(self.actors[actor_id].position,r['dry_interact_position'])>1.5:
            raise ValueError('must physically reach dry wiping position')
        self.advance(2 if commit else 1)
        if not commit:return False
        cell=tuple(r['cut_cell'])
        src['cut_cells'].add(cell);src['cells'].pop(cell,None)
        src['detached_fast_drain']=True;src['version']+=1
        self._receipt('ACTUAL_WATER_CUT_WIPED',src['root_id'],src['item_id'],source_episode_id=source_id,cell=list(cell))
        self._update_water()
        return True

    def claim_cleanup(self, source_episode_id):
        if self.phase not in {'BUSINESS','RECOVERY'}:
            raise ValueError('ordinary cleanup rewards wait for safe phase')
        src=self.sources.get(source_episode_id)
        if src and not src.get('cleanup_action_receipt'):
            raise ValueError('natural drying is not an actual paid cleaning action')
        if src and (src['flowing'] or src['cells']):
            raise ValueError('episode is not actually cleaned')
        stain=self.cleanup_stains.get(source_episode_id)
        if not src and not (stain and stain['removed']):raise ValueError('no actual cleanup episode')
        if source_episode_id in self.cleaned_episodes:return False
        self.cleaned_episodes.add(source_episode_id)
        self._receipt('CLEANUP_REWARD_ELIGIBLE_ONCE','world',source_episode_id)
        return True

    def clean_episode(self, source_episode_id):
        """Real safe-phase cleaning; natural expiry alone never earns work pay."""
        if self.phase not in {'BUSINESS','RECOVERY'}:
            raise ValueError('ordinary floor cleaning is deferred during invasion')
        src=self.sources[source_episode_id]
        if src['flowing']:
            raise ValueError('isolate actual source before completing cleanup')
        cleaned=0
        for cell in list(src['cells']):
            if cell not in src['cells']:continue
            self.walk(_centre(cell))
            if cell not in src['cells']:continue
            self.advance(1.5)
            if cell in src['cells']:
                del src['cells'][cell]
                src['cut_cells'].add(cell)
                src['version']+=1
                cleaned+=1
        if not cleaned:return False
        src['cleanup_action_receipt']=self._receipt('ACTUAL_EPISODE_CLEANED',src['root_id'],src['item_id'],
                                                   source_episode_id=source_episode_id,actual_cells_cleaned=cleaned)
        return True

    def set_door(self, door_id, closed):
        if door_id not in {d['id'] for d in self.nav.base['doors']}:raise ValueError('unknown door')
        if closed:self.closed_doors.add(door_id)
        else:self.closed_doors.discard(door_id)
        self.nav=StoreMap(closed_doors=self.closed_doors)
        self._receipt('DOOR_PHYSICAL_STATE_CHANGED','world',door_id,closed=closed)
        self._update_water()

    def set_power(self, domain, on, *, source_event_id):
        if domain not in self.power or not source_event_id:raise ValueError('actual circuit source required')
        self.power[domain]=bool(on)
        self._receipt('POWER_CHANGED','world',domain,source_event_id=source_event_id,on=bool(on))

    def light_level(self, position):
        total=0.
        for lamp in self.lamps.values():
            if not lamp['on'] or not self.power[lamp['power_domain']] or self.now+EPS>=lamp['expires_at']:continue
            d=math.dist(position,lamp['position'])
            if d>lamp['radius'] or not self.sight_clear(lamp['position'],position):continue
            total+=lamp['intensity']*max(0.,1-d/lamp['radius'])
        return total

    def is_dark(self,position):return self.light_level(position)<.2

    def switch_lamp(self,item_id,on):
        self.lamps[item_id]['on']=bool(on)
        self._receipt('LAMP_LOCAL_SWITCH',self.lamps[item_id]['root_id'],item_id,on=bool(on))

    def handcrank_task_group(self,root_id,*,commit=True):
        """Same installed isolated module, local two-second free manual power.

        Only an almost empty (<=10s) necessary module can enter this fallback.
        It restores 60s at most, never banks repeated credits, never advances a
        quest deadline or restores MAIN/ordinary facility buffs.
        """
        root=self.roots[root_id]
        lamps=[l for l in self.lamps.values() if l['root_id']==root_id and
               l['necessary_for_rule'] and l['power_domain']=='TASK_ISOLATED']
        if root['state']!='active' or not lamps or not all(l['handcrank_same_original_module'] for l in lamps):
            raise ValueError('same active root and real task module required')
        if any(self.items[l['id']]['removed'] for l in lamps):
            raise ValueError('missing original module cannot be restored by an energy action')
        if min(l['expires_at']-self.now for l in lamps)>10+EPS:
            raise ValueError('cannot stockpile manual task energy')
        control=lamps[0]['safe_control']
        if any(l['safe_control']!=control for l in lamps):raise ValueError('physical charging group mismatch')
        if math.dist(self.actors['PLAYER'].position,control)>1.5:
            raise ValueError('must reach real safe-side handcrank control')
        deadline=root.get('absolute_rule_deadline',float('inf'))
        if self.now+EPS>=deadline:
            root['state']=root.get('deadline_terminal','failed')
            root['rule_terminal_request']='original_absolute_deadline'
            root.pop('environment_guard',None)
            raise ValueError('expired original rule deadline cannot be reopened')
        if root.get('native_attack_pending',False) or self.now<root.get('native_freeze_until',0)-EPS:
            raise ValueError('pending native attack/old freeze must naturally end first')
        cycle=root.get('task_energy_cycle',0)
        old=root.get('task_recovery_window')
        if old is None or old['energy_cycle']!=cycle:
            root['task_recovery_window']={'energy_cycle':cycle,'opened_at':self.now,
                'until':self.now+3,'safe_control':control,
                'scope':'this_root_new_attacks_only; poison_maturity_world_and_other_sources_continue'}
            root['environment_guard']='local_task_handcrank_response'
        # Cancelling/re-entering the same depleted cycle does not renew its
        # three-second deadline. After it is spent, the normal native miss
        # recovery must supply the manual two-second work opportunity.
        self.advance(2 if commit else 1)
        if not commit:return False
        if root['state']!='active' or self.now+EPS>=deadline:return False
        for lamp in lamps:lamp['expires_at']=self.now+60
        root.pop('environment_guard',None)
        root['task_energy_cycle']=cycle+1
        self._receipt('SAME_TASK_MODULE_HANDCRANK_COMPLETED',root_id,lamps[0]['id'],
                      same_original_lamps=[l['id'] for l in lamps],charge_seconds=2,
                      usable_world_seconds=60,coin=0,xp=0,does_not_supply_MAIN=True)
        return True

    def heat_existing_reference_pack(self,item_id,*,commit=True):
        """Boundary/counterexample fixture for the withdrawn 900s warm-pack idea.

        It still requires the same actual item to reach FX14 and receive actual
        MAIN heat. It is never a replacement for F58's original hot meal or an
        automatic producer of a primary-rule fact.
        """
        item=self.items[item_id];position=tuple(self.nav.position('hot_food'))
        if item['kind']!='warmed_pack' or item['removed'] or not item['installed']:
            raise ValueError('physical original thermal item required')
        if tuple(item['position'])!=position or math.dist(self.actors['PLAYER'].position,position)>1.5:
            raise ValueError('both original item and actor must be at actual FX14 heater')
        if not self.power['MAIN']:raise ValueError('no actual heating source during MAIN outage')
        if item_id in self.warm_sources:raise ValueError('this original heat receipt is not resettable')
        self.advance(2 if commit else 1)
        if not commit:return False
        if not self.power['MAIN']:return False
        self.warm_sources[item_id]={'item_id':item_id,'root_id':item['root_id'],
            'position':position,'heated_at':self.now,'warm_until':self.now+900,
            'original_heat_receipt':self._receipt('ACTUAL_FX14_HEAT_TRANSFER',item['root_id'],item_id,
                                                heater_id='MAP_STORE:FX14',work_seconds=2),
            'F58_primary_food_substitute':False,'withdrawn_candidate_reference_only':True}
        return True

    def original_pack_still_warm(self,item_id):
        heat=self.warm_sources.get(item_id)
        item=self.items.get(item_id)
        return bool(heat and item and not item['removed'] and self.now+EPS<heat['warm_until'])

    def f58_use_thermal_backup(self,root_id,item_id):
        # Original F58 has a real-food OR free-close rule. A generic backup pack
        # cannot refresh that food's 40s quality or the 30/120s absolute clocks.
        raise ValueError('F58 uses original meal or physical cold-section closure; thermal packs cannot mint/refresh its rule source')

    def activate_f58_original_clocks(self,root_id):
        root=self.roots[root_id]
        if root['monster_id']!='F58' or root['state']!='active' or 'f58' in root:
            raise ValueError('one actual F58 arrival, never reset its original clocks')
        root['f58']={'fog_started_at':self.now,'fog_deadline':self.now+30,
                     'fog_present':True,'ordinary_cold_service_open':True,
                     'closure_receipt':None,'exit_receipt':None,'reward_eligible_once':False}
        root['absolute_rule_deadline']=self.now+120
        root['deadline_terminal']='expired'
        self._receipt('F58_ORIGINAL_FOG_STARTED',root_id,'OBJ_COLD_SECTION_SIGN',
                      fog_deadline=root['f58']['fog_deadline'],rule_deadline=root['absolute_rule_deadline'])

    def f58_close_cold_section(self,root_id,*,commit=True):
        root=self.roots[root_id];f58=root.get('f58')
        if root['state']!='active' or not f58:raise ValueError('active original F58 required')
        if math.dist(self.actors['PLAYER'].position,(24.5,15.5))>1.5:
            raise ValueError('actual fixed cold-section sign must be reached')
        self.advance(.5 if commit else .25)
        if not commit or root['state']!='active':return False
        if f58['closure_receipt']:return f58['closure_receipt']
        f58['ordinary_cold_service_open']=False
        f58['closure_receipt']=self._receipt('F58_ORDINARY_COLD_SECTION_CLOSED',root_id,
            'OBJ_COLD_SECTION_SIGN',world_action_seconds=.5,task_freezers_unchanged=True,
            emergency_doors_unchanged=True,ordinary_chore_reward=0)
        return f58['closure_receipt']

    def f58_exit_cold_boundary(self,root_id,*,commit=True):
        root=self.roots[root_id];f58=root.get('f58')
        if f58 and f58['exit_receipt']:return {'applied':False,'receipt':f58['exit_receipt']}
        if root['state']!='active' or not f58 or f58['ordinary_cold_service_open']:
            raise ValueError('close actual ordinary service before exiting F58 boundary')
        if math.dist(self.actors['PLAYER'].position,(21.5,15.5))>.3:
            raise ValueError('player must physically leave to original warm-side exit')
        self.advance(.5 if commit else .25)
        if not commit or root['state']!='active':return {'applied':False,'receipt':None}
        f58['fog_present']=False
        f58['exit_receipt']=self._receipt('F58_RULE_LEAVE_COLD_EXIT',root_id,'OBJ_COLD_SECTION_SIGN',
                                         actual_exit_position=list(self.actors['PLAYER'].position),
                                         resolution='rule_leave',root_reward_once=True,thermal_recharge=False)
        f58['reward_eligible_once']=True
        self.end_root(root_id)
        return {'applied':True,'receipt':f58['exit_receipt']}

    def sight_clear(self,a,b):
        """Eye/task-light height: real walls, tall shelves, doors and curtain.

        A low countertop blocks bodies but does not automatically occlude an
        eye-height ray; map blocks_rule_sight is the authority for this query.
        Projectile/body-height collision remains MA01's separate query.
        """
        blockers=list(self.nav.base['walls'])
        blockers.extend(x for x in self.nav.base['fixtures'] if x.get('blocks_rule_sight'))
        blockers.extend(x for x in self.nav.contract['new_fixtures'] if x.get('blocks_rule_sight'))
        blockers.extend(x for x in self.nav.base['doors'] if x['id'] in self.closed_doors)
        if any(_segment_rect_intersects(a,b,x['rect']) for x in blockers):return False
        if self.mirror_curtain_closed:
            # Actual OBJ_MIRROR_CURTAIN segment, not a permanent flag on F60.
            dy=b[1]-a[1]
            if abs(dy)>EPS:
                t=(23.-a[1])/dy
                if 0<=t<=1 and 18.5-EPS<=a[0]+t*(b[0]-a[0])<=20.5+EPS:return False
            elif abs(a[1]-23.)<EPS and max(min(a[0],b[0]),18.5)<=min(max(a[0],b[0]),20.5):return False
        return True

    def pull_mirror_curtain(self,closed=True):
        if math.dist(self.actors['PLAYER'].position,(19.5,23.5))>1.5:
            raise ValueError('actual curtain control must be reached')
        self.advance(1)
        self.mirror_curtain_closed=bool(closed)
        self._receipt('ACTUAL_CURTAIN_CHANGED','world','OBJ_MIRROR_CURTAIN',closed=closed)

    def cover_mirror(self,item_id,covered=True):
        surface=self.surfaces[item_id]
        if math.dist(self.actors['PLAYER'].position,surface['position'])>1.5:raise ValueError('reach original mirror to cover')
        self.advance(1)
        surface['covered']=bool(covered);surface['version']+=1
        self._receipt('MIRROR_COVER_CHANGED',surface['root_id'],item_id,covered=covered)

    def remove_item(self,item_id):
        item=self.items[item_id]
        item['removed']=True;item['version']+=1
        self.surfaces.pop(item_id,None)
        if item_id in self.nodes:self.nodes[item_id]['active']=False;self.nodes[item_id]['version']+=1
        if item_id in self.lamps:self.lamps[item_id]['on']=False
        for src in self.sources.values():
            if src['item_id']==item_id:src['flowing']=False;src['version']+=1
        self._receipt('ORIGINAL_ITEM_REMOVED',item['root_id'],item_id)

    def mirror_pair(self,a,b,root_id):
        """Topology probe only: it never grants a species a mirror capability."""
        if a==b:return None
        sa,sb=self.surfaces.get(a),self.surfaces.get(b)
        if not sa or not sb:return None
        for s in (sa,sb):
            if (not s['phase_port'] or s['covered'] or s['broken'] or s['reflectivity']<.65
                or s['root_id']!=root_id or s['layer']!='ground'
                or not self.nav.point_clear(s['position'])):return None
        return {'source_ids':[a,b],'root_id':root_id,'versions':[sa['version'],sb['version']],
                'positions':[sa['position'],sb['position']]}

    def recheck_mirror_pair(self,ticket):
        if not ticket:return False
        current=self.mirror_pair(*ticket['source_ids'],ticket['root_id'])
        return bool(current and current['versions']==ticket['versions'] and current['positions']==ticket['positions'])

    def reflection_visible(self,observer,surface_id,target):
        s=self.surfaces.get(surface_id)
        if not s or s['covered'] or s['broken'] or s['reflectivity']<.25:return False
        p=s['position'];n=s['normal']
        # Both legs must lie on the actual reflecting front hemisphere.
        if sum((q[i]-p[i])*n[i] for i in (0,1) for q in [observer])<=EPS:return False
        if sum((target[i]-p[i])*n[i] for i in (0,1))<=EPS:return False
        # Intersect observer -> mirrored target with the finite mirror plane.
        # This is a local planar reference; a convex production shader must
        # still keep the same bounded two-leg visibility/occlusion contract.
        signed=sum((target[i]-p[i])*n[i] for i in (0,1))
        virtual=tuple(target[i]-2*signed*n[i] for i in (0,1))
        delta=tuple(virtual[i]-observer[i] for i in (0,1))
        den=sum(delta[i]*n[i] for i in (0,1))
        if abs(den)<EPS:return False
        t=sum((p[i]-observer[i])*n[i] for i in (0,1))/den
        if t<0 or t>1:return False
        hit=tuple(observer[i]+t*delta[i] for i in (0,1))
        if math.dist(hit,p)>.75:return False
        return self.sight_clear(observer,hit) and self.sight_clear(hit,target)

    def direct_gaze(self,a,a_facing,b,b_facing,*,max_range=8,cos_half=.5):
        d=math.dist(a,b)
        if d<EPS or d>max_range or not self.sight_clear(a,b):return False
        delta=((b[0]-a[0])/d,(b[1]-a[1])/d)
        def face(v,dirn):
            norm=math.hypot(*v)
            return norm>EPS and sum(x*y for x,y in zip(v,dirn))/norm>=cos_half
        return face(a_facing,delta) and face(b_facing,(-delta[0],-delta[1]))

    def emit_sound(self,item_id,position,*,root_id='world',duration=3,range_tiles=3,power_domain=None):
        if not self.nav.point_clear(position):raise ValueError('source body/device must be at legal position')
        if duration<=0 or duration>30:raise ValueError('finite emission duration required')
        sid=self._id('sound')
        self.sounds[sid]={'id':sid,'item_id':item_id,'position':tuple(position),'root_id':root_id,
            'until':self.now+duration,'range':range_tiles,'power_domain':power_domain,
            'event':self._receipt('ACTUAL_SOUND_EMISSION',root_id,item_id)}
        return sid

    def sound_reaches(self,sound_id,position):
        s=self.sounds[sound_id]
        if self.now+EPS>=s['until'] or (s['power_domain'] and not self.power[s['power_domain']]):return False
        try:d=self.nav.route(s['position'],position)['distance']
        except ValueError:return False
        return d<=s['range']+EPS

    def glass_contact(self,item_id,actor_id='PLAYER'):
        hazard=self.hazards[item_id];actor=self.actors[actor_id]
        if hazard['isolated'] or hazard['contacted'] or self.now-hazard['warned_at']<3-EPS:return None
        if math.dist(actor.position,hazard['position'])>1.5:return None
        if any(w['actor_id']==actor_id for w in self.wounds.values()) or len(self.wounds)>=2:return None
        if actor_id not in {'PLAYER','COWORKER'}:raise ValueError('no customer/monster blood substitution')
        incident=self._id('glass_incident')
        hazard['contacted']=True
        self.wounds[incident]={'id':incident,'actor_id':actor_id,'item_id':item_id,'status':'fresh',
            'born_at':self.now,'expires_at':self.now+90,'source_event_id':self._receipt('GLASS_REAL_CONTACT','world',item_id,actor_id=actor_id)}
        actor.bleeding_incident=incident;actor.travelled_since_mark=0
        return incident

    def dress(self,actor_id='PLAYER',*,commit=True):
        actor=self.actors[actor_id];inc=self.wounds.get(actor.bleeding_incident)
        if not inc or inc['status']!='fresh':return False
        self.advance(3 if commit else 1)
        if commit and inc['status']=='fresh':
            inc['status']='dressed'
            self._receipt('REAL_DRESSING_COMPLETED','world',inc['id'],actor_id=actor_id)
            return True
        return False

    def fresh_wound(self,incident_id):
        w=self.wounds.get(incident_id)
        return bool(w and w['status']=='fresh' and self.now+EPS<w['expires_at'])

    def bind_blood_consumer(self,monster_id,incident_id,*,omen_seconds=20,response_seconds=24):
        """Read-only admission/budget probe; reserve_blood_consumer owns a slot."""
        if monster_id not in {'F26','F32'}:raise ValueError('not a blood consumer')
        wound=self.wounds.get(incident_id)
        if omen_seconds<20 or response_seconds<0:raise ValueError('BC02 actual preparation/response budget required')
        required_remaining=omen_seconds+response_seconds+6+3
        if not self.fresh_wound(incident_id) or wound['expires_at']-self.now<required_remaining-EPS:return None
        live=[t['id'] for t in self.traces.values() if t['incident_id']==incident_id and t['alive'] and t['expires_at']>self.now+EPS]
        if monster_id=='F26' and not any(self.traces[t]['expires_at']>self.now+omen_seconds+EPS for t in live):return None
        return {'monster_id':monster_id,'incident_id':incident_id,'trace_ids':live[-3:],
                'announced_at':self.now,'arrive_after':self.now+omen_seconds,
                'required_fresh_remaining':required_remaining}

    def reserve_blood_consumer(self,root_id,incident_id,**budget):
        root=self.roots[root_id]
        existing=self.blood_reservations.get(incident_id)
        if existing is not None:return None
        ticket=self.bind_blood_consumer(root['monster_id'],incident_id,**budget)
        if ticket is None:return None
        ticket['reserved_root_id']=root_id
        self.blood_reservations[incident_id]=ticket
        return copy.deepcopy(ticket)

    def blood_arrival(self,ticket):
        if not ticket or self.now+EPS<ticket['arrive_after']:return False
        if ticket['monster_id']=='F32':return self.fresh_wound(ticket['incident_id'])
        return any(self.traces[t]['alive'] and self.traces[t]['expires_at']>self.now+EPS for t in ticket['trace_ids'])

    def record_f13_defeat(self,root_id,hp,position):
        root=self.roots[root_id]
        if root['monster_id']!='F13' or hp!=0 or not self.nav.point_clear(position):raise ValueError('actual F13 zero-HP/landing required')
        key=f'{root_id}:cleanup_blood'
        if key in self.cleanup_stains:return key
        self.cleanup_stains[key]={'root_id':root_id,'position':tuple(position),'removed':False,
            'is_player_wound':False,'can_activate_blood_conditional_encounters':False,
            'source_event_id':self._receipt('F13_ACTUAL_DEFEAT','%s'%root_id,key)}
        return key

    def spawn_body(self,root_id,position,*,layer='ground'):
        root=self.roots[root_id]
        if root['state']!='reserved' or not self.nav.point_clear(position):raise ValueError('valid actual arrival required')
        if math.dist(position,self.actors['PLAYER'].position)<5-EPS:raise ValueError('arrival too close to player')
        root.update(state='active',body=tuple(position),layer=layer)
        self._receipt('ACTUAL_ROOT_BODY_ARRIVED',root_id,root['monster_id'],position=list(position),layer=layer)

    def _node_usable(self,node_id,root_id):
        n=self.nodes.get(node_id)
        return bool(n and n['active'] and n['root_id']==root_id
                    and (n['expires_at'] is None or self.now+EPS<n['expires_at'])
                    and self.nav.point_clear(n['position'])
                    and (not n['requires_dark'] or self.is_dark(n['position'])))

    def begin_transition(self,root_id,mode,destination,*,source_ids=()):
        root=self.roots[root_id];mid=root['monster_id'];origin=root['body']
        if root['state']!='active' or origin is None or self.now<root['cooldown_until']-EPS:raise ValueError('root not ready')
        if mode=='mirror':raise ValueError('no current MD01 monster has a mirror-phase capability')
        warning=1.5;recovery=.8;transit=.2;path=[origin,tuple(destination)]
        if mode=='water':
            if mid not in self.data['coverage']['water_movement_not_phase_ids']:raise ValueError('species has no water-lane movement')
            wet=self.wet_path(origin,destination,root_id=root_id,layer=root['layer'])
            if not wet:raise ValueError('no actual connected water path')
            path=wet['path'];source_ids=tuple(wet['source_episode_ids']);transit=wet['distance']/3.3;recovery=2.5
        elif mode in {'shadow','phase'}:
            spec=next((x for x in self.data['phase_anchor_catalog'] if x['monster_id']==mid),None)
            if spec is None or math.dist(origin,destination)>spec['max_distance_tiles']+EPS:raise ValueError('capability/range denied')
            if not source_ids or any(not self._node_usable(n,root_id) for n in source_ids):raise ValueError('missing actual live root anchor')
            if tuple(destination) not in [self.nodes[n]['position'] for n in source_ids]:raise ValueError('destination is not a registered endpoint')
            if any(self.nodes[n]['subtype']!=spec['subtype'] for n in source_ids):raise ValueError('wrong source subtype cannot be substituted')
            if any(self.nodes[n]['layer']!=root['layer'] for n in source_ids):raise ValueError('source layer mismatch')
            if mid=='F40':transit=.6
            if mid=='S22':transit=0;recovery=1.5
            if mid=='S23':warning=2;transit=0;recovery=4
        else:raise ValueError('unsupported native motion')
        t=Transition(self._id('transition'),root_id,mid,mode,origin,tuple(destination),tuple(source_ids),path,
                     warning,transit,recovery,self.now,self.actors['PLAYER'].position)
        if not self._transition_valid(t):raise ValueError('unsafe destination or lost source')
        self.transitions[t.id]=t
        root['cooldown_until']=self.now+(8 if mid=='S22' else 10)
        self._receipt('REAL_TRANSITION_WARNING',root_id,mid,origin=list(origin),destination=list(destination),source_ids=list(source_ids))
        return t

    def _transition_valid(self,t):
        root=self.roots[t.root_id]
        if root['state']!='active' or root.get('environment_guard') or not self.nav.point_clear(t.destination):return False
        if any(math.dist(t.destination,a.position)<.65 for a in self.actors.values() if not a.id.startswith('PORTER')):return False
        if t.mode=='water':
            current=self.wet_path(t.origin,t.destination,root_id=t.root_id,layer=root['layer'])
            return bool(current and current['path']==t.path and set(current['source_episode_ids'])==set(t.source_ids))
        if any(not self._node_usable(n,t.root_id) for n in t.source_ids):return False
        if t.destination not in [self.nodes[n]['position'] for n in t.source_ids]:return False
        if t.monster_id=='S22' and math.dist(t.destination,self.actors['PLAYER'].position)<=math.dist(t.origin,self.actors['PLAYER'].position)+EPS:return False
        return True

    def finish_transition(self,t,*,during_warning=None,during_transit=None):
        """Recheck at start, windup completion and before arrival; no retargeting.

        Water paths consume their actual length/3.3 time. This finite reference
        samples the occupied path at .1s; native water is not a ground-trap path.
        """
        if t.status!='warning':return t
        self.advance(t.warning_s)
        if during_warning:during_warning(self,t)
        if not self._transition_valid(t):return self._cancel_transition(t,'source_or_destination_changed_during_warning')
        t.status='moving'
        elapsed=0.
        while elapsed+EPS<t.transit_s:
            dt=min(.1,t.transit_s-elapsed);self.advance(dt);elapsed+=dt
            if during_transit:during_transit(self,t)
            if not self._transition_valid(t):return self._cancel_transition(t,'source_or_destination_changed_during_transit')
            if t.mode=='water':
                travelled=min(elapsed*3.3,max(0,len(t.path)-1))
                idx=min(int(travelled),len(t.path)-1)
                if idx+1<len(t.path):
                    frac=travelled-idx
                    self.roots[t.root_id]['body']=tuple(a+(b-a)*frac for a,b in zip(t.path[idx],t.path[idx+1]))
                else:self.roots[t.root_id]['body']=t.path[-1]
        if not self._transition_valid(t):return self._cancel_transition(t,'source_changed_before_arrival')
        self.roots[t.root_id]['body']=t.destination;t.status='committed';t.commits=1
        t.phase_event_count=0 if t.mode=='water' else 1
        t.recovery_until=self.now+t.recovery_s
        self._receipt('REAL_MOVEMENT_COMMITTED',t.root_id,t.monster_id,
                      origin=list(t.origin),destination=list(t.destination),actual_path=t.path,
                      phase_event=t.phase_event_count==1,ground_midpath_triggers=False)
        return t

    def _cancel_transition(self,t,reason):
        t.status='cancelled';t.reason=reason;t.recovery_until=self.now+t.recovery_s
        if t.mode=='water':
            # Surface at the body's actual last travelled point, not back at the
            # original source and not at a different dry-side destination.
            t.recovery_until+=1.5
            self.roots[t.root_id]['movement_substate']='visible_surface_recovery'
        # No alternative destination or virtual movement event; the abstract
        # phase body's last committed position remains its original legal point.
        self._receipt('TRANSITION_CANCELLED',t.root_id,t.monster_id,reason=reason,recovery_until=t.recovery_until)
        return t

    def end_root(self,root_id):
        self.roots[root_id]['state']='terminal'
        for n in self.nodes.values():
            if n['root_id']==root_id:n['active']=False;n['version']+=1
        for s in self.sources.values():
            if s['root_id']==root_id:s['flowing']=False;s['ended']=True
        for lamp in self.lamps.values():
            if lamp['root_id']==root_id:lamp['on']=False
        for t in self.transitions.values():
            if t.root_id==root_id and t.status in {'warning','moving'}:self._cancel_transition(t,'root_terminal')
        self._receipt('ROOT_ENVIRONMENT_RELEASED',root_id,root_id)

    def snapshot(self):
        """Reviewable checkpoint; full engine restore remains an integration gate."""
        return {'world_at':self.now,'phase':self.phase,'power':dict(self.power),
                'wounds':copy.deepcopy(self.wounds),'traces':copy.deepcopy(self.traces),
                'receipt_count':len(self.receipts),'roots':copy.deepcopy(self.roots),
                'live_wet_cells':sorted(self.live_wet_cells()),
                'source_count':len(self.sources),'phase_events':sum(t.phase_event_count for t in self.transitions.values())}
