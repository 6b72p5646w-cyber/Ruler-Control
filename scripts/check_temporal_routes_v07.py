#!/usr/bin/env python3
"""Reproduce the F42 local-route and F27 acceptance-window examples.

Read-only, no repository changes. This is not a full encounter simulator.
The offer table intentionally assumes no QTE budget/world offset; runtime must
check the world-patience boundary and budget boundary separately.
"""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
spec=importlib.util.spec_from_file_location('map_nav',ROOT/'scripts/validate_maps.py')
nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
maps=read('content/maps.json')
scene=next(x for x in maps['scenes'] if x['id']=='MAP_STORE')
roles={x['role']:x['position'] for x in scene['anchors']}
walkable=nav.graph(scene,())
cards={x['id']:x for x in read('content/encounters_v05.json')['encounters']}
store=read('content/store_systems_v05.json')
f42=cards['F42']['runtime_parameters']
carry_speed=2.4;walk_speed=3.0
pickup_seconds=1.5;drop_seconds=1.5
gate_seconds=f42['manual_gate_open_world_seconds']+f42['manual_gate_close_world_seconds']
routes=[]
for start,end in [('rear_door','loading_bay'),('rear_door','dumpster'),('receiving','rear_threshold'),('rear_door','rear_threshold')]:
 path=nav.shortest(walkable,nav.cell(roles[start]),nav.cell(roles[end]))
 if path is None:raise RuntimeError(f'No route: {start} to {end}')
 tiles=len(path)-1
 before_handling=tiles/carry_speed+tiles/walk_speed+gate_seconds
 with_handling=before_handling+pickup_seconds+drop_seconds
 routes.append({'start':start,'end':end,'tiles_one_way':tiles,
  'carry_out_world_seconds':round(tiles/carry_speed,6),
  'walk_back_world_seconds':round(tiles/walk_speed,6),
  'gate_open_close_world_seconds':gate_seconds,
  'before_pickup_drop_world_seconds':round(before_handling,6),
  'pickup_plus_drop_world_seconds':pickup_seconds+drop_seconds,
  'total_world_seconds':round(with_handling,6),
  'safe_window_world_seconds':f42['safe_low_pressure_world_seconds'],
  'fits_with_declared_handling':with_handling<=f42['safe_low_pressure_world_seconds'],
  'path_cell_centers':[[x+.5,y+.5] for x,y in path]})
arrival=store['omens']['arrival_second_in_phase']
phase_seconds=store['omens']['phase_seconds']
patience=store['service']['normal_order_patience_world_seconds']
offers=[]
for fid in ['F06','F09','F27','F44','F48','F51']:
 duration=cards[fid]['runtime_parameters']['accepted_special_order_deadline_world_seconds']
 waiting_expiry=arrival+patience
 last_budget_accept=phase_seconds-duration
 effective=min(waiting_expiry,last_budget_accept)
 offers.append({'id':fid,'arrival_phase_budget_second':arrival,
  'arrival_world_second_in_no_offset_example':arrival,
  'ordinary_world_patience_seconds':patience,
  'ordinary_expiry_in_no_offset_example':waiting_expiry,
  'required_contract_seconds':duration,
  'last_phase_budget_second_for_acceptance':last_budget_accept,
  'effective_expiry_in_no_offset_example':effective,
  'effective_offer_window_world_seconds':max(0,effective-arrival),
  'invalid_waiting_tail_without_cutoff_seconds':max(0,waiting_expiry-effective)})
inputs=['content/maps.json','content/encounters_v05.json','content/store_systems_v05.json','scripts/validate_maps.py']
report={'scope':'Static local path and explicit no-QTE-offset deadline examples only.',
 'assumptions':{'all_doors_open_for_route_example':True,'carry_tiles_per_world_second':carry_speed,
  'walk_tiles_per_world_second':walk_speed,'pickup_world_seconds':pickup_seconds,
  'drop_world_seconds':drop_seconds,'handling_durations_are_explicit_proposed_local_contract':True,
  'no_enemy_delay_or_touch_reaction_modelled':True,
  'runtime_offer_expires_on_either_world_or_budget_boundary':True},
 'input_sha256':{x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in inputs},
 'f42_routes':routes,'special_offer_windows':offers}
print(json.dumps(report,ensure_ascii=False,indent=2))
