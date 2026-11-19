#!/usr/bin/env python3
"""Render the MD01 index and full stat table from its three authored slices."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['content/monster_folklore_md01.json', 'content/monster_scp_a_md01.json', 'content/monster_scp_b_md01.json']
LABELS = {'kill_unlocked':'解锁击退','rule_leave':'机制离场','rule_weaken':'机制削弱'}


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def write(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n' if not isinstance(value, str) else value)


def main():
    rows, files = [], {}
    for path in FILES:
        part = json.loads((ROOT/path).read_text())['monsters']
        rows += part
        for m in part:
            files[m['id']] = path
    ids = [m['id'] for m in rows]
    if len(rows) != 105 or len(set(ids)) != 105:
        raise ValueError('expected 105 distinct monster designs')
    counts = Counter(m['resolution']['type'] for m in rows)
    sources = []
    for m in rows:
        if m['origin'] != 'new_scp_adaptation':
            continue
        src = next(s for s in m['source_refs'] if s.get('url','').startswith('https://scp-wiki.wikidot.com/scp-'))
        sources.append({'monster_id':m['id'],'adaptation_name':m['name'], **src,
                        'license':'CC BY-SA 3.0','adaptation_notice':m['adaptation_note'],
                        'derived_content_file':files[m['id']]})
    write('content/scp_attribution_md01.json', {
        'version':'MD01','source_count':len(sources),'consulted_date':'2026-11-19',
        'license':'CC BY-SA 3.0','license_url':'https://creativecommons.org/licenses/by-sa/3.0/',
        'license_notice':'SCP_CONTENT_LICENSE.md','images_included':False,
        'source_author_policy':'按官方Licensing/Citation署名；页面记Unknown Author即如实保留，不猜作者。',
        'sources':sources})
    registry={
        'version':'MD01','runtime_integrated':False,
        'baseline_commit':'835c782a4b786558166791421d9c2df2af2c6bea',
        'status':'complete_individual_design_and_bounded_reference_not_playtested',
        'total':105,'existing_folklore':60,'new_scp_adaptations':45,
        'data_files':FILES,'outcome_counts':dict(counts),
        'id_namespace':'monster:{id}; S01等只在怪物命名空间内使用，既有composition:S01组合保持原义。跨文件必须带文件路径/类型。',
        'contract':'content/monster_contracts_md01.json',
        'lottery_direction':'content/lottery_direction_md01.json',
        'source_attribution':'content/scp_attribution_md01.json',
        'baseline_catalog':'content/monsters.json 保持60民俗来源索引；105设计在本索引三分片，不向旧运行器偷塞新实体。',
        'runtime_admission':'逐怪default_enabled仅为设计候选；运行准入均关闭，需完成世界动作/地图/AI适配后逐项验收。',
        'file_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES},
        'entries':[{'entity_key':'monster:'+m['id'],'id':m['id'],'name':m['name'],
                    'file':files[m['id']],'resolution_type':m['resolution']['type'],
                    'first_day':m['first_day'],'default_enabled':m['default_enabled']} for m in rows]
    }
    write('content/monster_roster_md01.json',registry)
    table=['# MD01：105项完整属性速查\n',
           '数值单位：HP为当次载体耐久；物防/灵防是减免比例；速度为格/世界秒。箭头表示主机制完成后的数值。离场类箭头速度只作数据连续性，真正完成即退出敌对。`—`表示不可攻击，不能把它当0血开场死亡。\n',
           'F01–F60为既有民俗重设计；S01–S45为本轮新增SCP改编。ID带`monster:`命名空间，与旧S系列组合不同。完整动作、条件、能力与对策分别见[民俗](58_md01_folklore_roster.md)、[SCP前23项](59_md01_scp_roster_a.md)、[SCP后22项](60_md01_scp_roster_b.md)。\n',
           '| ID／名称 | 结局 | HP | 物防前→后 | 灵防前→后 | 体速前→后 | 最早日 |\n|---|---|---:|---:|---:|---:|---:|']
    for m in rows:
        a,b=m['stats'],m['post_rule']
        hp=str(a['hp']) if a['hp'] else '—'
        table.append(f"| {m['id']} {cell(m['name'])} | {LABELS[m['resolution']['type']]} | {hp} | {a['armor']:.0%}→{b['armor']:.0%} | {a['ward']:.0%}→{b['ward']:.0%} | {a['move_speed']:g}→{b['move_speed']:g} | {m['first_day']} |")
    table.append('\n**特殊速度要看完整周期。** 真实转场、跳跃、冲刺、驻点与水域条件不能由这张体速表单独推出综合速度。F46显体1.2和旋风4秒驻点分别记录；F10/F54锚定；低空对象不会自动落地给地面路障堵住。首现日只是候选门槛，不保证当天必出。\n')
    write('docs/65_md01_all_stats.md','\n'.join(table))
    credits=['# MD01：45项SCP来源与署名\n',
             '这些是本轮新增的店内改编设计，不是此前仓库已有的45个AI。原作特征从官方页面核对；店内物件、操作窗口、HP、防御、移动周期与塔防交互均为本作改编。没有复制文章照片或SCP-173旧雕塑图像。\n',
             '下列SCP相关改编文本按[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)发布，见[内容许可说明](../SCP_CONTENT_LICENSE.md)。仓库既有程序代码的许可未因此更改。来源署名以官方页的Licensing/Citation为准，Unknown Author照原页记录。\n',
             '| 怪物设计 | 原作／官方链接 | 作者署名 |\n|---|---|---|']
    for s in sources:
        author=s['author'] if isinstance(s['author'],str) else ' / '.join(s['author'])
        credits.append(f"| {s['monster_id']} {cell(s['adaptation_name'])} | [{cell(s['title'])}]({s['url']}) | {cell(author)} |")
    credits.append('\n来源核对日期：2026-11-19。结构化出处与各条改编说明见[署名索引](../content/scp_attribution_md01.json)。官方[Licensing Guide](https://scp-wiki.wikidot.com/licensing-guide)是本轮来源标记依据；本页不声称运行中的游戏或第三方素材已获额外授权。\n')
    write('docs/64_md01_scp_attribution.md','\n'.join(credits))
    overview=f'''# MD01：105项怪物与抽奖机方向

2026-11-19。基线为`835c782a4b786558166791421d9c2df2af2c6bea`。本轮优先完成逐怪设计及规则终态，再明确店内抽奖机方向；未进入美术，未接入完整游戏运行器。

## 本次真正完成的范围

仓库三个分支核对后，原有正式怪物来源记录是60个民俗条目，45项SCP是此前规划。本轮保留60个既有身份与实际店务机制，并新增45项有官方来源的SCP改编，形成105项完整设计目录。**105是设计原型数，不是105个已实现AI，也不是一周必定出现105只。** 普通人类不在怪物奖励名册内，F14仍默认排除。

| 结局类型 | 数量 | 塔防的战术任务 |
|---|---:|---|
| 解锁击退/击杀 | {counts['kill_unlocked']} | 提前削血、压制与铺状态，玩家完成规则后收尾 |
| 完成机制即离场 | {counts['rule_leave']} | 对可攻击显体压制，给真实操作争取时间；完成便结束 |
| 完成机制后削弱 | {counts['rule_weaken']} | 可以硬打；做机制则去防、封技、降速/降攻击，节省布防与跑位压力 |

所有卡都有独立主机制、线索、免费用品、实际步骤/时长、恢复方式、体速/移动模式、HP、物防与灵防、前后能力、塔陷阱适配、首现与压力预算。弱化类不靠把整条HP重置来“变阶段”；锁血类保留玩家已经造成的伤害。

## 阅读入口

| 文件 | 内容 |
|---|---|
| [完整属性速查](65_md01_all_stats.md) | 105项HP、两类防御、体速、三种结局和最早日 |
| [60民俗逐条设计](58_md01_folklore_roster.md) | 保留原物与身份，明确旧规则如何转成离场/解锁/削弱 |
| [S01–S23](59_md01_scp_roster_a.md) / [S24–S45](60_md01_scp_roster_b.md) | 45项新增SCP店内机制、移动、数值、分裂与召唤 |
| [终态与战斗合同](62_md01_combat_lifecycle.md) | 锁血、电链、压制重构、真实伤害、根结算与任务窗口 |
| [抽奖机方向](61_md01_lottery_direction.md) | 一晚一券、个人装备与消耗品、保底、营业关闭、周清边界 |
| [校验与数值结果](63_md01_validation.md) | 逐卡结构、生命状态、有限电图、分裂守恒与发券去重 |
| [SCP来源署名](64_md01_scp_attribution.md) | 45个官方原文链接、作者与本作改编边界 |
| [主索引](../content/monster_roster_md01.json) | 三分片数据入口，`monster:`命名空间与文件哈希 |

## 保留的塔防差异

狙击依然负责短窗口的单点收尾；永久积毒擅长长期压制、锁血前投资和解锁后收尾；广域烧伤提高群体受伤与合作价值；小范围持续伤需要把敌人真实留在可达区；群咒削弱真实攻击并制造失败；电器共振奖励带电独立池与实际通电设备的连通；连续跨区奖励引路；真实瞬移/影跃/镜穿按真实起终点穿过的有效格重复审计并刷新计时，不增加单格倍率。

不能把所有新怪物都改成站地面吃范围：低空、高空、影子、依锚点转移、固定异常源和条件访客分别保留目标/射界/路线限制。纯部件和假象不增加电图人数，真正独立子体才增加。纸偶最多拖1秒；长操作有本怪可见恢复或可取消检查点，不能凭一张纸偶凭空拿到3秒无敌。

## 新群体行为怎样闭环

召唤有公开前摇、冷却、当次总预算与最大同时存在量；关闭源或完成规则可以从生产端降压。真分裂先完成整批伤害再拆，剩余HP、毒q、电荷及来源质量守恒，死亡批次不能靠分裂逃掉。独立子体可让范围挂减益和电链发挥，但钱、灵能、规则额外收益仍按同一个遭遇根只发一次。

各SCP的生殖、造物、感染或不死性只提供灵感。本作有限数量、店内封存、载体耐久和操作秒数是明确改编，不能反向当作原作能力证明；不死设定采用当次显体击退/压制或机制收容。

## 收益和七夜节奏

成功击退与成功机制离场都给同根12币4灵能；真实主规则完成额外2灵能，和根终结一起入账。安全拒绝/超时不发完成奖，子体不发独立奖。TD05的保守152币14灵能、常规176币22灵能、熟练212币34灵能每夜参考不变，只把“击杀数”改为真实“成功根数”，让离场路线也能升级。

塔和陷阱沿TD05七天保留、每周清空；陷阱提前买、每天开班前布置、营业后不能补充。抽奖机每完成一晚正式交班发1张基础券，七晚7张，沿用60/30/10概率和第5/10抽保底；个人装备/券与周布防清理分账，不让抽奖变成营业中补陷阱。

## 验证与下一步边界

运行`python3 scripts/render_md01_roster.py`重建索引/速查/署名，再运行`python3 scripts/check_md01_design.py`。检查并不模拟105个实体的完整AI：规则回执由已验证动作适配器提供，测试只验证它与伤害/离场/奖励相接时的合同。SCP新锚点、完整移动AI、随机整周和手机触控仍需接入后实玩。

本轮的下一步重点是按这份105目录逐条接入及检验实际工位窗口，再敲定抽奖奖池。美术应以已确认的移动/显形/压制/分裂状态为依据，避免先画完再改根本机制。
'''
    write('docs/57_md01_monster_overview.md',overview)
    print(json.dumps({'total':105,'outcomes':dict(counts),'scp_sources':len(sources)},ensure_ascii=False))


if __name__=='__main__':
    main()
