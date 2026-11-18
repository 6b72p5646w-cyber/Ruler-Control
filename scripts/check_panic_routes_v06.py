#!/usr/bin/env python3
"""Reproduce static panic route counterexamples without changing the map.

Uses the repository's own four-neighbour graph/shortest-path implementation.
Only movement at the normal empty-handed walk speed plus the old 8-second
stationary stabilization cost is counted. No enemy, input delay or interaction
overhead is added; a result above 20 seconds is therefore already a counterexample.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/panic_route_counterexamples_v06.json'
module_path = ROOT/'scripts/validate_maps.py'
spec = importlib.util.spec_from_file_location('panic_map_validation', module_path)
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)
map_path = ROOT/'content/maps.json'
overlay_path = ROOT/'content/map_mechanics_v05.json'
data = json.loads(map_path.read_text())
scene = next(s for s in data['scenes'] if s['id']=='MAP_STORE')
anchors = {a['role']:a['position'] for a in scene['anchors']}
overlay = json.loads(overlay_path.read_text())
standing = next(w for w in overlay['wet_regions'] if w['id']=='WET_CHAIR')['dry_safe_position']
walk_speed = 3.0
stabilization_seconds = 8.0
old_panic_seconds = 20.0

def route(case_id,start,targets,closed=()):
    walkable = nav.graph(scene,closed)
    candidates=[]
    for name,target in targets:
        path=nav.shortest(walkable,nav.cell(start),nav.cell(target))
        if path is not None:candidates.append((len(path)-1,name,path,target))
    distance,name,path,target=min(candidates,key=lambda v:(v[0],v[1]))
    movement=distance/walk_speed
    total=movement+stabilization_seconds
    return {
      'id':case_id,'start_position':start,'chosen_target':name,'target_position':target,
      'candidate_targets':[{'name':n,'position':p} for n,p in targets],
      'closed_doors':list(closed),'all_other_doors_open':True,
      'length_tiles':distance,'walk_speed_tiles_per_world_second':walk_speed,
      'movement_world_seconds':round(movement,6),
      'stabilization_world_seconds':stabilization_seconds,
      'minimum_total_world_seconds':round(total,6),
      'old_panic_deadline_world_seconds':old_panic_seconds,
      'exceeds_deadline_by_world_seconds':round(total-old_panic_seconds,6),
      'is_counterexample':total>old_panic_seconds,
      'path_cell_centers':[[x+.5,y+.5] for x,y in path]
    }

counter=[('safe_counter',anchors['safe_counter'])]
both=counter+[('existing_employee_standing_recovery',standing)]
cases=[
 route('DUMPSTER_COUNTER_OPEN',anchors['dumpster'],counter),
 route('DUMPSTER_COUNTER_REAR_CLOSED',anchors['dumpster'],counter,['DOOR_REAR']),
 route('REAR_DOOR_COUNTER_OPEN',anchors['rear_door'],counter),
 route('EAST_ALLEY_TWO_EXISTING_RECOVERY_POINTS',[33.5,11.5],both)
]
result={
 'status':'CONFIRMED_STATIC_COUNTEREXAMPLES' if all(x['is_counterexample'] for x in cases) else 'RECHECK_REQUIRED',
 'map_scene':'MAP_STORE',
 'input_files':[
   {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
   for p in [map_path,overlay_path,module_path]
 ],
 'algorithm':'BFS on existing four-neighbour walkable cells from walk_surfaces minus walls/fixtures and explicitly closed doors; use repository validate_maps.graph/cell/shortest.',
 'neighbor_order':[[1,0],[-1,0],[0,1],[0,-1]],
 'assumptions':[
   'Empty-handed normal walking at 3 tiles per world second; no sprint is required or assumed.',
   'No moving enemies, no reaction delay, no input/door-opening overhead and no additional rule obstruction.',
   'Existing employee standing-recovery position is read from current WET_CHAIR dry_safe_position, not invented.',
   'The second target is a proposed reuse of an already-authored standing recovery position; adding it alone still does not cover the map within 20 seconds.',
   'These are lower-bound timing counterexamples to a station-only 8-second recovery under a 20-second panic deadline, not a full navigation or dynamic playtest.'
 ],
 'cases':cases,
 'recommended_fix':'Retain ordinary workstation recovery, but make the once-per-night 8-world-second emergency stabilization a portable cumulative action; permit normal walking, keep world/enemies running, pause progress during conflicting actions and consume the free use only on successful recovery.'
}
OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':result['status'],'output':str(OUTPUT),'cases':[{'id':c['id'],'tiles':c['length_tiles'],'seconds':c['minimum_total_world_seconds']} for c in cases]},ensure_ascii=False,indent=2))
