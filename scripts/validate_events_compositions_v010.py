#!/usr/bin/env python3
"""Event/source/clock review and measured-plan admission counterexamples.

This does not turn all event or monster prose into live AI.  It exercises the
actual map-backed admission arithmetic and the deliberately finite cases below.
"""
from pathlib import Path
from copy import deepcopy
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototype'))
from mechanism_model_v010 import MapRoutes, ContractModel
from composition_core_v010 import admit, expand_e045_operations, admit_e035_public_exit

def read(n):return json.loads((ROOT/'content'/n).read_text())

def validate():
    errors=[];checks=0;probes=[];composition_routes=[]
    def need(value,where,message):
        nonlocal checks
        checks+=1
        if not value:errors.append({'path':where,'message':message})
    events=read('event_contracts_v010.json');em={e['id']:e for e in events['events']}
    old={e['id']:e for e in read('events.json')['events']}
    compositions=read('composition_contracts_v010.json');cm={c['id']:c for c in compositions['compositions']}
    sy={s['id']:s for s in read('synergies.json')['synergies']}
    scene=next(s for s in read('maps.json')['scenes'] if s['id']=='MAP_STORE');routes=MapRoutes(scene)
    need(set(em)==set(old) and len(em)==72,'events','All 72 events must have a concrete current/archived contract')
    need(sum(e['enabled_current'] for e in em.values())==71,'events','Only source-less repair event E051 stays archived')
    for eid,event in em.items():
        need(bool(event['source']),eid,'Missing real producer')
        need(len(event['branches'])==2,eid,'Both authored choices need a concrete outcome')
        need(event['source_cannot_be_invented_after_sampling'],eid,'Sampling may not fabricate prior facts')
        need(bool(event['expiry']),eid,'Missing expiry')
        need(not event['client_implemented'],eid,'Design document must not claim a complete client')
        if event['phase']=='night':
            need(0<=event['effect_lifetime_world_seconds']<=120,eid,'Unbounded ambient lifetime')
            for branch in event['branches']:
                actual=0;position=None
                for operation in branch['operations']:
                    need(operation['anchor'] in routes.anchors,operation['id'],'Unknown actual station')
                    need(operation['world_seconds']>=0,operation['id'],'Invalid operation duration')
                    point=routes.anchors[operation['anchor']]
                    if position is not None:actual+=routes.distance(position,point)/2.4
                    repeats=operation.get('repeat_max',1)
                    if 'repeat_for' in operation:
                        need(eid=='E045' and operation['repeat_for']=='actual_due_contract_ids'
                             and operation.get('repeat_min')==1 and repeats==3,
                             operation['id'],'Unbound or unbounded repeated contract operation')
                    position=point;actual+=operation['world_seconds']*repeats
                    need(bool(operation['effect']),operation['id'],'No actual effect consumer')
                need(abs(actual-branch['local_action_and_route_seconds'])<0.001,branch['id'],'Local route/action budget drift')
                need(actual<=event['handling_budget_seconds']+1e-8,branch['id'],'Handling budget smaller than local required work')
        else:
            need(event['maximum_existing_day_slots'] in (0,1),eid,'Event invents extra day slots')
            need(0<=event['maximum_optional_preparation_minutes']<=60,eid,'Preparation exceeds shared optional budget')
            need(event['no_extra_slot_or_second_full_action_reward'],eid,'Double full-action reward')
    # Known counterexamples that prose-only validation had missed.
    procession=em['E037']['mechanic_details']
    need(procession['new_precision_qte_allowed_during_event'] is False,'E037','World-100 queue cannot coexist with unreserved frozen-world QTE spending')
    naive_world_at_budget120=120-3*8
    need(naive_world_at_budget120<100,'E037 counterexample','The QTE clock counterexample must remain visible')
    arrivals=procession['original_order_arrivals_transformed_before_phase_start']
    windows=procession['optional_delivery_windows_relative_to_stage']
    need(10+24<windows[0][0],'E037 old schedule counterexample','Original first order expires before the first window')
    for arrival,window in zip(arrivals,windows):
        need(arrival==window[0] and arrival+24>window[1],'E037 revised schedule','Real order must exist throughout its admitted crossing window')
    need(procession['two_orders_checkout_world_seconds']==7,'E037','Two actual silent orders cost 7 seconds plus travel')
    need(em['E008']['mechanic_details']['reschedule_before_actual_arrival_only'],'E008','Rider cannot become unarrived again')
    need(em['E028']['mechanic_details']['callback_does_not_restart_absence'],'E028','Callback must not create a new return deadline')
    visitor=em['E035']['mechanic_details']
    exit_point=visitor['visitor_exit_position']
    visitor_distance=routes.distance(visitor['visitor_initial_public_position'],exit_point)
    old_manager_roundtrip=2+2*routes.distance(routes.anchors['verification_desk'],exit_point)/3
    visitor_elapsed=2+visitor_distance/visitor['visitor_speed_tiles_per_world_second']
    need(old_manager_roundtrip>720-visitor['latest_start_shift_budget'],
         'E035 old escort counterexample','The old two-second manager escort must fail the real return-route budget')
    need(visitor_distance==visitor['visitor_measured_exit_route_tiles']==12
         and abs(visitor_elapsed-visitor['branch2_local_elapsed_with_visitor_exit_seconds'])<1e-8
         and visitor_elapsed<=720-visitor['latest_start_shift_budget'],
         'E035','Visitor exit must fit its actual public route before handover')
    need(visitor['manager_stays_at_verified_station'] and visitor['player_at_verified_desk_required_before_offer']
         and visitor['no_player_cross_store_travel_after_714']
         and visitor['visitor_exit_requires_current_unblocked_path']
         and visitor['front_exit_must_be_open_and_lawfully_traversable']
         and visitor['closed_exit_does_not_teleport_visitor'],
         'E035','Visitor direction cannot move the manager or bypass a closed public exit')
    probes.append({'id':'E035_old_manager_escort_exceeds_late_window','old_route_seconds':old_manager_roundtrip,
                   'available_seconds':720-visitor['latest_start_shift_budget'],'old_plan_allowed':False})
    need(visitor['latest_first_omen_shift_budget']==710
         and visitor['minimum_recognition_preparation_world_seconds']>=4
         and visitor['latest_first_omen_shift_budget']+visitor['minimum_recognition_preparation_world_seconds']+visitor_elapsed<=720,
         'E035','Director must reserve recognition time before the six-second exit, not first warn at 714')
    visitor_world={'shift_budget':714,'first_omen_shift_budget':710,'manager_position':routes.anchors['verification_desk'],
                   'manager_verified_current':True,'player_position':routes.anchors['verification_desk'],
                   'handover_capacity_reserved':True,'visitor_position':visitor['visitor_initial_public_position'],
                   'closed_doors':[],'public_exit_safe':True}
    for pid,changed,allowed,reason in [
        ('E035_actual_visitor_leaves_manager_stays',{},True,None),
        ('E035_closed_front_door_no_teleport',{'closed_doors':['DOOR_FRONT']},False,'actual_open_safe_public_exit_required'),
        ('E035_unsafe_public_exit_no_teleport',{'public_exit_safe':False},False,'actual_open_safe_public_exit_required'),
        ('E035_remote_player_not_instantly_at_desk',{'player_position':routes.anchors['cashier']},False,'player_and_handover_reservation_required_before_offer'),
        ('E035_after_last_safe_start',{'shift_budget':714.01},False,'outside_E035_offer_window'),
        ('E035_first_notice_at_last_action_start_is_too_late',{'first_omen_shift_budget':714},False,'late_or_missing_first_omen'),
        ('E035_no_instant_reaction_assumption',{'shift_budget':712},False,'recognition_preparation_margin_missing'),
        ('E035_manager_actually_escorted_away',{'manager_position':routes.anchors['front_door']},False,'current_verified_manager_must_stay_at_desk')]:
        w=deepcopy(visitor_world);w.update(changed);before=deepcopy(w)
        result=admit_e035_public_exit(em['E035'],w,routes)
        need(result['allowed']==allowed and (reason is None or reason in result['reasons']),pid,'Unsafe visitor exit was admitted')
        need(w==before,pid,'Admission teleported or changed an actor')
        probes.append({'id':pid,**result})
    need(em['E053']['mechanic_details']['item_id']=='I01' and em['E053']['mechanic_details']['actual_ingestion_satiety']==25,'E053','Meal must use actual meal consumer, not mint SAN consumer')
    need(em['E070']['branches'][0]['operations'][0]['world_seconds']==0,'E070','Natural recovery must not require walking to a station first')
    outage=em['E019']['mechanic_details']
    need(outage['subtype_fixed_before_first_omen'] and not outage['mask_expiry_repairs_fault'],'E019','Fault type must be fixed before sampling and survive mere mask expiry')
    need(outage['subtypes']['trip']['f59_eligible'] is False and outage['subtypes']['damaged_component']['same_optional_device_stays_disabled'],'S16','Six-second isolation must not dominate actual component repair')
    need(outage['second_manual_repair_after_F59_required'] is False,'S16','Same fault cannot require a redundant second reset')
    loan=em['E071']['mechanic_details']
    need(loan['max_open_contracts']*loan['wage_offset_per_contract']<=loan['base_wage_floor'],'E071','Loan exit must not require an impossible next base wage')
    settlement=em['E045'];details=settlement['mechanic_details']
    need(details['manual_window_start_shift_budget']==480 and details['manual_window_end_shift_budget']==600,
         'E045','Manual settlement must use the real N05 interval, not a 40-second ambient lifetime')
    need(settlement['effect_lifetime_world_seconds']==0 and settlement['handling_budget_seconds']==40,
         'E045','Forty seconds is the maximum local work budget; actual approach is additional')
    need(details['manual_completion_receipt_kind']!=details['automatic_offset_receipt_kind']
         and not details['automatic_offset_grants_manual_work_receipt']
         and not details['automatic_offset_grants_ordinary_work_credit']
         and details['unpaid_until_actual_wage_deduction'],
         'E045','Automatic fallback must not forge physical work or claim an undeducted debt was paid')
    for branch in settlement['branches']:
        for debt_count in range(1,4):
            original_ids=[f'original_due_loan_{i}' for i in range(debt_count)]
            operations=expand_e045_operations(settlement,branch['id'],original_ids)
            world={'player_position':routes.anchors['cashier'],'remaining_phase_budget':120,
                   'sources':{k:{'committed':True,'expired':False} for k in original_ids}}
            plan={'required_sources':original_ids,'operations':operations,'new_primary_count':1}
            result=admit(plan,world,routes);expected=8+8*debt_count+8
            need(result['allowed'] and result['measured_plan_seconds']==expected,
                 branch['id'],f'{debt_count} real debts need {expected} seconds, not one eight-second operation')
            need(branch['actual_count_cost_seconds'][str(debt_count)]==expected
                 and details['actual_contract_count_cost_seconds'][str(debt_count)]==expected
                 and old['E045']['reservation']['seconds']['actual_count_totals'][str(debt_count)]==expected,
                 branch['id'],'Current and linked original debt reservations disagree')
            need([o['object_id'] for o in operations if 'object_id' in o]==original_ids,
                 branch['id'],'Every debt must bind exactly one original ID')
            probes.append({'id':branch['id']+f'_manual_{debt_count}_original_debts',**result})
            too_late=deepcopy(world);too_late['remaining_phase_budget']=expected-0.01
            result=admit(plan,too_late,routes)
            need(not result['allowed'] and 'insufficient_actual_phase_budget' in result['reasons'],
                 branch['id'],'A manual batch ending after the N05 boundary must be rejected')
            probes.append({'id':branch['id']+f'_manual_{debt_count}_debts_001_late',**result})
            missing=deepcopy(world);del missing['sources'][original_ids[-1]]
            result=admit(plan,missing,routes)
            need(not result['allowed'] and 'missing_actual_source:'+original_ids[-1] in result['reasons'],
                 branch['id'],'An absent original debt must not become a payable row')
            probes.append({'id':branch['id']+f'_manual_{debt_count}_debts_missing_source',**result})
    for bad_ids in ([],['same','same'],['a','b','c','d'],['']):
        try:expand_e045_operations(settlement,'E045:B1',bad_ids)
        except ValueError:rejected=True
        else:rejected=False
        need(rejected,'E045','Empty, repeated, malformed or over-capacity debt rows must be rejected')
    try:expand_e045_operations(settlement,'automatic_wage_offset',['original_due_loan'])
    except ValueError:automatic_rejected=True
    else:automatic_rejected=False
    need(automatic_rejected,'E045','Automatic wage offset cannot be expanded into a physical-work plan')
    # Paid or gifted objects have a finite salvage quote and cannot finance a
    # buy-salvage-refund loop. These are arithmetic/ledger policy probes only.
    for reference,paid in [(60,42),(15,12),(60,6),(60,None),(10,1)]:
        cap=reference if paid is None else min(reference,paid)
        quote=int(cap*em['E066']['mechanic_details']['quote_fraction'])
        need(paid is None or quote<=paid,'E066','Salvage pays more than actual purchase')
        probes.append({'id':f'salvage_{reference}_{paid}','result':quote,'scope':'published quote arithmetic; transaction persistence remains adapter work'})
    need(len(cm)==18 and sum(c['enabled_current'] for c in cm.values())==13,'compositions','18 catalog / 13 enabled / 5 archived')
    for cid,composition in cm.items():
        need(composition['enabled_current']==sy[cid]['enabled_current'],cid,'Enabled status differs between catalogs')
        if composition['enabled_current']:
            need(bool(composition['required_actual_sources']),cid,'No causal producer')
            need(composition['active_player_pursuers_max']==1 and composition['new_primary_per_phase_max']==1,cid,'Composition bypasses director limits')
    identity=sy['S08']['temporal_witness_v08']['steps']
    elapsed=identity[-1]['budget']-identity[-3]['budget']
    need(abs(elapsed-(10/3+1+1.5))<1e-6 and elapsed<8,'S08','Fresh current identity must survive the actual local route, not the sixty-second omen wait')
    need(identity[2]['budget']<identity[3]['budget'],'S08','Current short credential is produced after the first far omen')
    need(routes.distance([15.5,28.5],[24.5,27.5])==10,'F38','Second body arrival must use the real ten-tile route')
    case_rows=[c for path in sorted((ROOT/'content').glob('mechanism_cases_v010_*.json')) for c in json.loads(path.read_text())['cases']]
    cases={c['id']:c for c in case_rows}
    # Route witnesses use the actual actions of each enabled composition, not the
    # generic rejection fixture below. State transitions are exercised separately
    # by validate_mechanisms; no interacting enemy movement is claimed here.
    for cid,composition in cm.items():
        if not composition['enabled_current']:continue
        operation_rows=[]
        measured_recovery_extra=0
        if cid=='S06':
            operation_rows.append({'operation_receipt_key':'S06_place_original_tool','anchor':'packing','seconds':0.5,'object_id':'actual_old_tool'})
        for fid in composition['active_model_ids']:
            if fid not in cases:
                need(False,cid,'Missing finite model '+fid);continue
            case=cases[fid];actions={a['id']:a for a in case['actions']}
            scenario=next(s for s in case['scenarios'] if s['kind']=='normal')
            if fid!='F53':
                def trace_cost(branch):
                    model=ContractModel(case,routes);trace=model.begin(branch)
                    for action_id in branch['steps']:
                        response=model.perform(trace,action_id)
                        declared=branch.get('expected_rejections',{}).get(action_id)
                        if not response['accepted'] and response.get('reason')!=declared:
                            raise ValueError(fid+': invalid recovery action '+action_id)
                    return trace.budget
                try:
                    base_cost=trace_cost(scenario)
                    recovery_cost=max((trace_cost(s) for s in case['scenarios'] if s['kind']=='recovery'),default=base_cost)
                    measured_recovery_extra+=max(0,recovery_cost-base_cost)
                except (KeyError,ValueError,TypeError) as exc:
                    need(False,cid,str(exc))
            for aid in scenario['steps']:
                a=actions[aid]
                if fid=='F53' and ('wait_until' in a or a.get('global_event')):
                    break  # Night-long retained stock is a residual commitment.
                if a.get('global_event'):continue
                operation={'operation_receipt_key':fid+':'+aid,'anchor':a['anchor'],'seconds':a['seconds'],
                           'travel_speed':a.get('travel_speed',2.4 if a.get('carry')=='heavy' else 3.0)}
                for key in ('position','end_position'):
                    if key in a:operation[key]=a[key]
                operation_rows.append(operation)
        for eid in composition['event_ids']:
            if cid=='S16' and eid=='E019':
                continue  # F59 already repairs this same damaged component; no second reset.
            # Optional ambient handling is a conservative extra reservation. If the
            # source expires first, the modifier ends rather than being recreated.
            for op in em[eid]['branches'][0].get('operations',[]):
                if op.get('global_event'):continue
                operation_rows.append({'operation_receipt_key':op['id'],'anchor':op['anchor'],'seconds':op['world_seconds']})
        if cid=='S09':operation_rows.append({'operation_receipt_key':'same_carried_N04_dirt','anchor':'goods_shelf','seconds':3})
        route_world={'player_position':routes.anchors['cashier'],'remaining_phase_budget':100,
                     'sources':{s:{'committed':True,'expired':False} for s in composition['required_actual_sources']},
                     'new_primary_this_phase':0,'active_pursuers':0,'slots':{},'inventory':{}}
        route_plan={'enabled':True,'required_sources':composition['required_actual_sources'],'new_primary_count':1,
                    'additional_pursuers':min(1,sum(cases[f]['reservations']['pursuers'] for f in composition['active_model_ids'])),
                    'operations':operation_rows,'already_committed_seconds':3,'recovery_seconds':max(8,measured_recovery_extra),'next_omen_seconds':10}
        measured=admit(route_plan,route_world,routes)
        # A conservative trace exceeding 100 seconds is intentionally not silently
        # admitted. Record the restriction; it must use a shorter current approach,
        # actual retained progress or defer optional handling at runtime.
        composition_routes.append({'id':cid,'model_actions':len(operation_rows),'recovery_reservation_seconds':round(route_plan['recovery_seconds'],6),**measured,
          'if_not_allowed':'必须按当时真实位置/已完成进度重算；仍不够就延期该组合，不添加时间或新源。'})
        need(not any(r.startswith('unmeasurable_operation') for r in measured['reasons']),cid,'Composition contains a nonexistent route/control')

    # Concrete, measurable two-station plan; source and object/slot identities
    # are explicit fixtures. Changing a source never mutates the input world.
    world={'player_position':routes.anchors['cashier'],'remaining_phase_budget':100,
           'sources':{'prepared_order':{'committed':True,'expired':False}},
           'new_primary_this_phase':0,'active_pursuers':0,'slots':{'TRAY_A':{'owner':None},'TRAY_B':{'owner':None}},
           'inventory':{'ORIGINAL_BOX':{'quantity':1,'protected_for':None},'PRESERVED_WATER':{'quantity':2,'protected_for':'F53'}},
           'existing_action_modifiers':{},'low_san_changes_this_action':{}}
    plan={'owner':'CURRENT','required_sources':['prepared_order'],'new_primary_count':1,'additional_pursuers':0,
          'slot_claims':[{'slot_instance_id':'TRAY_A','owner':'CURRENT'}],
          'stock_claims':[{'object_instance_id':'ORIGINAL_BOX','quantity':1}],
          'operations':[{'operation_receipt_key':'same_box_take','object_id':'ORIGINAL_BOX','anchor':'receiving','seconds':0.6,'travel_speed':3},
                        {'operation_receipt_key':'same_box_place','object_id':'ORIGINAL_BOX','anchor':'goods_shelf','seconds':0.6,'travel_speed':2.4}],
          'action_modifiers':{'same_box_place':['facing']},'already_committed_seconds':3,'recovery_seconds':8,'next_omen_seconds':10}
    def probe(pid,p,w,allowed,reason=None):
        result=admit(p,w,routes)
        need(result['allowed']==allowed,pid,'Unexpected admission decision: '+str(result['reasons']))
        need(result['world_unchanged'],pid,'Admission fabricated/consumed real state')
        if reason:need(reason in result['reasons'],pid,'Missing expected rejection reason')
        probes.append({'id':pid,**result})
        return result
    base=probe('measured_existing_two_station_delivery',deepcopy(plan),deepcopy(world),True)
    w=deepcopy(world);w['remaining_phase_budget']=base['measured_plan_seconds']-0.01
    probe('route_budget_one_centisecond_short',deepcopy(plan),w,False,'insufficient_actual_phase_budget')
    w=deepcopy(world);w['sources'].clear();probe('missing_history_does_not_materialize',deepcopy(plan),w,False,'missing_actual_source:prepared_order')
    w=deepcopy(world);w['sources']['prepared_order']['expired']=True;probe('expired_source_not_old_snapshot',deepcopy(plan),w,False,'missing_actual_source:prepared_order')
    w=deepcopy(world);w['new_primary_this_phase']=1;probe('already_spawned_one_primary',deepcopy(plan),w,False,'more_than_one_new_primary')
    w=deepcopy(world);w['active_pursuers']=1;p=deepcopy(plan);p['additional_pursuers']=1;probe('second_pursuer_rejected',p,w,False,'second_active_pursuer')
    p=deepcopy(plan);p['action_modifiers']['same_box_place']+=['distance'];w=deepcopy(world);w['low_san_changes_this_action']['same_box_place']=True
    probe('san_is_the_third_constraint',p,w,False,'more_than_two_constraints:same_box_place')
    p=deepcopy(plan);p['slot_claims'].append({'slot_instance_id':'TRAY_A','owner':'OTHER'})
    probe('two_names_same_physical_slot',p,deepcopy(world),False,'duplicate_physical_slot:TRAY_A')
    p=deepcopy(plan);p['stock_claims']*=2;probe('same_original_box_not_two_units',p,deepcopy(world),False,'insufficient_same_object:ORIGINAL_BOX')
    p=deepcopy(plan);p['stock_claims']=[{'object_instance_id':'PRESERVED_WATER','quantity':1}]
    probe('F36_cannot_consume_F53_preserved_bottle',p,deepcopy(world),False,'other_obligation_reserved_object:PRESERVED_WATER')
    p=deepcopy(plan);p['operations']+=deepcopy(p['operations']);r=probe('same_work_credit_once',p,deepcopy(world),True)
    need(r['unique_operation_count']==2 and r['measured_plan_seconds']==base['measured_plan_seconds'],'same_work_credit_once','Matched work must not double-charge time')
    p=deepcopy(plan);other=deepcopy(p['operations'][0]);other['object_id']='DIFFERENT_BOX';p['operations'].append(other)
    probe('same_label_different_box_not_free',p,deepcopy(world),False,'contradictory_shared_operation:same_box_take')
    w=deepcopy(world);w['closed_doors']=['DOOR_COLD'];r=probe('actual_closed_door_route',deepcopy(plan),w,True)
    need(r['measured_plan_seconds']>=base['measured_plan_seconds'],'closed_door','Blocking a door cannot shorten the actual route')
    for cid,row in cm.items():
        p=deepcopy(plan);p['enabled']=row['enabled_current'];p['required_sources']=row['required_actual_sources']
        w=deepcopy(world);w['sources']={s:{'committed':True,'expired':False} for s in row['required_actual_sources']}
        probe(cid+'_causal_admission_shape',p,w,row['enabled_current'],'archived_or_disabled' if not row['enabled_current'] else None)
        if row['enabled_current']:
            for source in row['required_actual_sources']:
                bad=deepcopy(w);del bad['sources'][source]
                probe(cid+'_remove_'+source,p,bad,False,'missing_actual_source:'+source)
    return {'version':'0.10','status':'PASS' if not errors else 'FAIL','checks':checks,'event_count':72,
            'current_events':sum(e['enabled_current'] for e in em.values()),'composition_catalog':len(cm),'current_compositions':sum(c['enabled_current'] for c in cm.values()),'probes':probes,
            'composition_route_witnesses':composition_routes,'errors':errors,
            'scope':['All 72 authored event branches are checked for explicit source, finite cost/expiry and existing station references.',
                     'Exercises concrete map-measured admission, source removal, same-object/slot conservation, SAN constraint count, phase time and shared-action counterexamples.',
                     'Per-composition source-rejection probes use a shared two-station fixture. Separate route witnesses use each enabled composition\'s actual normal model actions from the cashier and reserve 3 existing-work + max(8, measured recovery deltas) + 10 next-omen seconds.',
                     'Not proof of arbitrary 60×60 combinations, live physics, mobile input, all event effects, or production transaction persistence.']}

if __name__=='__main__':
    report=validate();(ROOT/'docs/events_compositions_validation_v010.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('probes','composition_route_witnesses')},ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['errors']))
