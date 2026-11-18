# V0.7：实际时限、资源用途与状态提交修订

> **历史审计说明：**本文件保留对应轮次的问题与修正记录。当前累计合同以 [V0.8版本边界](00_revision_v08.md)、[第三轮自洽审计](26_third_consistency_audit_v08.md) 和结构化数据为准；文中的旧版本结果不是本轮验证数字。


2026-11-18。本轮沿着用户提出的“条件到底能不能出现”继续检查。第一轮补齐生产来源后，第二轮发现：来源存在仍可能发生得太晚，物资名称相近仍可能不是同一种物品，动作单独成立仍可能在两名员工并行时重复提交。此次修正这些具体问题，不扩展怪物数量。

## 当前阅读顺序

1. [第二轮自洽审计](25_second_consistency_audit_v07.md)：实际问题、修正、流血完整闭环与验证限度。
2. [60卡条件矩阵](24_condition_matrix_v06.md)与[完整交互卡](21_monster_gameplay_v05.md)：当前每卡的来源、动作、截止、收益与退出。
3. [门店机制](20_store_gameplay_v05.md)、[72事件目录](05_events_and_director.md)、[物品装备宠物](04_items_equipment_pets.md)。
4. [验证结果](09_validation.md)：静态检查与有限无画面场景，分别说明覆盖范围。

## 权威顺序

- 用户固定的F12回形针诱离与F13同一登记生肉入柜，仍以[精确蓝图](../content/encounter_blueprints.json)为准；本轮没有修改此文件。
- 当前因果、伤口、库存、动作和交班合同在 [condition_lifecycle_v06.json](../content/condition_lifecycle_v06.json)；实际时限、角色到场与资源用途补充在 [temporal_resource_contract_v07.json](../content/temporal_resource_contract_v07.json)。两者必须一致。
- 当前60卡及120个事件变体读取 [encounters_v05.json](../content/encounters_v05.json)，门店共用机制读取 [store_systems_v05.json](../content/store_systems_v05.json)，事件读取 [events.json](../content/events.json)。这些数据版本已为0.7；文件名保留v05/v06仅为已有链接兼容。
- 辅助物效果消费者以 [auxiliary_targets_v07.json](../content/auxiliary_targets_v07.json) 联合道具、装备、宠物与部署目录为准。存在目录项不表示可获取，存在候选标记不表示客户端已实现。
- [condition_reachability_v06.json](../content/condition_reachability_v06.json)是有限来源依赖模型；V0.7另检实际时间与资源。它们不构成所有随机组合的通关证明。

历史V0.2—V0.6修订、原Claude审查与PR #2保留供追溯，不覆盖当前合同。民俗出处与原型没有在本轮更换；新增数值、动作与奖励都是本作设计。

## 保留的用户共识

00:00—06:00，七夜同样六阶段；通常每小时一个新主遭遇，重大事件替换。60原型、20规则、72事件、120当前变体；四项角色资源、白天学习休息购物、装备宠物与部署；低SAN缩小可见QTE判定并影响视野，不暗改输入。两名员工含主角，另有唯一店长；同事与店长可被冒名。五屏连续门店、前场、后门垃圾箱、家、道具店与资料室保留。

24即时道具、24装备目录保留；I22/I23/Q03暂无有效消费者，暂停新获取，已有实例不删除。当前设计层的道具获取候选为22项；仍需当前构建存在效果处理器与合法消费者才可发放。

## 实现边界

全部60卡仍为 `runtime_enabled=false`，所有当前合同仍标注 `client_implemented=false`；F14继续不进入默认候选。新增的时间准入、有限奖励事务和扩展伤口事务参考不是完整导演或微信客户端。前班交接真实性、物理取物与占手、动态追逐、完整怪物适配、随机分布和手机试玩仍须实现与验证。
