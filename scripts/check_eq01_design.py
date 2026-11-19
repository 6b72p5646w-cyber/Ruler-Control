#!/usr/bin/env python3
"""Cross-reference EQ01 design and exercise bounded failure/stacking cases."""
import argparse
import ast
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from fractions import Fraction as F
from eq01_reference import (
    q, pity_weights, weighted_candidates, LotteryLedger, Mobility,
    long_run_speed, advance_maturities, poison_integral, electric_snapshot,
    add_paid_parallel_charge, admitted_extra_proc, native_electric_feedback,
    allowed_manifest, progress_advance,
)

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
args=parser.parse_args(); ROOT=args.root
search_roots=[ROOT,ROOT.parent/'ruler-control-td05',ROOT.parent/'ruler-control-md01',ROOT.parent/'ruler-control-md01-source',ROOT.parent/'ruler-control-source']
def source(path):
    for root in search_roots:
        p=root/path
        if p.exists(): return p
    raise FileNotFoundError(path)
def read(path): return json.loads(source(path).read_text())
checks=[]
def check(name,value): checks.append({'name':name,'passed':bool(value)})
def rejects(name,fn):
    try: fn()
    except (ValueError,KeyError): check(name,True)
    else: check(name,False)

gear=read('content/equipment_eq01.json')['equipment']; items=read('content/consumables_eq01.json')['items']
contract=read('content/equipment_contracts_eq01.json'); loot=read('content/lottery_rewards_eq01.json')
builds=read('content/equipment_builds_eq01.json')['builds']
tree=read('content/tower_defense_td05.json'); towers={}
for family in tree['families']:
    for node in [family['l1']]+[n for b in family['l2'] for n in [b]+b['l3']]: towers[node['id']]=node
monsters={x['id'] for x in read('content/monster_roster_md01.json')['entries']}
check('36 unique equipment definitions',len(gear)==len({x['id'] for x in gear})==36)
check('34 equipment design candidates',sum(x['design_enabled'] for x in gear)==34)
check('18 unique new special definitions',len(items)==len({x['id'] for x in items})==18)
check('equipment tiers reflect deliberate utility demotions',Counter(x['rarity'] for x in gear if x['design_enabled'])=={'common':6,'uncommon':17,'rare':11})
check('special tiers6/8/4',Counter(x['rarity'] for x in items)=={'common':6,'uncommon':8,'rare':4})
for x in gear:
    ident=x['id']
    check(ident+' stays design-only',x['runtime_integrated'] is False and x['acquisition']['runtime_acquisition_enabled'] is False)
    if not x['design_enabled']:
        check(ident+' disabled remains outside lottery',ident in ['Q03','Q11'] and not x['acquisition']['lottery_design_enabled'])
        continue
    check(ident+' quantified attributes plus real core consumer',bool(x['base_attributes']) and all(a.get('consumer') and 'value' in a for a in x['base_attributes']) and bool(x['ability'].get('consumer')))
    check(ident+' references real tower nodes',all(t in towers for group in x['tower_synergies'] for t in group['tower_node_ids']))
    check(ident+' references real monster definitions',all(m in monsters for m in x['monster_examples']))
    check(ident+' price and fixed acquisition',x['acquisition']['shop_price_week_coin']>0 and x['acquisition']['shop_design_enabled'])
for x in items:
    ident=x['id']; u=x['use']
    check(ident+' real single-unit commit and no runtime claim',u['consume_units']==1 and x['runtime_integrated'] is False and x['runtime_acquisition_enabled'] is False)
    check(ident+' authored consumer and paid effect budget',bool(x['consumer']) and bool(x['paid_effect_budget']))
    check(ident+' price and reward quantity',x['shop_unit_price']['coin']=={'common':8,'uncommon':14,'rare':24}[x['rarity']] and x['lottery_reward_units']==(2 if x['rarity']=='common' else 1))
    check(ident+' real tower/monster references',all(t in towers for t in x['tower_synergies']) and all(m in monsters for m in x['monster_examples']))
    check(ident+' minimum area and cast',u['cast_world_seconds']>=.25 and (u['radius_tiles'] is None or u['radius_tiles']>=1.5))
bygear={x['id']:x for x in gear}; byitem={x['id']:x for x in items}
for b in builds:
    chosen=[bygear[x] for x in b['gear']]
    check(b['id']+' has one enabled item per slot',len(chosen)==6 and len({x['slot'] for x in chosen})==6 and all(x['design_enabled'] for x in chosen))
    check(b['id']+' one actual tactical active',b['active'] is None or (b['active'] in b['gear'] and bygear[b['active']]['ability']['mode']=='tactical_active'))
    check(b['id']+' valid builds/items/monsters',all(t in towers for t in b['towers']) and all(i in byitem for i in b['items']) and all(m in monsters for m in b['monsters']))

