from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import re

ROOT=Path(__file__).resolve().parents[1]
BASE='6445d758b9d1b63afad0afb7d75bc422e0d900a6'
EXPECTED_BLOBS={"content/monster_folklore_md01.json":"d3bbec91e4be2f2a7bc68e3079363c30ef5a6c76","content/monster_scp_a_md01.json":"fe3a69b4031345edc2f84d6b5fc7055e7e107145","content/monster_scp_b_md01.json":"20cf76da654982ae8e95a337328896db44959a41","content/tower_defense_td05.json":"4e8d7b42179e1aeafc9882eb9aadd1bd969e4fb3","content/traps_facilities_td05.json":"284fab6f1e3eb20e33b9622f97934a829ee22926","content/equipment_eq01.json":"31cfd8892b300c3b43c1f8b38a21d1d06ca2b4cf","content/consumables_eq01.json":"f388739832983c4ed0c7203ded63315f81ae4d8d","content/economy_week_td05.json":"d7367ffdcc22a160c22eeb6c0714c08fd5211c09"}
ATTACK_FILES=['content/monster_attacks_folklore_ma01.json','content/monster_attacks_scp_ma01.json']
SOURCE_FILES=['content/monster_folklore_md01.json','content/monster_scp_a_md01.json','content/monster_scp_b_md01.json']

def read(path):
    return json.loads((ROOT/path).read_text())

def ids(data):
    result=set()
    if isinstance(data,dict):
        if isinstance(data.get('id'),str):result.add(data['id'])
        for value in data.values():result.update(ids(value))
    elif isinstance(data,list):
        for value in data:result.update(ids(value))
    return result

