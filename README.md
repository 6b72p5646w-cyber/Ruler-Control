# 午夜便利店 Ruler Control

面向微信小游戏的2D俯瞰规则怪谈游戏。**当前V0.7：继续修正实际时间窗口、物资种类、奖励用途和并行动作；条件需要真实发生、来得及处理，并能正确结束。**

每晚00:00—06:00，玩家边工作边判断：欢迎语是不是邀请、空座是否有人、湿路把货拖向哪里、叫自己名字的同事能否信任。普通扫码和找零简化；搬运、朝向、距离、取放、封存、声音窗口和门槛保持实际操作。

本仓库包含设计、结构化内容、精确底图与机制补图、静态验证及局部无画面规则参考。**没有可玩微信客户端；60张当前设计卡不等于60个已实现的AI。**

## 当前优先阅读

| 文档 | 内容 |
|---|---|
| [V0.7修订与权威边界](docs/00_revision_v07.md) | 当前合同、保留要求、历史兼容与实现边界 |
| [第二轮自洽审计](docs/25_second_consistency_audit_v07.md) | 不可达店长、短路线、晚接单、奖励消费者、重复提交与完整血源闭环 |
| [第一轮条件审计](docs/23_condition_consistency_v06.md) | 基础来源、证据、资源及06:00结算；与V0.7补充合读 |
| [60卡条件矩阵](docs/24_condition_matrix_v06.md) | 每卡必要来源、提前处理、到期和拒绝终态 |
| [Claude审查回应](docs/19_claude_review_response_v05.md) | 对实际GitHub提案逐项采纳、重做与不采用，附固定提交来源 |
| [门店机制完整设计](docs/20_store_gameplay_v05.md) | 10种机制、六阶段、预兆、应急电、四资源、营业与失败取舍 |
| [60种当前怪物玩法](docs/21_monster_gameplay_v05.md) | 每怪核心禁忌、实际动作、恢复、免费解、两项事件变体 |
| [地图机制补件](docs/22_map_mechanics_v05.md) | 19物件、12位置组、5湿区、2防窗组、6入口档与真实几何限制 |
| [五屏底图与日间地图](docs/13_maps_v04.md) | 连续门店、前场后院、玩家家、道具店、资料室 |
| [F12/F13精确蓝图](docs/11_encounters_v03.md) | 回形针诱离与登记生肉入柜，优先于泛用模板 |
| [验证范围与结果](docs/09_validation.md) | 数据/静态地图/无画面参考分别验证，尚缺客户端和试玩 |

![V0.5门店机制地图](docs/maps/store_mechanics_v05.svg)

## 本轮具体修正

- 真实店长预算700回店，不能满足早期F20/F48变体；改用实际团单／小票机故障，E035只在已到场核验后的6秒可用窗口出现。
- F42的8秒限定为后门内外3格短转运，静态合计7.25秒；后门至垃圾箱往返至少12.5秒，不能放进原窗口。投箱和上架仍须实际完成。
- F27第20秒到场、完整任务90秒，最晚第30秒接受；六类特殊订单共同检查耐心与阶段截止。
- 流血仍由真实玻璃事故产生，90世界秒自然止血，免费敷料3秒包扎；F26到场复查实际血迹，F21事故必须有真实父遭遇及席位。
- F22供物与实际餐份类型对齐；F08维修料明确消耗，F39移除没有消费动作的材料门槛。
- F23／F29改发已有I21／I04各一件；F47三段各3／5／8金币，实际领取才结算。碎片3换1普通券、每夜至多一源；双选不重抽，退货须交回实付原物。
- I22、I23、Q03暂无消费者，暂停新获取；I21只延长F50／F60当前预告，和同类辅助取最大总值。
- 两名员工处理同一物件须对象锁；只计算实际推进的移动，取消与终局释放未提交预留，终态实例不可复活。

## 门店机制与保留决定

- 普通事务压缩，保留持物、背向移动、距离、节拍、开关与封存；每怪一个主要危险、最多三个关键步骤。
- 12格应急储备换额外观察和缓冲。基础冰柜、手动门、必要物件与免费核验不依赖它；四个人体资源精力、SAN、饱腹、体力全部保留。
- 预兆进入世界物件，初见不自动报正确怪名。真实记录也有时刻与视域；监控不能直接看穿伪装，便签署名和印章不自动授予权限。
- 全夜预排6单窗口领取、6单需实际入店。一直窗口可减少部分入店风险但最多6单；A级8单需要承担适量开门风险。少做经营降评级，不再直接判整夜失败。
- 取消全夜三次违规撤班，按怪物自身条件产生局部后果并给恢复动作；店务债最多1张、延续1阶段、本类工资扣款最多20币。
- F12不恢复吃铁成长、啃门或体型导航。F13任务肉不被吃掉，提前入柜可成功，已完成实例不因普通断电复活。
- 五屏地图尺寸和三张日间地图保留；补上真正可操作的位置。后场仍存在宽体无法穿过的窄连接，已显式记录，未假称全部通道有3格宽。