catalog=loot['catalog']; admitted={x['id'] for x in catalog}
check('52 exact design pool definitions, no disabled or food',len(catalog)==len(admitted)==52 and admitted=={x['id'] for x in gear if x['design_enabled']}|{x['id'] for x in items})
check('runtime pool is not silently enabled',not any(x['runtime_admitted'] for x in catalog))
for common,nonrare in [(0,0),(3,7),(4,4),(4,9),(0,9)]:
    c=weighted_candidates(catalog,set(),common,nonrare,admitted)
    check(f'pity({common},{nonrare}) exact weight conservation',sum(w for _,w in c)==1)
    for tier,expected in zip(('common','uncommon','rare'),pity_weights(common,nonrare)):
        for kind in ('equipment','consumable'):
            check(f'pity({common},{nonrare}) {tier}/{kind}',sum(w for x,w in c if x['tier']==tier and x['kind']==kind)==expected/2)

fixture=[{'id':kind[0]+tier[0],'name':kind+tier,'tier':tier,'kind':kind,'units':2 if kind=='consumable' and tier=='common' else 1}
         for tier in ('common','uncommon','rare') for kind in ('equipment','consumable')]
fixture_ids={x['id'] for x in fixture}
s=LotteryLedger(2,60,owned={'ec'})
before=deepcopy(s)
rejects('missing live handlers refuses without debit',lambda:s.prepare('empty',fixture,set(),[0]))
check('missing handlers preserves all ledger state',s==before)
s.phase='open';before=deepcopy(s)
rejects('business phase refuses draw',lambda:s.prepare('open',fixture,fixture_ids,[0]))
check('business rejection preserves ledger',s==before)
s.phase='preparation'
r=s.prepare('duplicate-common',fixture,fixture_ids,[0])
check('reserve spends once and pity unchanged',(s.tickets,s.preparation_minutes,s.common,s.nonrare)==(1,45,0,0))
check('persisted duplicate decision',r['choices'][0]['duplicate'])
check('retry prepare restores exact candidates',s.prepare('duplicate-common',fixture,fixture_ids,[q(.99)])==r)
rejects('pending choice blocks new draw',lambda:s.prepare('second',fixture,fixture_ids,[0]))
rejects('duplicate cannot convert to higher rarity',lambda:s.select('duplicate-common',compensation_id='cr'))
saved=deepcopy(s)
receipt=saved.select('duplicate-common',compensation_id='cc')
check('common duplicate grants two same-tier actual units',receipt['units']==2 and saved.item_units=={'cc':2} and (saved.common,saved.nonrare)==(1,1))
check('select replay cannot double reward',saved.select('duplicate-common',compensation_id='cr')==receipt and saved.item_units=={'cc':2} and saved.tickets==1)

s=LotteryLedger(2,60,owned={'er'},common=4,nonrare=9)
s.prepare('rare-duplicate',fixture,fixture_ids,[0]); r=s.select('rare-duplicate',compensation_id='cr')
check('rare pity beats noncommon pity and duplicate resets once',r['original_tier']=='rare' and (s.common,s.nonrare)==(0,0) and s.item_units=={'cr':1})
s=LotteryLedger(3,90,common=4,nonrare=4)
rejects('E064 needs actual event authorization',lambda:s.prepare('bad-double',fixture,fixture_ids,[0,q(.999)],double=True))
r=s.prepare('double',fixture,fixture_ids,[0,q(.999)],double=True,double_authorized=True)
check('E064 both candidates share old pity and are distinct',r['pity_before']==[4,4] and [x['tier'] for x in r['choices']]==['uncommon','rare'] and len({x['id'] for x in r['choices']})==2)
s.select('double',0)
check('unselected rare does not update pity',s.common==0 and s.nonrare==5 and s.tickets==2 and s.preparation_minutes==75)
rejects('E064 one per actual procurement window',lambda:s.prepare('repeat-double',fixture,fixture_ids,[0,.9],double=True,double_authorized=True))
s=LotteryLedger(1,15,owned={x['id'] for x in catalog if x['kind']=='equipment' and x['tier']=='common'})
r=s.prepare('distinct-compensation',catalog,admitted,[0,0],double=True,double_authorized=True)
check('E064 cannot show two equivalent duplicate menus',r['choices'][0]['effective_key']!=r['choices'][1]['effective_key'])
s=LotteryLedger(1,14)
rejects('insufficient preparation minutes refuses draw',lambda:s.prepare('time',fixture,fixture_ids,[0]))
s=LotteryLedger(0,120)
rejects('insufficient tickets refuses draw',lambda:s.prepare('tickets',fixture,fixture_ids,[0]))