def blob_sha(path):
    data=(ROOT/path).read_bytes()
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def run():
    checks=[]
    def check(name,condition,detail=None):
        entry={'name':name,'passed':bool(condition)}
        if not condition and detail is not None:entry['detail']=detail
        checks.append(entry)
    contract=read('content/attack_contracts_ma01.json')
    source={}
    for path in SOURCE_FILES:
        for card in read(path)['monsters']:source[card['id']]=(path,card)
    cards=[]
    for path in ATTACK_FILES:
        data=read(path)
        check(path+' design-only',data.get('runtime_integrated') is False)
        cards+=data['monsters']
    lookup={m['id']:m for m in cards}
    expected_ids={f'F{i:02d}' for i in range(1,61)}|{f'S{i:02d}' for i in range(1,46)}
    check('105 original IDs exactly once',len(cards)==105 and set(lookup)==expected_ids)
    check('shared contract runtime remains closed',contract['runtime_integrated'] is False and contract['validation']['runtime_admission'] is False)
    for path,sha in EXPECTED_BLOBS.items():
        check(path+' original blob unchanged',blob_sha(path)==sha)
    tower_ids=ids(read('content/tower_defense_td05.json'))
    gear_ids=ids(read('content/equipment_eq01.json'))
    item_ids=ids(read('content/consumables_eq01.json'))
    check('tower reference domain has 70 actual nodes',len({x for x in tower_ids if re.fullmatch(r'T\d{2}(?:\.[AB][12]?)?',x)})==70)
    check('equipment reference domain has all 36 definitions',len({x for x in gear_ids if re.fullmatch(r'Q\d{2}',x)})==36)
    attack_ids=[]
    families=collections.Counter()
    rows=[]
    required_card={'id','name','source_ref','baseline_resolution','admission','identity_note','basic_attack_id','attacks','child_profiles','selection','post_rule_summary','mechanism_work_window','synergies','adaptation_note'}
    required_attack={'id','name','role','family','availability','origin','timing','telegraph','geometry','movement','damage','hit_effect','interrupt','aftermath','counterplay','preserves','special'}
    timing_keys={'windup_s','active_s','recovery_hit_s','recovery_miss_s','cooldown_s','cooldown_basis'}
    geometry_keys={'shape','range_tiles','radius_tiles','width_tiles','arc_degrees','terrain_policy','hit_test','height_policy'}
    for m in cards:
        mid=m['id'];path,s=source[mid];attacks=m['attacks'];local={a['id']:a for a in attacks}
        check(mid+' preserves source identity/outcome and has complete card',
              required_card<=m.keys() and m['name']==s['name'] and m['baseline_resolution']==s['resolution']['type']
              and m['source_ref']==path+'#'+mid)
        basic=m['basic_attack_id']
        if mid=='F14':
            check(mid+' archived human host remains noncombat',m['admission']=='disabled' and basic is None and not attacks)
        elif mid=='F47':
            check(mid+' voluntary contest adds no damage penalty',m['admission']=='noncombat_source' and basic is None and not attacks and not m['child_profiles'])
        elif mid in ('S27','S32'):
            check(mid+' noncombat source delegates only real children',
                  m['admission']=='noncombat_source' and basic is None and bool(m['child_profiles']) and all(a['role']=='child' for a in attacks))
        else:
            check(mid+' has actual basic attack',basic in local and local[basic]['role']=='basic')
        synergy=m['synergies']
        missing=(set(synergy.get('towers',[]))-tower_ids)|(set(synergy.get('equipment',[]))-gear_ids)|(set(synergy.get('consumables',[]))-item_ids)
        check(mid+' references real tower/equipment/item IDs',not missing,sorted(missing))
        old_abilities={a['id'] for a in s.get('abilities',[])}
        mapped=m.get('selection',{}).get('preserved_abilities',[])
        mapped_ids={a.get('source_ability_id') for a in mapped if isinstance(a,dict)}
        check(mid+' accounts for every old ability without parallel copies',
              old_abilities<=mapped_ids and all(set(a.get('attack_ids',[]))<=set(local) for a in mapped if isinstance(a,dict)),
              {'missing_old':sorted(old_abilities-mapped_ids)})
        children=m['child_profiles']
        needs_children=s.get('children',{}).get('kind') in ('split','summon')
        check(mid+' child templates refer to actual attacks',
              (bool(children) if needs_children else True) and all(set(ch['attack_ids'])<=set(local) and bool(ch['attack_ids']) for ch in children))
        for a in attacks:
            aid=a['id'];attack_ids.append(aid);families[a['family']]+=1
            t=a['timing'];g=a['geometry'];d=a['damage'];mv=a['movement'];errors=[]
            if not required_attack<=a.keys():errors.append('missing attack fields')
            if a['family'] not in contract['families']:errors.append('unknown family')
            if not aid.startswith(mid+':'):errors.append('wrong actor namespace')
            if not timing_keys<=t.keys():errors.append('missing timing fields')
            if not geometry_keys<=g.keys():errors.append('missing geometry fields')
            for k in timing_keys-{'cooldown_basis'}:
                if not isinstance(t.get(k),(int,float)) or not math.isfinite(t[k]) or t[k]<0:errors.append('invalid '+k)
            if t['windup_s']<max(1.5,s['stats']['attack_telegraph']):errors.append('shortened baseline tell')
            if t['cooldown_basis']!='start_to_start_with_recovery_floor':errors.append('ambiguous clock')
            if not 0<d['san']<=18:errors.append('damage outside bounded design range')
            if not (d['once_per_attack_id'] and d['contact_inherits_same_id'] and d['global_grace_s']==2 and d['curse_check']=='once_at_commit'):errors.append('hit/curse identity mismatch')
            if len(a['counterplay'])<2:errors.append('missing counterplay')
            if a['interrupt']['stone'] not in ('none','ritual_focus_only'):errors.append('unbounded stone stun')
            if a['family']=='RITUAL':
                r=a['special'].get('ritual',{})
                if not (r.get('channel_total_s')==6 and r.get('interrupt_recovery_s')==.8 and r.get('mandatory_chase_s')==8 and r.get('minimum_recast_s')==16 and r.get('post_interrupt_basic_id')==basic):errors.append('ritual cycle differs')
                if s['stats']['move_speed']<=0 or s['movement']['mode']=='anchored':errors.append('anchored ritual would chase')
                if a['interrupt']['stone']!='ritual_focus_only':errors.append('ritual missing stone interrupt')
            elif a['interrupt']['stone']!='none':errors.append('stone stuns nonritual')
            if a['family']=='TETHER':
                z=a['special'].get('tether',{})
                if not (z.get('root_s')==.6 and z.get('slow_fraction')==.35 and z.get('total_s')==2 and z.get('unwrap_hold_s')==.6 and z.get('break_los_s')==.2 and 0<z.get('max_length_tiles',0)<=4 and z.get('rebind_immunity_s')==6 and z.get('attacker_channels') is True):errors.append('tether bounds differ')
                speed=a['special'].get('projectile_speed_tiles_s')
                if speed is None or speed<=0:errors.append('tether lacks real projectile speed')
            if a['family']=='CONTACT':
                if t['active_s']>3 or t['cooldown_s']<7:errors.append('contact temporal overreach')
                if a['telegraph']['aim_lock'] not in ('body_volume',):errors.append('undefined body exception')
            if g['shape']=='disc' and g['radius_tiles']<1.5:errors.append('harmful ground disc too small')
            if a['family']=='CHARGE' and mv['distance_tiles']>mv['speed_tiles_s']*t['active_s']+1e-8:errors.append('charge distance exceeds actual time')
            post=a['aftermath']['post_rule']
            if s['resolution']['type']=='rule_leave' and isinstance(post,dict) and not post.get('disabled',False):errors.append('leave still attacks')
            check(aid+' bounded geometry/timing/control contract',not errors,errors)
            rows.append({'id':aid,'monster':mid,'family':a['family'],'role':a['role'],'damage_san':d['san'],
                         'full_declared_active_cycle_hit_s':max(t['cooldown_s'],t['windup_s']+t['active_s']+t['recovery_hit_s']),
                         'full_declared_active_cycle_miss_s':max(t['cooldown_s'],t['windup_s']+(a['special'].get('maximum_flight_s',t['active_s']) if a['family']=='TETHER' else t['active_s'])+t['recovery_miss_s'])})
    check('all attack definition IDs are unique',len(attack_ids)==len(set(attack_ids)))
    check('requested six behaviors exist',all(families[x]>0 for x in ['CHARGE','CONTACT','RITUAL','BEAM','TETHER']) and all(a['timing']['windup_s']>=1.5 for m in cards for a in m['attacks']))
    for mid in ('F12','F13'):
        a=next(a for a in lookup[mid]['attacks'] if a['id']==lookup[mid]['basic_attack_id']);t=a['timing']
        check(mid+' original 3 second basic cadence retained',t['windup_s']==1.5 and t['active_s']==0 and t['recovery_hit_s']==1.5 and t['recovery_miss_s']==1.5 and t['cooldown_s']==3)
    check('stone is one three-object nightly shared ledger',
          contract['stones']['physical_count_per_night']==3 and contract['stones']['shared_across_all_ritual_roots']
          and contract['stones']['stamina_cost']==0 and not contract['stones']['ordinary_inventory'] and not contract['stones']['special_quota'])
    check('body contact is explicit exception only','contact_exception' in contract['lifecycle'] and contract['lifecycle']['basic_min_telegraph_s']==1.5)
    index=read('content/monster_attack_roster_ma01.json')
    check('attack index matches authored definitions',index['total']==105 and set(x['id'] for x in index['entries'])==expected_ids and index['attack_definition_count']==len(attack_ids))
    for path,sha in index['data_sha256'].items():
        check(path+' indexed content hash current',hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha)
    reference=read('docs/ma01_reference_report.json')
    current_refs=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in reference.get('input_hashes',{}).items())
    check('finite reference report is current and passed',reference['failed']==0 and current_refs and len(reference.get('input_hashes',{}))==2)
    counts=collections.Counter(m['baseline_resolution'] for m in cards)
    check('22 gates 45 departures 38 weakenings preserved',dict(counts)=={'kill_unlocked':22,'rule_leave':45,'rule_weaken':38})
    passed=sum(x['passed'] for x in checks)
    inputs=ATTACK_FILES+SOURCE_FILES+['content/attack_contracts_ma01.json','content/monster_attack_roster_ma01.json','scripts/ma01_reference.py','scripts/check_ma01_reference.py','scripts/check_ma01_design.py','scripts/render_ma01_design.py']
    return {'version':'MA01','runtime_integrated':False,'baseline_commit':BASE,
            'structural_passed':passed,'structural_failed':len(checks)-passed,
            'finite_passed':reference['passed'],'finite_failed':reference['failed'],
            'monster_count':len(cards),'attack_definition_count':len(attack_ids),'child_template_count':sum(len(m['child_profiles']) for m in cards),
            'family_counts':dict(sorted(families.items())),'outcome_counts':dict(counts),
            'scope':'逐卡字段/引用/预算及独立有限行为反例；不证明105AI、完整地图可达、运行物理或整周胜率。',
            'checks':checks,'timing_rows':rows,'review_corrections':reference.get('review_corrections',[])+[
                'Initial integration check had112 failures: legacy-ability mapping shape, post-rule enabled/disabled field names, and CONTACT aim-lock spelling differed between authors. These semantic fields were standardized before the final check; this is not claimed as a first-pass all-green integration.',
                'S35 native6-second4.2-speed lane bound was restored after an incorrect8-tile draft cap.',
                'F47 voluntary sealed-bag contest has no legal damage event; the attack admission explicitly remains noncombat, retaining its MD01 rule-leave outcome and unique reward receipts.'
            ],
            'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/ma01_validation_report.json');args=parser.parse_args()
    report=run();p=ROOT/args.output;p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['structural_passed','structural_failed','finite_passed','finite_failed','monster_count','attack_definition_count','child_template_count','family_counts']},ensure_ascii=False))
    failures=[x for x in report['checks'] if not x['passed']]
    if failures:print(json.dumps(failures,ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['structural_failed'] or report['finite_failed']))
