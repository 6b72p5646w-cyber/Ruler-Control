#!/usr/bin/env python3
"""Validate V0.9 contracts and the exact offline build without writing files.

This checks static agreement, not gameplay, physical receipt authentication,
all encounter combinations, a complete night, or a WeChat client release.
"""
from pathlib import Path
from html.parser import HTMLParser
import ast
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = re.compile(r"^import\s+(\*\s+as\s+\w+|\{[^}]+\})\s+from\s+['\"]([^'\"]+)['\"];?", re.M)
EXTERNAL_CODE_API = re.compile(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|importScripts|sendBeacon)\s*\(|\bimport\s*\(|\bnew\s+(?:SharedWorker|Worker)\s*\(')
REQUIRED_DATA = {
    'maps': 'maps', 'blueprints': 'encounter_blueprints', 'mechanics': 'map_mechanics_v05',
    'interactions': 'interactions', 'balance': 'balance', 'condition': 'condition_lifecycle_v06',
    'items': 'items', 'qte': 'qte', 'integration': 'integration_v09',
}
REQUIRED_FILES = [
    'scripts/build_playable_v09.py', 'prototype/playable_v09.mjs',
    'prototype/playable_v09.css', 'prototype/playable_v09.template.html',
    'prototype/world_core_v09.mjs', 'prototype/practice_session_core_v09.mjs',
    'prototype/day_cycle_core_v09.mjs', 'prototype/shift_settlement_core_v09.mjs',
    'prototype/condition_core_v06.mjs', 'prototype/consumer_core_v08.mjs',
    'prototype/store_core_v05.mjs', 'prototype/day_knowledge_core_v08.mjs',
    'prototype/rule_core.mjs', 'prototype/playable_v09.html', 'docs/playable_build_v09.json',
]


class Validation:
    def __init__(self, root=ROOT):
        self.root = root.resolve()
        self.errors, self.hashes, self.cache, self.counts = [], {}, {}, {}
        self.checks = 0

    def need(self, value, path, message):
        self.checks += 1
        if not value:
            self.errors.append({'path': path, 'message': message})

    def same(self, value, expected, path):
        # Bool is a subclass of int; flags must be real JSON booleans.
        valid_type = type(value) is bool if type(expected) is bool else not isinstance(value, bool) if isinstance(expected, (int, float)) else True
        self.need(valid_type and value == expected, path, f'Expected {expected!r}; found {value!r}')

    def read(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Path leaves the repository: ' + relative)
        raw = path.read_bytes()
        self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        return raw

    def document(self, relative):
        if relative not in self.cache:
            self.cache[relative] = json.loads(self.read(relative))
        return self.cache[relative]

    def content(self, name):
        return self.document('content/' + name + '.json')

    def index(self, rows, path):
        result = {x['id']: x for x in rows}
        self.need(len(result) == len(rows), path, 'Duplicate object IDs')
        return result

    def subset(self, actual, expected, path):
        for key, value in expected.items():
            if isinstance(value, dict):
                self.need(isinstance(actual.get(key), dict), path + '/' + key, 'Required object missing')
                if isinstance(actual.get(key), dict):
                    self.subset(actual[key], value, path + '/' + key)
            else:
                self.same(actual.get(key), value, path + '/' + key)

    def section(self, name, fn):
        try:
            fn(self)
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, SyntaxError, ArithmeticError) as error:
            self.need(False, name, f'Cannot validate malformed or missing input: {type(error).__name__}: {error}')


def check_contracts(v):
    i, b, items_data = v.content('integration_v09'), v.content('balance'), v.content('items')
    maps, condition = v.content('maps'), v.content('condition_lifecycle_v06')
    items = v.index(items_data['items'], 'items')
    cards = v.index(v.content('encounters_v05')['encounters'], 'encounters_v05')
    scenes = v.index(maps['scenes'], 'maps/scenes')
    v.subset(i, {'version': '0.9', 'production_runtime_enabled': False, 'canonical_blueprints_modified': False,
        'practice': {'encounter_ids': ['F12', 'F13'], 'map_id': 'MAP_STORE',
            'separate_fork_of_personal_resources': True, 'awards_official_wage_or_ticket': False,
            'returns_effects_or_items_to_original_day_state': False, 'world_step_seconds_max': 0.05,
            'pause_freezes_world_resources_and_panic': True, 'ordinary_movement_requires_stamina': False,
            'sprinting_implemented': False, 'door_interactions_read_W11': True,
            'F12_only_declared_front_exit_zone': True, 'F13_reuses_same_meat_atomic_delivery': True,
            'same_frame_delivery_before_attack': True},
        'state_ownership': {'night_san_and_panic': 'condition_core',
            'day_san_other_resources_inventory_and_coffee_debt': 'day_cycle_core',
            'world_positions_collisions_actions_and_monster_targets': 'world_core',
            'customer_patience_clock': 'actual_world_time_only',
            'F53_qualification': 'consumer_core_same_two_bottles_only',
            'formal_payments': 'campaign_id_and_night_id_ledger',
            'mirrors_never_award_resources_independently': True, 'actual_hit_is_not_passive_fear_cap': True},
        'calendar': {'clock': 'absolute_game_minutes', 'day_energy_uses_only_declared_action_costs': True,
            'precision_budget_cost_does_not_regenerate_stamina': True,
            'coffee_debt_survives_day_and_save_boundaries': True,
            'same_time_due_debts_before_action_rewards': True, 'daily_food_claim_survives_save_and_retry': True,
            'successful_day_to_night_transition_does_not_refill_resources': True,
            'short_lived_night_statuses_do_not_create_permanent_injury': True},
        'settlement': {'same_attempt_qte_san_outcome_before_true_six_checks': True,
            'F53_old_single_object_demo_forbidden_in_integrated_session': True,
            'F53_payment_after_verified_handover': True,
            'current_manager_body_requires_actual_arrival_and_bound_observations': True,
            'two_independent_sources_must_match_saved_baseline': True,
            'completed_key_and_account_handover_required': True,
            'wage_and_ticket_dedup_key': ['campaignId', 'nightId'],
            'changing_run_id_does_not_reset_rewards': True,
            'world_fact_authentication_is_external_to_reference': True}}, 'integration')
    p, c, s = i['practice'], i['calendar'], i['settlement']
    scene = scenes[p['map_id']]
    v.same(p['interior_tiles'], scene['interior_rect'][2:], 'practice/interior_tiles')
    v.same(p['viewport_tiles'], maps['camera']['world_view_tiles'], 'practice/viewport_tiles')
    v.same(math.prod(p['interior_tiles']) / math.prod(p['viewport_tiles']), maps['camera']['interior_viewport_area_ratio'], 'practice/five_screen_area')
    v.need(set(p['encounter_ids']) <= set(cards), 'practice/encounter_ids', 'Practice references unknown encounter cards')
    v.same(p['budget_seconds_per_practice'], b['night_seconds_per_hour'], 'practice/budget_seconds_per_practice')
    v.same(c['night_budget_seconds_per_game_minute'], b['night_seconds_per_hour'] / 60, 'calendar/night_clock_ratio')
    v.same(c['day_action_slots'], b['day_action_slots'], 'calendar/day_action_slots')
    v.same(c['minutes_per_day_action'], b['day_hours_per_slot'] * 60, 'calendar/minutes_per_day_action')
    v.same(c['sleep_satiety_per_game_hour'], b['resources']['satiety']['sleep_hour_drain'], 'calendar/sleep_satiety')
    v.same(c['awake_satiety_per_game_hour'], b['resources']['satiety']['awake_hour_drain'], 'calendar/awake_satiety')
    v.same(b['resources']['energy']['daytime_cost_policy'], 'explicit_action_costs_only', 'balance/daytime_energy')
    v.same(b['resources']['satiety']['action_satiety_annotations_add_extra_drain'], False, 'balance/no_double_satiety')
    v.same(b['resources']['stamina']['recovery_clock'], 'world_simulation', 'balance/stamina_clock')
    v.same(b['time_budget_semantics']['paused_world_generates_stamina_recovery'], False, 'balance/paused_stamina')
    v.same(b['time_budget_semantics']['night_hour_seconds'], b['night_seconds_per_hour'], 'balance/night_hour_seconds')
    for name, doc in [('balance', b), ('items', items_data)]:
        v.same(doc['day_cycle_contract'], 'content/integration_v09.json#/calendar', name + '/day_cycle_contract')
    night_phases = [x['id'] for x in b['daily_phases'] if x['id'].startswith('N')]
    arrival_phase = b['night_completion']['handover_actor_arrival_phase']
    v.same(s['true_six_budget_seconds'], len(night_phases) * b['night_seconds_per_hour'], 'settlement/true_six_phase_total')
    v.same(s['manager_arrival_budget_seconds'], night_phases.index(arrival_phase) * b['night_seconds_per_hour'] + b['night_completion']['handover_actor_arrival_phase_budget_second'], 'settlement/manager_schedule')
    for key in ['manager_arrival_budget_seconds', 'true_six_budget_seconds']:
        v.same(s[key], condition['end_of_shift'][key], 'settlement/' + key)
    v.need(0 < s['manager_arrival_budget_seconds'] < s['true_six_budget_seconds'], 'settlement/order', 'Manager must actually arrive before true six')
    v.same(condition['end_of_shift']['f53_san_reward_only_after_verified_handover'], s['F53_payment_after_verified_handover'], 'settlement/F53_reward_timing')
    resource_ids = set(b['resources'])
    for item_id in ['I01', 'I02', 'I03', 'I04', 'I05']:
        item = items[item_id]
        v.same(item['consumable'], True, item_id + '/consumable')
        v.same(item['food_source_policy'], 'personal_verified_required_for_ingestion', item_id + '/food_source_policy')
        deltas = item['resource_deltas']
        v.need(bool(deltas) and set(deltas) <= resource_ids, item_id + '/resource_deltas', 'Undefined or empty resource effect')
        v.need(all(type(x) in [int, float] and math.isfinite(x) for x in deltas.values()), item_id + '/resource_deltas', 'Resource effects must be finite numbers')
    coffee = items['I05']['delayed_effect']
    v.same(coffee['delay_game_minutes'], c['coffee_due_after_game_minutes'], 'I05/delay_game_minutes')
    v.need(coffee['delay_game_minutes'] > 0, 'I05/delay_game_minutes', 'Delayed debt must have a future due time')
    v.same(coffee['clock'], c['clock'], 'I05/debt_clock')
    v.subset(coffee, {'persists_across_days_and_saves': True, 'settles_once_per_item_instance': True,
        'same_time_debts_before_new_action_rewards': True}, 'I05/delayed_effect')
    v.need(set(coffee['resource_deltas']) <= resource_ids and bool(coffee['resource_deltas']), 'I05/debt_resources', 'Unknown or empty delayed resource effect')
    v.need(all(type(x) in [int, float] and math.isfinite(x) and x <= 0 for x in coffee['resource_deltas'].values()), 'I05/debt_values', 'Coffee debt must have finite nonpositive effects')
    food = items_data['job_supply']['daily_free_food']
    v.same(b['economy']['daily_free_job_food_bundle_id'], food['id'], 'economy/daily_free_job_food_bundle_id')
    v.subset(food, {'reset_time': '06:00', 'reset_period': 'game_day', 'claim_limit_per_game_day': 1,
        'requires_completed_night': False, 'price': 0}, 'job_supply/daily_free_food')
    total = 0
    for row in food['items']:
        v.need(row['item_id'] in items, 'job_supply/' + row['item_id'], 'Unknown food item')
        v.need(type(row['quantity']) is int and row['quantity'] > 0, 'job_supply/' + row['item_id'], 'Quantity must be a positive integer')
        total += items[row['item_id']]['resource_deltas'].get('satiety', 0) * row['quantity']
    v.same(total, food['nominal_satiety_total'], 'job_supply/nominal_satiety_total')


def check_canonical_blueprints(v):
    data = v.content('encounter_blueprints')
    blueprints = v.index(data['encounters'], 'encounter_blueprints')
    f12, f13 = blueprints['F12'], blueprints['F13']
    v.subset(data, {'baseline': {'player_walk_speed': 3, 'carrying_meat_walk_speed': 2.6,
        'monster_move_speed': 2.3, 'interaction_distance': 1, 'ai_decision_hz': 5, 'max_path_replans_per_second': 2},
        'shared_attack_proposal': {'telegraph_seconds': 1.5, 'windup_start_distance': 1.2,
            'hit_check_distance': 0.65, 'san_damage': 10, 'attack_cooldown_seconds': 3,
            'collision_grace_seconds': 2, 'first_touch_instant_death': False, 'destroys_quest_item': False},
        'default_director_policy': {'max_active_player_pursuers': 1, 'simultaneous_f12_f13_enabled': False},
        'world_interaction_policy': {'chase_actions_use_closeup': False, 'standard_pause_freezes_everything': True,
            'item_transfer_commits_before_ai_contact_check': True, 'success_is_terminal_per_instance': True,
            'pickup_drop_scatter_store_require_qte': False, 'delivery_receipt_survives_same_frame_power_loss': True}}, 'blueprints')
    v.subset(f12, {'objects': {'supply_tag': 'paperclip_supply', 'bait_tag': 'paperclip_bait', 'exit_tag': 'exit_success_zone'},
        'parameters': {'pickup_seconds': 1, 'backup_pickup_seconds': 2, 'charges_per_box': 6, 'backup_boxes': 1,
            'max_active_bait_points': 3, 'bait_place_distance': 1.5, 'bait_place_seconds': 0.25,
            'bait_detection_radius': 5, 'bait_lifetime_seconds': 15, 'eat_pause_seconds': 1.5,
            'exit_full_collider_hold_seconds': 0.25},
        'target_policy': {'priority': ['locked_valid_bait', 'nearest_reachable_unconsumed_bait_in_radius', 'player'],
            'chase_player_navigation_scope': 'store_interior_only', 'bait_navigation_scope': 'store_and_marked_exit_pad',
            'allow_throw_through_wall': False, 'overflow_new_bait_behavior': 'reject_with_feedback_keep_existing_points'},
        'success_requires_extra_close_door': False}, 'F12')
    v.subset(f13, {'objects': {'required_meat_count': 1, 'meat_tag': 'encounter_raw_meat_crate',
            'freezer_tag': 'registered_functional_freezer', 'uses_task_carry_slot': True, 'required_hands': 2},
        'parameters': {'pickup_seconds': 0.6, 'drop_seconds': 0.25, 'store_and_close_seconds': 0.6,
            'rage_windup_seconds': 1.5, 'interaction_distance': 1},
        'target_policy': {'before_meat_contact': 'quest_meat_world_position_or_carrier_position',
            'after_meat_contact': 'player', 'dropping_meat_reverts_rage': False, 'meat_consumed_on_contact': False,
            'path_model': 'same_2d_walkable_grid_as_ground_agents'}, 'preemptive_clear_before_contact': True,
        'container_acceptance': {'player_carries_required_crate': True, 'within_interaction_range': True,
            'reserved_capacity_required': True, 'door_operable_required': True, 'power_or_verified_backup_required': True,
            'deposit_and_close_atomic': True, 'cancel_before_commit': 'crate_remains_in_hand',
            'after_clear_reactivate_on_open_or_outage': False},
        'delivery_receipt_contract': {'created_only_after_successful_atomic_delivery': True,
            'fields': ['encounterInstanceId', 'itemId', 'containerId', 'closedAtCommit', 'functionalAtCommit', 'committed'],
            'instance_id_must_match_active_encounter': True, 'success_evaluates_committed_receipt_not_later_power_state': True,
            'touch_requires_registered_meat_instance': True}}, 'F13')
    expected_edges = {
        'F12': {'CHASE_PLAYER': [('valid_bait_available', 'SEEK_BAIT')],
            'SEEK_BAIT': [('whole_collider_inside_exit_success_zone_for_hold', 'CLEARED'), ('reached_bait', 'EAT_BAIT'), ('bait_invalid', 'CHASE_PLAYER')],
            'EAT_BAIT': [('whole_collider_inside_exit_success_zone_for_hold', 'CLEARED'), ('eat_timer_complete', 'CHASE_PLAYER')]},
        'F13': {'SEEK_MEAT': [('required_meat_stored_in_valid_freezer', 'CLEARED'), ('contact_required_meat_unstored', 'RAGE_WINDUP')],
            'RAGE_WINDUP': [('required_meat_stored_in_valid_freezer', 'CLEARED'), ('windup_timer_complete', 'CHASE_PLAYER')],
            'CHASE_PLAYER': [('required_meat_stored_in_valid_freezer', 'CLEARED')]},
    }
    cards = v.index(v.content('encounters_v05')['encounters'], 'canonical/cards')
    for fid, edges in expected_edges.items():
        bp = blueprints[fid]
        states = v.index(bp['states'], fid + '/states')
        v.same(set(states), set(edges) | {'CLEARED'}, fid + '/state_ids')
        for state_id, expected in edges.items():
            v.same([(t['trigger'], t['to']) for t in states[state_id]['transitions']], expected, fid + '/' + state_id + '/transitions')
        v.same(states['CLEARED']['terminal'], True, fid + '/terminal')
        v.need('settle_once' in states['CLEARED']['actions'], fid + '/terminal', 'Terminal result must settle once')
        v.same(bp['attack_enabled_states'], ['CHASE_PLAYER'], fid + '/attack_enabled_states')
        v.same(bp['pursuit_interactions_require_qte'], False, fid + '/pursuit_interactions_require_qte')
        v.same(cards[fid]['canonical_override'], 'fixed_F12_F13', fid + '/canonical_override')
    for state_id in ['SEEK_BAIT', 'EAT_BAIT']:
        state = next(x for x in f12['states'] if x['id'] == state_id)
        v.same(state['transitions'][0].get('guard'), 'currently_lured_to_bait', 'F12/' + state_id + '/exit_guard')
    scene = next(s for s in v.content('maps')['scenes'] if s['id'] == 'MAP_STORE')
    route = scene['lure_route']
    for key, source in [('capacity', 'charges_per_box'), ('max_active', 'max_active_bait_points'), ('bait_detection_radius', 'bait_detection_radius')]:
        v.same(route[key], f12['parameters'][source], 'F12/map_lure/' + key)
    v.need(len(route['bait_points']) <= route['capacity'] - 2, 'F12/map_lure', 'Teaching route consumes the declared two-charge recovery margin')
    v.same(route['exit_role'], 'front_exit', 'F12/declared_exit')
    anchors = {a['role'] for a in scene['anchors']}
    v.need({'metal_shelf', 'front_exit', 'front_door', 'warehouse_meat', 'freezer_main', 'packing'} <= anchors, 'practice/anchors', 'Actual task anchor missing')
    work = v.index(v.content('interactions')['work_templates'], 'interactions/work_templates')
    v.same(work['W11']['scale'], 'world', 'W11/scale')
    v.need(0 < work['W11']['base_operation_seconds'] <= work['W11']['max_attempt_operation_seconds'], 'W11/operation_seconds', 'Door duration must be positive and bounded')


def check_disabled_catalog(v):
    count = 0

    def visit(value, path):
        nonlocal count
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ['runtime_enabled', 'production_runtime_enabled']:
                    count += 1
                    v.same(child, False, path + '/' + key)
                visit(child, path + '/' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + '/' + str(index))

    for path in sorted((v.root / 'content').rglob('*.json')):
        rel = path.relative_to(v.root).as_posix()
        visit(v.document(rel), rel)
    cards = v.index(v.content('encounters_v05')['encounters'], 'runtime/cards')
    for fid, card in cards.items():
        v.same(card.get('runtime_enabled'), False, 'encounters_v05/' + fid + '/runtime_enabled')
    v.subset(cards['F14'], {'default_enabled': False, 'candidate_enabled': False, 'runtime_enabled': False}, 'F14')
    monsters = v.content('monsters')
    v.need('F14' in monsters['default_excluded_ids'], 'monsters/default_excluded_ids', 'F14 advanced possession is not available in this slice')
    f14 = next(x for x in monsters['monsters'] if x['id'] == 'F14')
    v.same(f14['enabled_default'], False, 'monsters/F14/enabled_default')
    v.same(v.content('condition_lifecycle_v06')['client_implemented'], False, 'condition/client_implemented')
    v.counts.update(formal_runtime_flags=count, encounter_cards=len(cards))


class OfflineHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dependencies, self.scripts = [], []
        self.active_raw_tag = None

    def css(self, text):
        if re.search(r'@import\b', text, re.I):
            self.dependencies.append('CSS @import')
        for url in re.findall(r'url\(\s*[\'\"]?([^\)\'\"]+)', text, re.I):
            if not (url.startswith('data:') or url.startswith('#')):
                self.dependencies.append('CSS url=' + url)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ['script', 'style']:
            self.active_raw_tag = tag
            if tag == 'script':
                self.scripts.append('')
        if 'style' in attrs:
            self.css(attrs['style'] or '')
        if tag == 'base' or (tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh'):
            self.dependencies.append(tag + ' navigation base/refresh')
        if tag == 'script' and 'src' in attrs:
            self.dependencies.append('external script src attribute')
        if tag == 'iframe':
            self.dependencies.append('iframe content is outside the standalone module graph')
        for key in ['src', 'srcset', 'poster', 'data', 'href', 'xlink:href']:
            value = attrs.get(key)
            if not value or (key == 'href' and tag not in ['link', 'use', 'image']):
                continue
            if key == 'srcset' or not (value.startswith('data:') or value.startswith('#')):
                self.dependencies.append(tag + '[' + key + ']=' + value)
        for key, value in attrs.items():
            if key.startswith('on') and value and EXTERNAL_CODE_API.search(value):
                self.dependencies.append(tag + '[' + key + '] external code API')

    def handle_data(self, text):
        if self.active_raw_tag == 'style':
            self.css(text)
        elif self.active_raw_tag == 'script':
            self.scripts[-1] += text

    def handle_endtag(self, tag):
        if tag == self.active_raw_tag:
            self.active_raw_tag = None

    handle_startendtag = handle_starttag


def check_build(v):
    for relative in REQUIRED_FILES:
        v.need((v.root / relative).is_file(), relative, 'Required V0.9 source or standalone build missing')
    tree = ast.parse(v.read('scripts/build_playable_v09.py').decode('utf-8'))
    assignments = {n.targets[0].id: n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    data_map = ast.literal_eval(assignments['DATA'])
    v.need(isinstance(data_map, dict), 'build/DATA', 'Builder data manifest must be a literal mapping')
    for key, value in REQUIRED_DATA.items():
        v.same(data_map.get(key), value, 'build/DATA/' + key)
    entry_expr = assignments['ENTRY']
    v.need(isinstance(entry_expr, ast.BinOp) and isinstance(entry_expr.op, ast.Div) and isinstance(entry_expr.left, ast.Name) and entry_expr.left.id == 'ROOT', 'build/ENTRY', 'Unsupported builder entry expression')
    entry = ast.literal_eval(entry_expr.right)
    v.same(entry, 'prototype/playable_v09.mjs', 'build/ENTRY')
    modules, visiting, blocks, sources = {}, set(), [], {}

    def source(relative):
        raw = v.read(relative)
        sources[relative] = hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8')

    def bundle(relative):
        if relative in modules:
            return modules[relative]
        if relative in visiting:
            raise ValueError('Circular import unsupported by current builder: ' + relative)
        path = (v.root / relative).resolve()
        if not path.is_relative_to(v.root / 'prototype') or path.suffix != '.mjs':
            raise ValueError('Nonlocal runtime dependency: ' + relative)
        visiting.add(relative)
        text, bindings = source(relative), []
        # Explicit supported offline policy; this is not a general JS security audit.
        remote_api = EXTERNAL_CODE_API.search(text)
        v.need(remote_api is None, relative, 'Standalone module contains a network or external code-loading API')
        for match in IMPORTS.finditer(text):
            clause, target = match.groups()
            if not target.startswith('./'):
                raise ValueError('Runtime import must be local: ' + target)
            dependency = (path.parent / target).resolve()
            if not dependency.is_relative_to(v.root / 'prototype'):
                raise ValueError('Runtime import leaves prototype directory: ' + target)
            name = bundle(dependency.relative_to(v.root).as_posix())
            bindings.append('const ' + clause.split()[-1] + ' = ' + name + ';' if clause.startswith('*') else 'const ' + re.sub(r'\s+as\s+', ': ', clause) + ' = ' + name + ';')
        text = IMPORTS.sub('', text)
        exports = re.findall(r'^export\s+(?:async\s+)?(?:function|class|const|let)\s+(\w+)', text, re.M)
        text = re.sub(r'^export\s+(?=(?:async\s+)?(?:function|class|const|let)\b)', '', text, flags=re.M)
        if re.search(r'^\s*(?:import|export)\s', text, re.M):
            raise ValueError('Unsupported module declaration: ' + relative)
        name = '__midnight_module_' + str(len(modules))
        modules[relative] = name
        blocks.append('const ' + name + ' = (() => {\n' + '\n'.join(bindings) + '\n' + text + '\nreturn {' + ', '.join(exports) + '};\n})();')
        visiting.remove(relative)
        return name

    bundle(entry)
    v.need('prototype/shift_settlement_core_v09.mjs' not in modules, 'build/practice_scope', 'Standalone two-scene practice must not import the official settlement adapter')
    for relative in ['prototype/practice_session_core_v09.mjs', 'prototype/world_core_v09.mjs', 'prototype/day_cycle_core_v09.mjs', 'prototype/condition_core_v06.mjs', 'prototype/rule_core.mjs']:
        v.need(relative in modules, 'build/modules', 'Required real core not used by the playable entry: ' + relative)
    payload = {key: json.loads(source('content/' + stem + '.json')) for key, stem in data_map.items()}
    css, template = source('prototype/playable_v09.css'), source('prototype/playable_v09.template.html')
    for marker in ['/* BUILD_CSS */', '/* BUILD_DATA */', '/* BUILD_JS */']:
        v.same(template.count(marker), 1, 'build/template/' + marker)
    v.need(re.search(r'@import\b', css, re.I) is None, 'build/css', 'External CSS import forbidden')
    for url in re.findall(r'url\(\s*[\'\"]?([^\)\'\"]+)', css, re.I):
        v.need(url.startswith('data:') or url.startswith('#'), 'build/css_url', 'Nonembedded CSS dependency: ' + url)
    data = 'window.MIDNIGHT_DATA = ' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') + ';'
    js = '"use strict";\n' + '\n'.join(blocks)
    v.need('</script' not in js.lower(), 'build/javascript', 'Literal script terminator in runtime source')
    expected = template.replace('/* BUILD_CSS */', css).replace('/* BUILD_DATA */', data).replace('/* BUILD_JS */', js).encode('utf-8')
    html = v.read('prototype/playable_v09.html')
    manifest = v.document('docs/playable_build_v09.json')
    v.same(manifest['status'], 'PASS', 'build_manifest/status')
    v.same(manifest['standalone_html'], 'prototype/playable_v09.html', 'build_manifest/output')
    v.same(manifest['bytes'], len(html), 'build_manifest/bytes')
    v.same(manifest['sha256'], hashlib.sha256(html).hexdigest(), 'build_manifest/sha256')
    v.same(manifest['module_count'], len(modules), 'build_manifest/module_count')
    declared = manifest['source_sha256']
    v.same(set(declared), set(sources), 'build_manifest/source_set')
    for relative, digest in sources.items():
        v.same(declared.get(relative), digest, 'build_manifest/source_sha256/' + relative)
    v.need(html == expected, 'prototype/playable_v09.html', 'Standalone HTML is stale or differs from the current local sources; run scripts/build_playable_v09.py')
    parser = OfflineHTML()
    parser.feed(html.decode('utf-8'))
    for script in parser.scripts:
        if script.strip() != data and EXTERNAL_CODE_API.search(script):
            parser.dependencies.append('inline script contains external code API')
    v.need(not parser.dependencies, 'build/offline_dependencies', 'External HTML dependency: ' + '; '.join(parser.dependencies))
    v.counts.update(bundle_modules=len(modules), bundle_sources=len(sources), standalone_bytes=len(html))


def validate(root=ROOT):
    v = Validation(root)
    for name, fn in [('integration_contracts', check_contracts), ('canonical_blueprints', check_canonical_blueprints),
                     ('disabled_catalog', check_disabled_catalog), ('standalone_build', check_build)]:
        v.section(name, fn)
    return {'status': 'FAIL' if v.errors else 'PASS', 'checks': v.checks, 'errors': v.errors,
        'inputs_sha256': v.hashes, 'counts': v.counts,
        'scope': 'Static V0.9 data/reference agreement, preserved F12/F13 constraints, disabled formal runtime flags and exact reproducible offline build. Does not prove physical actions, all combinations, full-night completion, mobile performance, production receipt authentication or WeChat release.'}


if __name__ == '__main__':
    report = validate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(report['status'] != 'PASS')
