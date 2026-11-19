#!/usr/bin/env python3
"""Run current design/model gates and retain exact input hashes, without UI claims."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess, json, hashlib, re

ROOT=Path(__file__).resolve().parents[1]
PYTHON=[
 ('validate_content','共享目录、历史条目与文档链接'),
 ('validate_design_v05','60当前卡、120变体与设计约束'),
 ('validate_maps','四场景静态路线与5.0视野比'),
 ('validate_map_mechanics_v05','机制物件、割点、局部窗口与遮线'),
 ('validate_conditions_v06','60独立来源见证及删源负例'),
 ('validate_consistency_v07','实际时限、四条路线、物资、奖励消费者'),
 ('validate_closure_v08','跨阶段来源、固定槽、赠食、有限收益与停用项目'),
 ('validate_integration_v09','原蓝图、正式开关、源码与离线构建一致性'),
 ('validate_mechanisms_v010','60有限模型、实际动作/误操作/自然到期、静态走位与06:00边界'),
 ('validate_auxiliary_v010','64辅助条目、实际消费者读点、期限与有限使用'),
 ('validate_events_compositions_v010','72事件、13当前组合来源、实路预算与冲突拒绝')
]
NODE=[
 ('check_rule_core','SAN、朝向距离、特写与F12/F13'),
 ('check_store_core_v05','营业、电量、订单、证据、店务债、交班防御'),
 ('check_condition_core_v06','实际事故、血迹、终局、并行事务与同刻边界'),
 ('check_admission_core_v07','历史与到场、双时钟截止、局部动作'),
 ('check_reward_core_v07','碎片、双选、退货、预告增时事务'),
 ('check_day_knowledge_core_v08','有限学习、案例来源、同物判定与重复整理'),
 ('check_consumer_core_v08','同物食品、声明奖励、06:00资格与交班、有限短休'),
 ('check_day_cycle_core_v09','24小时资源、日间六格、同物消费、债务和练习副本'),
 ('check_world_core_v09','原地图实际移动、碰撞、有限诱饵、门与生肉追逐'),
 ('check_shift_settlement_core_v09','统一SAN/世界钟、12单、双瓶、当前身体核验与工资账本'),
 ('check_practice_session_v09','两怪完整练习、实际命中、同刻边界、恢复与暂停')
]

def run(entry):
 cmd,scope=entry
 process=subprocess.run(cmd,text=True,capture_output=True,cwd=ROOT)
 try:result=json.loads(process.stdout)
 except json.JSONDecodeError:
  lines=process.stdout.strip().splitlines()
  try:
   result=json.loads(lines[-1]);result['status']='PASS' if process.returncode==0 else 'FAIL'
   result['passed_scenarios']=[line[5:] for line in lines[:-1] if line.startswith('PASS ')]
  except (json.JSONDecodeError,IndexError):result={'raw_output':process.stdout}
 return {'command':' '.join(cmd),'exit_code':process.returncode,'scope':scope,'result':result,'stderr':process.stderr}

def count(d):
 for key in ['checks','scenarioCount','scenarios']:
  if key in d:return len(d[key]) if isinstance(d[key],list) else d[key]
 return None

def main():
 commands=[(['python3',f'scripts/{name}.py']+(['--json'] if name=='validate_auxiliary_v010' else []),scope) for name,scope in PYTHON]+[(['node',f'prototype/{name}.mjs'],scope) for name,scope in NODE]
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(run,commands))
 total=sum(count(x['result']) or 0 for x in results if x['command'].startswith('node '))
 models=next(x['result'] for x in results if 'validate_mechanisms_v010.py' in x['command'])
 report={
  'revision':'0.10','date':'2026-11-19','status':'PASS' if all(x['exit_code']==0 for x in results) else 'FAIL',
  'client_implemented':False,'two_case_practice_source_implemented':True,'browser_rendering_verified':False,
  'mobile_playtest_completed':False,'suite_count':len(results),'existing_headless_scenario_count':total,
  'finite_mechanism_model_count':models.get('model_count',0),'finite_mechanism_counts':models.get('counts',{}),
  'scope':'Current finite lifecycles and sourced design contracts, measured static map routes, explicit expiry/cancellation/collision/budget counterexamples, existing two-monster continuous movement reference. Not 60 live AIs, arbitrary full-state reachability, all combinations, a playable full week, real browser/mobile UI, persistence security or measured fun.',
  'results':results,
  'input_files_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['content','scripts','prototype'] for p in sorted((ROOT/folder).glob('*')) if p.is_file()}
 }
 (ROOT/'docs/validation_v010_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 auxiliary=next(x['result'] for x in results if 'validate_auxiliary_v010.py' in x['command'])
 (ROOT/'docs/auxiliary_validation_v010.json').write_text(json.dumps(auxiliary,ensure_ascii=False,indent=2)+'\n')
 table=['| 命令 | 实际结果 | 实际覆盖 |','| --- | --- | --- |']
 for x in results:
  n=count(x['result']);status='PASS' if x['exit_code']==0 else 'FAIL'
  unit='个场景' if x['command'].startswith('node ') else '项检查'
  label=status+(f'，{n}{unit}' if n is not None else '')
  if 'validate_mechanisms_v010' in x['command']:
   label+=f"，{models.get('model_count',0)}模型/{models.get('counts',{}).get('scenario_traces',0)}条流程"
  table.append(f"| `{x['command']}` | {label} | {x['scope']} |")
  print(json.dumps({'command':x['command'],'result':label,'errors':x['result'].get('errors',[]),'stderr':x['stderr']},ensure_ascii=False))
 doc=ROOT/'docs/09_validation.md';s=doc.read_text()
 s=re.sub(r'(?<=<!-- CURRENT_RESULTS_BEGIN -->).*?(?=<!-- CURRENT_RESULTS_END -->)','\n'+'\n'.join(table)+'\n',s,flags=re.S)
 summary=f"当前{len(results)}组检查：{report['status']}。既有11组无画面参考共{total}个场景，另有60个有限机制模型的{models.get('counts',{}).get('scenario_traces',0)}条完整/补救/替代流程；guard删除和重放次数另列机器报告，不能与完整场景混算，也不能当作手机试玩次数。"
 s=re.sub(r'(?<=<!-- CURRENT_SCENARIO_TOTAL_BEGIN -->).*?(?=<!-- CURRENT_SCENARIO_TOTAL_END -->)','\n'+summary+'\n',s,flags=re.S)
 doc.write_text(s)
 print(json.dumps({'status':report['status'],'suites':len(results),'existing_headless_scenarios':total,'finite_counts':report['finite_mechanism_counts']},ensure_ascii=False))
 return report['status']!='PASS'

if __name__=='__main__':raise SystemExit(main())
