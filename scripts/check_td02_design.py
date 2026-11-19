#!/usr/bin/env python3
"""Check linked TD02 design data and disclosed arithmetic, not the combat runtime."""
from pathlib import Path
from fractions import Fraction
import argparse,hashlib,json,math

ROOT=Path(__file__).resolve().parents[1]
def frac(v): return Fraction(str(v))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',default='docs/tower_design_review_td02.json')
    args=parser.parse_args()
    tower_path=ROOT/'content/tower_defense_td02.json'
    monster_path=ROOT/'content/monster_migration_td02.json'
    t=json.loads(tower_path.read_text());m=json.loads(monster_path.read_text())
    bs={x['id']:x for x in t['branches']}
    fs={x['id']:x for x in t['families']}
    ids={x['id'] for x in m['monsters']}
    checks=[]
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'name':name,'result':'pass'})
    check('design_only_boundary',t['runtime_integrated'] is False and t['group_contract']['implemented'] is False)
    check('six_families_twelve_unique_branches',len(fs)==6 and len(bs)==12 and len(bs)==len(t['branches']))
    check('branch_links',all(len(f['branches'])==2 and all(b in bs and bs[b]['family_id']==f['id'] for b in f['branches']) for f in fs.values()))
    tracks=[s for b in bs.values() for s in b['skills']]
    ranks=[r for s in tracks for r in s['ranks']]
    check('twenty_four_tracks_forty_eight_ranks',len(tracks)==24 and len(ranks)==48 and len({s['id'] for s in tracks})==24)
    check('identical_paid_slot_prices',all(s['slot'] in (1,2) and [r['rank'] for r in s['ranks']]==[1,2] and s['ranks'][0]['cost']==t['skill_purchase']['rank_1'] and s['ranks'][1]['cost']==t['skill_purchase']['rank_2'] for s in tracks))
    check('full_skill_cost_reconciles',sum(t['skill_purchase'][f'rank_{i}']['coin'] for i in (1,2))*2==60 and sum(t['skill_purchase'][f'rank_{i}']['spirit'] for i in (1,2))*2==16)
    check('all_sixty_ids_present',ids=={f'F{i:02}' for i in range(1,61)} and len(m['monsters'])==60)
    check('f14_remains_disabled',next(x for x in m['monsters'] if x['id']=='F14')['default_enabled'] is False)
    check('monster_matchups_reference_real_branches',all(set(x['tower_matchup']['favorable_branches']+x['tower_matchup']['conditional_or_weak_branches'])<=set(bs) for x in m['monsters']))
    check('ground_artillery_no_implicit_antiair',all(bs[x]['attack']['layers']==['ground'] for x in ('T03A','T03B')) and t['effects']['freeze']['changes_height'] is False)
    check('bounded_crowd_slots',t['limits']['main_encounters']+t['limits']['late_child_actor_cap']==t['limits']['total_hostile_actor_cap']==8)
    check('heat_budget_18_not_per_tower',frac(t['effects']['heat_mark']['base_burst_contribution'])*t['effects']['heat_mark']['max_stacks']==18 and t['effects']['heat_mark']['target_shared_icd_s']==2.4)
    check('secondary_nonrecursive',t['damage']['secondary_max_generation']==1 and t['damage']['secondary_can_proc'] is False)

    a=bs['T01A'];b=bs['T01B'];aoe=bs['T03B']
    return_factor=frac(a['skills'][1]['ranks'][1]['parameters']['return_existing_multiplier'])
    pen=frac(a['attack']['source_armor_penetration_pp'])/100
    burn=frac(b['skills'][0]['ranks'][1]['parameters']['burn_dps_per_consumed_mark'])*8
    def steady_a(armor): return frac(a['attack']['damage'])/frac(a['attack']['interval_s'])*(1+return_factor)*(1-max(Fraction(0),armor-pen))
    def steady_b(armor): return (frac(b['attack']['damage'])/frac(b['attack']['interval_s'])+Fraction(18)/frac(t['effects']['heat_mark']['target_shared_icd_s']))*(1-armor)+burn
    comparisons=[]
    for armor in [Fraction(0),Fraction(3,10),Fraction(3,4)]:
        comparisons.append({'armor':float(armor),'ward':0,'T01A_full_single_dps':round(float(steady_a(armor)),6),'T01B_full_single_dps':round(float(steady_b(armor)),6)})
    check('sustain_and_armor_niches_not_dominated',steady_b(Fraction(0))>steady_a(Fraction(0)) and steady_a(Fraction(3,4))>steady_b(Fraction(3,4)))
    base_cost=lambda f:sum(f[k]['coin'] for k in ['l1_cost','l2_cost','l3_cost'])
    aoe_eff=(frac(aoe['attack']['damage'])/frac(aoe['attack']['interval_s'])/base_cost(fs['T03']))/(frac(a['attack']['damage'])/frac(a['attack']['interval_s'])/base_cost(fs['T01']))
    check('single_target_aoe_coin_efficiency',Fraction(7,10)<=aoe_eff<=Fraction(9,10))
    guard=bs['T05B'];bonus=frac(guard['skills'][0]['ranks'][1]['parameters']['flank_bonus_damage'])
    guard_base=frac(guard['attack']['damage'])*guard['attack']['guard_count']/frac(guard['attack']['interval_s'])
    rates=[Fraction(0),Fraction(1,10),Fraction(1,4),Fraction(3,10)]
    guard_rates=[float((guard_base+bonus)*(1+x)) for x in rates]
    check('guard_attack_buff_monotonic',all(y>x for x,y in zip(guard_rates,guard_rates[1:])) and 'target_icd_s' not in guard['skills'][0]['ranks'][1]['parameters'])
    heat_rates=[]
    for speed in rates:
        period=frac(b['attack']['interval_s'])/(1+speed)
        needed=max(8,math.ceil(frac(t['effects']['heat_mark']['target_shared_icd_s'])/period))
        heat_rates.append(float(frac(b['attack']['damage'])/period+Fraction(18)/(needed*period)+burn))
    check('heat_named_attack_buff_tiers_monotonic',all(y>x for x,y in zip(heat_rates,heat_rates[1:])))
    mix=4*frac(b['skills'][0]['ranks'][0]['parameters']['burn_dps_per_consumed_mark'])+4*frac(b['skills'][0]['ranks'][1]['parameters']['burn_dps_per_consumed_mark'])
    check('mixed_heat_dose_arithmetic',mix==Fraction(5,2))
    totals=[]
    for f in fs.values():totals.append({'family':f['id'],'l3_coin':base_cost(f),'full_tree_coin':base_cost(f)+60,'full_tree_spirit':28})
    inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [tower_path,monster_path]}
    report={'version':'TD02','status':'static_design_checks_passed','runtime_tested':False,'input_sha256':inputs,
            'counts':{'families':6,'branches':12,'tracks':24,'ranks':48,'monsters':60,'checks':len(checks)},'checks':checks,
            'arithmetic':{'assumptions':'Continuous legal lock, no misses, no other towers, no rule armor break, full chosen skills; T01A return hits original target; no idle first-shot buff. Not a combat simulation.',
                          'single_target_comparison':comparisons,'T03B_vs_T01A_base_damage_per_coin_ratio':round(float(aoe_eff),6),
                          'attack_rate_bonus_tiers':[float(x) for x in rates],'T05B_full_flank_dps':guard_rates,'T01B_full_dps_with_shared_heat_cooldown':heat_rates,
                          'four_rank1_four_rank2_heat_burn_dps':float(mix),'full_tree_costs':totals},
            'not_verified':['client integration','actual hit/LOS/navigation','control and fission runtime','mobile input/performance','all-sixty playable AI','seven-night economy and fun balance']}
    rp=ROOT/args.report;rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'counts':report['counts'],'report':str(rp),'arithmetic':report['arithmetic']},ensure_ascii=False))
if __name__=='__main__':main()
