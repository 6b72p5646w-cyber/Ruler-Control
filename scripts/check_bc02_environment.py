#!/usr/bin/env python3
"""Meaningful BC02 environment counterexamples and finite route/lifecycle traces."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

from bc02_environment_reference import EnvironmentWorld, contract, condition_index, consumer_bindings
from bc01_map_reference import StoreMap

ROOT=Path(__file__).resolve().parents[1]
CASES=[]
ASSERTIONS=0


def check(value,message):
    global ASSERTIONS
    ASSERTIONS+=1
    if not value:raise AssertionError(message)


def rejects(fn,message):
    try:fn()
    except (ValueError,KeyError):check(True,message);return
    check(False,message)


def case(fn):
    CASES.append(fn);return fn


def install(world,item_id,kind,root_id='world',destination=None,**config):
    world.declare_payload(item_id,kind=kind,root_id=root_id)
    tx=world.begin_deployment(item_id,kind=kind,destination=destination,**config)
    world.complete_deployment(tx)
    check(tx.status=='committed','physical deployment must finish')
    return tx


def water_world(region='WET_COLD',supply_kind='closed_loop'):
    w=EnvironmentWorld();w.reserve_root('water-root','F05')
    tx=install(w,'original-water-kit','water_module','water-root',region_id=region,supply_kind=supply_kind)
    w.advance(12)
    return w,next(iter(w.sources)),tx


def glass_world():
    w=EnvironmentWorld()
    tx=install(w,'E003:original-glass','glass_return',destination=(9.5,22.5))
    w.walk((9.5,22.5));w.advance(3)
    incident=w.glass_contact('E003:original-glass')
    check(incident is not None,'only a real local warned glass contact creates fresh wound')
    return w,incident


@case
def catalogue_is_real_105_and_not_mirror_invention():
    d=contract();check(len(condition_index())==23,'23 source condition types')
    md=[]
    for filename in ['monster_folklore_md01.json','monster_scp_a_md01.json','monster_scp_b_md01.json']:
        md+=json.loads((ROOT/'content'/filename).read_text())['monsters']
    check({x['id'] for x in md}=={x['monster_id'] for x in d['monster_consumers']},'all actual 105 IDs covered')
    check({x['id'] for x in md if x['movement'].get('actual_transition')}=={x['monster_id'] for x in d['phase_anchor_catalog']},'13 actual transition species, no inferred mirror species')
    check(not any(x['mirror_phase_capability'] for x in d['monster_consumers']),'no existing species receives mirror teleport')
    check(all(u['condition_id'] in condition_index() for c in d['monster_consumers'] for u in c['uses']),'every consumer joins a real condition ID')
    attacks=sum(len(m['attacks']) for f in ['monster_attacks_folklore_ma01.json','monster_attacks_scp_ma01.json'] for m in json.loads((ROOT/'content'/f).read_text())['monsters'])
    check(attacks==184,'184 actual MA01 attack definitions inspected')
    return {'monsters':len(md),'attacks':attacks,'phase_species':len(d['phase_anchor_catalog']),'mirror_phase_species':0}


@case
def source_references_resolve_to_repository_content():
    d=contract();refs=set()
    for c in d['monster_consumers']:
        refs.add(c['source_ref']);refs.update(u['source_ref'] for u in c['uses'])
    for p in d['producers']:refs.update(p['source_refs'])
    files={};resolved=0
    for ref in sorted(refs):
        if not ref.startswith('content/'):continue
        file,sep,pointer=ref.partition('#')
        path=ROOT/file
        check(path.exists(),'source file exists: '+ref)
        if sep and pointer.startswith('/'):
            if file not in files:files[file]=json.loads(path.read_text())
            obj=files[file]
            for token in pointer.split('/')[1:]:
                token=token.replace('~1','/').replace('~0','~')
                obj=obj[int(token)] if isinstance(obj,list) else obj[token]
            check(obj is not None,'source JSON pointer resolves: '+ref)
        resolved+=1
    return {'distinct_refs_resolved':resolved}


@case
def selecting_monsters_creates_no_environment():
    w=EnvironmentWorld()
    for c in contract()['monster_consumers']:w.reserve_root(c['monster_id']+':reserved',c['monster_id'])
    check(not w.sources and not w.nodes and not w.wounds and not w.traces,'105 reservations create no live prerequisites')
    check(set(w.surfaces)=={'FIXED_CONVEX_MIRROR'},'only original registered map mirror exists')
    check(not w.items,'monster selection cannot invent payload or past history')
    return {'reservations':len(w.roots),'water_sources':0,'wounds':0}


@case
def old_wet_geometry_has_real_floor_and_dry_counterplay():
    n=StoreMap();d=contract();old=json.loads((ROOT/'content/map_mechanics_v05.json').read_text())['wet_regions']
    totals=[]
    for new,base in zip(d['wet_regions'],old):
        check(new['wet_cells']==base['wet_cells'],'BC02 preserves original wet-cell coordinates')
        check(all(n.point_clear((c[0]+.5,c[1]+.5),.15) for c in new['wet_cells']),'each water cell is actual floor, not shelf/wall')
        check(n.point_clear(new['dry_interact_position']),'dry counterplay body fits')
        check(n.route('player_start',new['dry_interact_position'])['distance']>0,'real dry-control path exists')
        check(math.dist(new['dry_interact_position'],[v+.5 for v in new['cut_cell']])<=new['cut_interaction_max_tiles'],'cut action reaches actual cut cell')
        totals.append({'region':new['id'],'cells':len(new['wet_cells']),'dry_route':n.route('player_start',new['dry_interact_position'])['distance']})
    return {'regions':totals}


@case
def deployment_charges_walk_then_install_then_visible_propagation():
    w=EnvironmentWorld();w.reserve_root('r','F05');w.declare_payload('kit',kind='water_module',root_id='r')
    tx=w.begin_deployment('kit',kind='water_module',region_id='WET_COLD')
    check(not w.sources,'reservation and arrival do not install a source')
    w.advance_deployment(tx,tx.route_distance/3)
    check(not w.sources,'walking to source still has no committed installation')
    w.complete_deployment(tx)
    check(abs(tx.walked_distance-tx.route_distance)<1e-6,'actual travelled path equals charged route')
    check(w.now+1e-6>=tx.route_distance/3+2,'real route plus two-second installation charged')
    check(not w.live_wet_cells('r'),'three-second source warning before first wet cell')
    w.advance(3);check(len(w.live_wet_cells('r'))==1,'only source cell wets first')
    w.advance(5);check(len(w.live_wet_cells('r'))==6,'five actual edges fill six cold-zone cells')
    return {'walk_tiles':tx.route_distance,'install_s':2,'warning_s':3,'cold_fill_edges':5}


@case
def cancelled_deployment_preserves_same_item_and_partial_position():
    w=EnvironmentWorld();w.declare_payload('kit',kind='water_module',root_id='r')
    tx=w.begin_deployment('kit',kind='water_module',region_id='WET_COLD')
    w.advance_deployment(tx,2);w.cancel_deployment(tx)
    position=w.items['kit']['position']
    check(position!=(15.5,32.5),'partial real travel is not rolled back')
    check(not w.sources and len(w.items)==1,'cancel does not produce source or copy item')
    rejects(lambda:w.begin_deployment('kit',kind='water_module',region_id='WET_COLD'),'cannot remotely resume an unheld cancelled item')
    w.walk(position);w.pickup_cancelled('kit')
    tx2=w.begin_deployment('kit',kind='water_module',region_id='WET_COLD');w.complete_deployment(tx2)
    check(len(w.sources)==1 and len(w.items)==1,'physical retry uses original one source item')
    return {'cancel_position':position,'retry_item_count':len(w.items)}


@case
def closing_door_during_delivery_blocks_actual_path():
    w=EnvironmentWorld();w.declare_payload('kit',kind='water_module')
    tx=w.begin_deployment('kit',kind='water_module',region_id='WET_COLD')
    w.set_door('DOOR_FRONT',True);w.complete_deployment(tx)
    check(tx.status=='route_changed','door closure cancels actual swept path')
    check(not w.sources,'blocked porter cannot teleport cargo into source slot')
    check(w.items['kit']['position'][1]>=30,'same cargo stays outside physical door')
    return {'status':tx.status,'last_position':w.items['kit']['position']}


@case
def water_connection_uses_real_edges_and_root_ownership():
    w,s,tx=water_world()
    path=w.wet_path((26.5,10.5),(23.5,12.5),root_id='water-root')
    check(path['distance']==5,'wet route measures actual five edges, not Euclidean shortcut')
    check(w.wet_path((26.5,10.5),(23.5,12.5),root_id='other-root') is None,'root-specific water is not borrowed by another encounter')
    check(w.wet_path((26.5,10.5),(23.5,12.5),root_id='water-root',layer='high_air') is None,'wrong movement layer cannot consume ground water')
    check(w.wet_path((26.5,10.5),(24.5,12.5),root_id='water-root') is None,'dry destination is not silently made wet')
    return {'actual_water_path':path['path'],'distance_tiles':path['distance']}


@case
def finite_cup_volume_stops_feeding_and_does_not_refresh_for_180s():
    w,s,tx=water_world('WET_AISLE','finite_pour');src=w.sources[s]
    check(not src['flowing'],'six-cell cup source finishes feeding after its finite volume')
    check(len(src['ever_filled'])==6,'finite cup emitted six original units only')
    deadlines={c:v['expires_at'] for c,v in src['cells'].items()}
    w.advance(60)
    check({c:v['expires_at'] for c,v in src['cells'].items()}==deadlines,'cup does not keep refreshing residual water')
    w.advance(180)
    check(not src['cells'] and len(src['ever_filled'])==6,'expired finite water never respawns from empty cup')
    return {'volume_units':6,'feed_duration_max_s':6,'residual_ttl_s':180}


@case
def rain_has_seeded_origin_closed_door_and_finite_end():
    dry=EnvironmentWorld();check(dry.weather_rain(0) is None,'dry weather seed does not create water')
    w=EnvironmentWorld(closed_doors=['DOOR_FRONT']);s=w.weather_rain(1)
    check(s is not None and abs(w.now-20)<EPS,'rain event occurs from independent seed at actual time')
    check(not w.sources[s]['cells'],'rain warning precedes wet source')
    w.advance(12)
    check(all(c[1]>=30 for c in w.sources[s]['cells']),'closed door prevents water entering store')
    w.advance(140-w.now);check(not w.sources[s]['flowing'],'weather source ends at world140')
    w.advance(180);check(not w.sources[s]['cells'],'last actual rain-fed residual expires')
    return {'seed_dry':0,'seed_rain':1,'rain_end_world_s':140}


@case
def cut_cancelled_has_no_effect_committed_cut_disconnects_and_drains():
    w,s,tx=water_world();w.walk(w.regions['WET_COLD']['dry_interact_position'])
    w.wipe_cut(s,commit=False)
    check(w.wet_path((26.5,10.5),(23.5,12.5),root_id='water-root') is not None,'cancelled wipe does not submit cut')
    w.wipe_cut(s)
    check(w.wet_path((26.5,10.5),(23.5,12.5),root_id='water-root') is None,'real cut immediately removes connecting graph edge')
    w.advance(2)
    check((23,12) not in w.sources[s]['cells'],'detached branch drains after two seconds')
    w.advance(200)
    check((24,10) not in w.sources[s]['cells'],'same episode cannot grow across a cleaned locked cut')
    check((26,10) in w.sources[s]['cells'],'unrelated still-fed source component remains actual')
    return {'cut_cell':[24,10],'detached_drain_s':2,'source_component_preserved':True}


@case
def water_native_motion_is_not_a_phase_or_virtual_ground_trap():
    w,s,tx=water_world();w.spawn_body('water-root',(26.5,10.5))
    start=w.now;t=w.begin_transition('water-root','water',(23.5,12.5));w.finish_transition(t)
    check(t.status=='committed' and t.commits==1,'real connected native water movement commits once')
    check(w.now-start+1e-6>=1.5+5/3.3,'actual wet-route travel time is charged')
    check(t.phase_event_count==0 and t.physical_ground_midpath_hits==0,'water-lane native movement is not phase and not hidden ground trapping')
    check(w.roots['water-root']['body']==(23.5,12.5),'actual declared endpoint is used')
    return {'water_distance':5,'world_seconds':w.now-start,'phase_events':0}


@case
def water_cut_during_windup_cancels_without_retarget_or_cooldown_refund():
    w,s,tx=water_world();w.spawn_body('water-root',(26.5,10.5));w.walk((24.5,11.5))
    t=w.begin_transition('water-root','water',(23.5,12.5));cd=w.roots['water-root']['cooldown_until']
    w.finish_transition(t,during_warning=lambda world,ticket:world.wipe_cut(s))
    check(t.status=='cancelled' and t.commits==0,'water dependency rechecked after windup')
    check(w.roots['water-root']['body']==t.origin,'no alternative landing chosen')
    check(w.roots['water-root']['cooldown_until']==cd,'source denial does not refund ability cooldown')
    check(t.recovery_until>w.now+3.9,'visible resurfacing1.5 plus native recovery2.5 stays bounded')
    return {'reason':t.reason,'recovery_seconds':t.recovery_until-w.now}


@case
def water_cut_midroute_keeps_last_actual_position():
    w,s,tx=water_world();w.spawn_body('water-root',(26.5,10.5));w.walk((24.5,11.5))
    t=w.begin_transition('water-root','water',(23.5,12.5));calls=[0]
    def cut(world,ticket):
        calls[0]+=1
        if calls[0]==3:world.wipe_cut(s)
    w.finish_transition(t,during_transit=cut)
    p=w.roots['water-root']['body']
    check(t.status=='cancelled','interruption while physically travelling is observed')
    check(p!=t.origin and p!=t.destination,'cancel does not teleport back to source or finish locked destination')
    check(w.nav.point_clear(p),'resurfacing remains at actual legal last point')
    check(t.phase_event_count==0,'cancelled native route produces no phase audit')
    return {'last_real_body_position':p,'origin':t.origin,'destination':t.destination}


@case
def water_power_does_not_forge_electrical_or_optical_permissions():
    w,s,tx=water_world();w.set_power('MAIN',False,source_event_id='actual-grid-episode')
    check(w.wet_path((26.5,10.5),(23.5,12.5),root_id='water-root') is not None,'gravity-fed physical water survives MAIN outage')
    check(not any(x['phase_port'] for x in w.surfaces.values()),'water alone does not create a mirror port')
    check(not w.lamps,'water source is not an electrical light/AP producer')
    return {'water_remains':True,'new_electrical_nodes':0,'mirror_ports':0}


@case
def cleaned_episode_rewards_once_and_only_in_safe_phase():
    w,s,tx=water_world('WET_AISLE','finite_pour')
    w.phase='RAID';rejects(lambda:w.claim_cleanup(s),'ordinary cleanup rewards do not create raid chores')
    w.phase='RECOVERY'
    rejects(lambda:w.claim_cleanup(s),'unperformed cleaning cannot receive work pay')
    check(w.clean_episode(s),'player actually walks to and wipes original wet cells')
    check(w.claim_cleanup(s),'actual removed episode becomes eligible once')
    check(not w.claim_cleanup(s),'same cleanup episode cannot farm rewards')
    return {'eligible_receipts':1,'duplicate_eligible':False}


@case
def natural_drying_never_generates_cleaning_payment():
    w,s,tx=water_world('WET_AISLE','finite_pour');w.advance(200)
    check(not w.clean_episode(s),'already dry floor has no cleaning work to complete')
    rejects(lambda:w.claim_cleanup(s),'elapsed TTL is not a cleaning action receipt')
    return {'natural_expiry_cleaning_rewards':0}


def mirror_world():
    w=EnvironmentWorld()
    install(w,'original-mirror-A','mirror','mirror-job',destination=(19.5,22.5),phase_port=True)
    install(w,'original-mirror-B','mirror','mirror-job',destination=(22.5,22.5),phase_port=True)
    return w


@case
def mirror_needs_two_original_ports_and_never_grants_species_capability():
    w=mirror_world();ticket=w.mirror_pair('original-mirror-A','original-mirror-B','mirror-job')
    check(ticket is not None,'two physical independently deployed ports form candidate topology')
    check(w.mirror_pair('original-mirror-A','original-mirror-A','mirror-job') is None,'same original item cannot be both endpoints')
    check(w.mirror_pair('FIXED_CONVEX_MIRROR','original-mirror-B','mirror-job') is None,'ordinary fixed convex mirror is not a teleport endpoint')
    check(w.mirror_pair('original-mirror-A','original-mirror-B','other-root') is None,'cannot borrow a different roots port')
    w.reserve_root('f60','F60');w.spawn_body('f60',(19.5,21.5))
    rejects(lambda:w.begin_transition('f60','mirror',(22.5,22.5),source_ids=('original-mirror-A','original-mirror-B')),'F60 never acquires mirror-phase from nearby surfaces')
    return {'delivered_original_mirrors':2,'current_species_mirror_commits':0}


@case
def mirror_endpoint_cover_removal_low_reflectivity_and_stale_lease_fail():
    w=mirror_world();ticket=w.mirror_pair('original-mirror-A','original-mirror-B','mirror-job')
    w.walk((22.5,22.5));w.cover_mirror('original-mirror-B')
    check(not w.recheck_mirror_pair(ticket),'covered actual exit invalidates old pair before commit')
    w.cover_mirror('original-mirror-B',False)
    check(not w.recheck_mirror_pair(ticket),'uncover cannot revive an old versioned transition ticket')
    w.surfaces['original-mirror-B']['reflectivity']=.3
    check(w.mirror_pair('original-mirror-A','original-mirror-B','mirror-job') is None,'water-like reflection below.65 cannot be port')
    w.surfaces['original-mirror-B']['reflectivity']=.9
    fresh=w.mirror_pair('original-mirror-A','original-mirror-B','mirror-job');check(fresh is not None,'new valid pair can be re-evaluated after visible recovery')
    w.remove_item('original-mirror-B');check(not w.recheck_mirror_pair(fresh),'removing original physical mirror invalidates live exit')
    return {'failed_conditions':['covered','stale_version','low_reflectivity','removed']}


@case
def optical_reflection_uses_actual_plane_and_both_visible_legs():
    w=EnvironmentWorld()
    check(w.reflection_visible((19.5,24.5),'FIXED_CONVEX_MIRROR',(20.5,24.5)),'real bounded reflecting plane provides lawful observation')
    check(not w.reflection_visible((19.5,20.5),'FIXED_CONVEX_MIRROR',(20.5,24.5)),'back of mirror does not reflect')
    check(not w.reflection_visible((26.5,24.5),'FIXED_CONVEX_MIRROR',(27.5,24.5)),'ray outside finite mirror surface cannot reflect')
    w.set_power('MAIN',False,source_event_id='grid')
    check(w.reflection_visible((19.5,24.5),'FIXED_CONVEX_MIRROR',(20.5,24.5)),'passive mirror geometry is not erased by MAIN power event')
    return {'finite_plane_half_width':.75,'mirror_observation_is_direct_gaze':False}


def shadow_world():
    w=EnvironmentWorld();w.reserve_root('s22','S22')
    for label,pos in zip('ABC',[(20.5,18.5),(22.5,18.5),(24.5,18.5)]):
        install(w,'node-'+label,'phase_anchor','s22',destination=pos,subtype='same_three_task_dark_nodes',layer='low_air',requires_dark=True)
        install(w,'lamp-'+label,'lamp','s22',destination=pos,on=False,power_domain='TASK_ISOLATED',radius=1.5)
    w.spawn_body('s22',(20.5,18.5),layer='low_air')
    return w


@case
def task_lamps_are_real_independent_sources_during_MAIN_blackout():
    w=shadow_world();w.switch_lamp('lamp-C',True)
    check(not w.is_dark((24.5,18.5)),'actual C lamp changes measured illumination')
    w.set_power('MAIN',False,source_event_id='grid')
    check(not w.is_dark((24.5,18.5)),'isolated task battery does not require pursued player to restore MAIN')
    w.set_power('TASK_ISOLATED',False,source_event_id='task-battery-fault')
    check(w.is_dark((24.5,18.5)),'actual task-source failure really removes its light')
    w.set_power('TASK_ISOLATED',True,source_event_id='same-task-battery-recovery')
    check(not w.is_dark((24.5,18.5)),'same physical task source can recover without replacing root')
    return {'power_domains':['MAIN','TASK_ISOLATED'],'task_battery_world_seconds':900}


@case
def S22_escape_is_to_existing_darker_farther_node_and_no_ground_traps():
    w=shadow_world();w.walk((19.5,19.5));w.switch_lamp('lamp-A',True);w.switch_lamp('lamp-B',True)
    t=w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',));w.finish_transition(t)
    check(t.status=='committed' and t.phase_event_count==1,'explicit S22 true transition uses actual dark C')
    check(w.roots['s22']['body']==(24.5,18.5),'same C destination retained')
    check(t.recovery_until-w.now==1.5 and t.physical_ground_midpath_hits==0,'real recovery and nonphysical phase path separated')
    w.advance(8);w.switch_lamp('lamp-A',False)
    rejects(lambda:w.begin_transition('s22','shadow',(20.5,18.5),source_ids=('node-A',)),'defensive escape cannot jump closer to player')
    return {'origin':t.origin,'destination':t.destination,'recovery_s':1.5}


@case
def illumination_during_phase_warning_revokes_endpoint_without_soft_retarget():
    w=shadow_world();w.walk((19.5,19.5));t=w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',))
    w.finish_transition(t,during_warning=lambda world,ticket:world.switch_lamp('lamp-C',True))
    check(t.status=='cancelled','new real light invalidates a dark exit before teleport')
    check(w.roots['s22']['body']==(20.5,18.5) and t.phase_event_count==0,'no fallback invisible teleport')
    w.switch_lamp('lamp-C',False);w.advance(8)
    retry=w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',));w.finish_transition(retry)
    check(retry.status=='committed','same root/source survives missed window and can retry after real cooldown')
    return {'first':'cancelled','retry':'committed','source_recreated':False}


@case
def ambient_MAIN_light_is_not_ignored_when_claiming_a_dark_node():
    w=shadow_world()
    install(w,'actual-main-lamp','lamp','world',destination=(24.5,18.5),on=True,power_domain='MAIN',radius=3)
    check(not w.is_dark((24.5,18.5)),'all actual MAIN and task light contributions count, even when task-C switch is off')
    rejects(lambda:w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',)),'registered node is not automatically dark')
    w.switch_lamp('actual-main-lamp',False)
    check(w.is_dark((24.5,18.5)),'actual local lamp change, not node registration, removes this illumination')
    return {'ambient_lamp_blocks_dark_node':True,'task_switch_off_is_insufficient':True}


@case
def task_light_over_900s_has_free_local_energy_recovery_without_deadline_reset():
    w=shadow_world();w.walk((19.5,19.5));w.switch_lamp('lamp-A',True);w.switch_lamp('lamp-B',True)
    original_ids=set(w.items);old_sources={k:l['source_event_id'] for k,l in w.lamps.items()}
    deadline=w.now+2000;w.roots['s22']['absolute_rule_deadline']=deadline
    w.set_power('MAIN',False,source_event_id='real-long-blackout')
    w.advance(max(l['expires_at'] for l in w.lamps.values())-w.now+1)
    check(w.now>900 and w.is_dark((20.5,18.5)),'actual task batteries can expire during long raid')
    check(not w.roots['s22'].get('environment_guard'),'empty source alone cannot grant an unlimited combat pause')
    expires={k:l['expires_at'] for k,l in w.lamps.items()}
    check(not w.handcrank_task_group('s22',commit=False),'cancelled local handcrank gives no energy')
    window_until=w.roots['s22']['task_recovery_window']['until']
    check(w.roots['s22']['environment_guard']=='local_task_handcrank_response','only actual local manual action opens same-root bounded response')
    check({k:l['expires_at'] for k,l in w.lamps.items()}==expires,'cancelled work cannot refill necessary lamps')
    before=w.now;check(w.handcrank_task_group('s22'),'actual two-second safe-side action restores same module')
    check(w.roots['s22']['task_recovery_window']['until']==window_until,'cancel/retry cannot refresh the same three-second window')
    check(abs(w.now-before-2)<EPS and all(abs(l['expires_at']-w.now-60)<EPS for l in w.lamps.values()),'two real world seconds provide exactly60 bounded seconds')
    check(not w.is_dark((20.5,18.5)) and w.is_dark((24.5,18.5)),'existing A/B switches stay lit and C remains deliberately dark')
    check(not w.power['MAIN'] and w.roots['s22']['absolute_rule_deadline']==deadline,'manual source neither restores MAIN nor refreshes rule deadline')
    check(set(w.items)==original_ids and {k:l['source_event_id'] for k,l in w.lamps.items()}==old_sources,'no module or original source identity is recreated')
    rejects(lambda:w.handcrank_task_group('s22'),'repeated crank cannot stockpile energy while already charged')
    t=w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',));w.finish_transition(t)
    check(t.status=='committed','same original root still has a usable completion route after900s')
    w.advance(60);w.roots['s22']['absolute_rule_deadline']=w.now+1
    check(not w.handcrank_task_group('s22'),'deadline that expires during real crank cannot be extended by completion')
    check(w.roots['s22']['state']=='failed' and not w.roots['s22'].get('environment_guard'),'expired original rule enters its authored failure instead of staying in protected recovery')
    return {'initial_energy_s':900,'manual_work_s':2,'recovery_energy_s':60,'MAIN_restored':False,'deadline_refreshed':False}


@case
def F58_no_heat_free_exit_uses_original_sign_real_three_tile_walk_and_one_terminal():
    w=EnvironmentWorld();w.reserve_root('f58','F58');w.spawn_body('f58',(26.5,18.5))
    w.activate_f58_original_clocks('f58');deadline=w.roots['f58']['absolute_rule_deadline']
    w.set_power('MAIN',False,source_event_id='actual-blackout')
    w.walk((24.5,15.5))
    check(not w.f58_close_cold_section('f58',commit=False),'cancelled .5s cold sign action does not submit')
    check(w.roots['f58']['f58']['ordinary_cold_service_open'],'no-heat original service state remains before real action')
    check(w.f58_close_cold_section('f58'),'actual original cold-section sign closes ordinary service')
    rejects(lambda:w.f58_exit_cold_boundary('f58'),'cannot click exit remotely from sign3 tiles away')
    start=w.now;route=w.walk((21.5,15.5))
    check(route['distance']==3 and abs(w.now-start-1)<EPS,'original sign to warm-side exit is actual3-tile baseline walk')
    check(not w.f58_exit_cold_boundary('f58',commit=False)['applied'],'cancelled exit does not resolve root')
    result=w.f58_exit_cold_boundary('f58')
    check(result['applied'] and w.roots['f58']['state']=='terminal','original no-food branch really completes MD01 rule_leave')
    check(not w.f58_exit_cold_boundary('f58')['applied'],'repeated exit cannot generate another terminal reward')
    check(w.roots['f58']['absolute_rule_deadline']==deadline,'real no-heat solution never refreshes olddeadline')
    check(not w.closed_doors and w.nav.route('hot_food','freezer_main')['distance']>0,'ordinary cold sign does not close task freezer or emergency doors')
    check(not w.power['MAIN'] and not w.warm_sources,'free route needs neither backup heat nor MAIN restoration')
    return {'close_s':.5,'walk_tiles':3,'exit_s':.5,'main_power_required':False,'terminal':'rule_leave','root_reward_receipts':1}


@case
def F58_legacy_900s_backup_packages_both_cool_and_cannot_reopen_expired_root():
    w=EnvironmentWorld();w.reserve_root('f58','F58')
    for name in ['legacy-warm-original','legacy-warm-backup']:
        install(w,name,'warmed_pack','f58',destination=(21.5,15.5))
        w.walk((21.5,15.5));check(w.heat_existing_reference_pack(name),'old candidate package actually receives heat from real MAIN heater once')
    sources={k:(v['original_heat_receipt'],v['warm_until']) for k,v in w.warm_sources.items()}
    w.walk('safe_counter');w.spawn_body('f58',(26.5,18.5));w.activate_f58_original_clocks('f58')
    fog_deadline=w.roots['f58']['f58']['fog_deadline'];deadline=w.roots['f58']['absolute_rule_deadline']
    w.set_power('MAIN',False,source_event_id='long-real-blackout')
    w.advance(max(v['warm_until'] for v in w.warm_sources.values())-w.now+1)
    check(w.now>900 and not any(w.original_pack_still_warm(k) for k in sources),'original and reserved backup both cool from their real heat timestamps')
    check(w.roots['f58']['state']=='expired' and w.roots['f58']['terminal_receipt'],'F58 original120s deadline terminates earlier; it never waits forever for a900s pack')
    check(not w.roots['f58'].get('environment_guard'),'thermal expiry cannot hold indefinite protected combat pause')
    rejects(lambda:w.f58_use_thermal_backup('f58','legacy-warm-backup'),'taking backup cannot give it a new900s heat period or reopen F58')
    rejects(lambda:w.heat_existing_reference_pack('legacy-warm-backup'),'no actual MAIN heat and same original heat receipt prohibit resetting backup')
    check({k:(v['original_heat_receipt'],v['warm_until']) for k,v in w.warm_sources.items()}==sources,'old original IDs, source receipts and expiry timestamps are immutable')
    check(w.roots['f58']['absolute_rule_deadline']==deadline and w.roots['f58']['f58']['fog_deadline']==fog_deadline,'thermal inputs never reset30s fog or120s rootdeadline')
    check(not w.roots['f58']['f58']['reward_eligible_once'],'expiry gives no successful root reward')
    check(w.nav.route('hot_food','freezer_main')['distance']>0 and not w.closed_doors,'expired encounter leaves actual freezer and exit topology usable')
    return {'thermal_test_world_s':w.now,'fog_original_s':30,'rule_original_s':120,'both_backup_packages_cold':True,'infinite_pause':False,'root_rewards':0,
            'scope':'withdrawn900s candidate migration counterexample, not a director-admitted900s F58 raid'}


@case
def removed_or_wrong_layer_anchor_cannot_be_used():
    w=shadow_world();w.nodes['node-C']['layer']='high_air'
    rejects(lambda:w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',)),'wrong layer endpoint rejected')
    w.nodes['node-C']['layer']='low_air';w.remove_item('node-C')
    rejects(lambda:w.begin_transition('s22','shadow',(24.5,18.5),source_ids=('node-C',)),'removed original endpoint rejected')
    return {'failure_types':['layer','original_item_removed']}


@case
def warned_glass_real_contact_and_unchanged_90_second_deadline():
    w=EnvironmentWorld(player_position=(9.5,22.5));install(w,'glass','glass_return',destination=(9.5,22.5))
    check(w.glass_contact('glass') is None,'cannot cut before three-second visible warning')
    w.advance(3);incident=w.glass_contact('glass');check(incident is not None,'actual contact after warning creates wound')
    deadline=w.wounds[incident]['expires_at'];w.advance(20)
    check(w.glass_contact('glass') is None and w.wounds[incident]['expires_at']==deadline,'same incident contact cannot refresh90s')
    w.advance(deadline-w.now)
    check(not w.fresh_wound(incident),'expires at exact90-world-second deadline')
    return {'deadline_seconds':90,'same_incident_refresh':False}


@case
def fresh_traces_come_from_path_distance_not_waiting_or_static_points():
    w,incident=glass_world();w.advance(4)
    check(not w.traces,'standing injured does not create trail marks')
    before=w.now;w.walk((13.5,22.5))
    check(len(w.traces)==2,'four actual tiles create two marks')
    points=[t['position'] for t in w.traces.values()]
    check(all(abs(p[1]-22.5)<EPS for p in points),'marks lie on actual horizontal actor path, not old GRP_RED_TRACE examples')
    check(all(abs(t['expires_at']-t['born_at']-30)<EPS for t in w.traces.values()),'each trace retains actual30s TTL')
    check(w.now-before>1.3,'actual walking time also consumes wound/trace clock')
    return {'trace_positions':points,'actual_walk_tiles':4}


@case
def dressing_cancels_new_traces_but_does_not_erase_old_ones():
    w,incident=glass_world();w.walk((13.5,22.5));count=len(w.traces)
    w.dress(commit=False);check(w.fresh_wound(incident),'cancelled treatment cannot submit stop-bleeding')
    check(w.dress(),'actual three-second dressing completes')
    check(not w.fresh_wound(incident),'actual current wound becomes dressed')
    check(sum(t['alive'] for t in w.traces.values())==count,'old actual traces survive dressing')
    w.walk((15.5,22.5));check(len(w.traces)==count,'post-treatment movement makes no new traces')
    return {'old_marks_retained':count,'new_marks_after_dressing':0}


@case
def blood_admission_uses_current_20_second_omen_and_actual_remaining_budget():
    w,incident=glass_world();w.walk((13.5,22.5))
    f26=w.bind_blood_consumer('F26',incident);f32=w.bind_blood_consumer('F32',incident)
    check(f26 and f32,'legitimate fresh source can offer either reactive consumer')
    check(f32['required_fresh_remaining']==53,'20+24+6+3 budget replaces legacy45s gate')
    rejects(lambda:w.bind_blood_consumer('F32',incident,omen_seconds=12),'legacy12s omen cannot bypass BC02 preparation')
    w.advance(20)
    check(w.blood_arrival(f26) and w.blood_arrival(f32),'arrival rechecks actual remaining wound and original traces')
    w.advance(20)
    check(w.bind_blood_consumer('F32',incident) is None,'remaining<53s cannot start another full conservative response')
    return {'minimum_remaining_s':53,'minimum_omen_s':20}


@case
def blood_expiry_or_treatment_before_arrival_prevents_without_new_source():
    w,incident=glass_world();w.walk((13.5,22.5));a=w.bind_blood_consumer('F26',incident);b=w.bind_blood_consumer('F32',incident)
    w.dress();w.advance(20)
    check(not w.blood_arrival(b),'F32 cannot use treated wound snapshot')
    check(w.blood_arrival(a),'F26 still sees same incident live floor marks after wound treated')
    w.advance(15);check(not w.blood_arrival(a),'F26 cannot use expired mark snapshot or invent a replacement')
    check(len(w.wounds)==1,'no automatic new wound for selected blood encounter')
    return {'F32_after_dressing':False,'F26_after_trace_expiry':False}


@case
def same_incident_cannot_reserve_both_blood_consumers():
    w,incident=glass_world();w.walk((13.5,22.5))
    w.reserve_root('f26','F26');w.reserve_root('f32','F32')
    check(w.reserve_blood_consumer('f26',incident) is not None,'first legal same-incident consumer can reserve')
    check(w.reserve_blood_consumer('f32',incident) is None,'same incident cannot also create a second blood encounter')
    check(len(w.blood_reservations)==1,'incident owner ledger remains unique')
    return {'same_incident_reserved_consumers':1}


@case
def F21_next_default_raid_is_unreachable_without_extending_real_wound():
    # Same 90s source lifecycle applies to the real F21 contact integration event.
    w,incident=glass_world();w.advance(35+60+20)
    check(not w.fresh_wound(incident),'115s default inter-raid schedule exceeds90s source life')
    check(w.bind_blood_consumer('F32',incident) is None,'do not reserve a next-raid blood monster from expired F21-like source')
    check(w.wounds[incident]['status']=='dry','history is retained while current condition is absent')
    return {'default_followup_schedule_s':115,'real_wound_s':90,'next_raid_eligible':False}


@case
def F13_cleanup_blood_cannot_become_employee_blood():
    w=EnvironmentWorld();w.reserve_root('f13','F13')
    stain=w.record_f13_defeat('f13',0,(21.5,3.5))
    check(w.cleanup_stains[stain]['is_player_wound'] is False,'corpse stain is not a wound')
    check(not w.wounds and not w.traces,'F13 terminal cannot create player blood-trail producers')
    check(w.bind_blood_consumer('F26',stain) is None and w.bind_blood_consumer('F32',stain) is None,'both blood consumers reject corpse cleanup ID')
    check(w.record_f13_defeat('f13',0,(21.5,3.5))==stain and len(w.cleanup_stains)==1,'same root defeat produces only one cleanup episode')
    return {'corpse_stains':1,'employee_wounds':0}


@case
def sound_uses_actual_path_doors_source_time_and_power():
    w=EnvironmentWorld();s=w.emit_sound('speaker',(12.5,5.5),duration=10,range_tiles=3,power_domain='MAIN')
    check(w.sound_reaches(s,(14.5,5.5)),'open real link provides2-tile sound route')
    w.set_door('DOOR_LINK',True)
    check(not w.sound_reaches(s,(14.5,5.5)),'closed wall gate cannot be replaced with straight-line radius')
    w.set_door('DOOR_LINK',False);w.set_power('MAIN',False,source_event_id='grid')
    check(not w.sound_reaches(s,(14.5,5.5)),'powered speaker stops at real blackout')
    voice=w.emit_sound('actual-monster-voice',(12.5,5.5),duration=2,range_tiles=3)
    check(w.sound_reaches(voice,(14.5,5.5)),'biological voice does not require MAIN')
    w.advance(2);check(not w.sound_reaches(voice,(14.5,5.5)),'past subtitle is not an active sound source')
    return {'open_route_tiles':2,'closed_route_within_range':False}


@case
def direct_gaze_rechecks_current_geometry_and_facing():
    w=EnvironmentWorld();a=(12.5,5.5);b=(14.5,5.5)
    check(w.direct_gaze(a,(1,0),b,(-1,0)),'two current bodies genuinely face across open link')
    check(not w.direct_gaze(a,(-1,0),b,(-1,0)),'turning away changes current gaze without altering historical evidence')
    w.set_door('DOOR_LINK',True)
    check(not w.direct_gaze(a,(1,0),b,(-1,0)),'real closed gate occludes current gaze')
    return {'open_and_facing':True,'back_facing':False,'door_closed':False}


@case
def F60_curtain_blocks_only_current_intersecting_sight_segment():
    w=EnvironmentWorld(player_position=(19.5,23.5))
    check(w.direct_gaze((19.5,23.5),(0,-1),(19.5,21.5),(0,1)),'before actual curtain action current facing has direct gaze')
    w.pull_mirror_curtain()
    check(not w.direct_gaze((19.5,23.5),(0,-1),(19.5,21.5),(0,1)),'closed actual curtain intersects original gaze line')
    check(w.direct_gaze((19.5,23.5),(1,1),(20.5,24.5),(-1,-1)),'entity moves to same side: stale curtain result must not remain safe')
    check(w.sight_clear((7.5,23.5),(7.5,26.5)),'low cashier counter blocks bodies but not declared eye-height rule sight')
    check(not w.sight_clear((9.5,14.5),(13.5,14.5)),'actual tall stationery shelf still blocks rule sight')
    fixed=w.surfaces['FIXED_CONVEX_MIRROR']
    check(fixed['item_id']=='MAP_STORE:ATT02:mirror_surface' and fixed['position']==tuple(w.nav.position('convex_mirror')),'fixed mirror source is actual ATT02 attachment/anchor alias')
    return {'curtain_segment':[[18.5,23],[20.5,23]],'same_side_bypass_detected':True,'low_and_tall_layers_separated':True}


@case
def pause_freezes_real_sources_travel_and_deadlines_together():
    w,incident=glass_world();w.walk((13.5,22.5));before=w.snapshot();w.paused=True
    w.advance(300);walk=w.walk((15.5,22.5))
    check(w.now==before['world_at'] and w.fresh_wound(incident),'pause cannot age90s wound or30s trail')
    check(not walk['completed'],'paused movement cannot create free distance')
    check(len(w.traces)==len(before['traces']),'paused path does not produce blood marks')
    w.paused=False;w.advance(90);check(not w.fresh_wound(incident),'resume resumes real world expiry')
    return {'paused_wall_time_attempt_s':300,'advanced_world_s_while_paused':0}


@case
def root_terminal_revokes_live_capability_but_keeps_original_objects():
    w,s,tx=water_world();w.spawn_body('water-root',(26.5,10.5));t=w.begin_transition('water-root','water',(23.5,12.5))
    w.end_root('water-root')
    check(t.status=='cancelled' and w.roots['water-root']['state']=='terminal','root terminal withdraws pending native move')
    check(not w.sources[s]['flowing'],'root-owned task source ends feeding')
    check('original-water-kit' in w.items and not w.items['original-water-kit']['removed'],'original physical kit is not deleted or respawned')
    check(bool(w.sources[s]['cells']),'real residual water remains for later safe cleanup')
    return {'pending_move':'cancelled','original_item_retained':True,'residual_water_retained':True}


EPS=1e-7

def main():
    global ASSERTIONS
    results=[]
    for fn in CASES:
        start=ASSERTIONS
        try:
            details=fn();results.append({'case':fn.__name__,'passed':True,'assertions':ASSERTIONS-start,'details':details})
        except Exception as exc:
            results.append({'case':fn.__name__,'passed':False,'assertions':ASSERTIONS-start,'error':f'{type(exc).__name__}: {exc}','traceback':traceback.format_exc(limit=3)})
    dependency_names={
        'content/environment_conditions_bc02.json','scripts/check_bc02_environment.py',
        'scripts/bc02_environment_reference.py','scripts/bc01_map_reference.py',
        'content/maps.json','content/map_mechanics_v05.json','content/map_composition_bc01.json',
        'content/monster_folklore_md01.json','content/monster_scp_a_md01.json','content/monster_scp_b_md01.json',
        'content/monster_attacks_folklore_ma01.json','content/monster_attacks_scp_ma01.json',
        'content/attack_contracts_ma01.json','content/monster_contracts_md01.json',
        'content/chase_profiles_td05.json','content/combat_contracts_td05.json',
        'content/condition_lifecycle_v06.json','content/condition_reachability_v06.json',
        'content/mechanism_cases_v010_a.json','content/mechanism_cases_v010_b.json',
        'content/facilities_bc01.json','content/director_bc01.json'}
    def collect_source_files(x):
        if isinstance(x,dict):
            for value in x.values():collect_source_files(value)
        elif isinstance(x,list):
            for value in x:collect_source_files(value)
        elif isinstance(x,str) and x.startswith('content/'):
            name=x.split('#')[0]
            if (ROOT/name).is_file():dependency_names.add(name)
    collect_source_files(contract())
    report={'version':'BC02','baseline_commit':'dfd2e32eecb8fb4dc7dd3efa066cfa3817363788',
            'status':'passed' if all(x['passed'] for x in results) else 'failed',
            'scope':'source lifecycle and continuous-time sampled finite references; not engine/105 AI integration',
            'scenario_count':len(results),'assertion_count':ASSERTIONS,
            'passed_scenarios':sum(x['passed'] for x in results),'cases':results,
            'not_claimed':['complete player collision/animation engine','live105-monster AI','real device SDK callbacks','all optional combinations or runtime performance','mirror teleport content; no current species consumes it'],
            'hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(dependency_names)}}
    (ROOT/'docs/bc02_environment_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','scenario_count','assertion_count','passed_scenarios']},ensure_ascii=False))
    for r in results:
        if not r['passed']:print(r['case'],r['error'],r['traceback'])
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':sys.exit(main())
