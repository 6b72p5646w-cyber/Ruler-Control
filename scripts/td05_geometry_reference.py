#!/usr/bin/env python3
"""TD05 static, body-aware area compensation; not runtime navigation or height AI.

Nominal circles count a legal enemy centre inside their circle. A body need not
fit wholly inside that circle; it must fit on real floor and avoid solid objects.
Thus an empty unobstructed r=1 circle remains r=1 even for a radius-.3 body.
"""
from collections import deque
from bisect import bisect_right
import math


def inside_rect(point, rect):
    x, y = point; rx, ry, w, h = rect
    return rx <= x < rx + w and ry <= y < ry + h


def distance_to_rect(point, rect):
    x, y = point; rx, ry, w, h = rect
    return math.hypot(max(rx-x, 0, x-rx-w), max(ry-y, 0, y-ry-h))


def segment_hits_solid(a, b, rect):
    """Open interior intersection; touching a corner alone does not occlude."""
    lo, hi = 0., 1.
    for origin, delta, lower, upper in ((a[0], b[0]-a[0], rect[0], rect[0]+rect[2]),
                                         (a[1], b[1]-a[1], rect[1], rect[1]+rect[3])):
        if abs(delta) < 1e-12:
            if not lower + 1e-10 < origin < upper - 1e-10:
                return False
            continue
        v1, v2 = (lower-origin)/delta, (upper-origin)/delta
        lo, hi = max(lo, min(v1, v2)), min(hi, max(v1, v2))
        if hi-lo < 1e-10:
            return False
    return hi > 1e-10 and lo < 1-1e-10


class StaticFloor:
    def __init__(self, scene, body_radius=.3, start=(15, 30)):
        self.scene = scene
        self.body_radius = body_radius
        self.surfaces = [s['rect'] for s in scene['walk_surfaces']]
        self.solids = ([w['rect'] for w in scene['walls']] +
                       [f['rect'] for f in scene['fixtures'] if f['blocks_navigation']])
        xmin = math.floor(min(r[0] for r in self.surfaces))
        xmax = math.ceil(max(r[0]+r[2] for r in self.surfaces))
        ymin = math.floor(min(r[1] for r in self.surfaces))
        ymax = math.ceil(max(r[1]+r[3] for r in self.surfaces))
        cells = {(x, y) for x in range(xmin, xmax) for y in range(ymin, ymax)
                 if self.legal((x+.5, y+.5), body_radius)}
        self.reached = set()
        if start in cells:
            self.reached.add(start)
            todo = deque([start])
            while todo:
                x, y = todo.popleft()
                for nxt in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if nxt in cells and nxt not in self.reached:
                        self.reached.add(nxt); todo.append(nxt)

    def legal(self, point, body_radius=0):
        if not any(inside_rect(point, r) for r in self.surfaces):
            return False
        if any(inside_rect(point, r) or distance_to_rect(point, r) < body_radius-1e-9
               for r in self.solids):
            return False
        # Boundary clearance of the union; do not count a centre whose body is
        # outside the authored world. Eight probes suffice for this axis-grid
        # reference and are not a runtime curved-boundary collision proof.
        if body_radius:
            for i in range(8):
                probe=(point[0]+body_radius*math.cos(i*math.pi/4),
                       point[1]+body_radius*math.sin(i*math.pi/4))
                if not any(inside_rect(probe, r) for r in self.surfaces):
                    return False
        return True

    def visible(self, center, point):
        return not any(segment_hits_solid(center, point, r) for r in self.solids)

    def reachable(self, point):
        return (math.floor(point[0]), math.floor(point[1])) in self.reached


