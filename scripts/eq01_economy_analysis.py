#!/usr/bin/env python3
"""EQ01 fixed-income budget replays and exact finite lottery expectations.

This is a design analysis, not a victory simulation or runtime lottery sampler.
The optional personal purchase uses TD05's explicit reference hook. It neither
modifies authoritative prices nor creates a second wallet. Run from a complete
checkout, or use --root for the repository/overlay containing EQ01 files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path


TIERS = ('common', 'uncommon', 'rare')
BASELINE_DEFAULT_HASHES = {
    'cautious': 'e3de4e4996326aee9c0c88fdb262783b9bbdb77190a9135adbe6909afa2ec357',
    'standard': 'b4a1f59f7e898f832510a666d6ec522927ebbdef111f68c9093e97f9a247f871',
    'proficient': 'aba42d7456be5e2b629d4f258c8575b8b72ac1e248fe9ce874ef01a2eb081637',
}


def resolve(root: Path, relative: str) -> Path:
    """Complete checkout first; sibling caches are authoring-only fallbacks."""
    for candidate in [root/relative] + [root.parent/name/relative for name in
            ('ruler-control-td05', 'ruler-control-md01', 'ruler-control-md01-source', 'ruler-control-source')]:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f'Missing authoritative input: {relative}')


def read(root: Path, relative: str):
    return json.loads(resolve(root, relative).read_text())


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def load_reference(path: Path):
    spec = importlib.util.spec_from_file_location('eq01_td05_budget_reference', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def brief(replay):
    rows = replay['before_night_rows']
    return {
        'daily_income_coin': replay['daily_coin'],
        'daily_income_spirit': replay['daily_spirit'],
        'initial_minimum_build_coin': replay['initial_purchase_coin'],
        'initial_remaining_coin': replay['initial_remaining_coin'],
        'first_l2_tower_night': next((x['night'] for x in rows if any(t >= 2 for t in x['tower_tiers'].values())), None),
        'first_l3_tower_night': next((x['night'] for x in rows if x['l3_towers']), None),
        'first_l3_trap_night': next((x['night'] for x in rows if x['l3_traps']), None),
        'night7_l3_towers': rows[-1]['l3_towers'],
        'night7_l3_traps': rows[-1]['l3_traps'],
        'night7_open_coin': rows[-1]['before_night_coin'],
        'total_defense_build_coin': replay['total_build_coin'],
        'old_week_coin_closed_after_night7': replay['post_week_coin_recorded_then_closed'],
        'next_week_coin': replay['next_week_coin'],
        'next_week_spirit': replay['next_week_spirit'],
        'fully_paid_trap_stock_service_feasible': replay['actual_stock_service_plan_feasible'],
        'rows': [{
            'night': x['night'], 'opening_coin': x['before_night_coin'],
            'opening_spirit': x['before_night_spirit'], 'defense_purchases': x['purchases'],
            'l3_towers': x['l3_towers'], 'l3_traps': x['l3_traps'],
            'service_and_personal_spend': x['service_and_reserve_before_night_coin'],
            'personal_purchase_receipts': [e for e in x['service_events'] if e.get('kind') == 'eq01_personal_equipment_purchase'],
        } for x in rows],
    }


def number(value: Fraction):
    return {'value': float(value), 'exact_fraction': str(value)}


def lottery_expectations(catalog, starters, pity, duplicate_units):
    enabled = [x for x in catalog['equipment'] if x['design_enabled']]
    counts = Counter(x['rarity'] for x in enabled)
    owned = Counter(x['rarity'] for x in enabled if x['id'] in starters)
    pool_sizes = tuple(counts[t] for t in TIERS)
    assert all(pool_sizes)
    # Uniform item selection within a tier/category permits aggregation by
    # owned-item counts; this preserves duplicate probabilities exactly.
    states = {(0, 0, tuple(owned[t] for t in TIERS), False): Fraction(1)}
    tier_counts = [Fraction(0)]*3
    direct_special = duplicate_special = new_gear = duplicate_gear = Fraction(0)
    snapshots = []
    for draw in range(1, 9):
        after = {}
        for (common, nonrare, ownership, rare_seen), weight in states.items():
            if nonrare >= pity['rare_pity_after_nonrare_draws']:
                rates = (Fraction(0), Fraction(0), Fraction(1))
            elif common >= pity['noncommon_pity_after_common_draws']:
                rates = (Fraction(0), Fraction(str(pity['noncommon_pity_weights']['uncommon'])), Fraction(str(pity['noncommon_pity_weights']['rare'])))
            else:
                rates = tuple(Fraction(str(pity['base_tier_probabilities'][t])) for t in TIERS)
            assert sum(rates) == 1
            for tier, rate in enumerate(rates):
                if not rate:
                    continue
                mass = weight*rate
                tier_counts[tier] += mass
                new_common, new_nonrare = (common+1, nonrare+1) if tier == 0 else ((0, nonrare+1) if tier == 1 else (0,0))
                seen = rare_seen or tier == 2
                units = 2 if tier == 0 else 1
                for kind, probability in (
                    ('direct_special', Fraction(1,2)),
                    ('duplicate_gear', Fraction(1,2)*Fraction(ownership[tier], pool_sizes[tier])),
                    ('new_gear', Fraction(1,2)*Fraction(pool_sizes[tier]-ownership[tier], pool_sizes[tier])),
                ):
                    if not probability:
                        continue
                    branch = mass*probability
                    next_owned = list(ownership)
                    if kind == 'direct_special':
                        direct_special += branch*units
                    elif kind == 'duplicate_gear':
                        duplicate_gear += branch
                        duplicate_special += branch*duplicate_units[tier]
                    else:
                        new_gear += branch
                        next_owned[tier] += 1
                    key = (new_common, new_nonrare, tuple(next_owned), seen)
                    after[key] = after.get(key, Fraction(0))+branch
        states = after
        assert sum(states.values()) == 1
        assert new_gear+duplicate_gear == Fraction(draw,2)
        if draw in (7,8):
            snapshots.append({
                'draws': draw,
                'expected_tiers': {t: number(tier_counts[i]) for i,t in enumerate(TIERS)},
                'probability_at_least_one_rare': number(sum(p for (_,_,_,seen),p in states.items() if seen)),
                'expected_equipment_category_offers': number(Fraction(draw,2)),
                'expected_distinct_new_equipment': number(new_gear),
                'expected_owned_equipment_duplicates': number(duplicate_gear),
                'expected_direct_special_units': number(direct_special),
                'expected_duplicate_conversion_special_units': number(duplicate_special),
                'expected_total_special_units': number(direct_special+duplicate_special),
                'exact_probability_mass': str(sum(states.values())),
            })
    return {
        'tier_equipment_pool_counts': dict(zip(TIERS,pool_sizes)),
        'initial_owned_equipment': starters,
        'duplicate_conversion_units_by_tier': dict(zip(TIERS,duplicate_units)),
        'category_probabilities_each_tier': {'equipment': .5, 'special_consumable': .5},
        'normal_special_units_by_tier': {'common': 2, 'uncommon': 1, 'rare': 1},
        'selection_within_category_and_tier': 'uniform over eligible authored item IDs; duplicates convert, never reroll rarity',
        'scope': 'fresh pity counters, authored full pools and existing starter ownership only; no E064, purchases, migration ownership, fragments or missing-handler pool changes',
        'draw_count_interpretation': '7 means seven earned night tickets;8 additionally includes the retained one-time initial voucher, all spent once',
        'method': 'exact Fraction dynamic program over pity state and owned item counts per rarity; not Monte Carlo or a runtime sampler',
        'snapshots': snapshots,
    }


def build_report(root: Path):
    economy = read(root,'content/economy_week_td05.json')
    towers = read(root,'content/tower_defense_td05.json')
    traps = read(root,'content/traps_facilities_td05.json')
    catalog = read(root,'content/equipment_eq01.json')
    shared = read(root,'content/equipment_contracts_eq01.json')
    pity = read(root,'content/lottery_direction_md01.json')['retained_probability_and_pity']
    source = resolve(root,'scripts/td05_economy_reference.py')
    reference = load_reference(source)
    q06 = next(x for x in catalog['equipment'] if x['id']=='Q06')
    price = q06['acquisition']['shop_price_week_coin']
    rows = []
    default_gates = []
    for scenario in economy['replay_assumptions']['scenarios']:
        baseline = reference.week_replay(economy,towers,traps,scenario)
        actual_hash = digest(baseline)
        gate = actual_hash == BASELINE_DEFAULT_HASHES[scenario['id']]
        default_gates.append({'scenario':scenario['id'],'unchanged_full_default_result':gate,'sha256':actual_hash})
        assert gate, 'The empty optional schedule changed TD05 default reference behavior'
        rows.append({
            'scenario': scenario['id'],
            'baseline': brief(baseline),
            'Q06_before_night2': brief(reference.week_replay(economy,towers,traps,scenario,personal_purchases_by_night={2:[{'item_id':'Q06','coin':price}]})),
            'Q06_before_night3': brief(reference.week_replay(economy,towers,traps,scenario,personal_purchases_by_night={3:[{'item_id':'Q06','coin':price}]})),
        })
    assert all(r[v]['fully_paid_trap_stock_service_feasible'] for r in rows for v in ('baseline','Q06_before_night2','Q06_before_night3'))
    return {
        'version':'EQ01', 'runtime_integrated':False,
        'scope':'fixed completed-order/root assumptions, existing minimum build and adaptive priorities; no claim about actual victory, player skill, or pathfinding',
        'inputs': {'td05_reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'equipment_catalog_sha256':hashlib.sha256(resolve(root,'content/equipment_eq01.json').read_bytes()).hexdigest()},
        'default_regression_gates':default_gates,
        'purchase': {'item_id':'Q06','name':q06['name'],'actual_catalog_price_coin':price,'time':'after mandatory authored trap stock/service, before original defense priority','once_only':True},
        'personal_reserve': {
            'coin_per_night2to7':economy['replay_assumptions']['non_defense_consumables_per_completed_night_coin'],
            'uncommon_example':'14 special +10 other =24 already budgeted',
            'rare_example':'24 special +0 other =24 already budgeted',
            'not_additional_tax':True,
            'night1':'original minimum build112 of120 retained;8coin remains; no new mandatory consumable spend',
        },
        'interpretation':'Adaptive priority skips unaffordable upgrades, so identical later L3 counts do not imply a free equipment purchase; total defense mix and timing change.',
        'week_boundary':'All runs close old weekly coin/spirit and start120coin0spirit. Q06 is a separate persistent personal ownership receipt, no second wage, refund, sale or oldcash transfer.',
        'economy':rows,
        'lottery':lottery_expectations(catalog,shared['equipment']['starter_once_per_campaign'],pity,(2,1,1)),
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=args.root.resolve()
    report=build_report(root)
    output=args.output or root/'docs/eq01_economy_report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(output),'default_regressions_passed':sum(x['unchanged_full_default_result'] for x in report['default_regression_gates']),'budget_runs':9,'lottery':report['lottery']['snapshots']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
