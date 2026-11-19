#!/usr/bin/env python3
"""TD05 chase design reference, not a live AI or collision implementation.

Exact piecewise 1-D pursuit checks include pauses/slowdowns/work. A second,
explicitly narrower check enumerates a static map's accessible cell centres and
finds a zero-stamina walking escape from one locked 1.5-tile hazard. It does not
claim the same result for overlapping attack areas, new barriers or live actors.
"""
from __future__ import annotations
import argparse
from collections import deque
from fractions import Fraction
import json
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def q(x): return x if isinstance(x, Fraction) else Fraction(str(x))
def number(x): return float(x) if isinstance(x, Fraction) else x

def load_local(name, fallback=None):
    p = ROOT / 'content' / name
    if not p.exists() and fallback:
        p = ROOT.parent / fallback / 'content' / name
    return json.loads(p.read_text())

def profile_speed(profile, overrides=None):
    """Integral of actual phase displacement divided by all phase time."""
    overrides = overrides or {}
    if profile['type'] == 'node_cycle':
        return q(profile['reference_node_forward_advance_tiles'])/(q(profile['dwell_seconds'])+q(profile['travel_seconds']))
    if profile['type'] != 'cycle':
        return q(profile['base_speed'])
    duration = q(0); advance = q(0)
    for part in profile['segments']:
        name = part['name']
        dt = q(overrides.get(name + '_seconds', part['seconds']))
        speed = q(overrides.get(name + '_speed', part.get('speed', 0)))
        dx = q(overrides.get(name + '_advance', part.get('advance', speed * dt)))
        duration += dt; advance += dx
    if duration <= 0:
        raise ValueError('A traversal cycle needs positive actual duration.')
    return advance / duration

def active(intervals, t):
    return any(q(start) <= t < q(end) for start, end in intervals)

def time_to_attack_gap(enemy_speed, player_speed=3, initial_gap=6, attack_gap=1.2,
                       holds=(), slow_periods=(), work_periods=(), horizon=120):
    """First approach to the windup-start gap; no attack hit is simulated.

    Holds are physical paper contact. Slow intervals contain a speed multiplier.
    Work intervals stop player travel. Interval endpoints are half-open.
    """
    e, p, gap, target, end = map(q, [enemy_speed, player_speed, initial_gap, attack_gap, horizon])
    times = {q(0), end}
    for start, finish in list(holds) + list(work_periods):
        times.update([max(q(0), q(start)), min(end, q(finish))])
    for start, finish, factor in slow_periods:
        times.update([max(q(0), q(start)), min(end, q(finish))])
    times = sorted(t for t in times if 0 <= t <= end)
    trace = []
    for start, finish in zip(times, times[1:]):
        if gap <= target:
            return {'at_seconds': float(start), 'final_gap': float(gap), 'trace': trace}
        now_e = q(0) if active(holds, start) else e
        modifiers = [q(factor) for a, b, factor in slow_periods if q(a) <= start < q(b)]
        if modifiers:
            now_e *= min(modifiers)  # strongest slow, not a multiplicative stack
        now_p = q(0) if active(work_periods, start) else p
        delta = now_p - now_e
        dt = finish - start
        if delta < 0 and gap + delta * dt <= target:
            caught = start + (gap - target) / (-delta)
            trace.append({'from':float(start),'to':float(caught),'player_speed':float(now_p),'enemy_speed':float(now_e),'gap_before':float(gap),'gap_after':float(target)})
            return {'at_seconds': float(caught), 'final_gap': float(target), 'trace': trace}
        after = gap + delta * dt
        trace.append({'from':float(start),'to':float(finish),'player_speed':float(now_p),'enemy_speed':float(now_e),'gap_before':float(gap),'gap_after':float(after)})
        gap = after
    return {'at_seconds': None, 'final_gap': float(gap), 'trace': trace}