def compensate_circle(floor, center, nominal_radius, maximum_factor=1.5,
                      grid_step=.025, tolerance_fraction=.02):
    """Choose the smallest visible, reachable radius achieving the target area.

    Conservative occupancy and LOS are applied BEFORE measuring candidate
    area. No points behind fixtures or in isolated rooms become compensation.
    Radius expansion neither changes DPS, status count nor target cap.
    """
    if nominal_radius < 1:
        raise ValueError('a circular effect must have at least one-tile radius')
    if not 1 <= maximum_factor <= 1.5:
        raise ValueError('compensation is bounded at 1.5 times nominal radius')
    maximum_radius = nominal_radius * maximum_factor
    target = math.pi*nominal_radius**2
    center_ok = floor.legal(center, floor.body_radius) and floor.reachable(center)
    area_per_point=grid_step**2
    distances=[]
    sampled_floor_distances=[]
    side=math.ceil(2*maximum_radius/grid_step)
    for i in range(side):
        x=center[0]-maximum_radius+(i+.5)*grid_step
        for j in range(side):
            y=center[1]-maximum_radius+(j+.5)*grid_step
            distance=math.hypot(x-center[0], y-center[1])
            if distance > maximum_radius:
                continue
            p=(x,y)
            if not floor.legal(p) or not floor.reachable(p) or not floor.visible(center,p):
                continue
            sampled_floor_distances.append(distance)
            if floor.legal(p, floor.body_radius):
                distances.append(distance)
    distances.sort(); sampled_floor_distances.sort()
    nominal_area=bisect_right(distances,nominal_radius)*area_per_point
    required_count=math.ceil((1-tolerance_fraction)*target/area_per_point)
    available=len(distances)
    if center_ok and available >= required_count:
        candidate=max(nominal_radius,distances[required_count-1])
        effective_radius=min(maximum_radius, math.ceil((candidate-1e-10)/grid_step)*grid_step)
        accepted=True
    else:
        effective_radius=maximum_radius
        accepted=False
    effective_area=bisect_right(distances,effective_radius)*area_per_point
    floor_area=bisect_right(sampled_floor_distances,effective_radius)*area_per_point
    return {
        'center':list(center), 'nominal_radius_tiles':nominal_radius,
        'effective_radius_tiles':round(effective_radius,4),
        'maximum_radius_tiles':round(maximum_radius,4),
        'target_area_tiles2':round(target,6),
        'nominal_usable_body_center_area_tiles2':round(nominal_area,6),
        'effective_usable_body_center_area_tiles2':round(effective_area,6),
        'effective_visible_reachable_floor_area_tiles2':round(floor_area,6),
        'restored_target_fraction':round(effective_area/target,6),
        'center_legal_and_connected':center_ok,
        'area_target_met':accepted,
        'circular_mode_allowed_at_this_projection':accepted,
        'requires_other_projection_or_anchor':not accepted,
        'body_radius_tiles':floor.body_radius, 'grid_step_tiles':grid_step,
        'area_tolerance_fraction':tolerance_fraction,
        'collision_rule':'center in effect circle; body avoids solids; no requirement body fit inside effect circle',
        'scope':'static body-clear floor and straight LOS; dynamic enemies, height and runtime nav still required'
    }


def geometry_examples(traps, maps, nominal_radius=1, grid_step=.025):
    scene=next(s for s in maps['scenes'] if s['id']=='MAP_STORE')
    floor=StaticFloor(scene)
    fixtures={f['id']:f for f in scene['fixtures']}
    rows=[]
    for example in traps['map_constraints']['side_hung_projection_examples']:
        row=compensate_circle(floor, example['field_center'], nominal_radius,grid_step=grid_step)
        row.update(anchor=example['tower_anchor_id'],fixture=example['fixture_id'],
                   anchor_in_own_fixture=inside_rect(example['anchor_position'],fixtures[example['fixture_id']]['rect']))
        rows.append(row)
    return {'examples':rows,'minimum_radius':nominal_radius,
            'accepted_count':sum(r['area_target_met'] for r in rows),
            'scope':'deterministic static area compensation reference; not gameplay integration'}


