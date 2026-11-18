#!/usr/bin/env python3
"""Cross-check the second audit's time, typed-stock and consumer contracts.

This checks declared data and measured static paths. It does not simulate a
complete night, moving enemies, the random sampler or a WeChat client.
"""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
errors=[];checks=0;hashes={}
def need(value,path,message):
 global checks
 checks+=1
 if not value:errors.append({'path':path,'message':message})
def read(name):
 p=ROOT/'content'/f'{name}.json';raw=p.read_bytes();hashes[str(p.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def index(rows):return {x['id']:x for x in rows}

t=read('temporal_resource_contract_v07');c=read('condition_lifecycle_v06');cards=index(read('encounters_v05')['encounters']);contracts=index(c['encounter_contracts']);events=index(read('events')['events']);items=read('items');item=index(items['items']);equip=index(read('equipment')['equipment']);aux=read('auxiliary_targets_v07');store=read('store_systems_v05');maps=read('maps');graph=read('condition_reachability_v06')
need(len(cards)==len(contracts)==60,'catalog','60 current cards and contracts required')
need(len(events)==72,'events','72 events must remain')
need(len(item)==24 and len(equip)==24,'catalog','24 item/equipment history entries must remain')
for fid,f in cards.items():
 need(f['runtime_enabled'] is False,fid,'current design is not a client implementation')
 need(contracts[fid]['normal_resolution']==f['resolution_condition'],fid,'current condition mirror differs')
 need(contracts[fid]['recovery']==f['failure_recovery'],fid,'current recovery mirror differs')
 for v in f['variants']:
  need(v['id'] in events[v['event_id']]['v05_encounter_variant_ids'],v['id'],'event reverse index missing')
need(sum(len(x['variants']) for x in cards.values())==120,'variants','two current variants per card remain')
need(not events['E035']['v05_encounter_variant_ids'],'E035','manager cannot accompany early scheduled monsters')
need(events['E035']['allowed_hours']==[5],'E035','visit must be N06 only')
timing=events['E035']['v07_timing'];visit=t['manager_visit']
need(timing['earliest_budget_second']==c['end_of_shift']['manager_arrival_budget_seconds']==700,'E035','actual manager starts at 700')
need(timing['latest_start_budget_second']+timing['handling_world_seconds_max']<=720,'E035','handling must fit dawn')
need(timing['actor_must_be_present_and_verified'] is True,'E035','presence and verification required')
need(cards['F20']['variants'][1]['event_id']=='E009','F20','unreachable manager branch must be replaced')
need(cards['F48']['variants'][0]['event_id']=='E022','F48','unreachable manager branch must be replaced')
for fid in ['F20','F48']:
 need('manager_authority_claim' in cards[fid]['runtime_parameters']['authored_claim_capabilities'],fid,'E031 claim needs same-actor capability')
need(t['e031_branches']['branch_inputs_are_not_unioned'] is True,'E031','normal and false claim branches cannot require each other')

offer_results=[]
for row in t['special_order_windows']:
 fid=row['encounter_id'];p=cards[fid]['runtime_parameters'];duration=p['accepted_special_order_deadline_world_seconds']
 latest=120-duration;expiry=min(20+24,latest)
 need(row['accepted_world_seconds']==duration and row['latest_phase_budget_accept']==latest,fid,'special deadline inconsistent')
 need(p['latest_accept_phase_budget_second']==latest,fid,'UI acceptance window differs from reserved work')
 need(row['close_at_first_clock'] and row['exact_deadline_commit_before_expiry'],fid,'both-clock expiry and commit ordering required')
 need(expiry>=20,fid,'scheduled special offer is never acceptable')
 offer_results.append({'id':fid,'latest_budget_accept':latest,'no_offset_effective_expiry':expiry})
need(next(x for x in offer_results if x['id']=='F27')['no_offset_effective_expiry']==30,'F27','90-second contract must close offer at phase budget 30')

spec=importlib.util.spec_from_file_location('consistency_map_nav',ROOT/'scripts/validate_maps.py');nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
scene=next(s for s in maps['scenes'] if s['id']=='MAP_STORE');roles={a['role']:a['position'] for a in scene['anchors']};walkable=nav.graph(scene,())
f42=t['f42_local_transfer'];route_results=[]
for a,b in [('rear_door','rear_threshold'),('rear_door','loading_bay'),('rear_door','dumpster'),('receiving','rear_threshold')]:
 path=nav.shortest(walkable,nav.cell(roles[a]),nav.cell(roles[b]));need(path is not None,'F42/'+a+'/'+b,'static path missing')
 if path is None:continue
 distance=len(path)-1;seconds=distance/f42['carry_speed']+distance/f42['walk_speed']+sum(f42[k] for k in ['open_seconds','pickup_seconds','place_seconds','close_seconds'])
 route_results.append({'from':a,'to':b,'tiles':distance,'seconds':round(seconds,6),'fits_8_seconds':seconds<=8})
 if b=='rear_threshold' and a=='rear_door':
  need(distance==f42['distance_tiles']==3,'F42','local endpoint distance changed')
  need(abs(seconds-f42['required_world_seconds'])<1e-9 and seconds<=8,'F42','declared local window does not fit')
 else:need(seconds>8,'F42/'+a+'/'+b,'negative long-route example no longer reproduces; review scope')
need(f42['full_duty_receipt_not_granted_by_gate_transfer'] is True,'F42','short transfer cannot become full disposal')

sup=index(c['supply_catalog']);meal=sup['SUP_MEAL'];repair=sup['SUP_MATERIAL_REPAIR']
need(cards['F22']['runtime_parameters']['accepted_food_kind']==meal['item_kind']=='meal_portion','F22','promised food type has no matching supply')
need('F22' in meal['used_by'] and 'SUP_MEAL' in contracts['F22']['supplies_on_accept'],'F22','real portion must be reserved')
need(cards['F08']['runtime_parameters']['repair_material_is_consumable'] is True and repair['type']=='finite_shop_consumable','F08','repair cannot be both reusable and consumed')
need('F39' not in repair['used_by'] and not cards['F39']['runtime_parameters']['repair_material_required'],'F39','unused repair material must not gate plaque transfer')
need(all('SUP_MATERIAL_REPAIR' not in contracts['F39'][k] for k in ['supplies_required','supplies_on_accept','supplies_arrival_payload']),'F39','stale supply gate')
need(cards['F07']['runtime_parameters']['reservation_timer_start_event']=='actual_manifestation','F07','sign preparation must not start the clock')
need(cards['F07']['runtime_parameters']['rehanging_sign_does_not_reset_timer'] is True,'F07','sign reset exploit')
need(cards['F49']['runtime_parameters']['covered_cooling_world_seconds']+cards['F49']['runtime_parameters']['heat_event_additional_cooling_world_seconds']==40,'F49','hot-weather duration is not explicit')
need(cards['F49']['runtime_parameters']['cooling_modifier_snapshotted_once_per_episode'] is True,'F49','modifier must not stack on reopening')
need(cards['F60']['runtime_parameters']['targetless_departure_world_seconds']==t['timer_origins']['F60']['targetless_departure_world_seconds']==3,'F60','departure clocks disagree')

for iid in ['I22','I23']:
 for key in ['acquisition_enabled','shop_enabled','lottery_enabled','reward_enabled','crafting_enabled']:
  need(item[iid].get(key) is False,iid+'/'+key,'unsupported aid must not be issued')
for key in ['acquisition_enabled','shop_enabled','lottery_enabled','reward_enabled','crafting_enabled']:
 need(equip['Q03'].get(key) is False,'Q03/'+key,'undefined sound recipient must not be issued')
need(sum(x.get('acquisition_enabled') is True for x in item.values())==22,'items','catalog vs obtainable count drift')
extension=aux['telegraph_extension'];i21=[x for x in extension['entries'] if x['source_id']=='I21']
need({x['monster_id'] for x in i21}=={'F50','F60'},'I21','unsupported target leaked into aid list')
need(all(x['requested_total_bonus_world_seconds']==3 for x in i21),'I21','explicit finite bonus required')
need(extension['combination']=='maximum_total_bonus_not_sum' and extension['expired_or_missing_warning_consumes_charge'] is False,'I21','stacking/invalid consumption must be guarded')
for fid,iid in [('F23','I21'),('F29','I04')]:
 p=cards[fid]['runtime_parameters'];gift=t['fixed_friendly_rewards'][fid]
 need(p['fixed_gift_item_id']==gift['item_id']==iid and p['fixed_gift_quantity']==gift['quantity']==1,fid,'fixed gift has no matching finite payload')
 need(item[iid]['acquisition_enabled'] and item[iid]['reward_enabled'],fid,'promised gift is disabled')
 for field in ['actual_delivery_receipt_required_for_gift','same_encounter_gift_settles_once','reward_handler_and_acquisition_policy_checked_before_offer','full_inventory_does_not_destroy_gift']:
  need(p[field] is True,fid+'/'+field,'gift must remain a bounded actual transfer')
f47=cards['F47']['runtime_parameters']
need(f47['base_coin_reward_by_segment']==t['fixed_friendly_rewards']['F47']['base_coins_by_segment']==[3,5,8],'F47','base reward per segment undefined or inconsistent')
need(f47['reward_manifest_coin_total']==sum(f47['base_coin_reward_by_segment'])==16,'F47','finite reward manifest differs')
need(f47['e065_bonus_at_first_actual_cashout_only'] and f47['e065_share_root_reward_id_and_night_quota'],'F47','fragment reward source can be duplicated')
for field in ['on_player_prevented','on_source_expired','on_refused']:
 need('等2秒' not in contracts['F60'][field] and '3世界秒' in contracts['F60'][field],'F60/'+field,'stale departure prose')
handover=t['historical_fact_admission']['prior_handover_adapter_scope']
need(handover['current_reference_requires_same_run_and_scene'] and handover['prior_original_record_must_keep_original_run_id'],'F25','cross-run reference scope must not imply history rewriting')
need('cross_run_same_object_refund_uniqueness' in handover['not_implemented_by_current_history_guard'],'F25','same-run helper must not claim a complete cross-run implementation')
lot=items['lottery'];frag=lot['fragment_contract'];double=lot['double_choice_contract'];refund=lot['refund_contract']
need(frag['fragments_required_per_exchange']==3 and frag['tickets_granted_per_exchange']==1,'E065','fragments have no concrete consumer')
need(frag['max_reward_sources_per_night']==1 and frag['same_root_reward_id_settles_once'],'E065','same source or night can be paid repeatedly')
need(frag['f47_and_e065_share_root_reward_id'],'E065','F47 cannot create another independent payout')
need(double['currency']=='earned_shift_ticket' and double['cost']==1,'E064','a nonexistent special ticket reappeared')
need(double['candidate_count']==2 and double['only_selected_candidate_granted'] and double['selected_result_updates_pity_exactly_once'],'E064','two choices must yield one settled award')
need(double['resume_pending_choice_never_rerolls'] and double['cannot_start_second_draw_with_pending_choice'],'E064','reveal/cancel loop')
need(refund['eligible_source']=='paid_shop_purchase_only' and refund['lottery_and_gifts_eligible'] is False,'E072','refund must consume a real paid original')
need(refund['refund_limit']=='actual_paid_amount_of_purchase_line' and refund['one_refund_per_purchase_line'],'E072','refund can mint excess money')
need(events['E072']['v07_original_overpayment_condition_removed'] is True,'E072','old unproduced overpayment condition remains')
fear=events['E060']['v07_source_contract']
need(fear['previous_night_san_threshold']==fear['current_san_threshold']==40 and fear['max_instances_per_source']==1,'E060','nightmare must use finite actual SAN history')
need(fear['no_separate_trauma_or_sleep_debt_state'] and fear['event_reward_does_not_stack_with_action_reward'],'E060','phantom state or double day reward')

need(c['lifecycle']['instance_ids_cannot_be_overwritten_or_reopened'],'state','terminal IDs cannot be reused')
need(c['actors']['object_and_target_locks_required_in_addition_to_actor_lock'],'state','actor-only concurrency guard is insufficient')
need(c['clock_contract']['movement_credits_only_actual_advanced_world_time'],'state','requested future movement is not actual movement')
need(c['wounds']['reactive_consumers']['f21_child_slots_reference_parentSlotId'],'F21','child slots must bind actual parent')
need(c['wounds']['reactive_consumers']['repair_after_actual_cut_does_not_erase_wound_or_release_valid_child'],'F21','device repair cannot undo prior injury')
f02=next(x for x in graph['encounters'] if x['id']=='F02')
need('CORROBORATING_WORK_TRACE' in f02['required_before_arrival'],'F02','public work receipt is missing from source graph')
need(t['client_implemented'] is False and aux['client_implemented'] is False,'scope','design must not claim a client')

report={'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors,'scope':'Cross-file declared temporal, supply and consumer contracts plus four static route calculations; not full gameplay.','inputs_sha256':hashes,'special_offer_windows':offer_results,'f42_routes':route_results,'counts':{'encounters':60,'variants':120,'events':72,'item_catalog':24,'current_item_acquisition_candidates':22,'equipment_catalog':24}}
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
