#!/usr/bin/env python3
"""Validate authored tile geometry and route budgets; not an engine/playtest."""
from collections import deque
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cells(rect):
    x, y, w, h = rect
    return {(i, j) for i in range(x, x+w) for j in range(y, y+h)}


def graph(scene, closed=()):
    floor = set().union(*(cells(r['rect']) for r in scene['walk_surfaces']))
    blocked = set().union(*(cells(r['rect']) for r in scene['walls']+scene['fixtures']))
    for door in scene['doors']:
        if door['id'] in closed:
            blocked |= cells(door['rect'])
    return floor - blocked


def cell(position):
    return tuple(math.floor(v) for v in position)


def shortest(walkable, start, end):
    if start not in walkable or end not in walkable:
        return None
    queue, previous = deque([start]), {start: None}
    while queue:
        current = queue.popleft()
        if current == end:
            path = []
            while current is not None:
                path.append(current)
                current = previous[current]
            return path[::-1]
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            n=(current[0]+dx,current[1]+dy)
            if n in walkable and n not in previous:
                previous[n]=current
                queue.append(n)
    return None


def validate():
    data=json.loads((ROOT/'content/maps.json').read_text())
    errors, results, local_results = [], [], []
    view=data['camera']['world_view_tiles']
    store=next(s for s in data['scenes'] if s['id']=='MAP_STORE')
    interior=store['interior_rect']
    ratio=interior[2]*interior[3]/(view[0]*view[1])
    if ratio != 5: errors.append('Store footprint must equal five baseline world viewport areas')
    zone_cells = [cells(z['rect']) for z in store['zones']]
    if set().union(*zone_cells)!=cells(interior) or sum(map(len,zone_cells))!=len(cells(interior)):
        errors.append('Store zones must exactly partition interior footprint')
    for scene in data['scenes']:
        walkable=graph(scene)
        roles={a['role']:a for a in scene['anchors']}
        if len(roles)!=len(scene['anchors']): errors.append(scene['id']+': duplicate anchor roles')
        start=cell(roles['front_door' if scene['id']=='MAP_STORE' else 'exit']['position'])
        floor=set().union(*(cells(r['rect']) for r in scene['walk_surfaces']))
        for obj in scene['walls']+scene['fixtures']:
            if not cells(obj['rect'])<=floor: errors.append(scene['id']+': fixture outside floor: '+obj['id'])
        for a in scene['anchors']+scene.get('sockets',[]):
            if shortest(walkable,start,cell(a['position'])) is None:
                errors.append(scene['id']+': blocked or disconnected anchor '+a['role'])
        routes=[]
        for r in scene['route_checks']:
            g=graph(scene,r.get('closed_doors',[]))
            whole=[]; segment_lengths=[]
            for a,b in zip(r['roles'],r['roles'][1:]):
                path=shortest(g,cell(roles[a]['position']),cell(roles[b]['position']))
                if path is None:
                    errors.append(r['id']+': no route');break
                segment_lengths.append(len(path)-1)
                whole+=path if not whole else path[1:]
            else:
                length=len(whole)-1
                speeds=r.get('segment_speeds',[r['speed']]*len(segment_lengths))
                if len(speeds)!=len(segment_lengths):errors.append(r['id']+': segment speeds incomplete')
                sec=sum(length/speed for length,speed in zip(segment_lengths,speeds))
                if sec>r['max_seconds']:errors.append(r['id']+': movement budget exceeded')
                routes.append({'id':r['id'],'name':r['name'],'length_tiles':length,'movement_seconds':round(sec,2),'speed':r['speed'],'segment_speeds':speeds,'closed_doors':r.get('closed_doors',[]),'path':[[x+.5,y+.5] for x,y in whole]})
        results.append({'scene':scene['id'],'anchors_reachable':len(roles),'walkable_tiles':len(walkable),'routes':routes})
    roles={a['role']:a for a in store['anchors']}
    band=store['placement_contract']['distance_band']
    a=roles[store['placement_contract']['counter_work_role']]['position']
    b=roles[store['placement_contract']['distance_customer_role']]['position']
    separation=math.dist(a,b)
    if not band[0]<=separation<=band[1]:errors.append('Counter work/distance condition is contradictory')
    lure=store['lure_route'];points=[lure['spawn']]+lure['bait_points']
    for a,b in zip(points,points[1:]):
        if math.dist(a,b)>lure['bait_detection_radius']:errors.append('F12 authored lure gap exceeds detection')
        if shortest(graph(store),cell(a),cell(b)) is None:errors.append('F12 lure point unreachable')
    if len(lure['bait_points'])>lure['capacity']:errors.append('F12 lure needs more than guaranteed clip box')
    if cell(lure['bait_points'][-1]) not in cells(lure['guaranteed_exit_rect']):errors.append('F12 final bait not in exit zone')
    spawn_distance=math.dist(lure['spawn'],lure['tutorial_player_start'])
    if spawn_distance<store['placement_contract']['no_spawn_within_tiles']:errors.append('F12 tutorial violates spawn separation')
    g=graph(store); attachments={a['id']:a for a in store['fixed_attachments']}
    for attachment in attachments.values():
        for p in attachment.get('player_positions',[]):
            if shortest(g,cell(roles['front_door']['position']),cell(p)) is None:
                errors.append(attachment['id']+': inaccessible local control')
    def length(a,b):
        p=shortest(g,cell(a),cell(b))
        if p is None:
            errors.append('Disconnected local timing path');return 99999
        return len(p)-1
    rear=attachments['ATT12']
    seconds=2*length(rear['window_interact_position'],rear['drain_control_position'])/3+rear['control_action_seconds']+rear['close_window_seconds']
    if seconds>rear['window_read_seconds']:errors.append('F10 drain-and-close cannot fit reading window')
    local_results.append({'id':'F10','timed_local_seconds':round(seconds,2),'window_seconds':6})
    box=attachments['ATT13'];seconds=length(*box['player_positions'])/3+box['shutter_seconds']
    if seconds>box['attention_window_seconds']:errors.append('F32 counter box window impossible')
    if math.dist(box['player_positions'][0],box['box_position'])>1:errors.append('F32 counter item out of reach')
    if min(math.dist(p,box['guest_position']) for p in box['player_positions'])<2.5:errors.append('F32 unsafe control placement')
    local_results.append({'id':'F32','timed_local_seconds':round(seconds,2),'window_seconds':4})
    marks=attachments['ATT09']['positions']
    if any(math.dist(a,b)>4 for a,b in zip(marks,marks[1:])):errors.append('F40 fog markers farther than four tiles')
    windows=attachments['ATT14']
    for group in windows['groups']:
        for p in group['player_positions']+[group['board_pickup_position'],group['safe_position']]:
            if cell(p) not in g:errors.append('F50 control inside blocked cell')
        # The maximum admitted approach already includes pickup-to-target movement.
        seconds=windows['max_player_to_board_to_target_tiles']/3+windows['push_board_seconds']+max(length(p,group['safe_position']) for p in group['player_positions'])/3
        if seconds>windows['warning_seconds']:errors.append('F50 warned sequence does not fit')
        local_results.append({'id':'F50_'+group['id'],'timed_local_seconds':round(seconds,2),'window_seconds':8})
    crossing=attachments['ATT15'];op=crossing['operations']
    crossing_length=length(crossing['crossing_start'],crossing['crossing_end'])
    seconds=(2*length(crossing['local_lever_position'],crossing['board_player_position'])/3+
             crossing_length/2.4+crossing_length/3+sum(op.values()))
    if crossing_length>6 or seconds>crossing['maintenance_seconds']:errors.append('F57 complete maintenance window impossible')
    local_results.append({'id':'F57','timed_local_seconds':round(seconds,2),'window_seconds':8,'box_path_tiles':crossing_length})
    chair=attachments['ATT16']
    if any(tuple(n) not in g for n in chair['wet_nodes']):errors.append('F52 wet branch inside blocked cell')
    if max(math.dist([x+.5,y+.5],roles['rest_chair']['position']) for x,y in chair['wet_nodes'])>4:errors.append('F52 wet branch outside local cue range')
    designs_path=ROOT/'content/encounter_designs.json'
    if designs_path.exists():
        for c in json.loads(designs_path.read_text())['encounters']:
            b=c.get('local_spatial_bindings',{})
            if 'guest_position_proposal' in b:
                player=roles[b['player_anchor']]['position'];guest=b['guest_position_proposal']
                if cell(guest) not in g or math.dist(player,guest)<b['min_guest_distance_tiles']:
                    errors.append(c['id']+': guest and workstation incompatible')
                if 'parcel_position_proposal' in b and math.dist(player,b['parcel_position_proposal'])>b['item_interaction_max_tiles']:
                    errors.append(c['id']+': parcel out of reach')
    return {'status':'PASS' if not errors else 'FAIL','viewport_ratio':ratio,'counter_distance_tiles':separation,'scenes':results,'errors':errors,
            'tutorial_spawn_distance_tiles':round(spawn_distance,2),'local_timing_checks':local_results,
            'limits':'Static four-neighbor tile paths with doors fixed at scenario start. No moving enemies, collision radius sweep, timing AI, field-of-view renderer, touch UI or arbitrary event combinations were simulated.'}


if __name__=='__main__':
    report=validate()
    (ROOT/'docs/map_validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    summary={k:v for k,v in report.items() if k!='scenes'}
    summary['routes']=[{k:v for k,v in r.items() if k!='path'} for s in report['scenes'] for r in s['routes']]
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['errors']))
