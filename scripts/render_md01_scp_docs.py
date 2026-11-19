#!/usr/bin/env python3
"""Render readable SCP cards directly from authored design data."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LABELS={'kill_unlocked':'解锁击退','rule_leave':'机制离场','rule_weaken':'机制削弱'}
CHILD_LABELS={'kind':'群体方式','max_alive':'同场上限','total_budget':'总出生预算',
 'max_alive_children':'同时存活子体','total_spawn_budget':'当次总出生量',
 'spawn_cooldown_seconds':'生产间隔','spawn_telegraph_seconds':'生产前摇',
 'pool_policy':'生命池归属','terminal_cleanup':'根终态清退','stop_condition':'停止条件',
 'stop_production_condition':'停止生产条件','reward_policy':'奖励归属',
 'inheritance':'继承规则','conservation':'守恒规则','child_stats':'子体属性'}


def text(value):
    if value is None:return '—'
    if isinstance(value,bool):return '是' if value else '否'
    if isinstance(value,list):return '；'.join(text(v) for v in value) if value else '无'
    if isinstance(value,dict):return '；'.join(f'{CHILD_LABELS.get(k,k)}：{text(v)}' for k,v in value.items())
    return str(value)


def cell(value):return text(value).replace('|','\\|').replace('\n',' ')


def render(part, target, title):
    rows=json.loads((ROOT/part).read_text())['monsters']
    counts=Counter(m['resolution']['type'] for m in rows)
    out=[f'# {title}\n',
      '本页由对应JSON直接生成，数字与卡片字段同源。所有条目为本轮新增的SCP店内改编，运行尚未接入；原作特征与本作有限规则须分别理解。来源文章和作者逐条附于卡尾，汇总见[署名表](64_md01_scp_attribution.md)与[内容许可](../SCP_CONTENT_LICENSE.md)。\n',
      f"本片{len(rows)}项：解锁击退{counts['kill_unlocked']}，机制离场{counts['rule_leave']}，机制削弱{counts['rule_weaken']}。", 
      '\nHP是当次战斗载体耐久，物/灵防是减免比例；攻击数值扣玩家SAN，不新增玩家HP。不可攻击的源HP记为—，其子体属性单独列出。动作时间不包含未列的实际搬运路程；长等待须按卡片的工作窗口判定是否允许走动，不能一律当站桩。共享生命、压制/重构、锁血、电图、根奖励见[统一合同](62_md01_combat_lifecycle.md)。\n',
      '| ID／设计名 | 结局 | HP | 物防／灵防 | 体速 | 最早日 |\n|---|---|---:|---|---:|---:|']
    for m in rows:
        a=m['stats']
        out.append(f"| {m['id']} {cell(m['name'])} | {LABELS[m['resolution']['type']]} | {a['hp'] or '—'} | {a['armor']:.0%}/{a['ward']:.0%} | {a['move_speed']:g} | {m['first_day']} |")
    for m in rows:
        a,b=m['stats'],m['post_rule'];mech=m['mechanism'];move=m['movement'];combat=m['combat'];match=m['matchups']
        out += [f"\n## {m['id']} {m['name']}\n",
          f"**{LABELS[m['resolution']['type']]}**。{text(m['resolution']['rationale'])}\n",
          f"**改编边界：**{text(m['adaptation_note'])}\n",
          '| 参数 | 机制前 | 机制后 |\n|---|---|---|',
          f"| HP／性质 | {a['hp'] or '—'}；{cell(combat['hp_meaning'])} | 保留当前HP，不以正确操作回血；离场类直接退出战斗 |",
          f"| 物理减免 | {a['armor']:.0%} | {b['armor']:.0%} |",
          f"| 灵能减免 | {a['ward']:.0%} | {b['ward']:.0%} |",
          f"| 体速（格/秒） | {a['move_speed']:g} | {b['move_speed']:g} |",
          f"| 普攻SAN伤害 | {a['attack_damage']:g} | {b['attack_damage']:g} |",
          f"| 普攻前摇／间隔 | {a['attack_telegraph']:g}秒／{a['attack_cooldown']:g}秒 | 已封技能不再执行；原全局2秒受击保护保留 |",
          f"| 控制类别／压力 | {cell(a['control_class'])}／{m['pressure_cost']} | 最早第{m['first_day']}日成为设计候选 |",
          f"\n**识别线索：**{text(mech['cue'])}\n",
          f"**免费必要用品：**{text(mech['free_tools'])}\n",
          '**主机制动作：**\n']
        for index,step in enumerate(mech['steps'],1):
            execution=''
            if step.get('execution_mode')=='background_mobile_wait':execution='；后台等待，可按原限制移动'
            elif step.get('execution_mode')=='frozen_detail':execution='；原合同允许的冻结世界特写'
            out.append(f"{index}. {text(step['action'])}（{step['seconds']:g}秒；{text(step['anchor'])}{execution}）。")
        out += [f"\n**真实成功条件：**{text(mech['success_condition'])}\n",
          f"**失败恢复：**{text(mech['failure_recovery'])}\n",
          f"**可操作窗口：**{text(mech['work_window'])}\n",
          f"**移动与层级：**{text(move['mode'])}／{text(move['height'])}。{text(move['description'])}\n"]
        if move.get('pursuit_cycle'):
            out.append(f"完整追逐周期：{text(move['pursuit_cycle'])}\n")
        if move['actual_transition']:
            out.append(f"真实转场审计：{text(move.get('phase_audit'))}\n")
        out += [f"**可受击边界：**{text(combat['target_policy'])}\n",
          f"**解前耐久耗尽：**{text(combat['pre_rule_zero_hp'])}\n",
          f"**主机制效果与终态：**{text(combat['rule_completion_effect'])} {text(m['resolution']['terminal_description'])}\n",
          f"**封掉的能力：**{text(b['removed_abilities'])}；**额外效果：**{text(b['added_effects'])}\n",
          '**个性能力：**\n']
        for ability in m['abilities']:
            out.append(f"- **{text(ability.get('name',ability.get('id')))}**：{text(ability.get('trigger'))}。前摇{text(ability.get('telegraph_seconds'))}秒，间隔{text(ability.get('cooldown_seconds'))}秒。{text(ability.get('effect'))} 应对：{text(ability.get('counterplay'))}")
        out.append('\n**分裂／召唤／部件：**\n')
        for k,v in m['children'].items():
            out.append(f'- {CHILD_LABELS.get(k,k)}：{text(v)}')
        out += [f"\n**塔与陷阱：**优势{', '.join(match['favorable']) or '无'}；有条件{', '.join(match['conditional']) or '无'}；弱项{', '.join(match['unfavorable']) or '无'}；陷阱{', '.join(match['traps']) or '无'}。\n",
          f"{text(match['explanation'])}\n",
          f"**奖励：**{text(m['reward']['eligibility'])} 基础12币4灵能，真实主规则资格额外2灵能随根成功结算；子体、压制、重复回执不另结。\n",
          '**来源：**\n']
        for source in m['source_refs']:
            out.append(f"- [{text(source['title'])}]({source['url']})；作者：{text(source.get('author'))}。{text(source.get('author_status',''))}")
    out.append(f'\n完整结构化数据：[对应JSON](../{part})。所有SCP相关改编文本按CC BY-SA 3.0标记，未包含原作图像。\n')
    (ROOT/target).write_text('\n'.join(out))
    print(target,len(rows))


if __name__=='__main__':
    render('content/monster_scp_a_md01.json','docs/59_md01_scp_roster_a.md','MD01：S01–S23新增SCP遭遇')
    render('content/monster_scp_b_md01.json','docs/60_md01_scp_roster_b.md','MD01：S24–S45新增SCP遭遇')