def geometry_counterexamples():
    """Empty floor stays nominal; wall cannot become useful extra area."""
    empty={'walk_surfaces':[{'rect':[0,0,10,10]}],'walls':[],'fixtures':[]}
    f=StaticFloor(empty,start=(5,5))
    open_circle=compensate_circle(f,(5.5,5.5),1)
    # A one-wide corridor permits a .3-radius enemy, but only .4 width of
    # available centres. Even r=1.5 cannot recreate a pi-square-tile area.
    narrow={'walk_surfaces':[{'rect':[0,0,10,10]}],
            'walls':[{'rect':[0,0,5,10]},{'rect':[6,0,4,10]}],
            'fixtures':[]}
    f2=StaticFloor(narrow,start=(5,5))
    # A connected real corridor still lacks sufficient visible area.
    confined=compensate_circle(f2,(5.5,5.5),1)
    blocked={'walk_surfaces':[{'rect':[0,0,10,10]}],
             'walls':[{'rect':[4,0,1,10]}],'fixtures':[]}
    f3=StaticFloor(blocked,start=(2,5))
    through_wall=f3.visible((3.5,5.5),(5.5,5.5))
    return {'unobstructed':open_circle,'narrow_insufficient_area_projection':confined,
            'solid_wall_line_of_sight_is_clear':through_wall,
            'reference_body_does_not_expand_empty_circle':open_circle['effective_radius_tiles']==1,
            'cannot_compensate_through_wall':not through_wall}


def _closest_point_to_rect(point, rect):
    x,y,w,h=rect
    return (max(x,min(point[0],x+w)),max(y,min(point[1],y+h)))


def _closest_rect_pair(a,b):
    pair=[]
    for ai,bi,size in ((a[0],b[0],(a[2],b[2])),(a[1],b[1],(a[3],b[3]))):
        ae,be=ai+size[0],bi+size[1]
        if ae<bi:pair.append((ae,bi))
        elif be<ai:pair.append((ai,be))
        else:
            midpoint=(max(ai,bi)+min(ae,be))/2
            pair.append((midpoint,midpoint))
    return (pair[0][0],pair[1][0]),(pair[0][1],pair[1][1])


def electric_store_fixture(traps,maps):
    """Actual store two-pool corridor, including the third appliance relay.

    This establishes one static legal map example. It does not assert an enemy
    will stand at those positions or that gameplay AI has been integrated.
    """
    scene=next(s for s in maps['scenes'] if s['id']=='MAP_STORE')
    floor=StaticFloor(scene)
    units={'POOL_A':(24.5,12.5),'POOL_B':(24.5,14.5)}
    devices={d['id']:tuple(d['rect']) for d in traps['appliances'] if d['design_enabled']}
    all_ids=[*units,*devices]
    edges=[];geometry=[]
    for i,aid in enumerate(all_ids):
        for bid in all_ids[i+1:]:
            if aid in units and bid in units:a,b=units[aid],units[bid]
            elif aid in units:a,b=units[aid],_closest_point_to_rect(units[aid],devices[bid])
            elif bid in units:a,b=_closest_point_to_rect(units[bid],devices[aid]),units[bid]
            else:a,b=_closest_rect_pair(devices[aid],devices[bid])
            distance=math.dist(a,b);visible=floor.visible(a,b)
            eligible=distance<=2.5+1e-9 and visible
            geometry.append({'a':aid,'b':bid,'surface_or_unit_distance_tiles':round(distance,6),
                             'segment':[list(a),list(b)],'static_los_clear':visible,'edge':eligible})
            if eligible:edges.append((aid,bid))
    adjacency={n:set() for n in all_ids}
    for a,b in edges:adjacency[a].add(b);adjacency[b].add(a)
    reached={'POOL_A'};todo=deque(['POOL_A'])
    while todo:
        for nxt in adjacency[todo.popleft()]:
            if nxt not in reached:reached.add(nxt);todo.append(nxt)
    local=[]
    for uid in units:
        n=1+sum(v in units for v in adjacency[uid])
        e=sum(v in devices for v in adjacency[uid])
        local.append({'unit_id':uid,'N_including_self':n,'E_local_powered_devices':e,
                      'D6_raw_damage_per_overload':6*(n+e)})
    return {'unit_positions':{k:list(v) for k,v in units.items()},
            'unit_body_clear_and_reachable':{k:floor.legal(v,.3) and floor.reachable(v) for k,v in units.items()},
            'powered_registered_appliances':list(devices),'edge_geometry':geometry,
            'reachable_component_from_A':sorted(reached),'local_formula_counts':local,
            'third_appliance_note':'AP_COLD_CABINET is reachable through AP_FREEZER, but outside each pool local2.5 range; it remains a relay node and is not counted as a third local E.',
            'same_circuit_used_as_edge':False,
            'scope':'static authored-map fixture for two independent charged health pools; no predicted enemy behavior or runtime integration'}
