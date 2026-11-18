from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
d=json.loads((R/'content/encounters_v05.json').read_text())
store=json.loads((R/'content/store_systems_v05.json').read_text())
contracts={r['id']:r for r in json.loads((R/'content/condition_lifecycle_v06.json').read_text())['encounter_contracts']}
systems={s['id']:s['name'] for s in store['systems']}
lines=['# V0.8：有实际来源、时限与收益闭环的60种怪物玩法','',
 '2026-11-18。先定义可操作物件，再让怪物原型改变其条件。当前权威数据为[encounters_v05.json](../content/encounters_v05.json)，共60张设计、120个事件变体；全部客户端开关关闭。', '',
 '普通店务、应急电、四资源、信息可信度与结算以[门店机制](20_store_gameplay_v05.md)为准。地图绑定见[机制补图](22_map_mechanics_v05.md)；[F12/F13详细蓝图](11_encounters_v03.md)保留最高优先级。旧V0.4卡仅供历史推导，不直接混合加载。','',
 '所有禁令、预兆和解法都是本作的游戏改编，民俗原型与资料出处沿用[原型目录](../content/monsters.json)和[资料索引](../references/README.md)。不要求玩家先填对怪名；不把“识别出来”当作自动完成，也不把同类怪强塞进一个终态。','',
 '每张以一个主机制、最多两个辅机制组成。中文完成条件用于审阅，不可通过eval执行；客户端仍需为实际状态和可见反馈编写适配。时段表示可投放阶段，不把热饮、擦地等通用动作锁死到某一小时。','',
 '当前条件来源、时钟和终态以[第三轮自洽审计](26_third_consistency_audit_v08.md)、[消费者合同](../content/consumer_closure_v08.json)及[60卡条件矩阵](24_condition_matrix_v06.md)为准；第一、二轮审计保留追溯。当前数据版本为0.8，文件名保留v05仅为现有链接兼容。','',
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
    params=row.get('runtime_parameters',{})
    if 'latest_accept_phase_budget_second' in params:
        lines+=['','**接单截止：** 普通到场耐心24世界秒与本阶段预算第'+str(params['latest_accept_phase_budget_second'])+'秒，两者谁先到就关闭未接受报价；接受后须预留完整'+str(params['accepted_special_order_deadline_world_seconds'])+'世界秒，不把接受前耐心再接在执行期后。']
    if 'fixed_gift_item_id' in params:
        lines+=['','**有限实物回报：** 本卡规定的实际交付与退场条件成立后，只能领取来客已声明携带的'+params['fixed_gift_item_id']+' × '+str(params['fixed_gift_quantity'])+'；同一实例只领取一次，背包满时保留原物，不复制或删除。可选领取不阻止遭遇终结；食物所有权本身不等于可食用。']
    if fid=='F29':
        lines+=['','**赠食核验：** 礼物仅为已知目录的完整封装I04。将同一份实际领取的糖放到既有柜台核验槽，安全状态下完成3世界秒动作，核对完整封装与早于赠送的实际供货批次后变为personal_verified；未知、自制或批次不符的食物不适用。没有核验处理器时不承诺可食用奖励。']
    if fid=='F07':
        lines+=['','**计时起点：** 45世界秒从童子实际出现开始；提前挂保留牌属于有效准备，重挂牌和重复出现回调都不重置计时。']
    if fid=='F42':
        lines+=['','**短窗口尺度：** 先在窗口外完成候运；8秒只覆盖后门内外3格的短转运。开门1秒、取物1.5秒、携物3/2.4秒、放下1.5秒、空手返回3/3秒、关门1秒，合计7.25秒。投垃圾或入货架仍需后续实际完成，不能凭跨门回执结清整项工作。']
    if fid=='F47':
        lines+=['','**有限奖励：** 三段各为3、5、8金币，总载荷16币；实际完成并封袋领取才归玩家。E065只给第一份实际兑现附加1碎片，与本夜其他碎片来源共享上限；后两段基础金币保留。数值为待试玩的初始提案。']
    if fid=='F49':
        lines+=['','**冷却计时：** 合盖累计20世界秒；E018在该次冷却开始时若实际生效，只加20秒，共40秒。开盖暂停而不清零，反复开合或事件重发不重复叠加。']
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
