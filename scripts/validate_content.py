#!/usr/bin/env python3
"""Validate V0.4 design references and configuration invariants, not gameplay balance."""

from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
checks = 0
errors = []


def require(condition, message):
    global checks
    checks += 1
    if not condition:
        errors.append(message)


def catalog(name, key, prefix, count):
    data = json.loads((ROOT / 'content' / f'{name}.json').read_text(encoding='utf-8'))
    rows = data[key]
    expected = {f'{prefix}{i:03d}' if prefix == 'E' else f'{prefix}{i:02d}' for i in range(1, count + 1)}
    require(len(rows) == count, f'{name}: expected {count} rows')
    require({r['id'] for r in rows} == expected, f'{name}: IDs must be exactly {sorted(expected)}')
    require(len({r['id'] for r in rows}) == len(rows), f'{name}: duplicate IDs')
    return data, {r['id']: r for r in rows}


def main():
    monster_data, monsters = catalog('monsters', 'monsters', 'F', 60)
    event_data, events = catalog('events', 'events', 'E', 72)
    rule_data, rules = catalog('rules', 'rules', 'H', 20)
    item_data, items = catalog('items', 'items', 'I', 24)
    gear_data, gear = catalog('equipment', 'equipment', 'Q', 24)
    pet_data, pets = catalog('pets', 'pets', 'P', 8)
    synergy_data, synergies = catalog('synergies', 'synergies', 'S', 18)
    balance = json.loads((ROOT / 'content/balance.json').read_text(encoding='utf-8'))
    source_data = json.loads((ROOT / 'content/sources.json').read_text(encoding='utf-8'))
    sources = {s['id']: s for s in source_data['sources']}
    require(len(sources) == len(source_data['sources']) == 63, 'sources: 63 unique records required')
    require(sum(s['source_type'] == 'folklore_reference' for s in sources.values()) == 57, 'sources: 57 folklore records required')
    require(sum(s['source_type'] == 'official_screen_reference' for s in sources.values()) == 2, 'sources: 2 screen references required')
    require(sum(s['source_type'] == 'official_game_reference' for s in sources.values()) == 4, 'sources: 4 official game references required')
    for sid, source in sources.items():
        require(urlparse(source['url']).scheme in {'https', 'http'}, f'{sid}: invalid source URL')
        require(bool(source['title'] and source['supported_claim'] and source['accessed_date']), f'{sid}: missing attribution fields')

    for fid, monster in monsters.items():
        require(len(monster['evidence']) >= 2 and len(set(monster['evidence'])) >= 2, f'{fid}: two evidence descriptions required')
        require(bool(monster['source_ids']) and all(s in sources for s in monster['source_ids']), f'{fid}: unresolved source')
        require(bool(monster['signature_interaction'] and monster['safe_response'] and monster['adaptation_notice']), f'{fid}: incomplete encounter design')
        require(bool(monster['synergy_conditions'].get('harder') and monster['synergy_conditions'].get('easier')), f'{fid}: two conditional synergy directions required')
        require(1 <= monster['base_cost'] <= 3, f'{fid}: base pressure out of range')
        require(set(monster['impersonation']['targets']) <= {'同事', '店长'}, f'{fid}: unplanned core staff target')
        if not monster['impersonation']['enabled']:
            require(not monster['impersonation']['targets'], f'{fid}: disabled impersonation must not target staff')
        # Cross-reference syntax is F followed by exactly two digits.
        for ref in set(re.findall(r'\bF\d{2}\b', json.dumps(monster, ensure_ascii=False))):
            require(ref in monsters, f'{fid}: dangling monster reference {ref}')
    require(monster_data['default_excluded_ids'] == ['F14'], 'default exclusion must explicitly include F14')
    require(monsters['F14']['enabled_default'] is False and monsters['F14']['advanced_optional'] is True, 'F14 must be optional and disabled')
    require(monsters['F14']['impersonation']['enabled'] is False, 'F14 possession must not silently become impersonation')
    require(sum(m['enabled_default'] for m in monsters.values()) == 59, 'default pool must contain 59 enabled candidates')

    require(balance['week_length_days'] == 7 and balance['same_phases_every_day'] is True, 'week must share fixed daily phases')
    require(balance['night_seconds_per_hour'] == 120, 'night hour budget must be 120 seconds')
    require(balance['day_action_slots'] == 6 and balance['day_hours_per_slot'] == 2, 'daytime must have six two-hour slots')
    night_phases = [p for p in balance['daily_phases'] if p['id'].startswith('N')]
    expected_intervals = [(f'{h:02d}:00', f'{h+1:02d}:00') for h in range(6)]
    require([(p['start'], p['end']) for p in night_phases] == expected_intervals, 'night phases must run 00:00 to 06:00 in order')
    require(len(balance['director']['active_limits_by_day']) == len(balance['director']['stress_budgets_by_day']) == 7, 'director needs seven daily budgets')
    require(balance['director']['max_new_primary_per_hour'] == 1, 'one new primary encounter per hour required')
    require(balance['director']['impersonators_max_first_week'] == 1, 'first week must cap simultaneous impersonators at one')
    require(balance['resources']['energy']['daytime_hour_drain'] == 0, 'day energy must not have hidden hourly drain')
    require(balance['resources']['satiety']['accounting_clock'] == 'unified_24_hour_game_clock', 'satiety must use one clock')
    require(balance['resources']['san']['stabilization_allowed_during_panic'] is True, 'stabilization must remain possible during panic')
    require(balance['resources']['san']['safe_zone_stabilization_seconds'] <= balance['resources']['san']['panic_window_seconds'], 'panic response must fit time budget')

    rule_tags = {r['tag'] for r in rules.values()}
    require(rule_data['canonical_manual_immutable'] is True, 'confirmed manual must remain stable')
    category_counts = Counter(e['category'] for e in events.values())
    require(len(category_counts) == 8 and set(category_counts.values()) == {9}, 'events must contain 8 groups of 9')
    for eid, event in events.items():
        require(len(event['choices']) >= 2 and all(c['label'] and c['consequence'] for c in event['choices']), f'{eid}: choices need consequences')
        require(set(event['required_rule_tags']) <= rule_tags, f'{eid}: unknown prerequisite rule tag')
        require(event['allowed_hours'] and all(isinstance(h, int) and 0 <= h <= 23 for h in event['allowed_hours']), f'{eid}: invalid allowed hours')
        require(bool(event['latest_finish'] and event['time_binding'] and event['work_credit']), f'{eid}: missing scheduling contract')
        require(0 <= event['duration_seconds'] <= 120, f'{eid}: invalid operation budget')
        if event['phase'] == 'night':
            require(set(event['allowed_hours']) <= set(range(6)), f'{eid}: night event outside night hours')
        if event['phase'] == 'day':
            require(event['duration_seconds'] == 0, f'{eid}: day event must resolve through stated action slots')
        for choice in event['choices']:
            require('time_cost' in choice, f'{eid}: unstated branch time cost')
    require(5 not in events['E004']['allowed_hours'], 'E004 must not accept a next-hour order after 05:00')
    for eid in ['E029', 'E030']:
        binding = events[eid]['entity_binding']
        require(binding['anomalous_variant_requires_binding'] is True and binding['create_new_entity'] is False, f'{eid}: identity event bypasses entity budget')
        require(events[eid]['permission_policy']['high_risk_independent_sources_min'] >= 2, f'{eid}: high-risk permissions require two independent sources')
    parade = events['E037']
    require(parade['allowed_hours'] == [1, 2, 3, 4] and parade['duration_seconds'] == 120, 'E037: full-hour event must stay in compatible work phases')
    require(parade['primary_slot'] is True, 'E037 must occupy primary encounter slot')
    require(sum(t['end_second'] - t['start_second'] for t in parade['timeline']) == 120, 'E037 timeline must total 120 seconds')
    for hour, actions in parade['work_credit']['required_actions_by_hour'].items():
        require(sum(a['count'] * a['seconds_each'] for a in actions) == 40, f'E037 hour {hour}: embedded work must total 40 seconds')
    require(events['E045']['reservation']['one_batch_per_due_night'] is True, 'E045 must merge obligations into one batch')
    require(events['E071']['creates_obligation']['reserve_before_reward'] is True, 'E071 must reserve before paying reward')
    require(events['E048']['time_binding']['no_half_day_slot'] is True, 'E048 cannot invent half daytime slots')

    lottery = item_data['lottery']
    require(abs(sum(lottery['base_tier_probabilities'].values()) - 1.0) < 1e-9, 'lottery base probabilities must sum to one')
    require(abs(sum(lottery['noncommon_pity_weights'].values()) - 1.0) < 1e-9, 'lottery pity weights must sum to one')
    require(Counter(i['rarity'] for i in items.values()) == Counter({'common': 12, 'uncommon': 8, 'rare': 4}), 'lottery tier counts must remain 12/8/4')
    require(lottery['noncommon_pity_after_common_draws'] == 4 and lottery['rare_pity_after_nonrare_draws'] == 9, 'lottery pity thresholds must be 5th/10th draws')
    require(lottery['rare_pity_has_priority'] is True and lottery['pity_persistence']['across_weeks'] is True, 'rare pity priority and cross-week persistence required')
    require(lottery['atomic_ticket_reward_counter_save'] is True, 'draw cost, prize and counters must save together')
    meal = item_data['job_supply']['daily_free_food']
    require({i['item_id']: i['quantity'] for i in meal['items']} == {'I01': 1, 'I02': 1}, 'daily basic meals missing')
    require(meal['nominal_satiety_total'] == 65 and meal['requires_completed_night'] is False, 'meal safety provision must not depend on winning')
    require(gear_data['baseline_inventory_slots'] == 4 and gear_data['available_hands'] == 2, 'baseline inventory and hands not defined')
    require(Counter(g['slot'] for g in gear.values()) == Counter({slot: 4 for slot in gear_data['slots']}), 'each of six equipment slots needs four entries')
    require(all(0 <= g['hands_required'] <= 2 for g in gear.values()), 'gear has impossible hand requirement')
    require(gear['Q05']['hands_required'] == 1 and gear['Q06']['hands_required'] == 0, 'handheld light must differ from headlamp')
    care_ids = {s['id'] for s in pet_data['care_supplies']}
    for pid, pet in pets.items():
        require(pet['uses_per_night'] == (1 if pid in {'P07', 'P08'} else 2), f'{pid}: inconsistent active-use limit')
        require(pet['care_supply_id'] in care_ids, f'{pid}: missing care supply')
    require(pet_data['may_replace_identity_proof'] is False and pet_data['permanent_death'] is False, 'pet scope changed')

    for sid, synergy in synergies.items():
        require(bool(synergy['monster_ids']) and all(fid in monsters for fid in synergy['monster_ids']), f'{sid}: dangling monster reference')
        require(all(eid in events for eid in synergy['event_ids']), f'{sid}: dangling event reference')
        require('F14' not in synergy['monster_ids'], f'{sid}: disabled possession must not enter default synergy cases')
        require(bool(synergy['condition'] and synergy['hard_admission_gate'] and synergy['player_response']), f'{sid}: needs conditions, admission limits and response')

    # V0.3 interaction-first contract. These are design integrity checks, not a client simulation.
    interaction_data, verbs = catalog('interactions', 'verbs', 'V', 10)
    _, work = catalog('interactions', 'work_templates', 'W', 16)
    qte_data, qtes = catalog('qte', 'templates', 'QT', 3)
    component_data, components = catalog('rule_components', 'components', 'RC', 8)
    variant_data, variants = catalog('event_variants', 'event_variants', 'EV', 12)
    deploy_data, deployables = catalog('deployables', 'deployables', 'B', 8)
    blueprints = json.loads((ROOT / 'content/encounter_blueprints.json').read_text(encoding='utf-8'))
    encounters = {e['id']: e for e in blueprints['encounters']}
    require(set(encounters) == {'F12', 'F13'}, 'V0.3: exactly two detailed encounter blueprints')
    require(blueprints['default_director_policy']['max_active_player_pursuers'] == 1, 'prototype must cap active pursuers')
    require(blueprints['default_director_policy']['simultaneous_f12_f13_enabled'] is False, 'F12/F13 double pursuit is disabled')
    require(balance['director']['prototype_max_active_player_pursuers'] == 1, 'director and blueprint pursuit limits differ')
    require(balance['time_budget_semantics']['wall_clock_session_duration_is_fixed'] is False, 'closeups must not promise a fixed real session duration')
    for wid, task in work.items():
        require(set(task['verb_ids']) <= set(verbs), f'{wid}: missing shared verb')
        require(set(task['phases']) <= {p['id'] for p in night_phases}, f'{wid}: invalid phase')
        require(0 < task['base_operation_seconds'] <= task['max_attempt_operation_seconds'], f'{wid}: operation budget invalid')
        require(bool(task['success_feedback'] and task['failure_feedback'] and task['modifier_fields']), f'{wid}: missing feedback or modifiers')
    require(work['W06']['scale'] == work['W15']['scale'] == 'world', 'meat and lure handling must stay in world scale')
    for vid, variant in variants.items():
        require(variant['event_id'] in events, f'{vid}: dangling event')
        require(set(variant['work_template_ids']) <= set(work), f'{vid}: dangling work template')
        require(set(variant['monster_ids']) <= set(monsters), f'{vid}: dangling monster')
        require(set(variant['implementation_gate']['required_rule_components']) <= set(components), f'{vid}: dangling rule component')
        task_fields = set().union(*(set(work[wid]['modifier_fields']) for wid in variant['work_template_ids']))
        require(variant['modifier_field'] in task_fields, f'{vid}: event override not allowed by its work templates')
        require(variant['modifier_field'] in components['RC08']['allowed_fields'], f'{vid}: override missing from component registry')
        require(variant['victory_contract']['preserve_monster_core_win_predicate'] is True, f'{vid}: cannot replace core victory')
        require(variant['implementation_gate']['all_required_features_must_be_implemented_and_enabled'] is True, f'{vid}: feature gate missing')
        require(vid in events[variant['event_id']]['interaction_variant_ids'], f'{vid}: event backlink missing')
    require(variants['EV03']['implementation_stage'] == 'expansion' and variants['EV03']['enabled_by_default'] is False, 'F13/freezer-failure combination must stay gated')
    require(qte_data['snapshot_modifiers_at_attempt_start'] is True, 'QTE geometry must be snapshotted')
    require(qte_data['timing_window_seconds_min'] >= 0.6 and qte_data['telegraph_seconds_min'] >= 1.5, 'QTE warning/window floors invalid')
    require(qte_data['ordinary_button_and_grab_areas_shrink'] is False, 'SAN may not shrink ordinary controls')
    require(qte_data['closeup_time_policy']['admit_only_if_no_active_chase'] is True, 'chase-to-closeup exploit')
    require(qte_data['closeup_time_policy']['cost_reserved_on_start_charged_once_on_exit'] is True, 'closeup cost commit contract missing')
    for san in range(101):
        bands = [b for b in qte_data['bands'] if b['san_min'] <= san <= b['san_max']]
        require(len(bands) == 1, f'SAN {san}: needs exactly one profile')
        require(bands and bands[0]['clear_radius_tiles'] >= qte_data['world_clear_radius_tiles_min'], f'SAN {san}: clear radius below floor')
    require(blueprints['baseline']['carrying_meat_walk_speed'] == component_data['units']['raw_meat_carry_speed'] == 2.6, 'meat carrying speeds differ')
    require(blueprints['baseline']['monster_move_speed'] < blueprints['baseline']['carrying_meat_walk_speed'], 'prototype baseline chase lacks carrying speed margin')
    for fid, encounter in encounters.items():
        state_ids = {s['id'] for s in encounter['states']}
        require('CLEARED' in state_ids, f'{fid}: missing terminal state')
        for state in encounter['states']:
            for transition in state.get('transitions', []):
                require(transition['to'] in state_ids, f'{fid}: unknown state transition')
        require(encounter['pursuit_interactions_require_qte'] is False, f'{fid}: pursuit actions may not require QTE')
        require(encounter['playable_client_implemented'] is False, f'{fid}: headless reference is not a client')
    require(encounters['F13']['preemptive_clear_before_contact'] is True, 'early meat delivery must clear')
    require(encounters['F13']['delivery_receipt_contract']['success_evaluates_committed_receipt_not_later_power_state'] is True, 'committed meat receipt priority missing')
    require(encounters['F12']['success_requires_extra_close_door'] is False, 'F12 victory must not add extra door objective')
    require(pet_data['ability_rules']['general_and_special_share_charge_pool'] is True, 'pet skills must share charges')
    for pid, pet in pets.items():
        require(pet['shared_ability_charge_pool'] is True and bool(pet['general_help'] and pet['special_help']), f'{pid}: general/specific help missing')
        for ability in [pet['general_help']] + pet['special_help']:
            require(set(ability['target_monster_ids']) <= set(monsters), f'{pid}: unknown special target')
            require(ability['shared_charge_cost'] == 1, f'{pid}: unclear charge use')
    dog_effect = pets['P02']['special_help'][0]['effects'][0]
    require(dog_effect['target_state'] == 'CHASE_PLAYER' and dog_effect['value'] == 0.7, 'P02 must match F13 chase state')
    hamster_effect = pets['P04']['special_help'][0]['effects'][0]
    require(hamster_effect['lure_tag'] == encounters['F12']['objects']['bait_tag'], 'P04 lure tag mismatch')
    require(hamster_effect['max_extensions_per_lure_instance'] == 1 and hamster_effect['does_not_create_lure'] is True, 'P04 cannot duplicate lure or stack indefinitely')
    require(deploy_data['shared_rules']['max_active_total'] == 3 and deploy_data['shared_rules']['navigation_graph_changes'] is False, 'deployment scope grew beyond fixed sockets')
    for bid, device in deployables.items():
        require(device['world_path_graph_mutation'] is False, f'{bid}: dynamic navigation blocker outside scope')
        require(device['instances_preserve_remaining_resources'] is True, f'{bid}: recovery must not refill resources')
        require(device['may_complete_encounter_goal'] is False, f'{bid}: helper cannot auto-clear encounter')
        require(set(device['special_target_monster_ids']) <= set(monsters), f'{bid}: unknown target')
    require(deployables['B05']['effect']['lure_tag'] == encounters['F12']['objects']['bait_tag'], 'B05 lure tag mismatch')
    require(deployables['B06']['effect']['item_tag'] == encounters['F13']['objects']['meat_tag'], 'B06 meat tag mismatch')
    require(sum('operational_extension' in item for item in items.values()) == 13, '13 immediate item extensions expected')

    # Full encounter design and map bindings. Feature completion is deliberately separate.
    design_data, designs = catalog('encounter_designs', 'encounters', 'F', 60)
    system_data, systems = catalog('systems_v04', 'modules', 'MC', 12)
    map_data = json.loads((ROOT / 'content/maps.json').read_text(encoding='utf-8'))
    map_scenes = {s['id']: s for s in map_data['scenes']}
    require(set(map_scenes) == {'MAP_STORE', 'MAP_HOME', 'MAP_SHOP', 'MAP_STUDY'}, 'four authored map scenes required')
    require(map_data['district']['mode'] == 'menu_graph_not_open_world', 'district scope must remain explicit')
    roles = {a['role'] for a in map_scenes['MAP_STORE']['anchors']}
    design_variants = []
    uniqueness_keys = []
    for fid, design in designs.items():
        require(design['design_status'] == 'complete_proposal_not_playtested', f'{fid}: completion/playtest status unclear')
        require(bool(design['signature'] and design['prototype_basis'] and design['success_predicate']), f'{fid}: incomplete design loop')
        require(len(design['observable_cues']) >= 2, f'{fid}: two observable cues required')
        require(3 <= len(design['player_actions']) <= 7, f'{fid}: needs actual action sequence')
        require(bool(design['work_ids']) and set(design['work_ids']) <= set(work), f'{fid}: unresolved work binding')
        require(bool(design['component_ids']) and set(design['component_ids']) <= set(systems), f'{fid}: unresolved shared module')
        require(set(design['rule_ids']) <= set(rules), f'{fid}: unresolved handbook rule')
        require(bool(design['map_anchor_roles']) and set(design['map_anchor_roles']) <= roles, f'{fid}: unresolved map anchor')
        require(design['implementation']['client_implemented'] is False, f'{fid}: design falsely labeled implemented')
        require(design['implementation']['tier'] in {'low', 'medium', 'high'}, f'{fid}: missing relative implementation tier')
        require(bool(design['implementation']['feature_gate']), f'{fid}: runtime feature gate missing')
        require(monsters[fid]['interaction_design_stage'] == 'v04_complete_design', f'{fid}: stale design stage')
        require(all(design['counterplay'].get(k) for k in ['free_baseline','optional_support','does_not_solve']), f'{fid}: free response/support boundary missing')
        require(all(design['failure_and_recovery'].get(k) for k in ['trigger','consequence','recovery','escape']), f'{fid}: recovery path missing')
        require(set(design['resource_pressure']) == {'energy','san','satiety','stamina'}, f'{fid}: resource contract changed')
        t=design['timing']
        expected=sum(t[k] for k in ['world_action_seconds','closeup_commit_seconds','route_reserve_seconds','recovery_reserve_seconds'])
        require(abs(expected-t['total_required_seconds']) < 1e-8, f'{fid}: time total inconsistent')
        require(t['phase_budget_seconds'] == 120 and expected <= 90, f'{fid}: no reserved ordinary work margin')
        require(t['route_reserve_seconds'] > 0 and t['recovery_reserve_seconds'] > 0, f'{fid}: missing movement or recovery allowance')
        require(1 <= design['difficulty']['base_cost'] <= 3, f'{fid}: invalid base director pressure')
        require(bool(design['difficulty']['harder_when'] and design['difficulty']['easier_when'] and design['difficulty']['forbidden_combinations']), f'{fid}: conditional difficulty incomplete')
        states={s['id']:s for s in design['states']}
        require(len(states)==len(design['states']) and 'CLEARED' in states, f'{fid}: duplicate or missing state')
        edges={sid:set() for sid in states}
        for sid,state in states.items():
            require(bool(state['monster_behavior'] and state['player_window']), f'{fid}/{sid}: missing behavior or response window')
            for edge in state['transitions']:
                require(edge['to'] in states and bool(edge['event'] and edge['guard']), f'{fid}/{sid}: invalid guarded state edge')
                edges[sid].add(edge['to'])
        for edge in design.get('global_transitions', []):
            require(edge['from'] == 'ANY_NONTERMINAL' and edge['to'] in states and bool(edge['event'] and edge['guard']), f'{fid}: invalid global transition')
            for sid,state in states.items():
                if state['transitions']:
                    edges[sid].add(edge['to'])
        reached={design['states'][0]['id']}
        while True:
            grown=reached | set().union(*(edges.get(s,set()) for s in reached))
            if grown==reached: break
            reached=grown
        require('CLEARED' in reached, f'{fid}: CLEARED unreachable in stated graph')
        require(not states['CLEARED']['transitions'], f'{fid}: cleared encounter must be terminal')
        for sid in states:
            require(sid in reached, f'{fid}: orphan state {sid}')
        require(len(design['variants']) >= 2, f'{fid}: two event variants required')
        for variant in design['variants']:
            design_variants.append(variant['id'])
            require(variant['event_id'] in events, f'{fid}: unknown variant event')
            require(variant['id'].startswith(fid+'V'), f'{fid}: wrong variant ID namespace')
            require(all(variant.get(k) for k in ['name','changed_condition','required_action','admission_gate']), f'{fid}: variant needs condition, action and gate')
            require(variant['id'] in events[variant['event_id']].get('encounter_variant_ids',[]), f'{variant["id"]}: event backlink absent')
        uniqueness_keys.append(design['uniqueness_key'])
    require(len(design_variants) >= 120 and len(design_variants)==len(set(design_variants)), 'at least 120 unique encounter variants required')
    require(len(set(uniqueness_keys)) == 60, 'mechanical uniqueness keys must be distinct; manual design review still required')
    require(design_data['authoritative_detailed_blueprints'] == ['F12','F13'], 'F12/F13 exact blueprint precedence missing')
    require(design_data['all_clients_implemented'] is False, 'full design is not a playable client')

    for path in ROOT.rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        require(not re.search(r'^(<<<<<<<|=======|>>>>>>>)', text, re.MULTILINE), f'{path}: merge conflict marker')
        for destination in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if destination.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            relative = unquote(destination.split('#', 1)[0])
            require((path.parent / relative).exists(), f'{path.relative_to(ROOT)}: missing link {destination}')

    result = {'status': 'PASS' if not errors else 'FAIL', 'checks': checks,
              'counts': {'monsters': len(monsters), 'default_enabled_monsters': 59, 'events': len(events),
                         'rules': len(rules), 'temporary_items': len(items), 'equipment': len(gear),
                         'pets': len(pets), 'synergy_cases': len(synergies), 'sources': len(sources),
                         'shared_verbs': len(verbs), 'work_templates': len(work), 'qte_templates': len(qtes),
                         'rule_components': len(components), 'event_variants': len(variants),
                         'encounter_blueprints': len(encounters), 'deployables': len(deployables),
                         'complete_encounter_designs': len(designs), 'encounter_event_variants': len(design_variants),
                         'mechanism_modules': len(systems), 'map_scenes': len(map_scenes)},
              'scope': 'Content integrity and declared configuration only. Separate headless checks do not validate navigation, touch UI, phone performance or play balance.',
              'errors': errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