def accept_paper_contacts(requests, maximum_hold=1, interval=6):
    """Requests: time, target id, source id. One target timer spans all sources."""
    ready = {}; accepted = []; refused = []
    for time, target, source in sorted(requests):
        t = q(time)
        if t < ready.get(target, q(-1)):
            refused.append({'at':float(t),'target':target,'source':source,'next_at':float(ready[target])})
        else:
            ready[target] = t + q(interval)
            accepted.append({'at':float(t),'until':float(t+q(maximum_hold)),'target':target,'source':source})
    return {'accepted':accepted,'refused':refused,'next':{k:float(v) for k,v in ready.items()}}

def circle_overlaps_rect(x,y,r,rect):
    left,top,width,height=rect
    nearest_x=max(left,min(x,left+width));nearest_y=max(top,min(y,top+height))
    return (x-nearest_x)**2+(y-nearest_y)**2 < r*r-1e-12

def static_map_escape(map_data, body_radius=.3, hazard_radius=1.5, speed=3, telegraph=1.5):
    scene=next(s for s in map_data['scenes'] if s['id']=='MAP_STORE')
    surfaces=[x['rect'] for x in scene['walk_surfaces']]
    solids=[x['rect'] for x in scene['walls']]+[x['rect'] for x in scene['fixtures'] if x.get('blocks_navigation')]
    walk=set()
    xmin=min(x for x,y,w,h in surfaces);xmax=max(x+w for x,y,w,h in surfaces)
    ymin=min(y for x,y,w,h in surfaces);ymax=max(y+h for x,y,w,h in surfaces)
    for iy in range(int(ymin),int(ymax)):
        for ix in range(int(xmin),int(xmax)):
            x,y=ix+.5,iy+.5
            if not any(a+body_radius<=x<=a+w-body_radius and b+body_radius<=y<=b+h-body_radius for a,b,w,h in surfaces):continue
            if any(circle_overlaps_rect(x,y,body_radius,r) for r in solids):continue
            walk.add((ix,iy))
    directions=((1,0),(-1,0),(0,1),(0,-1))
    entry=(15,30); reachable={entry}; queue=deque([entry])
    while queue:
        x,y=queue.popleft()
        for dx,dy in directions:
            nxt=(x+dx,y+dy)
            if nxt in walk and nxt not in reachable:reachable.add(nxt);queue.append(nxt)
    tested=[]; failures=[]
    # Exact shortest orthogonal cell path. A cell-centre escape goal includes body radius.
    for start in sorted(p for p in reachable if 0<=p[0]<30 and 0<=p[1]<30):
        todo=deque([(start,0)]);seen={start};dist=None;goal=None
        while todo:
            point,length=todo.popleft()
            if (point[0]-start[0])**2+(point[1]-start[1])**2 > (hazard_radius+body_radius)**2:
                dist=length;goal=point;break
            if length >= ceil(speed*telegraph):continue
            for dx,dy in directions:
                nxt=(point[0]+dx,point[1]+dy)
                if nxt in reachable and nxt not in seen:seen.add(nxt);todo.append((nxt,length+1))
        ok=dist is not None and dist/speed<=telegraph
        row={'cell':[start[0]+.5,start[1]+.5],'path_tiles':dist,'seconds':None if dist is None else dist/speed,'ok':ok}
        tested.append(row)
        if not ok:failures.append(row)
    return {'tested_cell_centres':len(tested),'reachable_floor_cell_centres':len(reachable),'failures':failures,
            'maximum_escape_path_tiles':max((r['path_tiles'] or 0) for r in tested),
            'maximum_escape_seconds':max((r['seconds'] or 0) for r in tested),
            'examples':tested[::max(1,len(tested)//8)][:8],
            'body_radius':body_radius,'locked_hazard_radius':hazard_radius,'telegraph_seconds':telegraph,
            'scope':'Static existing map, open default doors, one locked radial hazard, cardinal paths, no added barriers/other enemies. Not all live attack patterns.'}

def run_reference(chase=None,matchups=None,map_data=None):
    chase=chase or load_local('chase_profiles_td05.json')
    matchups=matchups or load_local('monster_matchups_td05.json')
    map_data=map_data or load_local('maps.json','ruler-control-source')
    checks=[]
    def check(name,condition,detail=None):checks.append({'name':name,'passed':bool(condition),'detail':detail})
    profiles={p['id']:p for p in chase['profiles']}
    speeds=[]
    for p in profiles.values():
        got=profile_speed(p)
        check('profile_integral_'+p['id'],abs(float(got)-p['reference_effective_speed'])<1e-8)
        if p['type']=='cycle':check('complete_cycle_time_'+p['id'],sum(q(x['seconds']) for x in p['segments'])==q(p['cycle_seconds']))
        speeds.append({'id':p['id'],'speed':float(got),'ratio_to_player':float(got/q(3))})
    all_ids={m['id'] for m in matchups['monsters']}
    check('sixty_identity_rows',all_ids=={f'F{i:02}' for i in range(1,61)})
    known=set(matchups['known_l3_ids'])
    for m in matchups['monsters']:
        sets=[set(m[c]) for c in ['favorable','conditional','weak']]
        check('category_disjoint_'+m['id'],all(len(s)>=2 and s<=known for s in sets) and not any(sets[i]&sets[j] for i in range(3) for j in range(i+1,3)))
        check('rationales_complete_'+m['id'],set.union(*sets)<=m['branch_rationale'].keys())
        check('reviewed_no_new_ability_'+m['id'],m['balance_review_td05']['reviewed'] and not m['movement_speed_review']['new_movement_ability_added'])
    monsters={m['id']:m for m in chase['monsters']}
    check('F14_disabled',not monsters['F14']['default_enabled'])
    check('F60_no_mirror',monsters['F60']['profile_id']=='WALK' and '不获镜穿' in monsters['F60']['correct_response'])
    check('F54_anchored',monsters['F54']['base_pursuit_speed_tiles_per_second']==0)
    check('F46_dwell_preserved',profiles['NODE_DWELL']['dwell_seconds']==4 and profiles['NODE_DWELL']['telegraph_overlaps_final_dwell'])
    check('F46_rule_response_does_not_grant_speed',monsters['F46']['post_response_base_speed_tiles_per_second']==profiles['NODE_DWELL']['revealed_body_walk_speed']==monsters['F46']['revealed_body_walk_speed_before_and_after_response'] and monsters['F46']['post_response_base_speed_tiles_per_second']<=float(profile_speed(profiles['NODE_DWELL'])) and not monsters['F46']['rule_response_grants_faster_basic_movement'])
    check('F03_weakened_integral',abs(float(profile_speed(profiles['LEAP'],{'ground_cruise_seconds':5.4,'landing_recovery_seconds':2.5}))-monsters['F03']['post_response_reference_effective_speed_tiles_per_second'])<1e-8)
    for mid in ['F32','F55']:
        check('fast_leap_integral_'+mid,abs(float(profile_speed(profiles['LEAP'],monsters[mid]['cycle_overrides']))-monsters[mid]['reference_effective_speed_tiles_per_second'])<1e-8)
    check('F43_pre_response_integral',abs(float(profile_speed(profiles['DASH'],monsters['F43']['cycle_overrides']))-monsters['F43']['reference_effective_speed_tiles_per_second'])<1e-8)
    check('F43_post_response_integral',abs(float(profile_speed(profiles['DASH'],{'ground_cruise_seconds':6.7,'telegraph_seconds':1.8}))-monsters['F43']['post_response_reference_effective_speed_tiles_per_second'])<1e-8)
    cases={
      'legacy_enemy_2_3':time_to_attack_gap(2.3,horizon=20),
      'normal_enemy_3_3':time_to_attack_gap(3.3),
      'heavy_enemy_3_24':time_to_attack_gap(3.24),
      'agile_enemy_3_45':time_to_attack_gap(3.45),
      'one_cold_layer_for_six_seconds':time_to_attack_gap(3.3,slow_periods=[(0,6,.92)]),
      'two_cold_layers_for_six_seconds':time_to_attack_gap(3.3,slow_periods=[(0,6,.84)]),
      'one_second_paper_contact':time_to_attack_gap(3.3,holds=[(2,3)]),
      'ideal_paper_every_six_seconds':time_to_attack_gap(3.3,holds=[(i,i+1) for i in range(0,120,6)]),
      'two_pursuers_first':time_to_attack_gap(3.3,initial_gap=6),
      'two_pursuers_second':time_to_attack_gap(3.3,initial_gap=8),
      'one_point_five_second_work_without_paper':time_to_attack_gap(3.3,initial_gap=3.2,work_periods=[(0,1.5)],horizon=1.5),
      'one_point_five_second_work_with_paper':time_to_attack_gap(3.3,initial_gap=3.2,work_periods=[(0,1.5)],holds=[(0,1)],horizon=1.5),
    }
    check('legacy_cannot_catch',cases['legacy_enemy_2_3']['at_seconds'] is None)
    check('normal_16s_to_windup_range',cases['normal_enemy_3_3']['at_seconds']==16)
    check('heavy_20s_to_windup_range',cases['heavy_enemy_3_24']['at_seconds']==20)
    check('single_paper_delays_to27s',cases['one_second_paper_contact']['at_seconds']==27)
    check('real_control_can_make_safe_route',cases['ideal_paper_every_six_seconds']['at_seconds'] is None)
    check('paper_can_cover_short_action_window',cases['one_point_five_second_work_with_paper']['at_seconds'] is None and cases['one_point_five_second_work_without_paper']['at_seconds'] is not None)
    check('cold_one_still_pursues',q(3.3)*q(.92)>q(3))
    check('cold_two_opens_distance',q(3.3)*q(.84)<q(3))
    contacts=accept_paper_contacts([(2,'A','post1'),(2.2,'A','post2'),(3,'A','new_doll'),(4,'B','post2'),(7.99,'A','upgrade'),(8,'A','post3')])
    check('paper_all_sources_share_timer',len(contacts['accepted'])==3 and len(contacts['refused'])==3 and contacts['accepted'][-1]['at']==8)
    check('paper_different_targets_independent',any(x['target']=='B' for x in contacts['accepted']))
    check('paper_release1s',all(q(x['until'])-q(x['at'])==1 for x in contacts['accepted']))
    corners={}
    for key in ['WALK','HEAVY','AGILE']:
        p=profiles[key];v=q(p['base_speed']);delay=q(p['turn_delay_90_seconds']);length=q(8)
        corners[key]={'straight_speed':float(v),'one90deg_corner_per8tiles_effective_speed':float(length/(length/v+delay)),'extra_turn_seconds':float(delay)}
    check('heavy_corner_still_slightly_faster_on_reference',corners['HEAVY']['one90deg_corner_per8tiles_effective_speed']>3)
    escape=static_map_escape(map_data)
    check('single_locked_hazard_static_map_walk_escape',escape['tested_cell_centres']>400 and not escape['failures'])
    return {'version':'TD05','runtime_integrated':False,'status':'reference_checks_not_full_gameplay','profile_integrals':speeds,'pursuit_cases':cases,'paper_contact_cases':contacts,'corner_reference':corners,'static_map_escape':escape,'checks':checks,'checks_passed':sum(x['passed'] for x in checks),'checks_failed':sum(not x['passed'] for x in checks),'limits':chase['limits']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--json',action='store_true');args=parser.parse_args()
    report=run_reference()
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:print(json.dumps({'passed':report['checks_passed'],'failed':report['checks_failed'],'profile_integrals':report['profile_integrals'],'pursuit_cases':{k:{x:v for x,v in value.items() if x!='trace'} for k,value in report['pursuit_cases'].items()},'map_escape':report['static_map_escape']},ensure_ascii=False,indent=2))
    if report['checks_failed']:raise SystemExit(1)
