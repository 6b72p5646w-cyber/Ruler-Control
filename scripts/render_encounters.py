from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
d=json.loads((R/'content/encounters_v05.json').read_text())
store=json.loads((R/'content/store_systems_v05.json').read_text())
contracts={r['id']:r for r in json.loads((R/'content/condition_lifecycle_v06.json').read_text())['encounter_contracts']}
systems={s['id']:s['name'] for s in store['systems']}
lines=['# V0.6：有实际条件来源的60种怪物玩法','',
 '2026-11-18。先定义可操作物件，再让怪物原型改变其条件。当前权威数据为[encounters_v05.json](../content/encounters_v05.json)，共60张设计、120个事件变体；全部客户端开关关闭。', '',
 '普通店务、应急电、四资源、信息可信度与结算以[门店机制](20_store_gameplay_v05.md)为准。地图绑定见[机制补图](22_map_mechanics_v05.md)；[F12/F13详细蓝图](11_encounters_v03.md)保留最高优先级。旧V0.4卡仅供历史推导，不直接混合加载。','',
 '所有禁令、预兆和解法都是本作的游戏改编，民俗原型与资料出处沿用[原型目录](../content/monsters.json)和[资料索引](../references/README.md)。不要求玩家先填对怪名；不把“识别出来”当作自动完成，也不把同类怪强塞进一个终态。','',
 '每张以一个主机制、最多两个辅机制组成。中文完成条件用于审阅，不可通过eval执行；客户端仍需为实际状态和可见反馈编写适配。时段表示可投放阶段，不把热饮、擦地等通用动作锁死到某一小时。','',
 '本轮条件来源、时钟和终态以[条件生命周期](23_condition_consistency_v06.md)、[60卡条件矩阵](24_condition_matrix_v06.md)为准；文件名保留v05仅为现有链接兼容。','',
 '## 快速索引','',
 '| 原型 | 主机制 | 核心实际操作 |','|---|---|---|']
for row in d['encounters']:
    lines.append(f"| {row['id']} {row['name']} | {row['primary_system']} {systems[row['primary_system']]} | {row['critical_action']} |")
lines+=['','## 完整卡片','']
for row in d['encounters']:
    fid=row['id'];mechanisms=[row['primary_system']]+row['secondary_systems']
    lines += [f"### {fid} {row['name']}",'',
        '**机制：** '+'、'.join(k+' '+systems[k] for k in mechanisms)+'。**阶段：** '+'、'.join(row['allowed_phases'])+'。', '',
        '**工作里的问题：** '+row['work_hook'],'',
        '**核心禁忌：** '+row['taboo'],'',
        '**预兆：** '+'；'.join(f"{o['text']}（{o['scale']}）" for o in row['omens'])+'。','',
        '**玩家怎么处理：**','']
    for ix,step in enumerate(row['action_steps'],1):lines.append(f'{ix}. {step}')
    lines += ['', '**完成条件：** '+row['resolution_condition'],'',
        '**取舍：** '+row['pressure_tradeoff'],'',
        '**免费基础解：** '+row['free_solution'],'',
        '**犯错与补救：** '+row['failure_recovery'],'',
        '**事件变体：**','']
    for variant in row['variants']:
        lines.append(f"- {variant['id']} / {variant['event_id']}：{variant['change']} 应对：{variant['counterplay']}")
    contract=contracts[fid]
    lines+=['','**条件从哪里来：** '+'；'.join(contract['requires_before_omen']),'','**提前处理：** '+contract['on_player_prevented'],'','**来源到期：** '+contract['on_source_expired'],'','**拒绝边界：** '+contract['on_refused']]
    timed=[t for t in contract['timers'] if 'seconds' in t]
    if timed:lines+=['','**明确计时：** '+'；'.join(t['id']+'='+str(t['seconds'])+'秒（'+t['clock']+'）' for t in timed)]
    bind=row['map_binding']
    extra=bind['object_ids']+bind['spatial_group_ids']+bind['wet_region_ids']+bind['defense_group_ids']
    lines += ['', '**地图绑定：** 入口 '+bind['entry_profile']+'；基础位 '+ '、'.join(bind['base_anchors'])+'；机制附件 '+('、'.join(extra) if extra else '使用基础物件')+'。', '',
        '**实现边界：** '+row['implementation']['tier']+'；组件 '+ '、'.join(row['implementation']['required_components'])+'。客户端未实现，动态路线与合并预算仍需准入验证。']
    if row['implementation'].get('new_discrete_features'):
        lines.append('新增离散能力：'+'、'.join(row['implementation']['new_discrete_features'])+'。')
    if row.get('admission_note'):lines+=['', '**额外准入：** '+row['admission_note']]
    if not row['candidate_enabled']:lines+=['','**默认候选关闭。** 功能完成前不进入随机怪池。']
    if row.get('canonical_blueprint_file'):lines+=['', '**精确条件不允许被泛用模板覆盖：** [encounter_blueprints.json](../content/encounter_blueprints.json)。']
    lines+=['']
lines+=['## 共同准入与验收','',
 '两个事件变体不是任意同时叠加。先查已实现能力、当前阶段、必要线索、可达物件、出生安全、携带速度、独占岗位和完整时间预算，再比较压力。单项动作最多承受两类限制，低SAN的操作负担一起计入；无法兼容的组合不生成。','',
 '第一切片为F12、F13、F32、F05、F07、F43。现有静态数据和无画面参考只验证其声明边界，不能声称60种AI、动态碰撞、手机触控、黑视舒适度或趣味性已经验收。']
(R/'docs/21_monster_gameplay_v05.md').write_text('\n'.join(lines)+'\n')
print('Rendered current 60-card document')
