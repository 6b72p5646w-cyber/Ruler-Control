#!/usr/bin/env python3
"""Check declared cross-phase examples and actual consumer links, not full play."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
errors=[];checks=0;hashes={}
def need(v,path,message):
 global checks
 checks+=1
 if not v:errors.append({'path':path,'message':message})
def read(name):
 p=ROOT/'content'/f'{name}.json';raw=p.read_bytes();hashes[str(p.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def index(rows):return {x['id']:x for x in rows}
cards=index(read('encounters_v05')['encounters']);core=read('condition_lifecycle_v06');contracts=index(core['encounter_contracts']);events=index(read('events')['events']);closure=read('consumer_closure_v08');items=index(read('items')['items']);equipment=index(read('equipment')['equipment']);pets=index(read('pets')['pets']);balance=read('balance');actions=index(balance['day_actions']);rules=index(read('rules')['rules']);synergies=index(read('synergies')['synergies']);store=read('store_systems_v05');aux=read('auxiliary_targets_v07');maps=read('maps');mechanics=read('map_mechanics_v05')
need(len(cards)==60 and len(events)==72 and len(rules)==20,'catalog','preserve current scope')
need(len(synergies)==18 and sum(x.get('enabled_current',False) for x in synergies.values())==13,'synergies','current count drift after explicit S05/S14 archival')
need({k for k,v in synergies.items() if not v.get('enabled_current',False)}=={'S03','S05','S11','S12','S14'},'synergies','unsupported causal links and dual pursuit must remain archived')
need(all(x['runtime_enabled'] is False for x in cards.values()),'scope','client flags cannot be inferred from static checks')
for fid,c in cards.items():
 need(c['resolution_condition']==contracts[fid]['normal_resolution'],fid,'condition resolution mirror differs')
 need(c['failure_recovery']==contracts[fid]['recovery'],fid,'recovery mirror differs')
 for v in c['variants']:
  overlap={int(p[1:])-1 for p in c['allowed_phases']}&set(events[v['event_id']]['allowed_hours'])
  need(bool(overlap),v['id'],'no possible phase shared by monster and event')
  need(v['id'] in events[v['event_id']]['v05_encounter_variant_ids'],v['id'],'reverse event index missing')

carry=core['active_carryover'];need(carry['max_additional_phases']==1 and carry['latch_on_announcement_or_activation'],'carryover','bounded lifetime must be latched')
need(carry['origin_phase_source']=='admitted_instance_reserved_slot.phase','carryover','origin must be the real admitted slot')
need(carry['deadline_does_not_reset_at_phase_change'] and carry['same_time_actions_and_terminal_updates_before_expiry'],'carryover','reset or same-time ordering regression')
need(carry['true_six_promise_policy_exempt'],'F53','long promise cannot use hostile carryover deadline')
need(min((3+1+carry['max_additional_phases'])*120,720)==600,'F26','N04 threat must finish by N05 end')
for k in ['actual_movement_outputs_commit_before_same_time_arrival_recheck','requested_future_movement_is_not_actual_fact','expired_trace_ttl_frees_live_cap_at_same_endpoint']:
 need(core['clock_contract'].get(k) is True,'clock/'+k,'same-time world production contract missing')
for k in ['daytime_zero_has_no_night_world_countdown','night_entry_at_zero_starts_one_panic','night_only_reference_rejects_day_mode','initial_zero_night_keeps_existing_free_stabilization']:
 need(balance['resources']['san'].get(k) is True,'san/'+k,'initial SAN policy missing')

s6=synergies['S06'];s8=synergies['S08'];s17=synergies['S17'];s15=synergies['S15']
need(s6['monster_ids']==s6['active_monster_ids']==['F12'],'S06','old tool must not imply an active F08')
need(not s6['source_contract_v08']['tool_created_by_synergy'] and not s6['source_contract_v08']['fixture_created_by_synergy'],'S06','object or fixture invented')
need(s6['source_contract_v08']['paperclip_only_lure_unchanged'] and s6['source_contract_v08']['tool_already_placed_skips_preparation'],'S06','prevention or canonical lure changed')
need(s8['active_monster_ids']==['F38'] and not s8['source_contract_v08']['F21_must_remain_active'],'S08','history mistaken for concurrent entity')
for k in ['requires_distinct_second_root_and_independence_domain','historical_receipt_is_not_current_presence_proof','current_body_requires_bound_continuity_or_current_species_test','must_precede_F38_first_omen']:
 need(s8['source_contract_v08'][k] is True,'S08/'+k,'historical identity support too broad')
steps=s8['temporal_witness_v08']['steps'];need([x['budget'] for x in steps]==sorted(x['budget'] for x in steps),'S08','time witness unordered')
need(steps[0]['budget']<steps[2]['budget']<steps[3]['budget'],'S08','history is too late for omen')
need(s8['temporal_witness_v08']['historical_presence_age_at_F38_arrival_world_seconds']>core['evidence']['live_presence_snapshot_world_ttl_seconds'],'S08','stale-presence negative example lost')
need(s15['source_contract_v08']['partial_acceptance_enabled'] is False,'S15','unsupported partial contract remains')
need([s15['source_contract_v08'][x] for x in ['offered_bottles','retained_bottles','saleable_bottles']]==[6,2,4],'S15','fixed water quantities differ')
need(set(s17['monster_ids'])=={'F36','F53'} and s17['active_monster_ids']==['F36'],'S17','unreachable F36/F51 pair remains')
source=s17['source_contract_v08'];timeline=s17['temporal_witness_v08']['steps']
need(source['requires_actual_prior_acceptance_receipt'] and source['requires_actual_water_split_and_seal_receipt'],'S17','prior commitment has no real source')
need(source['all_three_slot_instance_ids_must_differ'] and source['new_slots_created'] is False,'S17','slot alias or invented slot')
need(timeline[2]['budget']<timeline[3]['budget']<timeline[4]['budget'],'S17','source not ready by first omen')
need(timeline[6]['budget']-timeline[5]['budget']==cards['F36']['runtime_parameters']['lease_world_seconds']==20,'S17','short lease timing differs')
need(timeline[-1]['budget']==720 and timeline[6]['budget']<=240,'S17','long and short contracts collapse')
scene=next(x for x in maps['scenes'] if x['id']=='MAP_STORE');anchors={x['role']:x['position'] for x in scene['anchors']}
objects=index(mechanics['objects']);lease=objects['OBJ_LEASE_MARKER'];recorded_rect=s17['temporal_witness_v08']['map_witness']['lease_rect']
actual_rect=lease.get('leased_rect')
need(actual_rect==recorded_rect,'S17','lease rectangle changed; remeasure source witness')
x,y,w,h=recorded_rect
for key in ['retained_container_anchor','saleable_container_anchor']:
 px,py=anchors[source[key]];need(not (x<=px<x+w and y<=py<y+h),'S17/'+key,'water slot lies inside lease')

food=closure['food_verification'];need(food['inspection_world_seconds']==3 and not food['requires_qte'],'H10','free inspection changed')
need(set(food['edible_item_ids'])<=set(items),'H10','food kind absent from item catalog')
need('I04' in food['edible_item_ids'] and items['I04']['tag']=='san','H10','effect tag must not bypass food provenance')
need(items['I04']['resource_deltas']=={'san':8},'I04','machine-readable effect missing')
need(food['ownership_alone_makes_food_safe'] is False and food['guest_gift_initial_status']=='sealed_unverified','H10','ownership incorrectly authenticates food')
need(cards['F29']['runtime_parameters']['gift_food_inspection_world_seconds']==food['inspection_world_seconds'],'F29','gift and H10 inspection disagree')
need(cards['F29']['runtime_parameters']['gift_inspection_handler_required_before_offer'],'F29','edible gift promised without an inspection consumer')
need('consumer_closure_v08' in rules['H10']['v06_condition_contract']['consumer_closure_contract'],'H10','rule still lacks gift verification path')
need(core['lifecycle']['per_declared_reward_key_max']==1 and 'root_episode_reward_max' not in core['lifecycle'],'rewards','one overall claim must not block three declared segments')
benefits={(x['monster_id'],x['reward_key']):x for x in closure['friendly_benefits']['benefits']}
need(len(benefits)==len(closure['friendly_benefits']['benefits']),'rewards','duplicate reward key')
need([benefits[('F47',f'segment_{i}')]['amount'] for i in [1,2,3]]==cards['F47']['runtime_parameters']['base_coin_reward_by_segment']==[3,5,8],'F47','segment reward manifest differs')
for fid,key,field in [('F33','aid','aid_reward_san'),('F36','rent','full_lease_rent_coins'),('F53','dawn','fulfilled_reward_san'),('F55','escort','completed_escort_san_reward')]:
 need(benefits[(fid,key)]['amount']==cards[fid]['runtime_parameters'][field],fid,'reward amount differs')
need(benefits[('F35','cleaning')]['kind']=='existing_work_credit' and not benefits[('F35','cleaning')]['extra_token_or_currency'],'F35','phantom secondary reward')
need(not cards['F55']['runtime_parameters']['next_night_warning_token_enabled'],'F55','undefined warning token remains')
need(benefits[('F53','dawn')]['payment_phase']=='after_verified_handover' and 'verified_handover_completed' in benefits[('F53','dawn')]['requires'],'F53','reward may bypass active panic at six')
need(closure['f53_preserved_stock']['promised_items_block_unrelated_sale_or_consumption'] and closure['f53_preserved_stock']['unfulfilled_or_cancelled_san_delta']==0,'F53','unreachable sale-breach punishment remains')
for fid in ['F23','F29']:
 need(cards[fid]['runtime_parameters']['encounter_can_end_before_optional_gift_claim'],'gift/'+fid,'unclaimed reward can hold encounter active')

for eid in ['Q03','Q11']:
 for flag in ['acquisition_enabled','shop_enabled','lottery_enabled','reward_enabled','crafting_enabled']:
  need(equipment[eid].get(flag) is False,eid+'/'+flag,'undefined effect still obtainable')
need('Q11' in aux['acquisition']['disabled_ids'],'Q11','auxiliary availability disagrees')
need(actions['A06']['enabled'] is False and actions['A06']['selectable'] is False and not actions['A06']['unavailable_consumes_slot'],'A06','unsupported maintenance still consumes time')
need(events['E051']['enabled_current'] is False and not events['E051']['v08_availability']['invalid_selection_consumes_time'],'E051','repair event not gated with A06')
p06=pets['P06']['general_help'];effect=p06['effects'][0]
need(p06['effect_type']=='scheduled_item_transfer' and p06['duration_seconds']==3,'P06','undefined escalation timer remains')
need(effect['requires_actual_existing_world_instance'] and effect['requires_owned_unreserved_unequipped_tool'],'P06','ordinary retrieval has no concrete item')
need('hidden_light_tool' in effect['forbidden_tags'] and effect['transfer_mode']=='move_same_existing_instance','P06','general aid replaces F46 or duplicates tool')
p08=pets['P08']['special_help'][0]['effects'][0];rest=closure['f31_p08_rest'];f31=cards['F31']['runtime_parameters']
need(p08['first_actual_failure_energy_compensation']==f31['p08_first_real_failure_energy_compensation']==rest['pet_first_real_failure_compensation_energy']==2,'P08','compensation differs')
need(p08['total_rest_energy_cap']==f31['successful_rest_energy_total']==rest['successful_rest_total_energy']==4,'P08','rest can pay 2+4 rather than total4')
need('retained_rest_fraction' not in p08 and p08['voluntary_cancel_grants_compensation'] is False,'P08','undefined prior gain or cancellation farming remains')
rest=closure['f31_p08_rest'];qte=read('qte');wake=index(qte['task_profiles'])['F31_wake']
need('pet_retry_world_or_local_seconds' not in rest and rest['pet_retry_local_window_seconds']==1.5,'F31','retry clock remains ambiguous')
need(rest['attempt_cost_budget_seconds']==wake['attempt_cost_seconds']==cards['F31']['runtime_parameters']['attempt_cost_budget_seconds']==8,'F31','per-attempt cost differs')
need(rest['local_attempt_cycle_seconds']==wake['cycle_seconds']==3 and wake['local_cycles_per_attempt']==1,'F31','local timing remains unbounded')
need(wake['segment_base_windows_seconds']==[rest['normal_first_base_hit_window_local_seconds']]==[1.2],'F31','first hit window differs')
need(rest['max_attempts_without_pet']==1 and rest['max_attempts_with_prepared_pet']==2,'F31','unlimited rest retry remains')
need(rest['retry_requires_positive_san'] and rest['san_zero_exits_to_normal_panic_without_new_qte'],'F31','zero SAN grants a precision retry')
need(rest['each_retry_separately_reserved_and_charged'] and rest['started_cancel_cost_budget_seconds']==8,'F31','retry or cancellation avoids attempt cost')
need(rest['second_failure_ends_rest_episode'] and rest['first_failure_without_usable_retry_ends_rest_episode'],'F31','failed rest never terminates')
need(wake['prepared_p08_retry']['visible_hit_window_local_seconds']==p08['retry_visible_hit_window_seconds']==1.5,'P08','normal retry window differs')
need(wake['prepared_p08_retry']['attempt_cost_seconds']==p08['retry_attempt_cost_budget_seconds']==8,'P08','pet retry cost differs')
need(p08['max_extra_attempts']==1 and p08['retry_clock']=='local_qte' and p08['retry_failure_ends_rest_episode'],'P08','pet still offers a world-time or unlimited retry')
need(cards['F31']['qte_binding']['task_profile_id']=='F31_wake','F31','wake profile has no current consumer')

k=balance['knowledge'];pages=index(k['method_pages']);systems=index(store['systems'])
need(len(pages)==7 and k['base_twenty_rules_always_free'] and k['base_safe_actions_never_require_method_page'],'knowledge','finite optional knowledge and free safety boundary required')
need(k['base_rule_unlocks_still_progressive'] and k['free_does_not_mean_all_rules_unlocked_at_new_game'],'knowledge','free learning erases progressive rule discovery')
for pid,p in pages.items():
 need(bool(p['applicable_phenomena'] and p['method_steps'] and p['limits']),pid,'method page only has a name')
 need(set(p['system_ids'])<=set(systems) and set(p['monster_ids'])<=set(cards) and set(p['event_ids'])<=set(events),pid,'unknown method reference')
need(actions['A03']['study_points']==k['study_action']['points_per_completed_action']==k['study_action']['page_price']==2,'A03','points without a page consumer')
need(actions['A04']['research_progress']==k['case_review']['progress_consumed_per_case_revision']==1,'A04','progress without a case consumer')
need(k['case_review']['independent_count_is_necessary_not_sufficient'] and not k['case_review']['may_change_current_permissions'],'A04','record count alone authenticates identity')
for eid in ['Q04','Q07','Q18']:
 need(equipment[eid].get('paid_knowledge_page_required') is False,eid,'optional knowledge page gates an item effect')
need('净化灵体仅对已研究' not in items['I20']['tradeoff'],'I20','unimplemented researched purification effect remains')
for eid in ['E050','E055','E056','E059','E060','E063']:
 need(events[eid]['knowledge_contract']=='content/balance.json#/knowledge',eid,'knowledge event not linked')
 need(events[eid]['v08_day_action_binding']['no_duplicate_full_action_reward'] and events[eid]['v08_day_action_binding']['no_available_target_consumes_nothing'],eid,'day rewards may stack or empty action may charge')
noise=closure['e062_noise_sleep'];need(noise['stay_home']['coins_cost']==0 and noise['move_to_existing_study_rest_area']['coins_cost']==10,'E062','no free noise branch or price undefined')
need(not noise['extra_soundproof_item_required'] and not noise['stack_full_A01_reward_again'],'E062','unproduced item or double sleep reward')
need(events['E062']['consumer_closure_contract'].endswith('/e062_noise_sleep'),'E062','event not linked to actual sleep effect')

report={'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors,'inputs_sha256':hashes,'counts':{'current_cards':60,'current_variants':120,'event_catalog':72,'current_event_design_candidates':sum(e.get('enabled_current',True) for e in events.values()),'current_synergy_design_cases':13,'method_pages':7},'scope':'Cross-file consumer and temporal consistency plus explicit S06/S08/S17 source chronology and fixed-slot geometry. Not complete dynamic reachability, all random combinations, client or playtesting.'}
print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(bool(errors))
