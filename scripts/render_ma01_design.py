from pathlib import Path
import collections
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
FILES=['content/monster_attacks_folklore_ma01.json','content/monster_attacks_scp_ma01.json']
entries=[]
for path in FILES:
    for m in json.loads((ROOT/path).read_text())['monsters']:
        entries.append({'id':m['id'],'name':m['name'],'source':path+'#'+m['id'],'baseline_source':m['source_ref'],
                        'resolution':m['baseline_resolution'],'admission':m['admission'],'basic_attack_id':m['basic_attack_id'],
                        'attack_ids':[a['id'] for a in m['attacks']],'families':sorted({a['family'] for a in m['attacks']}),
                        'child_template_ids':[c['id'] for c in m['child_profiles']]})
index={'version':'MA01','runtime_integrated':False,'baseline_commit':'6445d758b9d1b63afad0afb7d75bc422e0d900a6',
       'total':len(entries),'attack_definition_count':sum(len(e['attack_ids']) for e in entries),
       'contract':'content/attack_contracts_ma01.json','baseline_roster':'content/monster_roster_md01.json',
       'scope':'Attack-only overlays; original identity, HP/defense/base movement, resolution and child budgets remain MD01.',
       'data_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES},
       'entries':entries}
(ROOT/'content/monster_attack_roster_ma01.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'docs/ma01_validation_report.json'
if p.exists():
    r=json.loads(p.read_text())
    stats='结构/引用检查：**{}通过 / {}失败**。独立有限行为样例：**{}通过 / {}失败**。'.format(r['structural_passed'],r['structural_failed'],r['finite_passed'],r['finite_failed'])
    roster='覆盖105原条目、{}个攻击定义、{}个真实子体模板。'.format(r['attack_definition_count'],r['child_template_count'])
    table='\n'.join('| {} | {} |'.format(k,v) for k,v in r['family_counts'].items())
else:
    stats='等待运行MA01检查脚本，不作已通过声明。'
    roster='当前索引覆盖{}条目、{}攻击定义。'.format(index['total'],index['attack_definition_count'])
    table='| 待验证 | — |'
doc="""# MA01：验证结果与适用范围

{stats}

{roster} 其中101条有本体攻击，S27/S32为仅有子体攻击的非战斗源，F47保留自愿竞赛无伤害例外，F14继续停用人类宿主战斗。原三结局分配保持22个机制解锁、45个规则离场、38个完成后削弱。原105怪物数据文件以及塔、陷阱、装备、特殊道具和周经济文件均核对基线Git blob；本轮仅新增攻击层与路由说明。

## 攻击定义分布

| 类型 | 定义数 |
|---|---:|
{table}

同一怪可以有多种攻击，子体模板可复用定义；这些不是新增怪物数或同屏攻击数。

## 验证内容

- 原ID、名称、结局、非战斗源/归档人类宿主、真实子体引用与旧技能映射。
- 攻击时序、几何字段、伤害范围、共享受击保护、控制界限与不重复命中。
- 连续相对扫掠、墙体遮挡、固定射线的有限二维夹具。
- I37实际截止顺延、咒整招一次、I39整次零接触、已发独立残留与actor收招分离。
- 三枚原石唯一身份、0体力操作、真实投线、同帧石击优先、仪式转追逐和冷却。
- 缠绕定身/减速、免费挣脱、遮挡与源失效断线、共享免缠。
- F12/F13三秒基础周期、场景危险预约与原物/电图/奖励边界。

## 审查中实际修正

独立审查发现仪式中断接口缺少now不早于started_at的下界，回放旧函数确认过去时刻也会被接受；已补下界及反例。残留区现与本体动作分离，避免8秒丝线加3秒梳理把怪物锁住11秒；残留仍占危险槽并延后整次闪避判断。石头半径对齐0.1格；自然仪式基准6–8秒与已支付最多3秒延长共用真实截止。

首轮集成结构检查另有112项未通过，来自两侧旧技能映射格式、离场字段名及接触锁定标记不统一；已统一数据格式后再验证。S35初稿误缩短原25.2格车道上限也已恢复。F47依原自愿竞赛保留无伤害准入，避免泛用10SAN占位值成为额外失败处罚。

这些属于本轮设计/参考模型审查修正，不把自动检查通过写成实机验收。

## 未覆盖

没有启用105个运行AI、完整地图导航和层高物理、所有反射/音路、整周随机胜率、手机操作或美术。仪式可达函数只计算已经由地图适配器证明的实际路径时间，不替代寻路。所有新目录仍runtime_integrated=false。

## 复现

在完整仓库依次运行：

1. python3 scripts/check_ma01_reference.py
2. python3 scripts/render_ma01_design.py
3. python3 scripts/check_ma01_design.py
4. python3 scripts/render_ma01_design.py

[原始结构报告](ma01_validation_report.json) · [有限行为报告](ma01_reference_report.json) · [共享合同](../content/attack_contracts_ma01.json)
""".format(stats=stats,roster=roster,table=table)
(ROOT/'docs/79_ma01_validation.md').write_text(doc)
print(json.dumps({'monster_count':index['total'],'attack_definition_count':index['attack_definition_count'],'index':'content/monster_attack_roster_ma01.json'},ensure_ascii=False))