## 持续保留的共识

一周一个周期，七天使用相同阶段；通常每小时一个新主遭遇，有益怪也占名额，重大事件替换。20条逐步解锁店规、72项事件、60种民俗原型；低SAN缩QTE判定与黑视，但不随机改输入。

两个员工含主角，另有店长，同事和店长可能被假扮。白天学习、休息、购物、装备与宠物照料继续存在。24种即时道具、24件装备、8宠物及8部署目录保留（当前22项道具获取候选，另有构建能力门槛）；宠物继续有通用与指定怪作用，不能单独证明身份或自动解除。

初版F14附身候选仍默认关闭。其余59个默认候选也须通过实际功能、已知规则、当前路线与预算门槛；设计完整不等于可以运行时投放。

## 结构化入口

| 文件 | 当前用途 |
|---|---|
| [temporal_resource_contract_v07.json](content/temporal_resource_contract_v07.json) | 实际时限、历史交接、角色到场、局部路线与有限奖励补充 |
| [auxiliary_targets_v07.json](content/auxiliary_targets_v07.json) | 辅助效果的消费者、增时上限与暂停获取项目 |
| [condition_lifecycle_v06.json](content/condition_lifecycle_v06.json) | 当前60卡条件、伤情、物资、时钟、身份与终态合同 |
| [condition_reachability_v06.json](content/condition_reachability_v06.json) | 独立来源依赖模型，附删除来源负例；不是完整通关证明 |
| [store_systems_v05.json](content/store_systems_v05.json) | 门店机制、普通工作、预兆、营业、电量、信息、结算与实现边界 |
| [encounters_v05.json](content/encounters_v05.json) | 当前60怪玩法与120个条件变体 |
| [map_mechanics_v05.json](content/map_mechanics_v05.json) | 精确机制附件、湿区、入口和局部路程 |
| [maps.json](content/maps.json) | 既有四场景底图与42基础锚点；和V0.5补件合用 |
| [monsters.json](content/monsters.json) / [sources.json](content/sources.json) | 原型、来源、候选策略和当前玩法索引 |
| [encounter_blueprints.json](content/encounter_blueprints.json) | F12/F13权威参数、目标切换和原子成功 |
| [balance.json](content/balance.json) / [rules.json](content/rules.json) | 四资源、固定日程、当前评级、20条店规 |
| [interactions.json](content/interactions.json) / [qte.json](content/qte.json) | 基础动作、异常工位特写、SAN/QTE |
| [events.json](content/events.json) | 72事件和当前/历史变体的分别引用 |
| [items.json](content/items.json) / [equipment.json](content/equipment.json) | 道具、抽奖、装备；I06电池用途互斥消费 |
| [pets.json](content/pets.json) / [deployables.json](content/deployables.json) | 通用/专属宠物帮助与有限部署 |

V0.4的[完整旧卡](docs/12_all_encounters_v04.md)和[机制模块](docs/14_systems_and_director_v04.md)作为历史推导与组件参考保留，不能覆盖当前V0.7条件与玩法。Claude的[审查](docs/16_review_rules_maps_v04.md)与[预兆提案](docs/17_omen_system_proposal_v04.md)保留原文；最新[PR #2](https://github.com/6b72p5646w-cyber/Ruler-Control/pull/2)原提案通过固定提交引用，未直接合并。

## 验证与复现

```sh
python3 scripts/validate_content.py
python3 scripts/validate_design_v05.py
python3 scripts/validate_maps.py
python3 scripts/validate_map_mechanics_v05.py
python3 scripts/validate_conditions_v06.py
python3 scripts/validate_consistency_v07.py
node prototype/check_rule_core.mjs
node prototype/check_store_core_v05.mjs
node prototype/check_condition_core_v06.mjs
node prototype/check_admission_core_v07.mjs
node prototype/check_reward_core_v07.mjs
python3 scripts/check_panic_routes_v06.py
python3 scripts/check_temporal_routes_v07.py
python3 scripts/render_encounters.py
python3 scripts/render_condition_matrix.py
python3 scripts/render_maps.py
python3 scripts/render_map_mechanics_v05.py
```

旧内容检查保留历史数据完整性，新检查覆盖当前60卡和店铺机制，另有60个独立条件来源见证及缺源负例。无画面参考覆盖部分合同，不是完整游戏状态机；地图脚本检查静态可达、割点与短窗口，不能证明动态追逐、触控、黑视舒适度、联动平衡或微信性能。详细结果以验证文档为准。

## 系统资料

[固定日夜循环](docs/01_core_loop.md) · [四资源与白天](docs/02_resources_and_daytime.md) · [员工与假扮](docs/03_staff_and_impersonation.md) · [物品装备宠物](docs/04_items_equipment_pets.md) · [事件目录](docs/05_events_and_director.md) · [民俗资料](docs/06_folklore_bestiary.md) · [20条店规](docs/07_rules.md) · [制作顺序](docs/08_implementation_plan.md)