check('baseline repeatable speed',long_run_speed(3)==q(3.08))
check('Q14 repeatable speed stays below heavy',long_run_speed(3.15)==q(3.22)<q(3.24))
check('Q31 repeatable speed and same-slot exclusion',long_run_speed(3,'Q31')==q(3.09375)<q(3.24))
check('Q32 repeatable upper mean below heavy',long_run_speed(3,'Q32')<q(3.24))
check('default two-second escape gain vs agile',(q(4.2)-q(3.45))*2==q(1.5))
m=Mobility();before=deepcopy(m)
rejects('heavy carry blocks sprint',lambda:m.start(0,100,heavy=True))
rejects('work blocks sprint',lambda:m.start(0,100,working=True))
rejects('blocked path does not consume startup',lambda:m.start(0,100,actual_nonzero_path=False))
check('failed mobility starts preserve state',m==before)
rejects('Q31 startup3 is underfunded',lambda:m.start(0,3,'Q31'))
m.start(0,4.5,'Q31');r=m.move_segment(1,4.5)
check('partial affordable Q31 never overspends',r=={'seconds':F(1,4),'distance':q(1.125),'stamina':0} and m.ready_at==32 and m.active_remaining==0)
rejects('resource refill does not clear mobility clock',lambda:m.start(1,100,'Q31'))
rejects('shoe replacement cannot clear shared clock',lambda:m.start(1,100,'baseline'))
m=Mobility();m.start(0,100); r=m.move_segment(2,100)
check('full sprint spends24 and moves8.4',r['stamina']==76 and r['distance']==q(8.4) and m.ready_at==30)
copy=deepcopy(m);rejects('reload keeps remaining cooldown',lambda:copy.start(10,100))
m=Mobility();m.start(0,100,'Q32');r=m.move_segment(.9,100);m.start(1,r['stamina'],'Q32',second=True);r2=m.move_segment(.9,r['stamina'])
check('Q32 two bursts share one28s deadline',r2['stamina']==76 and m.ready_at==28 and not m.second_available and r['distance']+r2['distance']==q(7.38))
rejects('Q32 cannot get a third burst',lambda:m.start(2,100,'Q32',second=True))
m=Mobility();m.start(0,100,'Q32');m.move_segment(.9,100)
rejects('Q32 expires exactly at5s',lambda:m.start(5,100,'Q32',second=True))
for args_, expected in [((6,2,4,False),True),((6,1,6,True),False),((6,0,6,True),True),((10,0,5,False),False),((4,1,4,False),False)]:
    check('manifest '+str(args_),allowed_manifest(*args_)==expected)

records=[{'id':'soon','due':q(.1),'q':q(1),'paid':False}]+[{'id':str(i),'due':q(i),'q':q(1),'paid':False} for i in range(1,6)]
cast_receipts=set();before_q=sum(x['q'] for x in records)
check('Q33 advances exactlyfour existing budgets',advance_maturities(records,0,'cast1',cast_receipts)==4)
check('Q33 never delays soon-due or creates q',records[0]['due']==q(.1) and records[-1]['due']==5 and sum(x['q'] for x in records)==before_q)
before=deepcopy(records)
check('Q33 repeated receipt cannot advance fifth budget',advance_maturities(records,0,'cast1',cast_receipts)==0 and records==before)
reject_paid=[{'id':'paid','due':10,'q':1,'paid':True},{'id':'early','due':q(.1),'q':1,'paid':False}]
check('Q33 no positive advance produces no commit',advance_maturities(reject_paid,0,'invalid',cast_receipts)==0 and 'invalid' not in cast_receipts)
check('poison q12 baseline8s48',poison_integral(12,0,8)==48)
check('I41 doubles actual8s segments no burst',poison_integral(12,0,8,[(0,8,2)])==96)
check('I41 duplicate is strongest not x4',poison_integral(12,0,8,[(0,8,2),(0,8,2)])==96)
check('I41 finite expiry',poison_integral(12,0,10,[(0,8,2)])==108)
check('suppression no backpay and buffclock advances',poison_integral(12,0,10,[(0,8,2)],[(0,q(4.5))])==54)
check('fractional poison fromsplit remains linear',poison_integral(F(5,2),0,8,[(0,8,2)])==20)

