#!/usr/bin/env python3
"""Validate V0.2 design references and configuration invariants, not gameplay balance."""

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
    require(len(sources) == len(source_data['sources']) == 59, 'sources: 59 unique records required')
    require(sum(s['source_type'] == 'folklore_reference' for s in sources.values()) == 57, 'sources: 57 folklore records required')
    require(sum(s['source_type'] == 'official_screen_reference' for s in sources.values()) == 2, 'sources: 2 screen references required')
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
                         'pets': len(pets), 'synergy_cases': len(synergies), 'sources': len(sources)},
              'scope': 'Content integrity and declared configuration only; no client, simulation, phone performance or play-balance validation.',
              'errors': errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
