#!/usr/bin/env python3
"""Check authored V0.5 overlay geometry, not a playable client or an AI test."""
import json
import math
from pathlib import Path

from validate_maps import cell, cells, graph, shortest

ROOT = Path(__file__).resolve().parents[1]


def validate():
    base = json.loads((ROOT / 'content/maps.json').read_text())
    data = json.loads((ROOT / 'content/map_mechanics_v05.json').read_text())
    scene = next(s for s in base['scenes'] if s['id'] == data['scene_id'])
    walk = graph(scene)
    floor = set().union(*(cells(r['rect']) for r in scene['walk_surfaces']))
    anchors = {a['role']: a['position'] for a in scene['anchors']}
    objects = {o['id']: o for o in data['objects']}
    positions = {**anchors, **{k: o['player_position'] for k, o in objects.items()}}
    start = cell(anchors['front_door'])
    errors, routes, water, defense, probes, limits = [], [], [], [], [], []
    checks = 0

    def check(ok, message):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(message)

    def reachable(point, identifier, grid=walk, origin=start):
        check(shortest(grid, origin, cell(point)) is not None,
              identifier + ': interaction/entry point blocked or disconnected')

    def route_length(a, b, grid=walk):
        result = shortest(grid, cell(a), cell(b))
        return None if result is None else len(result) - 1

    for field in ['objects', 'spatial_groups', 'wet_regions', 'defense_groups', 'entry_profiles']:
        ids = [v['id'] for v in data[field]]
        check(len(ids) == len(set(ids)), field + ': duplicate ids')
    check(not data['client_implemented'], 'Overlay must not claim a playable client')

    for o in data['objects']:
        check(o['owner_anchor'] in anchors, o['id'] + ': unknown anchor')
        check(not o['blocks_navigation'], o['id'] + ': overlay silently adds obstacle')
        check(cell(o['object_position']) in floor, o['id'] + ': object outside authored floor/wall')
        reachable(o['player_position'], o['id'])
        check(math.dist(o['object_position'], o['player_position']) <= o['interaction_radius_tiles'],
              o['id'] + ': object beyond interaction reach')
        if o.get('reuses_attachment'):
            check(o['reuses_attachment'] in {v['id'] for v in scene['fixed_attachments']},
                  o['id'] + ': missing inherited attachment')
        for p in [o[k] for k in ['guest_wait_position', 'window_take_position'] if k in o]:
            reachable(p, o['id'] + ': guest position')

    curtain = objects['OBJ_MIRROR_CURTAIN']
    a, b = curtain['rule_occlusion_segment']
    p, q = curtain['sight_test_player'], curtain['sight_test_monster']
    def orient(a, b, p):
        return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    reachable(p, 'F60: sight player')
    reachable(q, 'F60: sight target')
    check(orient(a,b,p)*orient(a,b,q) < 0 and orient(p,q,a)*orient(p,q,b) < 0,
          'F60 curtain must cut the authored player-to-entity sight, not only cover the mirror')
    parcel = objects['OBJ_PUBLIC_PARCEL']
    public_rect = cells(next(z['rect'] for z in scene['zones'] if z['id'] == 'Z01'))
    check(cell(parcel['guest_wait_position']) in public_rect, 'F17 visitor must stay in public area')
    check(math.dist(parcel['guest_wait_position'], parcel['player_position']) >= parcel['min_guest_distance_tiles'],
          'F17 visitor separation invalid')
    for q in data['spatial_groups']:
        check(q['owner_anchor'] in anchors, q['id'] + ': unknown owner')
        check(not q['blocks_navigation'], q['id'] + ': marker unexpectedly blocks path')
        for p in q['positions']:
            reachable(p, q['id'])
        if q.get('max_adjacent_distance_tiles'):
            check(all(math.dist(a, b) <= q['max_adjacent_distance_tiles']
                      for a, b in zip(q['positions'], q['positions'][1:])),
                  q['id'] + ': marker spacing exceeds visible range')
        check(q['owner_anchor'] != 'floor_markers' or q['id'] == 'GRP_LESHY_MARKERS',
              q['id'] + ': generic floor_markers cannot serve unrelated mechanics')

    all_wet = set()
    for region in data['wet_regions']:
        wet = {tuple(p) for p in region['wet_cells']}
        source, target, cut = map(tuple, [region['source_cell'], region['target_cell'], region['cut_cell']])
        check(len(wet) == len(region['wet_cells']), region['id'] + ': duplicate wet cells')
        check(wet <= walk, region['id'] + ': wet region includes wall or fixture')
        check(not wet & all_wet, region['id'] + ': independent regions unexpectedly touch same cell')
        all_wet |= wet
        check({source, target, cut} <= wet, region['id'] + ': source/target/cut outside region')
        check(shortest(wet, source, target) is not None, region['id'] + ': initial wet line disconnected')
        check(shortest(wet - {cut}, source, target) is None, region['id'] + ': cut does not isolate target')
        dry = walk - wet
        for label in ['dry_interact_position', 'dry_safe_position']:
            reachable(region[label], region['id'] + ':' + label, grid=dry)
            check(cell(region[label]) not in wet, region['id'] + ': dry control is wet')
        check(math.dist(region['dry_interact_position'], [cut[0] + .5, cut[1] + .5])
              <= region['cut_interaction_max_tiles'], region['id'] + ': cut out of dry-side reach')
        for role in region['dry_required_roles']:
            check(role in anchors, region['id'] + ': unknown protected anchor')
            reachable(anchors[role], region['id'] + ':' + role, grid=dry)
        for o in objects.values():
            check(cell(o['player_position']) not in wet, region['id'] + ': wets essential control ' + o['id'])
        check(not wet & {tuple(p) for p in region.get('forbidden_wet_cells', [])},
              region['id'] + ': floods protected staff slot')
        for p in region.get('protected_source_cells', []):
            check(tuple(p) != cut and shortest(wet - {cut}, source, tuple(p)) is not None,
                  region['id'] + ': cut destroys protected source flow')
        water.append({'id': region['id'], 'wet_cells': len(wet), 'cut_disconnects_target': True,
                      'dry_controls_and_required_paths_checked': True})

    for group in data['defense_groups']:
        points = group['player_positions'] + [group['board_pickup_position'], group['safe_position']]
        for p in points:
            reachable(p, group['id'])
            check(cell(p) in cells(scene['interior_rect']), group['id'] + ': player control outside store')
            check(not any(cell(p) in cells(r) for r in group['dive_strips']),
                  group['id'] + ': interior control in exterior dive strip')
        retreat = [route_length(p, group['safe_position']) for p in group['player_positions']]
        check(all(v is not None for v in retreat), group['id'] + ': no retreat route')
        seconds = group['max_player_to_board_to_target_tiles'] / 3 + group['push_board_seconds'] + max(v or 0 for v in retreat) / 3
        check(seconds <= group['warning_seconds'], group['id'] + ': complete board-and-retreat exceeds warning')
        check({tuple(p) for p in group['interior_impact_cells']} <= walk and
              cell(group['safe_position']) not in {tuple(p) for p in group['interior_impact_cells']},
              group['id'] + ': inside impact cells or safe retreat are invalid')
        check(seconds + group['hands_release_seconds_max'] <= group['warning_seconds'],
              group['id'] + ': no allowance to put down a carried object')
        defense.append({'id': group['id'], 'maximum_authored_seconds': round(seconds, 2),
                        'warning_seconds': group['warning_seconds'], 'runtime_approach_limit_tiles': group['max_player_to_board_to_target_tiles']})

    for entry in data['entry_profiles']:
        for p in entry['positions']:
            reachable(p, entry['id'])
        for a, b in zip(entry['positions'], entry['positions'][1:]):
            check(route_length(a, b) is not None, entry['id'] + ': disconnected approach')
        check({'player_distance', 'doors_current', 'not_cut_only_required_route', 'work_and_escape_budget', 'active_pursuer_cap'}
              <= set(entry['runtime_gate']), entry['id'] + ': missing dynamic placement gate')
        check(entry['activation_min_distance_tiles'] >= 5, entry['id'] + ': no safe hostile activation separation')
    f12 = next(v for v in data['entry_profiles'] if v['id'] == 'EP_F12_RESERVED')
    check(f12['positions'][0] == scene['lure_route']['spawn'], 'F12 authored spawn contract changed')

    for corridor in data['main_corridors']:
        check(cells(corridor['rect']) <= walk, corridor['id'] + ': claimed wide corridor contains obstacle')
        width = corridor['rect'][2 if corridor['orientation'] == 'vertical' else 3]
        check(width >= corridor['min_width'], corridor['id'] + ': insufficient declared transverse width')

    def eroded(radius):
        # Circle against axis-aligned blocked tile squares, including outside floor.
        reach = math.ceil(radius + .5)
        unsafe_offsets = [(dx, dy) for dx in range(-reach, reach + 1)
                          for dy in range(-reach, reach + 1)
                          if math.hypot(max(abs(dx) - .5, 0), max(abs(dy) - .5, 0)) < radius - 1e-9]
        return {p for p in walk if all((p[0] + dx, p[1] + dy) in walk for dx, dy in unsafe_offsets)}

    for probe in data['clearance_probes']:
        filtered = eroded(probe['radius_tiles'])
        interior = cells(scene['interior_rect'])
        if probe['scope'] == 'interior':
            filtered &= interior
        path = shortest(filtered, cell(probe['start']), cell(probe['end']))
        length = len(path) - 1 if path else None
        check(path is not None, probe['id'] + ': radius probe cannot pass; do not claim a wide route')
        probes.append({'id': probe['id'], 'radius_tiles': probe['radius_tiles'], 'path_tiles': length,
                       'uses_exterior': any(p not in interior for p in path) if path else None,
                       'meaning': 'Specific center-path clearance only, not all store aisles'})
    for limit in data['known_geometry_limits']:
        filtered = eroded(limit['radius_tiles']) & cells(scene['interior_rect'])
        path = shortest(filtered, cell(limit['start']), cell(limit['end']))
        check((path is not None) == limit['expected_reachable'],
              limit['id'] + ': update the authored limitation; geometry has changed')
        check(bool(limit.get('admission_gate')), limit['id'] + ': known risk lacks admission gate')
        limits.append({'id': limit['id'], 'radius_tiles': limit['radius_tiles'],
                       'interior_route_reachable': path is not None, 'admission_gate': limit['admission_gate']})
    for niche in data['service_recesses']:
        check({tuple(p) for p in niche['cells']} <= walk, niche['id'] + ': declared service recess blocked')

    for panel in data.get('station_local_panels', []):
        check(panel['anchor'] in anchors and panel['uses_same_interaction_position'] and
              not panel['new_world_positions'] and len(panel['selector_ids']) <= 3,
              panel['id'] + ': local panel must bind an existing reachable station')
    for route in data['route_checks']:
        names = [route['start']] + route['via'] + [route['end']]
        check(all(k in positions for k in names), route['id'] + ': unknown binding')
        lengths = [route_length(positions[a], positions[b]) for a, b in zip(names, names[1:])]
        check(all(n is not None for n in lengths), route['id'] + ': no local path')
        seconds = sum(n or 0 for n in lengths) / route['speed']
        check(seconds <= route['max_seconds'], route['id'] + ': local movement budget exceeded')
        routes.append({'id': route['id'], 'path_tiles': sum(n or 0 for n in lengths),
                       'movement_seconds': round(seconds, 2), 'max_seconds': route['max_seconds']})

    return {'status': 'FAIL' if errors else 'PASS', 'checks': checks, 'errors': errors,
            'counts': {k: len(data[k]) for k in ['objects', 'spatial_groups', 'wet_regions', 'defense_groups', 'entry_profiles']},
            'water': water, 'defense': defense, 'routes': routes, 'clearance_probes': probes,
            'known_geometry_limits': limits,
            'limitations': data['validation_scope']}


if __name__ == '__main__':
    report = validate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(report['status'] != 'PASS')
