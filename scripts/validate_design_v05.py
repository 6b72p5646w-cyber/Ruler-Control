#!/usr/bin/env python3
"""Check current V0.5 design links and explicit contracts, not playability or AI."""
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
checks=0
errors=[]

def read(name):
    return json.loads((ROOT/'content'/f'{name}.json').read_text())

def need(condition,message):
    global checks
    checks+=1
    if not condition: errors.append(message)

def main():
    store=read('store_systems_v05')
    data=read('encounters_v05')
    monsters={m['id']:m for m in read('monsters')['monsters']}
    events={e['id']:e for e in read('events')['events']}
    systems={s['id']:s for s in store['systems']}
    modules={x['id'] for x in read('systems_v04')['modules']}
    components={x['id'] for x in read('rule_components')['components']}
    rows=data['encounters']
    base_map=read('maps')
    overlay=read('map_mechanics_v05')
    roles={a['role'] for s in base_map['scenes'] if s['id']=='MAP_STORE' for a in s['anchors']}
    object_ids={x['id'] for x in overlay['objects']}
    group_ids={x['id'] for x in overlay['spatial_groups']}
    wet_ids={x['id'] for x in overlay['wet_regions']}
    entry_ids={x['id'] for x in overlay['entry_profiles']}
    defense_ids={x['id'] for x in overlay['defense_groups']}
    pets={x['id']:x for x in read('pets')['pets']}
    qte=read('qte')
    qte_templates={x['id'] for x in qte['templates']}
    qte_profiles={x['id'] for x in qte['task_profiles']}
    phases={f'N0{i}' for i in range(1,7)}
    need(set(systems)=={f'SG{i:02d}' for i in range(1,11)},'ten complete SG mechanisms')
    need(len(rows)==60 and {x['id'] for x in rows}==set(monsters),'60 current unique monster IDs')
    need(data.get('client_implemented') is False,'current catalog must not claim playable client')
    variant_count=0
    for row in rows:
        fid=row['id']
        need(row['primary_system'] in systems,f'{fid}: primary SG missing')
        secondary=row['secondary_systems']
        need(len(secondary)<=2 and len(set(secondary))==len(secondary),f'{fid}: at most two distinct secondary mechanisms')
        need(set(secondary)<=set(systems) and row['primary_system'] not in secondary,f'{fid}: invalid secondary mechanism')
        need(bool(row['allowed_phases']) and set(row['allowed_phases'])<=phases,f'{fid}: invalid phase')
        for field in ['work_hook','taboo','critical_action','pressure_tradeoff','free_solution','failure_recovery','resolution_condition']:
            need(bool(row.get(field)),f'{fid}: missing {field}')
        need(1<=len(row['action_steps'])<=3,f'{fid}: critical action count outside 1..3')
        need(2<=len(row['omens'])<=3,f'{fid}: 2..3 authored omens required')
        for omen in row['omens']:
            need(omen.get('scale') in {'world','closeup','panel'},f'{fid}: omen scale absent')
            need(bool(omen.get('text')) and bool(omen.get('kind')),f'{fid}: omen information absent')
        implementation=row['implementation']
        need(implementation.get('client_implemented') is False,f'{fid}: falsely implemented')
        need(implementation.get('tier') in {'low','medium','high'},f'{fid}: implementation tier missing')
        need(bool(implementation.get('required_components')) and
             set(implementation['required_components'])<=modules|components,f'{fid}: unknown implementation component')
        need(bool(row.get('source_ids')) and row['source_ids']==monsters[fid]['source_ids'],f'{fid}: folklore source index differs')
        need(bool(row.get('adaptation_notice')),f'{fid}: folklore/game adaptation boundary absent')
        need(len(row['variants'])==2,f'{fid}: exactly two current event variants expected')
        for variant in row['variants']:
            variant_count+=1
            event=events.get(variant.get('event_id'))
            need(event is not None,f'{fid}: missing event')
            need(bool(variant.get('change')) and bool(variant.get('counterplay')),f'{fid}: variant lacks action effect')
            need(set(variant.get('environment_wet_region_ids',[]))<=wet_ids,f'{fid}: event refers to missing wet region')
            if event:
                hour_phases={f'N0{h+1}' for h in event['allowed_hours'] if 0<=h<=5}
                need(bool(set(row['allowed_phases'])&hour_phases),f'{fid}/{event["id"]}: no phase intersection')
                need(variant.get('id') in event.get('v05_encounter_variant_ids',[]),f'{fid}: current event backlink missing')
        binding=row.get('map_binding',{})
        need(binding.get('entry_profile') in entry_ids,f'{fid}: entry profile absent')
        need(bool(binding.get('base_anchors')) and set(binding.get('base_anchors',[]))<=roles,f'{fid}: invalid base anchor')
        need('floor_markers' not in binding.get('base_anchors',[]) or fid=='F40',f'{fid}: generic floor marker retained')
        need(set(binding.get('object_ids',[]))<=object_ids,f'{fid}: invalid mechanic object')
        need(set(binding.get('spatial_group_ids',[]))<=group_ids,f'{fid}: invalid named positions')
        need(set(binding.get('wet_region_ids',[]))<=wet_ids,f'{fid}: invalid wet region')
        need(set(binding.get('defense_group_ids',[]))<=defense_ids,f'{fid}: invalid board slots')
        need(monsters[fid]['interaction_card_file']=='content/encounters_v05.json',f'{fid}: stale current catalog pointer')
        need(row.get('candidate_enabled')==monsters[fid]['enabled_default'],f'{fid}: candidate default mismatch')
        need(row.get('runtime_enabled') is False,f'{fid}: runtime enable must remain false')
        if 'qte_binding' in row:
            binding=row['qte_binding']
            need(binding['template_id'] in qte_templates,f'{fid}: QTE template absent')
            need(binding.get('task_profile_id') is None or binding['task_profile_id'] in qte_profiles,f'{fid}: QTE profile absent')
    by_id={r['id']:r for r in rows}
    for fid in ['F12','F13']:
        need(by_id[fid].get('canonical_override')=='fixed_F12_F13',f'{fid}: immutable blueprint precedence missing')
        need(by_id[fid].get('canonical_blueprint_file')=='content/encounter_blueprints.json',f'{fid}: blueprint reference absent')
    need(by_id['F14']['candidate_enabled'] is False,'F14 must remain excluded')
    general_tags=set(pets['P03']['general_help']['effects'][0]['task_tags'])
    current_tags={tag for r in rows for tag in r.get('qte_binding',{}).get('task_tags',[])}
    need(bool(general_tags) and general_tags<=current_tags,'P03 general ability has no current QTE targets')
    need(not general_tags&{'scan','order_pack'},'ordinary checkout must not reintroduce a precision QTE')
    pet_binding=by_id['F46']['pet_binding']
    pet_effect=pets['P06']['special_help'][0]['effects'][0]
    need(pet_binding['source_group_id'] in group_ids,'F46 pet source positions missing')
    need(pet_binding['item_tag']==pet_effect['item_tag'],'F46 hidden tool tag differs from P06')
    need(pet_binding['transfer_world_seconds']==pet_effect['delay_seconds']<=pet_binding['candidate_dwell_world_seconds'],'F46 transfer cannot fit stop')
    need(pet_binding['transfer_same_existing_instance'] and pet_binding['wind_cannot_relocate_reserved_item'],'F46 duplicate/steal during item transfer')
    need(pet_binding['does_not_satisfy_wind_interception'],'P06 cannot automatically resolve F46')
    need(variant_count==120,'120 current event variants')
    need(read('encounter_designs').get('runtime_loading_allowed') is False,'legacy detailed cards must not load as current')
    need(set(store['four_resources']['retained'])=={'energy','san','satiety','stamina'},'four resources must remain')
    need(store['emergency_power']['capacity_units']==12,'initial reserve proposal changed without migration')
    for flag in ['baseline_fridge_depends_on_reserve','baseline_manual_door_depends_on_reserve',
                 'baseline_task_materials_depend_on_reserve','zero_reserve_adds_san_blackout','borrow_from_cold_chain']:
        need(store['emergency_power'][flag] is False,'emergency power cannot gate '+flag)
    costs={a['id']:a['units'] for a in store['emergency_power']['actions']}
    for example in store['emergency_power']['budget_examples']:
        need(sum(costs[k]*v for k,v in example['uses'].items())==example['total_units'],'power example sum')
    need(store['work_contract']['window_silent_cost_stacks'] is False,'double silent-window cost')
    need(store['failure']['global_three_strikes_ends_night'] is False,'global failure ladder returned')
    need(store['information']['snapshot_sees_through_disguise'] is False,'omniscient camera')
    need(store['information']['schedule_is_presence_proof'] is False,'roster treated as proof')
    need(store['omens']['auto_identify_from_rule_page'] is False,'omen leaks correct monster name')
    need(store['four_resources']['omen_observation_san_damage']==0,'observing clues damages SAN')
    need(store['attention_and_pause']['read_handbook_pauses_all'] is True,'reading pause contract')
    need(store['attention_and_pause']['new_information_generated_while_paused'] is False,'pause information farming')
    need(store['work_debt']['max_carryover_tasks']==1 and store['work_debt']['wage_deduction_night_cap']==20,'bounded work debt')
    need(store['completion']['order_target_for_top_grade']==8 and store['completion']['minimum_orders_to_survive_shift']==0,'orders confused with survival')
    mix=store['service']['base_order_mix']
    need(mix['pickup_per_night']==6 and mix['browse_per_night']==6,'six pickup / six browse slots')
    need(mix['no_extra_orders_to_bypass_mode_tradeoff'] is True,'special orders bypass service tradeoff')
    need(store['service']['service_mode_or_greeting_change_cancels_current_checkout'] is True,'mode switching bypasses checkout')
    need(sum(store['director']['budget_example_seconds'].values())==120,'phase budget example sum')
    omen=store['omens']
    need(omen['far_second_previous_phase']-120-omen['arrival_second_in_phase']==omen['far_relative_to_arrival_seconds'],'far cue clock')
    need(omen['near_second_previous_phase']-120-omen['arrival_second_in_phase']==omen['near_relative_to_arrival_seconds'],'near cue clock')
    need(omen['threshold_second_current_phase']-omen['arrival_second_in_phase']==omen['threshold_relative_to_arrival_seconds'],'threshold cue clock')
    need({d['phase'] for d in store['duties']}==phases,'six identical daily duty phases')
    result={'status':'PASS' if not errors else 'FAIL','checks':checks,
      'counts':{'current_monsters':len(rows),'current_variants':variant_count,'store_mechanisms':len(systems),
                'primary_mechanism_distribution':dict(Counter(r['primary_system'] for r in rows))},
      'scope':'Current design coverage, links, budgets and authored invariants. No full monster runtime, dynamic route or fun validation.',
      'errors':errors}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return bool(errors)

if __name__=='__main__':
    raise SystemExit(main())