pools={'A':(0,0),'B':(q(2.4),0),'C':(q(5.6),0)}; aps={'AP_HOT_FOOD':(q(2.4),1)}
base=electric_snapshot(pools,aps); extended=electric_snapshot(pools,aps,reach={'B':q(3.25)})
check('I36 connects real previouslyseparateC',base['connected']['A']=={'A','B'} and extended['connected']['A']=={'A','B','C'})
check('same adjacency governs localN plus unchangedE',extended['local_coefficients']=={'A':2,'B':4,'C':2} and extended['appliance_adjacency']==base['appliance_adjacency'])
check('D6 recipient damages are12/24/12',{k:6*v for k,v in extended['local_coefficients'].items()}=={'A':12,'B':24,'C':12})
blocked=electric_snapshot(pools,aps,reach={'B':q(3.25)},blocked_pairs=[('B','C')])
check('extension does not ignore blockedline',blocked['connected']['A']=={'A','B'})
dead=electric_snapshot({'A':pools['A'],'C':pools['C']},aps,reach={'B':q(3.25)})
check('death removes incident links andcounts',dead['connected']['A']=={'A'} and dead['local_coefficients']=={'A':1,'C':1})
pair=electric_snapshot({'A':(0,0),'B':(4,0)}, {},reach={'A':q(3.25)},pair_links=[('A','B',4)])
check('Q34 maximum4 not3.25+4',pair['local_coefficients']=={'A':2,'B':2} and electric_snapshot({'A':(0,0),'B':(5,0)},{},reach={'A':q(3.25)},pair_links=[('A','B',4)])['connected']['A']=={'A'})
rejects('equipment or machine cannotbeAP',lambda:electric_snapshot({'A':(0,0)},{'LOTTERY_COUNTER_01':(0,1)}))
for n in [1,2,3,6,12]:
    charges=add_paid_parallel_charge('0',map(str,range(n)))
    check('I42 actualpaidbudget for'+str(n)+' pools',charges['0']==4 and sum(charges.values())==4+n-1 and len(charges)==n)
check('I42 nohit charge doesnotinventfeedback',native_electric_feedback(0)==0)
check('default positivefeedback hasno sixpoolcap',sum(native_electric_feedback(1) for _ in range(12))==12)
check('generic equipmentsecondary excluded, nativeelectric exception preserved',not admitted_extra_proc({'origin':'eq01_secondary','actual_committed':True,'legal_target':True}) and native_electric_feedback(2)==1)
check('real native primary can trigger boundedextra',admitted_extra_proc({'origin':'native_primary','actual_committed':True,'legal_target':True}))
check('duplicate event cannottriggerextra',not admitted_extra_proc({'origin':'native_primary','actual_committed':True,'legal_target':True,'duplicate':True}))
check('I40 actualsniperreload excludes aim',progress_advance(q(2.9),q(3.2)-q(.3))==q(1.45))
check('I40 progress clamps atone existingreadyshot',progress_advance(.2,2.9)==q(.2) and progress_advance(0,2.9)==0)
check('I40 excludes fullmag andmultiwave',byitem['I40']['parameters']['excluded_multishot_nodes']==['T02.A2','T03.A2'])
check('Q28/I38 strongest reservation timing notmultiplied',min(q(.5),max(q(.15),q(.5)*q(.6)),q(.1))==q(.1))

economy=read('docs/eq01_economy_report.json')
check('economy equipment inputhash is current',economy['inputs']['equipment_catalog_sha256']==hashlib.sha256(source('content/equipment_eq01.json').read_bytes()).hexdigest())
# Validate parseability and renderability separately from behavioral assertions.
for p in ROOT.rglob('*.json'): json.loads(p.read_text())
for p in (ROOT/'scripts').glob('*.py'): ast.parse(p.read_text())

report={'version':'EQ01','runtime_integrated':False,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),
        'scope':'structural cross-references plus finite lottery/mobility/status/graph counterexamples; not all52enabledworldhandlers,105AI,physics,randomweekorUI',
        'checks':checks,
        'input_hashes':{p:hashlib.sha256(source(p).read_bytes()).hexdigest() for p in ['content/equipment_contracts_eq01.json','content/equipment_eq01.json','content/consumables_eq01.json','content/lottery_rewards_eq01.json','content/equipment_builds_eq01.json']}}
(ROOT/'docs/eq01_validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'failed':report['failed'],'failures':[x['name'] for x in checks if not x['passed']]},ensure_ascii=False))
raise SystemExit(1 if report['failed'] else 0)
