# 午夜便利店 Ruler Control

面向微信小游戏的2D俯瞰规则怪谈经营与生存设计。当前版本为 **V0.3：先完成便利店交互，再把怪物与事件做成动作题**。

本仓库包含设计、结构化内容和一个无画面JavaScript规则参考。客户端、地图导航、画面与微信适配尚未实现；数值与相对开发成本均待原型验证。

## 当前方向

- 一周一个周期，七天共用日夜阶段；夜班固定00:00—06:00，通常每小时一个新主遭遇。
- 先设计取放、搬运、扫码、补货、冷链、清洁、开关和部署；怪物改变工作限制，事件改变路线、对象、设备与参数。
- 低SAN显式缩小QTE判定区并造成黑视，普通按钮、紧急操作、可信HUD和记录保持可用。
- 三种交互尺度：大地图处理走位和追逐；工位面板安排任务；安全特写处理精细操作。追逐中取、撒、搬、入柜不弹QTE。
- F12不可杀伊：默认追玩家，玩家取货架回形针、洒地引出店外获胜。
- F13飞头女鬼：先追任务生肉，触肉后追玩家，玩家搬肉入冰柜解除。
- 员工两人包含主角，另有店长；同事和店长均可被假扮。四资源、白天学习与休息、抽奖和装备继续采用。
- 宠物有普通工作辅助和特定怪物作用；便利店材料组成有限的部署装置，帮助玩家完成工作与规则目标。

## 优先阅读

1. [V0.3修订依据](docs/00_revision_v03.md)
2. [16项店务、三种尺度、SAN/QTE、朝向和距离规则](docs/10_interactions_v03.md)
3. [不可杀伊与飞头女鬼的完整动作和状态机](docs/11_encounters_v03.md)
4. [即时道具、装备、8种宠物及8种店铺部署](docs/04_items_equipment_pets.md)
5. [制作顺序、复杂度与验收](docs/08_implementation_plan.md)

## 保留并更新的完整设计

| 内容 | 文档 |
|---|---|
| 固定日夜循环 | [01_core_loop.md](docs/01_core_loop.md) |
| 精力、SAN、饱腹与体力 | [02_resources_and_daytime.md](docs/02_resources_and_daytime.md) |
| 同事、店长与假扮 | [03_staff_and_impersonation.md](docs/03_staff_and_impersonation.md) |
| 72项随机事件与调度 | [05_events_and_director.md](docs/05_events_and_director.md) |
| 60个志怪候选 | [06_folklore_bestiary.md](docs/06_folklore_bestiary.md) |
| 20条渐进店规 | [07_rules.md](docs/07_rules.md) |
| 验证范围与结果 | [09_validation.md](docs/09_validation.md) |
| 原型及参考资料 | [来源目录](references/README.md) |
| 旧版修订依据 | [V0.2历史记录](docs/00_revision_v02.md) |

V0.1的M01—M60不采用。新的F01—F60是民俗来源支持的候选；F12/F13按V0.3重写，其他58项继续等待店务映射和成本筛选。F14附身作为进阶可选项默认关闭。`enabled_default`只表达完整候选池的意向，运行时还需通过功能实现和可解性门槛，不能据此直接投放59种未开发角色。

## 内容数据

| 文件 | 用途 |
|---|---|
| [interactions.json](content/interactions.json) | 10个动作原语、16项工作、交互尺度和时间约定 |
| [qte.json](content/qte.json) | 3种QTE、SAN分档、缩区与黑视下限 |
| [rule_components.json](content/rule_components.json) | 8种朝向、距离、区域、携带与目标组件 |
| [encounter_blueprints.json](content/encounter_blueprints.json) | F12/F13状态、参数、胜利条件及各3项变体 |
| [event_variants.json](content/event_variants.json) | 12项事件到工作与怪物的变体映射 |
| [deployables.json](content/deployables.json) | B01—B08部署、作用范围、次数和升级取舍 |
| [monsters.json](content/monsters.json) | 60个原型、资料与交互候选 |
| [events.json](content/events.json) | 72项事件、时间预算与实际动作要求 |
| [synergies.json](content/synergies.json) | 18组条件组合，含首轮禁配 |
| [items.json](content/items.json) | 24项临时道具、13项可操作扩展、抽奖与岗位补给 |
| [equipment.json](content/equipment.json) | 6槽24件装备与实际占手 |
| [pets.json](content/pets.json) | 8宠物、通用/专属技能、共用次数与照料 |
| [rules.json](content/rules.json) | 20条店规及解锁 |
| [balance.json](content/balance.json) | 四资源、日程、预算与投放上限 |
| [sources.json](content/sources.json) | 57条民俗资料、2条影视官方资料、1条游戏官方介绍 |

## 无画面规则参考与验证

[rule_core.mjs](prototype/rule_core.mjs)实现一部分纯逻辑：SAN缩区、朝向与距离、特写入场与一次结算、F12诱饵状态、F13任务肉触发和入柜凭证、共享受击保护。它不包含完整游戏循环或美术。

```sh
python3 scripts/validate_content.py
node prototype/check_rule_core.mjs
```

内容检查验证引用与配置约束；逻辑检查覆盖20个边界场景。两者都不等于已经完成地图可解性、手机触控、数值平衡或微信实机测试。

## 决定边界

用户明确的玩法方向已写入修订记录。道具数值、宠物技能细节、设施清单与制作阶段为本轮提案；不标作逐项最终审定。资料记载与游戏原创规则分开列出，外部文章与影视、美术资产不打包复制。
