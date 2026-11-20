# BC02：105 条遭遇的原物、来源、动作与终态前置

> 基线：`dfd2e32eecb8fb4dc7dd3efa066cfa3817363788`。本文件覆盖 F01–F60、S01–S45 全部 105 条；不是关闭 93 条以后把剩余少量参考当成完整设计。新权威规格是 [encounter_prerequisites_bc02.json](../content/encounter_prerequisites_bc02.json)。

## 1. 本轮达到的层级

本轮把 105 条逐一写成了可施工的来源、原物、岗位工具、地图模块、动作前提、NPC 响应、时间窗口、失败恢复、奖励和清理规格。亲读范围包括 MD01 的主机制、移动与能力，MA01 的工作窗口与攻击限制，F 系旧 v010 实例的真实 state_sources/actions，BC01 已拼装的实际地图与既有 12 条参考路线。

**设计规格覆盖 105 条，不等于正式客户端的 105 条已可玩。** 本轮新增的模型验证来源事务、依赖边和具体反例；没有凭报告数字宣布实际寻路、触屏、动画、连续攻击与全部新模块的几何通过。

| 层级 | 本轮结果 | 不能由此推出的结论 |
|---|---|---|
| 逐条设计前置 | 105 条，406 个规则动作节点；每条原物、模块、NPC 与有效修订具体记录 | 不代表一个地图里同时摆 105 套设施 |
| 有限检查 | 928 项通过，564 次逐源删除实验 | 不代表 928 次实机胜利或 105 个完整 AI |
| 既有几何参考 | 保留 BC01 的 12 条；本轮没有新增几何通过数 | 其余 93 的模块绑定仍需实际场景证明 |
| 正式运行准入 | 本注册表全部 `runtime_integrated=false`、`client_adapter_ready=false` | 写一份规格不能直接开运行开关 |
| F14 人类宿主模式 | 具体规格补齐，仍独立可选默认关闭 | 真人不得成为塔/陷阱试错靶子 |

验证代码：[bc02_prerequisite_reference.py](../scripts/bc02_prerequisite_reference.py)、[check_bc02_prerequisites.py](../scripts/check_bc02_prerequisites.py)。完整逐项结果：[bc02_prerequisite_report.json](bc02_prerequisite_report.json)。

## 2. 这次真正发现并改掉的断链

| 原断链 | BC02 有效规则 |
|---|---|
| 把所有环境条件都当入场前必须为真 | 区分“当前真源”“已注册生产/消费适配器”“可选分支”“终态输出”。F13 不需先有自己的尸血；F03 呼气由后续玩家动作产生；F30 水只由实际误用产生；S25 无影圈由转板后形成。 |
| F02/F38 核验依赖真实前史，普通交班又要简化 | 开班服务记录实际到岗、领物；此清单不自动生成当前双证。F38 先在 OMEN 核 A，B 实际走入后才提交异常根，8 秒当前链必须不断。 |
| F16 首偷/S26 称重咬痕被写成开场真值 | 先预约原币/原见证物，再实际可见偷取、压板、咬见证条，形成 arrival_effect_receipt，最后 root commit。不得由抽选直接制造历史。 |
| 已付款但没领取的顾客被误当已交付历史 | `paid_pending_claim` 是原物领取权；F19/F25 要读 `delivery_received` 与实际原物归属链，跨夜领取不补旧设备 buff/订单奖。 |
| F21 的 90 秒伤口被默认供给下一场 F26/F32 | 标准恢复35+营业60+预兆20=115秒，不能跨过去。默认仅用当段 BUSINESS 真实 E003 割伤；首兆动态预算，24秒反制例需至少53秒伤口剩余；30秒血迹还要在 commit 活着。 |
| F34 的 6 秒环境休拍混成 2.5 秒冲锋收招 | 环境8秒周期为强拍2+休拍6；去2格+擦2秒+返2格共3.334秒。2.5秒只是怪物收招，不能覆盖这条路线。取/放各按原1.5秒。 |
| F03/F42/F46 等行走被短交互秒数替代或重复计费 | F03 1.85秒已经含3/2.4行走+.6放置；F42完整7.25秒装入8秒低压；F46退1格至少1/3秒，.25秒不够。 |
| S30 的丝危险8秒过期后若物体删除便永远无法收齐 | 两原丝保留同ID，危险失活后变惰性残丝；或同ID回源线轴可夹取，绝不额外生成两条补数。 |
| S25“等目标进入无影圈”没有行为驱动 | 原玩家投影诱导同体沿真实地面路进入；入圈失影后2.5秒停顿，.8秒关罩；不是瞬移到圈。 |
| S27/S32 关源或扶正后直接清掉子体 | 停止未提交出生；活子体实际沿本根召回路返池/返舱，已死者凭真实击退回执闭合；路阻不假装已回收。 |
| S45 原器具在手中却被安全台按钮收走 | 同体攻击落空后真实持械回盘、放下，才开始2.5秒整理窗；玩家分次收原A/B，碎片只有实际产生才要求收。 |
| F53 把战斗解法绑到700–720秒人工交钥匙账本 | 同A/B封签立即战斗削弱；夜结实物快照+真正shift_close持久提交处理可选履约，取消强制人工交班。 |
| 随机抽到哪个大型设施就假设已装哪个 | 班前冻结本夜大模块（最多1件）和兼容小模块清单；只能从实际已装候选池抽。105是跨夜模块库。 |
| 规则解完却没有任何免费伤害可完成根 | 所有kill_unlocked/rule_weaken还要验证实际唯一免费T02的范围、视线、目标高度、完整必要池；锚定体必须有已部署合法射界，不能自动搬玩家塔或强制购买。 |

## 3. 从候选到入侵的事务

1. 班前实际安装本夜模块，保留原塔、陷阱、出口与顾客路线，冻结装配清单。
2. 只有真实已有的原物/库存/历史/环境满足所需分支，导演才选候选并预约它们。
3. 受控配送/到场物允许在 OMEN 按原路线实际送到已有槽；当前踩垫、偷币、咬痕、吞物也必须真的发生。
4. 正常顾客离开危险区；确实参与本题的员工/任务 NPC 在可验证的安全位置。玩家真实放下双手货物，预兆和所有取工具路线按世界钟计费。
5. 重读原物身份、所有权、模块清单、活源寿命、剩余窗口、手数、视线/碰撞/实际路径。通过才以稳定 logical_root_id 一次提交根。
6. 失败的前置事务释放预约；已交付的原物保留实际当前位置并挂隔离/回收工单，不能远程消失或恢复成新库存。未提交根不发成功奖励。

`immutable_prior_receipt` 不可由本次选择补造；`arrival_effect_receipt` 仅由本次预约之后真实可见动作生产。普通加载恢复同一原物与绝对世界期限；attempt_id 只隔离消息包，不能改变订单/怪根/奖励身份。

### 3.1 条件注册不等于条件已发生

每条 `environment_bindings` 分别声明 `condition_must_be_true_at_admission`。例如必须活着的伤口是入场真源；“能根据当前人/光/遮挡计算直视”是能力注册，不要求玩家先直视怪物；F13 尸血只是终态生产；F60 镜观光照是可选分支。每次使用技能或机制动作，仍需重新读当前源，不能拿开场能力注册代替当下条件。

### 3.2 工具和原物

每条 `original_objects` 是明列数量、原ID、来源与岗位的清单。列表一行可能包含多个相关成员，运行适配器必须逐个展开，不能把一行文字替换成任意一枚占位物就声称齐备。`free_tools.module_ref_nonpositional` 只引用该卡模块，不是一个伪造的工具坐标；要按原物清单、真实供应目录和实际槽位分别绑定。

可重用岗位工具取消后保留，掉落后拿回同件；有限食品/水/封袋/维修份额在接受前实点、真实消耗一次，不因重试/广告补满。关键任务原物不能用另一件类似物代替。仅非原物的可重用辅助工具因适配错误变不可达时，可在安全期由真实服务注销旧实例并登记一个关联替代件，无收入/售卖/兑换。

### 3.3 人、付款与奖励

正常顾客必须同时具有 NORMAL_CUSTOMER 身份、普通订单实际付款、设备实际使用回执，才产生营业支援。假扮员工、非人来客、帮手、被附身真人、子体及异常订单都不能冒用此身份。真实员工始终不入塔目标；怪物须有合法敌对/暴露证据。

必要怪物规则动作可以出现在入侵中，因为它们直接处理本根危险；补货、普通收银、卸货、常规清洁和普通设备维护则冻结到安全期。怪物借用已有工单完成一项工作，普通收入仍只记原 job_id 一次；原物归还、退款、回收失币不当新收入。

规则离场要实际收容、领取、退场等终态；kill_unlocked/rule_weaken 还需全部必要活池真实HP归零，不能把最后一个主规则按钮当补刀。子体、压制、分裂、工具补发均无独立根币。F17/S40/S43 等领取/退场保护沿既有有界同根回应，保HP与永久毒，不给玩家无敌、不重置期限。

## 4. Codex 分批施工依赖

| 批次 | 数量/卡 | 核心依赖 | 要交付的实际能力 |
|---|---|---|
| `P0_existing_geometry` | 12：F01, F05, F12, F13, F17, F60, S09, S29, S34, S38, S40, S43 | transaction_identity, environment, same_root_response, actual_navigation | 已有12几何参考转正式客户端；11主动+1无奖被动。 |
| `P1_order_and_offer` | 11：F04, F06, F09, F11, F20, F27, F29, F44, F47, F48, F55 | transaction_identity, order_ledger, NPC_transfer, actual_navigation | 物理食品/商品供应、定时服务、异常来客与正常支付拆开。 |
| `P1_history_identity` | 12：F02, F16, F18, F19, F23, F25, F37, F38, F41, F43, F45, F51 | immutable_work_history, cross_night_sale_ledger, current_body_evidence, same_root_response | 先真实发生历史，再抽对应怪；当前核验不由开班自动给真。 |
| `P1_environment_routes` | 11：F10, F24, F28, F34, F40, F52, F56, F57, S22, S23, S25 | environment, condition_TTL, phase_revalidation, actual_navigation | 水源/干边/影节点/实际反射/通道模块与安全侧控制。 |
| `P1_work_orders` | 12：F07, F08, F21, F22, F31, F35, F36, F39, F49, F53, F58, F59 | real_jobs, staff_safe_staging, pause_clock, shift_close_ledger | 真实杂务来源与根机制分账；任务保护窗口内可做必要规则动作。 |
| `P1_timed_originals` | 10：F03, F15, F26, F30, F32, F33, F42, F46, F50, F54 | hands_and_carry, source_transactions, world_timers, timed_route_proof | 原物搬运、不可刷新窗口、活伤/活迹生成约束与有界失误恢复。 |
| `P1_containment` | 10：S01, S02, S03, S06, S07, S13, S31, S32, S35, S39 | reserved_large_module, actual_navigation, NPC_transfer, finite_children | 固定笼/槽/车道/门/脚圈原位安装，实体真实进场/收容/返舱。 |
| `P1_side_workstations` | 17：S04, S05, S10, S11, S12, S19, S20, S21, S24, S26, S30, S33, S36, S37, S42, S44, S45 | reserved_counter_modules, physical_evidence, source_transactions, same_root_response | 工具/证据/黏液/原丝/武器实际收回；安全侧工位与当前实体对应。 |
| `P1_finite_lineages` | 9：S08, S14, S15, S16, S17, S18, S27, S28, S41 | finite_children, material_identity, group_attack_reservations, condition_cleanup | 有限原料/卵/源口/成对与群体池，已死编号可闭合，绝不要求重生。 |
| `P2_host_opt_in` | 1：F14 | verified_human_host, three_slot_shadow_module, no_human_damage | 独立验证的人类宿主保护模式；默认禁用保留。 |

每一批的完成定义都包含：真实对象/槽位绑定、身体可达路线、实际手部取放、剩余时间准入、NPC 物理回应、正常/错误/取消/断电/保存恢复/最终结算场景。不能只把 `admitted` 改成 true。大型模块在整周已部署防御上没有合法空间，就保持该夜不准入，并让其他合格候选替换；这不否认其跨夜模块设计存在。

## 5. 全 105 条逐项审计

以下逐条列出原始机制、具体来源与装配要求。完整机器可读 requires/produces、原源引用、手数和终态在 JSON 中；旧 v010 示例根值仅供阅读，运行时必须使用 `$logical_root_id` 和真实 `$source_bindings`。

### F01 狐精

- **模块/结局**：`inspection` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：可见异常送货者把同箱两件原货送到receiving，签收只代表实物到场，不代表验真/付款。
- **原物与供应**：箱1+真饮料1+幻货1@receiving，由同批到货清单绑定；幻货永不可售；秤1@receiving、量杯1与双分拣槽@packing，雇主常备
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：原箱放秤离手；receiving→packing真实重搬；透明量杯两槽不能被其他工单占用。
- **主步骤**：weigh：放箱离手称重 [2秒原值] → measure：在打包台对照两件实际容量 [3秒原值] → sort：分入已验货槽和封闭退回槽 [2秒原值]
- **NPC/世界回应**：同一送货者在验收线外等待；退整箱要实际取回；分拣后只注册一个敌池。
- **有效修订/恢复**：留已分拣实物，错架只隔离同箱；真实销售另走普通库存，不把异常交货当正常顾客支付。
- **终态**：同一原箱经离手称重和容量复核，两件原货各在已验真货槽/封闭幻货退回槽，误上架限制已清。整箱未验退回是安全撤销，不提交主规则奖励。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/0/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/0/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/0)

### F02 画皮鬼

- **模块/结局**：`identity` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同一假扮体从公开入口到核验位；独立员工记录在抽选之前生成。
- **原物与供应**：原围裙1+原钥匙1@员工权限槽，雇主财产；手压侧灯1@verification_desk；同一claimant_id，不复用COWORKER身份
- **不能补造的前史**：SHIFT_STAFF_CHECKIN：真实员工在开班服务中实际到岗、领取围裙/钥匙登记；CURRENT_HANDOVER_RECORD：本班真实授权/领物事件覆盖请求时刻
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：侧灯/读记录/封权限都在员工边界内；公开回收槽与不穿员工区的10秒内退出路须实算。
- **主步骤**：observe_edges：手压侧灯观察双皮缘 [2秒原值] → check_record：核对已经发生的公开交接和当前身体 [2秒原值] → secure_and_depart：锁妥交接物并目送未授权者走出公开出口 [10秒原值]
- **NPC/世界回应**：访客默认无员工权限；误递围裙后同体放到回收槽，玩家取回；限权后真正沿出口走出。
- **有效修订/恢复**：简化交班由实际开班服务产生清单，不能自动生成当前双证核验；证据不足只安全撤销，不刷主解奖励。
- **终态**：本次双皮缘与独立当前交接证据均核实，原围裙/钥匙未交未授权者或已实际收回，高风险授权已撤，异常的本次索权终止。仅证据不足的保守限权为安全撤销。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/1/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/1/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/1)

### F03 僵尸

- **模块/结局**：`short_cargo_lane` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实送货单两件原货预摆到短口起点；实体到场不等于已经吐气。
- **原物与供应**：cargo_a+ cargo_b@goods_shelf，同一delivery_id的两个单位；三格暴露短口、两侧固体遮挡与两个目标槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：目标槽与取货槽间最多3格；可在短口外留雾点，锁定落区不得与跨口扫掠体相交；空返另走。
- **主步骤**：take_a：取第一件登记货物 [0.6秒原值] → leave_breath：在远离目标槽的暴露格留一次真实吐气 [0.5秒原值] → wait_landing：在真实遮挡侧等下一个已锁远离短口的跳跃窗口 [0秒原值] → carry_a：在2秒停顿中步行越过3格短口并放第一件 [1.85秒原值] → wait_return：在真实遮挡侧等下一个已锁远离短口的跳跃窗口 [0秒原值] → return_crossing：空手沿同一短口走回取货侧 [1秒原值] → take_b：回货位取第二件 [0.6秒原值] → wait_landing_2：在真实遮挡侧等下一个已锁远离短口的跳跃窗口 [0秒原值] → carry_b：等停顿后分段搬第二件 [1.85秒原值] → withdraw_and_dissipate：退遮挡线让最后雾点自然失效 [6秒原值]
- **NPC/世界回应**：只追真实6秒呼气点；不存在雾点则正常追逐，不能导演注入breath_seen。
- **有效修订/恢复**：采用MA01 2秒预告；跨口1.85秒已含3/2.4行走+0.6放置，不能再重复加路程；两件分别一窗，末雾自然过期。
- **终态**：两件真实运输货均到预留槽，玩家已退真实遮挡线且最后雾点自然过6秒；未接加运的封存退回只取消邀请。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/2/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/2/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/2)

### F04 鲛人

- **模块/结局**：`counter_delivery` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：来客真实交付运输湿盘和唯一湿纱；雇主保湿盘与一份应急水先预约。
- **原物与供应**：湿纱1@receiving运输盘；有盖保湿盘1@ sink；应急清水1份与量尺1@packing
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：sink灌水→receiving转纱→packing同台量尺合盖→寄售槽；20秒暴露只在离水且世界运行累计。
- **主步骤**：fill_tray：领取并给工作盘加一份水 [2秒原值] → take_fiber：从来客盘转移同一湿纱 [1秒原值] → measure_close：对齐量尺并将湿纱放回盘合盖 [3秒原值] → deliver：端封盘到寄售槽交付 [1.5秒原值]
- **NPC/世界回应**：同体量纱时护幕忙碌3秒不攻击；交付同盘后领取/收容位验物再离场。
- **有效修订/恢复**：原盘水可复湿2秒，不反复消耗新水；无供水仍使用实际预留应急水。
- **终态**：同一湿纱已量尺确认，回原保湿盘合盖并实际交寄售槽；主动退回原纱安全撤销，不算寄售成功。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/3/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/3/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/3)

### F05 河童

- **模块/结局**：`wet_route` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：既有收货篮停放回执与cold_branch实际漏水产生连通图；怪物抽选不生成篮或水。
- **原物与供应**：原篮1@湿侧登记槽；干布1@ mop_station；独立cold_branch手阀、干侧擦点、干槽
- **不能补造的前史**：BASKET_PARKED：真实原篮已由收货/上货放到[23.5,12.5]
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：采用BC01 [24.5,11.5]干侧擦割点与[25.5,11.5]放篮槽；取放身体不可进入水中；rear_source独立。
- **主步骤**：take_cloth：从清洁位实际取一条常备干布 [1秒原值] → close_valve：关已登记冷区水阀 [0.5秒原值] → wipe_cut：站干侧擦断24,10割点 [2秒原值] → take_basket：从干侧拿回同一篮 [0.6秒原值] → place_dry：将原篮放干侧接收格 [0.6秒原值] → confirm_disconnect：等一次5Hz世界更新核实断连 [0.2秒原值]
- **NPC/世界回应**：牵引只沿同源湿边；断边后实体按当前合法位置转普通追逐，不把篮或本体传送。
- **有效修订/恢复**：关阀.5+擦2+取.6+放.6+真实步行+5Hz核对；普通顾客水渍不是本根水源。
- **终态**：免费路径实际关阀0.5秒、在[24.5,11.5]擦断割点2秒、干侧取原篮0.6秒并搬到[25.5,11.5]放0.6秒，经0.2秒确认。最终判断是原篮已干且无篮—源连接；若真实B07提供临时断边也可搬出完成，不强加阀永远关闭。 本卡关闭的明确是water_valve工位cold_branch，不是F57的rear_source。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/4/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/4/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/4)

### F06 雪女

- **模块/结局**：`order_service` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：预留一个尚未执行的异常热饮订单名额，来客实际出示纸单后根提交；不伪装正常付费顾客。
- **原物与供应**：同order_id纸票1@cashier；热饮配额2份@hot_food（首杯+最多一次重做）；隔线自提槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：柜台→热食→自提槽全程按3格/秒及持杯速度实算，接受后45秒不刷新；免费手动保温制作可在停电时完成。
- **主步骤**：accept_mute_paper：接受订单、关闭广播并取同号纸票 [1.5秒原值] → make_cup：用一份额度制作并封好热饮 [3秒原值] → deliver：在2.5格外实际放热饮和同单纸票 [2秒原值]
- **NPC/世界回应**：接受后3秒制作服务停攻；客人离玩家≥2.5格，从原槽拿同号杯；冻普通电器不冻任务设备。
- **有效修订/恢复**：冷杯先报损才用第二份；材料不足/剩余路程超过45秒则不接受本题，不补杯不造债。
- **终态**：同一订单的真实热饮与同号纸票已实际放入同一交付槽；广播未继续泄露本单，已误播的当前薄霜按原恢复动作清除。拒单/退单不计成功。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/5/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/5/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/5)

### F07 座敷童子

- **模块/结局**：`reserved_seat` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实椅垫到场下陷与已存在的浏览客任务；先将普通客安置在公共安全等候线。
- **原物与供应**：固定椅1+保留牌1；独立第二等候格1；可选零食只从SUP_SNACK实际库存取
- **不能补造的前史**：BROWSING_CUSTOMER_PRESENT：已有同一普通客，无新订单克隆
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：第一/第二候客位互不堵出口；45秒从异常到场世界时间起算；引导真实客必须在OMEN或安全服务窗完成。
- **主步骤**：hang_sign：移开椅上普通货并挂保留牌 [1.5秒原值] → redirect：实际将原浏览客引向第二等候格 [1.5秒原值] → watch_window：在处理别处工作时等本次45秒保护期结束 [45秒原值] → quiet_depart：观察椅垫回弹并收回保留牌 [1秒原值]
- **NPC/世界回应**：原顾客实际改走第二等候位或取消后离店；进入RAID前其离开危险区并被冻结普通订单期限；椅灵每9秒坐回3秒。
- **有效修订/恢复**：普通顾客的真实付款只归自己的正常order_id；根的引导/守椅回执不生成设备buff；45秒无人坐也不强迫补一次占椅。
- **终态**：本轮45世界秒内保留椅位按原恢复规则保持空闲，原顾客已引至真实第二等候格或取消本单，45秒结束且椅垫回弹，收牌只结一次。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/6/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/6/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/6)

### F08 付丧神

- **模块/结局**：`repair_retire` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：已有实际老旧工具离电仍敲击，放入维修盘；导演不能先写玩家曾损坏。
- **原物与供应**：旧可拆工具1@repair_tray；退役槽1（始终免费）；可选修补片1仅有库存才预约
- **不能补造的前史**：TOOL_DEFECT_RECEIPT：旧工具实点/磨损检验记录
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：packing维修盘和退役槽在同一隔台；混垃圾恢复取回1秒、放盘1秒，原工具不销毁。
- **主步骤**：locate_crack：离电后按敲击找裂位 [2秒原值] → repair_test：贴一份修补片并试作一次 [3秒原值]
- **NPC/世界回应**：工具显化共享原物根；修好或退役封残响，之后解死亡锁仍须真实击退。
- **有效修订/恢复**：基础主解改明确包含零材料retire分支；缺修补片不阻免费主解；退役不售卖、不刷修补物资。
- **终态**：同一原工具按真实裂纹修好，或已从混合垃圾实际搬到退役槽。原工具合法安置切掉敲击残响锚，不要求抽到修补道具。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/7/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/7/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/7)

### F09 轆轤首

- **模块/结局**：`order_service` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：异常长颈客身体持唯一篮进场，替换一个基础订单名额；身体和头不是两名顾客。
- **原物与供应**：同体篮1+纸号1；同订单商品2（E009批准时3）@goods_shelf；已预约结账位
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：身体浏览位→柜台真实路至少按2.4速度计算，不能用固定8秒覆盖更长路线；70秒含玩家取货搬放与NPC走路。
- **主步骤**：tag_accept：给身体篮挂号并接受同一单 [1秒原值] → take_goods：拿齐两件已登记商品 [2秒原值] → put_basket：避开颈线把商品放入同一身体篮 [1.5秒原值] → wait_body：沿可见队列等身体走到柜台 [8秒原值] → checkout：身体到柜台后同一篮结账一次 [1.5秒原值]
- **NPC/世界回应**：身体按实际队列到柜台，持续服务安全窗至少1.5秒；头只作共享部件，不独立付款、奖励或电节点。
- **有效修订/恢复**：真实订单记店内账一次但actor_class=anomalous_visitor，不产生普通顾客设备支援。
- **终态**：同一身体篮装齐本单两件（已获准E009变体三件）原商品，并实际到柜台完成一次1.5秒收银；头身只计一个顾客和一单。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/8/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/8/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/8)

### F10 海坊主

- **模块/结局**：`rear_window` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：本班已有真实故障/险情处理回执，来客在预装后窗显现一档本根异常水。
- **原物与供应**：原问题回执1@cashier证据副联；干布1@mop_station；ATT12服务缝+本地排水杆
- **不能补造的前史**：FAULT_HANDLED_RECEIPT：同班真实问题处理完成且可追溯原物
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：后窗服务缝不等于逃生后门；读票6秒内排水1+关窗1均在相邻干侧。
- **主步骤**：take_cloth：从清洁位实际取一条常备干布 [1秒原值] → lay_cloth：在窗下铺同一干布 [2秒原值] → present_receipt：夹上本班真实处理回执 [0.5秒原值] → drain：在相邻拉杆排空本实例局部水位 [1秒原值] → close_window：回服务缝关窗封住吸水布 [1秒原值]
- **NPC/世界回应**：同根巨影读原票暂停涨水6秒；本地三档水只由此root管理，实体不进员工区。
- **有效修订/恢复**：引用损坏安全取消不补历史；移除只清本根水位，不清其他水源。
- **终态**：同一真实问题回执已呈本窗，ATT12局部杆将本实例三档水位降至0并关小窗；不清除其他根怪独立水源。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/9/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/9/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/9)

### F11 韩国鬼怪

- **模块/结局**：`challenge_ring` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：来客携带有限邀请及原I21奖品到前场，免费食品分支有真实荞麦份才准入。
- **原物与供应**：荞麦份1@hot_food；比赛圈1@forecourt_handoff；来客原I21×1放独立领取盘
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：圈外交食位与退出线明确；选择12秒比赛须25体力且没有其他追逐；基础食品路径零体力可做。
- **主步骤**：take_food：取一份荞麦食品并封装 [2秒原值] → give_food：把同一份食品放圈边交换盘 [1秒原值]
- **NPC/世界回应**：实际吃下原份后离场；比赛两轮真实完成才胜出；赠品可留盘，不因背包满卡根。
- **有效修订/恢复**：比赛只一次，失败仍能交食/撤销；原奖品领取键独立且不额外产生重复根奖励。
- **终态**：本次受约的两轮比赛确实完成，或原预留荞麦份已实际交到圈边盘；独立I21奖品可稍后取，背包满不阻离场。未接受即拒绝不计成功。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/10/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/10/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/10)

### F12 不可杀伊

- **模块/结局**：`bait_lane` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：雇主金属岗位实际配备6次原盒与唯一6次备用盒，原实体在5格外入场。
- **原物与供应**：纸夹主盒6+备用盒6@metal_shelf；合法真实地面撒点
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：继承BC01 safe_counter与实际spawn距离≥5；撒点不在墙/任务槽/顾客身下，食点路线要通。
- **主步骤**：take_clips：从原货架取一盒6次回形针 [1秒原值] → scatter1：在第1个真实地面点手撒 [0.25秒原值] → wait_node1：观察它到第1点并停食1.5秒 [3.7秒原值]
- **NPC/世界回应**：真实抵达撒点后连续1.5秒吃完首次永久破壳，后续只停食；不瞬移吃纸夹。
- **有效修订/恢复**：一夜两盒用完无无限补；主解需仅首次一份，剩余可失误；已吃原诱饵销账，未吃可原位回收但不产币。
- **终态**：同一实例第一次实际消耗原纸夹并完成1.5秒停食，立即永久破壳；以后纸夹只提供各自停食窗。引至门外不自动获得击退奖励。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/11/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/11/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/11)

### F13 飞头女鬼

- **模块/结局**：`meat_delivery` / `kill_unlocked`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：雇主真实任务库存的唯一登记生肉箱与有效主冰柜先预约，肉与普通冷冻商品分隔。
- **原物与供应**：任务肉箱1@warehouse_meat；freezer_main独立任务容积与机械门
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：实际路径20格/2.6≈7.69秒，加取.6合柜.6；两手任务槽不能同时拿石/工具；断电保任务冷链封闭与手动门。
- **主步骤**：take_meat：用双手任务槽取原肉箱 [0.6秒原值] → store_close：同一肉在有效冰柜1格内入柜关门 [0.6秒原值]
- **NPC/世界回应**：初始追原肉；真实触肉才狂怒1.5秒；入柜关门原子提交先于同帧旧攻击。
- **有效修订/恢复**：松手同肉留合法槽，怒态不重置；封肉永久，开门/断电不重开死亡锁；尸血仅清洁，不作为活人伤口。
- **终态**：本实例同一登记肉在合法有效柜1格内完成0.6秒存入并关门原子提交；永久封高飞/吸食恢复并解锁本投影的终结，不因再开柜/断电恢复。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/12/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/12/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/12)

### F14 饕食附身灵

- **模块/结局**：`host_separation` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：默认禁用的独立附身模块；已核验同事自愿转餐桌，当前原影附着不改人类身份。
- **原物与供应**：测试餐2份（独立SUP_MEAL）；透明封盒1；同台三个影引槽+原封条秤
- **不能补造的前史**：REAL_COWORKER_AT_WORK：同一真实员工在场；HOST_PAUSED_FOOD_DUTY：实际暂停岗位并到餐桌
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：同台三槽均可观察、长夹安全操作；真人停安全区与塔射界隔离；封盒至门外隔离槽真实搬运。
- **主步骤**：pause_observe：暂停食品岗并对照两盒封条与重量 [3秒原值] → move_slot1：把带影原盒移动到同台第二槽 [2秒原值] → move_slot2：把同盒移到第三槽等影手完全入盒 [2秒原值] → close_box：影完全入盒后实际合盖 [0.6秒原值] → send_box：携原封盒送到门外隔离槽 [1秒原值]
- **NPC/世界回应**：真人从不敌对/不受塔弹；原影按同盒实物换槽，完全入盒才能合盖；原员工恢复原权限。
- **有效修订/恢复**：独立开关继续默认false；不能以默认禁用代替设计，仍需宿主引用/双证/三槽/出口组件集成后独立验收。
- **终态**：同一影子实际封入登记盒并送出，真人留店；恢复其原有权限范围，再按当前可用岗位安排，不瞬移回已被占用工位。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/13/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/13/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/13)

### F15 蓬蒂雅娜

- **模块/结局**：`sequence_kit` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：来客带一套原灯箱/布/铃盒/专用电池，装置演示是内容示范，不是本店过去事件。
- **原物与供应**：同kit_id灯箱1+布1+铃盒1+任务电池1@packing
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：同台实际灯槽、布槽、铃盒与两个已登记真转场端点；端点避开玩家、墙和出口。
- **主步骤**：demo_lamp：看两段短演示并实际点灯 [2秒原值] → cover：把同一布盖到影子指出的槽 [1秒原值] → close_bell：盖布到位后合铃盒 [0.5秒原值] → stable_return：真实稳定3秒后交回原装置 [3秒原值]
- **NPC/世界回应**：错序只当前铃盒重开；稳定3秒期间能移动，完成后同体取回原套件。
- **有效修订/恢复**：任务电池不进入电器buff或电图，断电可完成；演示重播不写动作回执。
- **终态**：同一装置已真实点灯、盖布在正确原槽、合铃并连续稳定3世界秒；退回未操作装置只安全取消。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/14/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/14/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/14)

### F16 图尤尔

- **模块/结局**：`coin_trace` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：开放零钱盘产生一次可见实偷回执后才有怪；预留原盘3枚与出口回收槽。
- **原物与供应**：原盘币共3枚；不可兑换显色币1@cashier；固定出口收集槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：TILL_TRANSFER_RECEIPT：本实例真实转移第一枚店铺币，私人钱包不扣
- **物理绑定**：封盘→三实际显色节点→出口拾取→原盘归还均是实体路径；不是点击灰印自动取币。
- **主步骤**：seal_till：封好原零钱袋停止新偷取 [1秒原值] → place_test_coin：把单枚显色币放桌边 [0.5秒原值] → trace1：跟第一处实际底层显色印 [0.5秒原值] → trace2：跟第二处显色印 [0.5秒原值] → trace3：沿最后显色印确认出口收集槽 [0.5秒原值] → recover_coins：取回同批失币与测试币 [1秒原值] → bag_return：把失币归原袋、测试币回工具槽 [1秒原值]
- **NPC/世界回应**：同根最多转移3枚，每枚只一次恢复；测试币实际滚动才产轨迹；盘封后不可继续偷。
- **有效修订/恢复**：中止时已偷币留可达回收槽，管理员实际回收；回币是恢复店存款，绝不能记新收入/广告翻倍。 首偷是预兆物化中本体的可见实际操作，属于arrival_effect_receipt；抽选前只预约开盘与原3币，不能把首偷伪造为旧历史。物化后取消需同币实际退回/追踪至恢复工单。
- **终态**：实际盘封闭、同事故所有1—3枚失币回原袋、不可兑换测试币回工具槽；首偷前封盘直接预防，不要求做三次转移。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/15/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/15/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/15)

### F17 裹尸鬼

- **模块/结局**：`parcel_take` / `rule_leave`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：同一来客交三结原包裹于BC01原公共槽，玩家与领取路线预留。
- **原物与供应**：原三结包裹1@pickup_shelf；同来客实体1；原公共领取槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：沿BC01实际位置：包裹[19.5,26.5]，NPC取位[19.5,25.5]；玩家退4格实际1.333秒。
- **主步骤**：untie_all：沿同一发光绳路松开三个结 [3秒原值] → place_ready：把原包裹放可领取槽 [0.5秒原值] → step_back：实际退到距包裹4格的公共站位 [1秒原值] → guest_pickup：等来者走近并拿走原包裹 [2秒原值]
- **NPC/世界回应**：三结全开+原包裹在槽+玩家≥2.5格后实际走近并取2秒；按BC01有界同根非战斗领取保护。
- **有效修订/恢复**：沿三次1秒解结提交；毒/硬控不能重置领取预算，保护不清毒/不补血/不刷新绝对时限。
- **终态**：同一原包裹三结已实际松开且放原公共槽；玩家退至2.5格外，来客真正走近并用2秒取走。退回未受理包裹是安全取消。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/16/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/16/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/16)

### F18 阿斯旺

- **模块/结局**：`identity` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同一身体真实踩粉印垫并由独立电池计次器记录一次过门，才提交身份候选。
- **原物与供应**：原粉印垫+入口计次器@rear_door；员工内门1；员工钥匙原件
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：同一来客身体真实过粉垫产生本窗口连续爪鞋痕；独立门框计数器为同次真实穿越产生计次回执
- **物理绑定**：粉印与计次同一时间窗但独立来源；关内门保留后门公共退出路线；动物避雨格不误当员工入口。
- **主步骤**：observe_trace：沿粉垫边保留并观察连续爪鞋变化 [2秒原值] → read_tally：读取同窗口真实一次过门记录 [1秒原值] → deny_staff_access：实际关员工内门并保留公共出口 [0.5秒原值] → guest_depart：目送未授权来者从后门公开出口离开 [5秒原值]
- **NPC/世界回应**：误擦只允许同体再过垫一次，真实新时间戳；拒配合5秒限权送客不是识破奖励。
- **有效修订/恢复**：动物足迹单证不足；真变形来者仍须真实越权才可成为敌对塔目标。
- **终态**：同一实际爪鞋连续变化与当前入口记录已核验，员工内门已关且保留公共出口，来者未获得越界权限；索权在此结束，非敌对出门表现后台进行。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/17/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/17/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/17)

### F19 吠陀罗尸鬼

- **模块/结局**：`receipt_chain` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：实际同订单销售与交付两原始回执已存在，来客带同件寄存包裹。
- **原物与供应**：原包裹1@receiving；两原回执的非兑换副联；matching_locker唯一寄存格
- **不能补造的前史**：ORDER_SALE_AND_DELIVERY：同order_id两个真实事件回执；退款变体须实际原销售+退款 真实交付必须存在delivery_received（顾客实际取到原物）的回执；paid-only customer-owned pending_claim不能冒充已交付，跨夜安全领取只履约，不补旧订单奖/旧设施buff。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：receiving/packing两真实站与原柜相连；同包裹回跳只回已登记上一站，不清正确票。
- **主步骤**：attach_first：放下原包裹并挂本单第一真实凭据 [1.5秒原值] → waypoint_two：把包裹送第二台并挂同链第二凭据 [1.5秒原值] → store_parcel：把同件包裹实际入匹配寄存柜并关门 [1秒原值]
- **NPC/世界回应**：错误票不接纳；真实挂两票后封原柜才解锁；包裹和寄影共享根。
- **有效修订/恢复**：缺任何链先不抽；重印1.5秒只是引用同原据，不能重演销售/退款，不补历史。 真实交付必须存在delivery_received（顾客实际取到原物）的回执；paid-only customer-owned pending_claim不能冒充已交付，跨夜安全领取只履约，不补旧订单奖/旧设施buff。
- **终态**：同一原包裹在receiving和packing两站挂入同一实际订单链的两份回执后，实际搬入pickup_shelf匹配格并关门。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/18/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/18/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/18)

### F20 罗刹访客

- **模块/结局**：`order_service` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实一份交换食品与空追加盘在服务缝两侧；来客只请求一份。
- **原物与供应**：SUP_MEAL原份1；单份盒1；空追加盘1；服务缝
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：门外实体与台内玩家隔开；hot_food到服务缝真实搬运，2.5秒食用窗仅用于收空盘.5+关缝.5。
- **主步骤**：accept_one：当场确认仅一份、显示实际库存后接受 [0.5秒原值] → pack_one：取唯一预留食品装入单份盒 [2秒原值] → give_one：从服务窗实际推出这一个盒 [1秒原值] → close_scope：收回空追加盘并关交单缝 [0.5秒原值]
- **NPC/世界回应**：先接受限定一份再吃原盒；不得从口头店长声取得钥匙/全库权限。
- **有效修订/恢复**：只消耗实际食品一次；未接受无义务，已备未交原盒挂待退，不造跨夜债。
- **终态**：本单限定一份真实食品已交，追加空盘已收回，服务缝已关且钥匙/全库权限未越线；接受前拒绝不是成功交易。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/19/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/19/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/19)

### F21 报丧女妖

- **模块/结局**：`fault_safety` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实玻璃防护故障且真实人员在危险岗位，40秒故障预告与机械旗先成立。
- **原物与供应**：同故障机械旗+独立副卡；安全侧隔离杆；柜台敷料2份原库存
- **不能补造的前史**：GLASS_GUARD_FAULT：实际故障状态与fault_id；WORKER_IN_HAZARD：PLAYER或已核验COWORKER实际占格
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：危险位到2格外真实路线，不以leave_station1秒代替任意远路；隔离杆在危险带外，包扎可先于怪到。
- **主步骤**：check_flag：对照现场机械旗和柜台已带副卡 [1.5秒原值] → leave_station：放下任务并实际走出2格危险带 [1秒原值] → isolate_device：在危险格外停机并挂待修牌 [1秒原值]
- **NPC/世界回应**：同事可按撤离请求实际走安全线；40秒终点仍在运行危险格才产一次伤口。
- **有效修订/恢复**：故障预告可在BUSINESS出现，但无普通维护强制RAID；未出血不能给F26/F32写源；停机后挂修复待办安全期做。
- **终态**：同fault_id的真实人员已实际离开危险格，设备已从安全侧停机并挂待修牌；离岗与停机先后可换。事故是否发生另按真实历史保留。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/20/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/20/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/20)

### F22 布朗尼家务精

- **模块/结局**：`helper_job` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实一项未完成杂务与一份交换餐存在，帮手请求绑定该job_id。
- **原物与供应**：交换餐1@hot_food；原未完成工点1；独立供物盘
- **不能补造的前史**：PENDING_JOB：未完成且未被真人/其他帮手占用的原工单
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：原工点与可背向走位路线可达，8秒世界工作可跨中断累计；禁止与强制凝视根并场。
- **主步骤**：take_offer_food：取一份真实交换餐 [1秒原值] → place_offer：把原餐放供物台并登记现有工单 [1秒原值] → assign_job：在原工区指派这一项未完杂务 [0.5秒原值] → work_away_first：背开工区做4秒普通封袋或步行 [4秒原值] → work_away_second：背开继续真实世界4秒 [4秒原值] → inspect：回到原工区实际验收同一点 [1.5秒原值]
- **NPC/世界回应**：背向帮手实际做同工单，回头暂停；8秒后原工点验收1.5秒。
- **有效修订/恢复**：帮手完成计原工单一次；若玩家先完成就撤销未受约邀请，不再造脏点，也不多付一份普通杂活收入。
- **终态**：真实交换餐交供物台，原未完成工单已指派，在未直视工区时累计8世界秒完成，玩家回原工点真实验收1.5秒。没有旧工单不生成新脏点。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/21/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/21/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/21)

### F23 塞尔基海豹人

- **模块/结局**：`lost_property` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实此前交存原皮衣且可追原交存回执，两个不同claimant在公开待核位。
- **原物与供应**：原湿皮衣1@lost_property；两人独立认领记录；正确认领者原I21×1
- **不能补造的前史**：COAT_DEPOSIT：真实交存人/物ID/补缝描述/时间原据
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：先锁两人口述再翻衣核原记，玩家不得从隐藏true_id得到答案；中立台到出口路线真实无阻。
- **主步骤**：record_claims：两位来客先各自登记认领特征 [1.5秒原值] → inspect_match：翻看原皮衣内侧补缝并对真实交存记录 [2秒原值] → return_coat：把同一皮衣放中立台让匹配者拿走 [2秒原值] → watch_depart：清出离店线并看到正确认领者带原衣离店 [5秒原值]
- **NPC/世界回应**：匹配者从中立台拿同衣，实际带衣离开；错误认领3秒内可取回，带走后只记有限损失。
- **有效修订/恢复**：礼物独立领取，没背包可留槽；原衣不可克隆找回；正确者不是怪敌池，支援支付资格仍读NORMAL_CUSTOMER。
- **终态**：同一真实皮衣经实物特征与已有归属线索核对后已放中立交还台并归正确者，离店路线真实可通行。未认领物不以随机衣物替代。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/22/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/22/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/22)

### F24 凯尔皮水马

- **模块/结局**：`rear_wet_cart` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实配送原车原货与rear湿路已连通车轮，先预约干交接槽及备槽。
- **原物与供应**：原货车1+原货1@[28.5,1.5]；干布1@清洁柜；主干槽[27.5,1.5]+隔离备槽
- **不能补造的前史**：REAR_DELIVERY_PARKED：真实货车/原货已在湿边停放
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：大型马只能走宽连通路径，擦点干侧与取车点均可达；错误只第二预设停点[28.5,.5]。
- **主步骤**：take_cloth：实际领取常备干布 [1秒原值] → cut_water：从后门干侧擦断原湿边 [2秒原值] → take_cargo：在断连后取回原车上的货 [0.6秒原值] → place_dry：放后门内已预约干侧交接槽 [0.6秒原值]
- **NPC/世界回应**：冲断水边踉跄2.5秒供擦拭；拉回1秒必须从干侧作用同车。
- **有效修订/恢复**：不许为了生成怪把已经干交接的同货推回水里；断湿与退车都完成才弱化。
- **终态**：本卡原货与原车已实际退到干交接线内，真实湿路割点断开，不再连接该货车；提前合法断湿和安置也有效。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/23/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/23/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/23)

### F25 普卡变形精

- **模块/结局**：`refund_identity` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实原sales_id/item_id及付款已经存在，变形客实际带回同一商品。
- **原物与供应**：原退货物1；透明退货槽1；退款备用店铺币足原额，不用玩家钱
- **不能补造的前史**：ORIGINAL_SALE：跨班持久同campaign销售行/付款/数量1 真实交付必须存在delivery_received（顾客实际取到原物）的回执；paid-only customer-owned pending_claim不能冒充已交付，跨夜安全领取只履约，不补旧订单奖/旧设施buff。；RETURNED_ORIGINAL：实际来客携原item_id到店
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：退款canonical键为campaign/sales_id/item_id，不用night工资键；离线纸联同步同键。
- **主步骤**：accept_item：核对真实原销售并把同一商品放透明槽 [2秒原值] → refund_once：提交同活动/原销售/原物唯一退款 [1.5秒原值]
- **NPC/世界回应**：最多两次变貌与追加请求，只同体；原实物归槽并完成唯一退款才解锁。
- **有效修订/恢复**：夜重试恢复checkpoint，跨夜原销售/原物/退款账本保留；已退款只查键不重付。金额退款为店铺资金转移，不作为可翻倍收入。 真实交付必须存在delivery_received（顾客实际取到原物）的回执；paid-only customer-owned pending_claim不能冒充已交付，跨夜安全领取只履约，不补旧订单奖/旧设施buff。
- **终态**：同一退货实物已实际在透明槽，且同sales_id/item_id的唯一退款回执已存在；新增外观和重复索款不使回执失效。无原销售的保守待核退货只安全撤销，不能发成功奖。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/24/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/24/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/24)

### F26 红帽妖

- **模块/结局**：`wound_cleanup` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：只真实玻璃割伤或F21事故，原伤口剩余满足动态53秒基准门；真实走够2格才滴血，绝不由怪抽选造伤。
- **原物与供应**：柜台免费敷料1（从2份库存保留）；同干布/拖把工具带；原空污袋1@packing；需先领袋回执
- **不能补造的前史**：LIVE_WOUND：有效PLAYER/COWORKER伤口ID来源白名单；TRACE_PATH：同伤口实际行走滴出最多3绑定/总6迹
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：预兆内取齐布/袋到安全位，整个源寿命内路线/包扎/清迹可行；未持工具时把真实取工具路计入。
- **主步骤**：take_dressing：柜台取一份同夜免费敷料 [1秒原值] → dress_self：原地3秒包扎同一真实伤口 [3秒原值] → wipe_c：擦当前脚边真实血迹 [1.5秒原值] → wipe_b：擦同回程第二枚原血迹 [1.5秒原值] → wipe_a：擦同回程第一枚原血迹 [1.5秒原值] → seal_park：把实际污布封袋放柜台外沿处理箱 [2秒原值]
- **NPC/世界回应**：伤员先自包扎或实际协作包扎；怪只锁同伤口活迹，清过不再生成，站立不滴。
- **有效修订/恢复**：自然止血/自然干允许无污袋终态；有脏布才封原袋。已无活伤或迹则候选取消，不重刷血。 BC02首兆剩余须>=actual_omen(至少20)+actual_response_and_route(基准24)+6恢复+3离场，基准53秒；root commit重算剩余和30秒活迹。F21结束后35+60+20=115秒超过伤口90秒，标准单根下不能作为下一场默认血源，首版只当段BUSINESS真实E003接触。
- **终态**：实际源伤已包扎/自然止血，绑定原血迹全部擦净或自然干，确有污布则封原袋并放ATT13；无血迹时不创造血与污袋来凑条件。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/25/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/25/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/25)

### F27 山林巨魔

- **模块/结局**：`large_order` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同订单两个真实大件预摆验收位，巨客门外原交付槽等待。
- **原物与供应**：原大件A+B@receiving；门外大件牌1；宽通道与外侧交接槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：90秒接受窗口含两次重载往返，巨大体型不进入窄门；新路障不能封唯一进出线。
- **主步骤**：sign_accept：清大件槽挂门外交付牌并接受90秒本单 [2秒原值] → take_a：从原验收位取第一批 [0.6秒原值] → give_a：第一批实际交给门外来客 [1.5秒原值] → take_b：空手回原验收位取第二批 [0.6秒原值] → give_b：第二批交付并结同一订单 [1.5秒原值]
- **NPC/世界回应**：每交一批卸担2.5秒，已交原货永久移交；误邀在3秒内1秒撤邀退门外。
- **有效修订/恢复**：异常订单只一次店账，无普通customer buff；主解后仍真实战斗或终态按MD01。
- **终态**：原单两批真实大件分别送到门前大件槽，两个分批回执都成立且主通道恢复畅通；普通订单只总计一次。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/26/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/26/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/26)

### F28 诺肯水乐灵

- **模块/结局**：`water_source_test` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：预装三支路与带盖异常浅盘，受控异常配送把本根有限异常水注入其中一真实支路。
- **原物与供应**：A/B/C独立阀；有限原异常水盘1+盖1；真源实际source_branch
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：同一干侧测试阀位与盖盘位，错误阀可复位；真源与候选跳点均有真实水/占位，不能点击提示得答案。
- **主步骤**：test_a：试关A支路1秒看拍纹未停再复位 [1秒原值] → test_b：试关B支路看乐曲与拍纹同步停 [1秒原值] → seal_known_source：实际记录已知本实例源后直接关B [0.5秒原值] → cover_pan：从同一干侧盖住已隔离原源盘 [1秒原值]
- **NPC/世界回应**：乐曲/拍纹随实际支路同步停，源已识别再封；转场只读真端点。
- **有效修订/恢复**：普通停水不等于封异常盘。仪式需全夜共享3原石可达及6–8秒完整放物/拾投/飞行验收，否则不启动仪式。
- **终态**：真实试阀取得乐曲/拍纹同步变化证据，原真源支路已关且从干侧盖住同一源盘；错误支路复位可恢复，不以普通水声冒充证据。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/27/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/27/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/27)

### F29 托姆特家园精灵

- **模块/结局**：`food_surface` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：库存有真实粥份+合规黄油，来客携原I04赠品；缺任一材料不给该报价。
- **原物与供应**：粥1+黄油1@hot_food；原碗1+运输盖1；原赠品I04×1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：hot_food制备到独立供物台实际搬运，黄油表层可见且不得把食用当交付。
- **主步骤**：prepare：接受后取同一粥份和黄油装碗 [2秒原值] → deliver_uncover：把原碗放供物台再揭盖显示黄油 [1秒原值]
- **NPC/世界回应**：同一碗放错退原碗，可1.5秒重摆同黄油；原赠品另过食品检查再领取。
- **有效修订/恢复**：无无限重做份；赠品batch真实性必须实际存在，不能交粥后才生成安全检验历史。
- **终态**：同碗真实热粥和原黄油已按表层条件备好，实际运到独立供食台并揭盖；I04赠品领取独立，不要求吃掉才离场。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/28/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/28/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/28)

### F30 海亡灵

- **模块/结局**：`original_stone` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：可见配送把一箱合法原货与额外原压箱石送到验收台，原货清单先有。
- **原物与供应**：合法原货1+额外石1@receiving；秤；主门外隔离盘+备用isolation_cage
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：秤→分原货→同石主/备封盘真实搬运；两个封盘至少一个实际可用，石不可阻逃生门。
- **主步骤**：weigh_unpack：原箱过秤并拆出多余原石 [2秒原值] → seal_primary：把同一石实际放门外隔离托盘封存 [1.5秒原值]
- **NPC/世界回应**：石真的顶门后才产本地渗水；移开石使该源退潮3秒，封同石解锁。
- **有效修订/恢复**：历史ever_used不再阻完成；该石不等于MA01投石；封存不能销毁或变成抽奖材料。
- **终态**：同一合法商品已在已验槽，同一额外原石实际封在主/备登记隔离槽，当前不作门挡且本地水线停止；历史误用不阻止恢复。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/29/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/29/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/29)

### F31 马拉梦魇

- **模块/结局**：`rest_fixture` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：固定危险椅当前存在，雇主常备停用牌；休息只可选且须真实安全接岗或清客停业。
- **原物与供应**：停用牌1@rest_chair；可选机械钟+杯@staff_desk
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：.5秒挂牌封椅是免费主解；8秒短休不在追逐中启动，0体力仍可站起走出。
- **主步骤**：decline_chair：给椅位挂暂不用标记后离开 [0.5秒原值]
- **NPC/世界回应**：停椅封出生锚，实际显化解锁后仍需击退；不以要求睡觉才能停止追逐。
- **有效修订/恢复**：P08失败补偿只读真实照护次数，普通休息不得伪造宠物；已封椅不重新刷梦魇。
- **终态**：危险椅实际挂上停用牌并关闭本实例出生锚，或已正确准备钟杯并从真实短休醒来；前者免费且不要求睡觉，两条只能提交一次规则回执。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/30/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/30/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/30)

### F32 夜返吸血鬼

- **模块/结局**：`wound_boundary` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实PLAYER/COWORKER伤口未止血，前门嗅血者读原伤口；迎宾开关开不等于已欢迎。
- **原物与供应**：原免费敷料1@cashier；迎宾声道开关；安全规则线
- **不能补造的前史**：LIVE_WOUND：玻璃或F21实际伤口仍在90秒内；INJURED_ACTOR_PRESENT：原伤员可在近侧≤6格实际走到规则边界
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：关声.5→标线1→伤员实际走≤6格→取敷料1→距离≤1.5包扎3；不是2秒强行移动远处员工。
- **主步骤**：mute_welcome：关闭实际迎宾声道 [0.5秒原值] → mark_boundary：在柜台规则线标记员工边界 [1秒原值] → walk_patient：伤者沿可见近侧线进入规则边界 [2秒原值] → take_bandage：取一份原有敷料 [1秒原值] → bandage_patient：近距离连续包扎3秒 [3秒原值] → targetless_departure：最后血源消失后退去 [3秒原值]
- **NPC/世界回应**：已邀请只追公共区原血源，关声封新越门；无目标后实际3秒退去，不等击杀。
- **有效修订/恢复**：所有伤口均处理或自然止血后才能解根；COWORKER先置任务安全线，普通顾客不能成为被追杀目标。 采用同F26动态预兆/路线剩余门；F21跨标准115秒间隔后不是合法默认来源，禁止延伤口90秒。
- **终态**：已实际投放的本实例所有合法嗅血目标都不再流血，3秒非敌对离场确认完成；关闭声道可阻新越门。未生成根时普通关门/包扎不发击退币。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/31/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/31/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/31)

### F33 狼人

- **模块/结局**：`visitor_aid` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受伤来客自带专用急救包，来客伤不产生员工伤口/血迹条件。
- **原物与供应**：来客专用急救包1；公共托盘；原空周转箱1@交付台侧
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：公共台与可见离店干线，移挡箱1.5秒在3秒预告内；形态观察6秒可重新发生。
- **主步骤**：observe_form：观察同一身体一次形态切换 [6秒原值] → place_aid：把来客交出的专用急救包放公共托盘 [1.5秒原值] → visitor_take_aid：同一来客实际取用专用急救包 [1.5秒原值] → depart：保持路口让同一来客沿预留线离开 [3秒原值] → claim_aid：结算同一援助与离店回执 [0.5秒原值]
- **NPC/世界回应**：同体取原包1.5秒后自行包扎3秒，完毕失自卫态、实际走离店；不能省略3秒自包扎。
- **有效修订/恢复**：未接援助自行离去无援助奖；真人/未知访客不供塔试射；原包不占员工两份敷料。
- **终态**：来客实际接受其携带的原专用急救物，玩家已清出公开离店线，包扎自卫状态结束；未接受援助自行安全离去不结援助规则奖。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/32/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/32/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/32)

### F34 鲁萨尔卡水灵

- **模块/结局**：`front_beat_water` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：既有WET_FRONT支路实际湿化且原登记货袋在末端，预兆显示真实相位。
- **原物与供应**：原货袋1；常备拖把1；干侧切点[13,29]+安全点[15.5,28.5]
- **不能补造的前史**：FRONT_CARGO_PARKED：真实原袋已停放[14.5,27.5]
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：基准环境8秒周期=强拍2秒+休拍6秒，真实2格去+擦2+2格返合3.334秒；怪DASH落空2.5秒仅是攻击收招。
- **主步骤**：observe_beat：在干格看完整8秒强弱拍 [8秒原值] → wipe_cut：休拍从近侧擦断实际割点 [2秒原值] → retreat_dry：回到两格外的干站点 [0.25秒原值] → take_dry_bag：从已断水的末端取原袋 [1.5秒原值] → place_dry_bag：放入门内干交付槽 [1.5秒原值]
- **NPC/世界回应**：两独立时钟可同时观察，不能把2.5秒怪收招写成6秒环境休拍；袋干后不再拖回湿边。
- **有效修订/恢复**：取/放各保留steps1.5秒，断水后可安全分段；retreat_dry写实际2/3秒行走而非.25秒传送。
- **终态**：本卡真实目标湿边已断，登记原货已从干侧实际移走；提前正确完成同样成功，不重造水/重放原货。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/33/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/33/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/33)

### F35 芭芭雅嘎

- **模块/结局**：`helper_job` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：实际普通清洁工单的一处脏点尚未完工，来客带扫帚与边界牌。
- **原物与供应**：访客扫帚1+边界牌1；原空盒1@侧槽
- **不能补造的前史**：DIRT_JOB_PENDING：同一真实脏点工单尚未完成
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：工区牌只限定工作范围，不新增导航墙；8秒背向施工真实累计，取还工具有到场双方距离。
- **主步骤**：set_boundary：把工区牌放在该脏槽边 [1.5秒原值] → place_broom：把来客扫帚放入指定工位 [1.5秒原值] → unwatched_clean：背向工区让扫帚工作8秒 [8秒原值] → return_broom：取回并交给工位边同一来客 [1.5秒原值] → credit_cleaning：核同一脏槽已清洁回执 [0.5秒原值]
- **NPC/世界回应**：原扫帚工作完成停下，同来客实际取回工具；越界只推原空盒.5格一次，仍可抓柄恢复。
- **有效修订/恢复**：普通清洁收入归原job一次；玩家先清完成则取消邀请，无新脏点或凭空工具奖。
- **终态**：同一真实脏点由受限原扫帚完成清洁，原工具已实际收回；拒绝借用或提前自行清完只取消未开始的邀请，不新增清洁收入。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/34/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/34/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/34)

### F36 精灵访客

- **模块/结局**：`lease_slot` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实[18,4,3,2]空槽且来客自带有限放置物与6枚实租金，槽不与双瓶合同共用。
- **原物与供应**：槽边界牌1+通行条1；访客有限私物1箱；原租金6币
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：只授该槽20秒，原实体路线能到槽，公共访客进入特定槽用租约能力而非全员工权限。
- **主步骤**：mark_slot：摆定此槽边界 [1.5秒原值] → grant_slot：只授予同一槽20秒许可 [1秒原值] → lease_twenty：合法使用满20秒后许可自动到期 [20秒原值] → clear_slot：来客把自身有限物件拿离原槽 [2秒原值] → collect_rent：领取同租约六枚实际金币 [0.5秒原值]
- **NPC/世界回应**：20秒后台满后同体用2秒拿走全部原私物；真实清空才结租金，原位物不可远程消失。
- **有效修订/恢复**：提前撤权.5秒立刻停敌对索权并走2秒清槽，租约不重开；租金唯一源转移，不给重复根。
- **终态**：本次限定单槽许可真实满20秒后到期，原借用物实际清离槽位且无越界权限。提前撤权或拒借允许安全撤销，不能刷完整租金/主规则奖。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/35/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/35/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/35)

### F37 古尔荒野妖

- **模块/结局**：`order_boundary` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：已有真实待取订单袋，诱离声音请求无凭改址；订单地址不可被声音覆写。
- **原物与供应**：原袋1@pickup_shelf；真实原取件单；门内保管槽
- **不能补造的前史**：PICKUP_ORDER_PENDING：已有原订单、登记袋与合法门内交付槽
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：门外第一线[15.5,30.5]到门内[15.5,28.5]须实走；合法原袋取放在原槽。
- **主步骤**：verify_order：核原取件单及原交付槽 [1.5秒原值] → take_bag：取同一原单袋 [1.5秒原值] → place_registered：放在门内原登记保管交付槽 [1.5秒原值] → end_lure：保持门内及原物归属，让诱离声退去 [3秒原值]
- **NPC/世界回应**：拒无凭改址1秒后同体诱声退去；不能以交给无资格者完成订单。
- **有效修订/恢复**：保持门内且原物归属正确即可解根，商品没交不记销售；不存在原袋就不生成诱离题。
- **终态**：已实际投放的诱离请求被识别，玩家停止跟随并留在真实门内，原订单物归属保持且高权限未被交出，本次诱离终止；可没有交付成交。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/36/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/36/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/36)

### F38 双重身

- **模块/结局**：`dual_identity` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实员工在三工位留下本班工作回执与独立班表，班前两项独立基准未泄露。
- **原物与供应**：当前身体A及后来实到同脸B两个actor_id；钥匙原件封槽；双公共待核位
- **不能补造的前史**：THREE_WORK_RECEIPTS：同COWORKER三真实工位回执；SEALED_ROSTER：独立班表/时刻；PRIVATE_BASELINE：真实班前私约；BODY_BASELINE：独立腕绳动作原记录
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：当前A现场私约+腕绳两证之后才产生8秒连续身体链；B走入10格/3=3.333秒、分位1+授权1.5共5.833秒，视线必须不断。
- **主步骤**：read_work_receipts：核三工位同班原作业回执 [1.5秒原值] → read_independent_roster：比对独立封存班表及完成时刻 [1.5秒原值] → observe_current_private：在核验位看当前身体回应未泄露的班前私约 [1.5秒原值] → observe_current_body：同一身体实际展示独立腕绳动作基准 [1.5秒原值] → commit_current_check：提交两项当前独立核验并建立8秒身体链 [0秒原值] → see_second_arrive：实际见第二同脸身体从前门走到待核格 [3.3333333333333335秒原值] → separate_bodies：让A随近侧线停住、B留第二公共待核格 [1秒原值] → grant_tracked_body：仅给仍连续见证的A恢复有限员工权限 [1.5秒原值]
- **NPC/世界回应**：A始终真实员工不敌对；B仅实证暴露的异常显影成一个敌池；无法核验双方限权而非杀真人试错。
- **有效修订/恢复**：普通自动交班绝不自动给current_check；凭证过期安全撤销无奖励，不能重看几帧复活旧链。 当前A的两证与8秒身体链是OMEN precommit行动；B随后真实走入才root_commit。所有前置操作仍耗实际世界时间，未commit无根奖励。
- **终态**：两项独立当前核验已提交，8世界秒身体链未断且分位完成，只给仍被连续见证的真人A恢复有限权限；异常B的独立显影在此时注册为唯一敌池，绝不对真人开火验明。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/37/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/37/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/37)

### F39 多莫沃伊家宅灵

- **模块/结局**：`paired_workbench` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实设备迁位工单未完，原旧灶木牌、新旧槽和独立基础灯存在。
- **原物与供应**：唯一原木牌；同工位新旧两槽；独立手压基础灯
- **不能补造的前史**：DEVICE_RELOCATION_PENDING：真实迁位需求未被提前修复/完成
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：同台两槽手达范围内；暖新3秒→迁同牌3秒→停旧.5，迁牌不得写1.5秒；离台路程另算。
- **主步骤**：warm_new：使新槽基础落脚标记亮起3秒 [3秒原值] → move_plaque：把唯一木牌从旧槽取放到同工位新槽 [3秒原值] → stop_old：安全停用旧位 [0.5秒原值]
- **NPC/世界回应**：落点禁攻窗3秒允许原地完整3秒迁牌；若不足须分两次1.5取放保留原牌位置，不能瞬移。
- **有效修订/恢复**：故障设备断电不影响基础标记；需求先消失取消候选，不能为了来怪再坏一次。
- **终态**：同一真实迁位需求对应的木牌已到亮起的新合法槽，旧设备已安全停用。故障先修好、根未投放时只取消迁位预约。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/38/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/38/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/38)

### F40 列希森林灵

- **模块/结局**：`marked_shadow_route` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：一株此前真实误收树苗与固定三路标盒，林影只覆盖原图不改导航。
- **原物与供应**：原树苗1@goods_shelf；原路标3枚@floor_markers；原归还/隔离槽
- **不能补造的前史**：SAPLING_MISRECEIVED：实际货单识别误收同苗的原事件
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：每路标绑定实际林影节点，贴后仅对应节点关闭；保留连续三点带货路线、已贴点作可复核路标。
- **主步骤**：mark_one：在第一个实体槽贴原路标 [1秒原值] → mark_two：在第二个实体槽贴原路标 [1秒原值] → mark_three：在第三个实体槽贴原路标 [1秒原值] → take_sapling：拿同一株误收树苗 [1.5秒原值] → follow_last_mark：带原树苗沿已贴的近门标记前进 [0.5秒原值] → return_sapling：实际放入门内树苗归还槽 [1.5秒原值]
- **NPC/世界回应**：同一影只能在登记节点间预告跳；苗回原合法槽即封锚、终态后不拿回重考。
- **有效修订/恢复**：提前正确还苗可主解，牌辅助而非必须刷三次；无真实苗不能临时造错收历史。
- **终态**：同一登记树苗实际回到门内归还槽或本卡合法隔离槽；三个亲手路标辅助辨路及关影锚，但提前正确归还不强制补走三次。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/39/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/39/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/39)

### F41 哭泣女

- **模块/结局**：`lost_property` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：普通顾客先前真实遗留并登记封袋，未知哭声无领取资格。
- **原物与供应**：原失物袋1@lost_property；游戏内求助面板；机械服务缝
- **不能补造的前史**：LOST_BAG_REGISTERED：原顾客遗留、封存时间、封袋ID回执
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：求助登记在柜台安全侧，不要求双手拿袋拨号；越门只退2格并实际放回原柜。
- **主步骤**：read_seal：读同一原袋封签和真实时间 [1.5秒原值] → register_help：在游戏内面板登记同一失物求助 [1.5秒原值] → close_service：关闭交付缝，保留原袋合法托管 [0.5秒原值] → lure_depart：在门内等待诱离水印退去 [3秒原值]
- **NPC/世界回应**：求助原据与保管成立后诱声3秒退，不能新增儿童或虚构失主。
- **有效修订/恢复**：本地求助面板是游戏内事件，不发外部消息；关缝不封逃生门，袋留真实托管位。
- **终态**：本次真实求助已登记，原失物袋合规保管或已合法交付，玩家停止跟随未知哭声且本次诱离请求终止；不把向未知人交袋设为条件。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/40/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/40/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/40)

### F42 哨声亡灵

- **模块/结局**：`pressure_threshold` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实候运货1–2件先预摆后门内，独立机械压差周期有8秒低压。
- **原物与供应**：候运箱1–2；机械压差表；原后门闸；两侧真实缓冲槽
- **不能补造的前史**：TRANSFER_CARGO_STAGED：原箱实际到近侧候运槽
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：每件实际一轮开1+取1.5+重搬3/2.4+放1.5+空返3/3+关1=7.25秒，完整8秒剩余才开。
- **主步骤**：open_low：确认完整8秒低压窗口后开闸 [1秒原值] → take_cargo：拿原候运货 [1.5秒原值] → place_across：持货跨3格并放外侧候运位 [1.5秒原值] → return_close：空手回3格关闸 [1秒原值]
- **NPC/世界回应**：实体只沿真实门线，关闸不关闭唯一安全退出；第二箱另等一轮。
- **有效修订/恢复**：关闸统一1秒不采用window旧.5；错开立刻1秒关，已过箱保位置；不算商品上架/垃圾清运。
- **终态**：本次实际登记的1—2件原货都完成后门两侧短转运，真实闸门已关；投垃圾/上架/销售没有到各自目的地便不记功。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/41/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/41/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/41)

### F43 图恩达

- **模块/结局**：`identity` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：已有真实当前交接任务和覆盖声称时段的封存工作记录；假同事到公共粉垫。
- **原物与供应**：原任务物（若本单有）；原实钥匙；公共粉印垫+本次便签
- **不能补造的前史**：CURRENT_HANDOVER_JOB：真实交接任务；COVERING_WORK_RECORD：独立记录覆盖便签时间
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：让同body实际过垫产生木足印，不能把已有普通脚印当当前身份；核验桌路径可达。
- **主步骤**：observe_foot：让当前来客站公共垫，读木足轮廓 [1.5秒原值] → read_record：比对覆盖同一时段的原记录与便签 [1.5秒原值] → deny_crossing：保留原任务与实钥匙，结束越界请求 [0.5秒原值]
- **NPC/世界回应**：证据齐全可撤越权请求；任一缺失只限权待核，不能从true_id读取答案。
- **有效修订/恢复**：足印1.5+记录1.5各自提交，攻击3秒收招可用；没待交物不生空清运任务。
- **终态**：同一实际公开粉垫留下可核木足/脚印，结合已存在的独立工作连续性记录确认异常请求且未授越权；证据不足的限权保留是安全分支而非伪造真相。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/42/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/42/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/42)

### F44 巨帽夜曲客

- **模块/结局**：`rhythm_order` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：来客当场报价单曲单货，原商品预留于自提架，固定价牌与托盘有空位。
- **原物与供应**：原订单商品1；实体价牌1；托盘盖1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：接受后30秒同一截止，6秒周期末2秒交货，实际1.5秒交付必须在末拍内起止；等下一拍可走位。
- **主步骤**：set_price：放唯一一曲一单价牌并接受本单 [1.5秒原值] → take_good：取同一已预留商品 [1.5秒原值] → wait_downbeat：在柜台等最多4秒到可交付末拍 [4秒原值] → deliver_downbeat：末拍内实际把原商品交到托盘 [1.5秒原值] → close_tray：合上本托盘并撤销未接受的续约 [0.5秒原值]
- **NPC/世界回应**：首次签牌唱2.5秒停攻；交后.5秒封单取消未受约续曲，最多两次重奏。
- **有效修订/恢复**：异常订单不产正常顾客buff；仪式石规则独立，打断不等于售货成功。
- **终态**：一块实体牌确实绑定本单一曲，本单原商品实际交付且托盘封住、未授下一曲合同；接受前拒绝不算完成一单。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/43/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/43/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/43)

### F45 逆足林守

- **模块/结局**：`wheeltrace_order` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实同批箱被拖运形成连续轮痕并保原封签，正确货格来自本次物流记录。
- **原物与供应**：原箱1@receiving；真实当前轮痕；对应原货格+可封错槽
- **不能补造的前史**：BOX_DRAG_TRACE：先前实际同箱拖运路径与终点
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：三候选槽必须各可达、当前痕清晰；沿痕到正确格不是任意传送。
- **主步骤**：read_wheel_trace：核原箱封签并看连续轮痕 [2秒原值] → take_box：拿同一批箱 [1.5秒原值] → place_correct：把原箱实际推入轮痕对应槽 [1.5秒原值] → close_wrong_slot：封住可见错向槽，核入架回执 [0.5秒原值]
- **NPC/世界回应**：本体冲旧方向后3秒收招供1.5上架；错槽仍同箱实际取回，核验不回滚。
- **有效修订/恢复**：若原箱早已正确上架可预防成功仅对已承诺root；未有root普通上架不给额外怪奖励。
- **终态**：同一原登记货箱已沿真实连续轮痕归对应正确货格并有实际回执；提前正确上架同样成功，不倒退货箱。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/44/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/44/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/44)

### F46 红帽萨西

- **模块/结局**：`three_node_wind` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同体可见到场后实际拿走未预约的普通轻工具；筛罩在开班实点。
- **原物与供应**：原轻工具1；筛罩1@storage_shelf；3个固定风停点+各侧操作槽
- **不能补造的前史**：NONCRITICAL_TOOL_AVAILABLE：真实工具未被任何任务/宠物预约
- **本次实际到场动作**：同体可见拿走未被预约的原普通工具，原物位置从柜到旋风
- **物理绑定**：每停4秒末1.5秒预告、移动.4秒，完整13.2秒；罩放前一停点窗，玩家退1格实际1/3秒。
- **主步骤**：take_sieve：取固定免费筛罩 [1.5秒原值] → observe_cycle：观察三停点完整周期 [13.2秒原值] → place_correct_sieve：把筛罩放在已预告中槽 [1.5秒原值] → step_clear：退开一格让旋风进入筛罩 [0.25秒原值] → capture_next_pass：等最多一完整三停点周期让原旋风进入原罩 [13.2秒原值] → take_tool：从已截住风的固定槽拿回原工具 [1.5秒原值]
- **NPC/世界回应**：截到同一旋风才封跳锚；工具真正入罩才取，宠物取回也不替代截风。
- **有效修订/恢复**：原工具回收后不再偷；退步旧.25秒改真实路程；错放不删工具，可收同罩重放。
- **终态**：原筛罩确实截住本次旋风一次，且原工具已在玩家或原工具槽；封节点换位、解死亡锁，收走筛罩是后续普通整理。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/45/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/45/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/45)

### F47 水歌伊阿拉

- **模块/结局**：`rhythm_offer` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同来客带有限3份封袋材料与3/5/8共16枚原奖币，明确接受当前段才开始。
- **原物与供应**：段材料最多3份；三原奖袋与3+5+8币；水槽旁安全封袋设备
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：八秒单段QTE世界窗，末拍2秒预输入/字幕；不与追逐并场，不把广告时间计入段时钟。
- **主步骤**：seal_one：第一段实际封袋QT成功 [8秒原值] → claim_one：实际领取第一段3币 [0.5秒原值] → cash_out：带已兑金币离开水槽邀请 [0.5秒原值]
- **NPC/世界回应**：段成功后原袋封好且实际取走，再cash_out；下一段失败不扣已领原币。
- **有效修订/恢复**：每次实际启动无论取消/失败只占本段预算一次，失败材料耗掉不免费补满；不再开页生袋。
- **终态**：任一已完成歌段的原奖袋已实际封好并从交付槽拿离，玩家明确cash_out；未接受、未完成第一段便失败/退出是安全撤销而非成功领奖。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/46/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/46/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/46)

### F48 河海豚化人客

- **模块/结局**：`restricted_order` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：非人访客提出普通商品交易但actor_class仍anomalous_visitor，员工帽钥为实物权限独立。
- **原物与供应**：原基础订单商品1@pickup_shelf；原员工帽1+钥匙1@staff_locker；公共托盘
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：柜台交物与公开离店路线；员工帽移交不自动授员工权，追回需同人交回与玩家实际回柜。
- **主步骤**：accept_order：按原价格接受唯一普通订单 [0.5秒原值] → take_good：取同一订单商品 [1.5秒原值] → deliver_public：在公共柜台交付原商品 [1.5秒原值] → depart_public：保持访客权限，沿公开路线送客离开 [3秒原值]
- **NPC/世界回应**：没有实际越界时保持非敌对受限访客；发生越权并实证才能注册敌对根。
- **有效修订/恢复**：无越权的普通受限成交只有本单店账，无怪根奖也无正常顾客设备支援；不可自动把所有非人当敌人。
- **终态**：本次原商品交访客托盘，原帽钥仍在员工侧或已追回，来客未获得未授权员工权限且公共出口保持可通行。没有越界请求时只是普通受限交易，不生成额外战斗根。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/47/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/47/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/47)

### F49 火蛇博伊塔塔

- **模块/结局**：`hot_waste` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实热食营业产生同袋热废物及温度，原隔热盖/温标与安全暂存槽已存在。
- **原物与供应**：原热废袋1@waste_sort；隔热盖1+外温标；安全暂存槽+原垃圾箱
- **不能补造的前史**：HOT_WASTE_CREATED：真实制作报废工单产同袋废物
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：合盖统一1秒；封闭累计20秒（闷热40一次快照），开盖只暂停；走去垃圾箱另按重载真实路线。
- **主步骤**：close_lid：用已有隔热盖封闭同一热垃圾袋 [1秒原值] → cool_ten：在封闭状态累计10秒有效冷却 [10秒原值] → cool_ten_2：在封闭状态累计10秒有效冷却 [10秒原值] → serpent_recedes：封盖后火蛇3秒失去暴露热源 [3秒原值] → take_cold_bag：拿同一已冷却封袋 [1.5秒原值] → dispose：实际沿原路到垃圾箱投同一袋 [1.5秒原值]
- **NPC/世界回应**：暴露热源封住后3秒退火，怪不能把店内全部热食当本根原热废。
- **有效修订/恢复**：冷却+安全暂存可解怪，实际投垃圾箱才结普通清运；I15同袋只一次减10秒。
- **终态**：原热废袋真实合盖封存且外温标达到本卡冷却条件，已安全暂存或实际投放；只有后者结清运回执。热食台不是本卡热垃圾。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/48/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/48/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/48)

### F50 泽西恶魔

- **模块/结局**：`window_defense` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：原双窗组、防护板、机械帘和安全点班前落位，来客两次真实掠影锁左窗。
- **原物与供应**：防护板1@[23.5,28.5]；左/右原窗槽；同组机械帘+停业牌
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：2秒观察+拿1.5+插板2+真实位移与退安全点全程装入8秒，不靠.25秒传送；不足则不启动攻击。
- **主步骤**：observe_target：在已预约准备点看两次掠影 [2秒原值] → take_board：取同一防护板 [1.5秒原值] → push_correct：把板推入已锁定左窗槽 [2秒原值] → retreat_safe：离开实际内侧冲击格 [0.25秒原值] → wait_locked_impact：等待已锁定的原撞击时点 [0秒原值] → impact_passes：读取已经发生的同次撞击回执 [0秒原值]
- **NPC/世界回应**：同attack_id撞锁窗一次；预告不因观察/错窗刷新，撞后4秒低空不是自动ground。
- **有效修订/恢复**：MA01直接伤10映射HP，旧SAN−8同次停用；错窗安全封区不计成功；合法延长只按来源正差。
- **终态**：同一8秒锁窗撞击真实结算时，正确板在锁定窗、玩家已退同组安全点且本轮未命中；错窗拉帘及时撤离是安全退避，不获得完整防御规则奖。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/49/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/49/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/49)

### F51 蜘蛛故事商

- **模块/结局**：`receipt_story` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同班已经有3张不同真实销售回执，再预留一件当前商品；故事矛盾从真实字段生成。
- **原物与供应**：原三回执；当前原商品1；实体唯一价牌+封单托盘
- **不能补造的前史**：THREE_DISTINCT_SALES：本班不同sales_id且付款/商品/金额/时间可查
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：原据柜台可读2秒；同字段矛盾槽动态生成，不能固定选第二；取货实际路计入服务窗。
- **主步骤**：read_three_receipts：对照三张实际收据的原字段 [2秒原值] → place_contradiction：把对应原收据放矛盾短句槽 [1秒原值] → take_order_good：实际取原当前订单商品 [1.5秒原值] → deliver_order：按已锁唯一价牌交同一商品 [1.5秒原值] → close_deal：合托盘结束已交付的有限交易 [0.5秒原值]
- **NPC/世界回应**：叙述时2秒停攻，压真票剪对应护丝；同实体最多三共享丝，不多敌池。
- **有效修订/恢复**：无3真实票不抽、不虚构销量；当前异常订单不产生设施buff或反哺自己的前置销售记录。
- **终态**：真实原回执已压对应矛盾段，唯一价牌锁定，原商品实际交付且有限交易托盘封闭；无本班真实旧票不投放，不要求凭空补交易历史。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/50/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/50/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/50)

### F52 矮水灵托科洛舍

- **模块/结局**：`chair_water` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实WET_CHAIR南支路连椅底，原手压低灯和干布从岗位实际领取。
- **原物与供应**：原危险椅；常备干布1；手压低灯1；停用牌
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：[4.5,8.5]擦点、[4.5,6.5]低查、[4.5,7.5]退出点均干侧；不能采用废弃北湿格。
- **主步骤**：wipe_chair_cut：从干侧擦断椅位短水线 [2秒原值] → low_inspect：手压低灯观察真实椅底影子退去 [1秒原值]
- **NPC/世界回应**：断水且低灯真实发现影离椅底才解死亡锁；误坐3秒预告内.5起身。
- **有效修订/恢复**：基础主解不含6秒短休；短休只安全状态、本夜一次，不能休息生成同怪或自刷血。
- **终态**：本椅实际水线断开且低位灯检查已确认原影离开椅底成为合法显影；此时封回潜并解死亡锁，不必进行六秒短休。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/51/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/51/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/51)

### F53 水之母来访

- **模块/结局**：`bottle_contract` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实独立同批6瓶A–F及两个容器，报价时间充分才受约；非玩家保底水。
- **原物与供应**：原A/B@同一goods_shelf保留容器；可售C/D/E/F@独立pickup_shelf可售容器；原封签
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：A/B必须在同一保留容器，take_pair3秒为分次取放同ID；两容器不等于两瓶各占一库房槽。
- **主步骤**：accept_promise：240前接受双瓶承诺并预约原两容器 [1秒原值] → take_pair：实际拿原瓶A与B [3秒原值] → place_a：把原A放进商品位同一保留容器 [1.5秒原值] → place_b：把原B也放进这个保留容器 [1.5秒原值] → seal_pair：同一保留容器中两原瓶齐备，实际封2秒 [2秒原值]
- **NPC/世界回应**：封双瓶2秒立即战斗削弱，不站等天亮；水母仍按MD01必要实际击退。
- **有效修订/恢复**：BC02简化交班：夜结先快照原A/B封存→真实shift_close服务持久提交，再一次履约账；取消700–720手搬账钥/店长短凭证门槛。夜结收益不在战斗提前回SAN，C–F销售另行实际发生。
- **终态**：原A/B同在唯一预约保留容器且真实封签2秒完成：一次提交战斗削弱。720世界秒资格冻结、店长当前核验、原物交班和SAN+5按原履约合同另行判断。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/52/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/52/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/52)

### F54 吞世巨兽

- **模块/结局**：`giant_retrieval` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：三件未被任何订单/任务/口粮预约的原普通货预摆门前；巨口实际到场按A→B→C吞入才建栈。
- **原物与供应**：原普通A/B/C各1；原回收绳3；外槽1=[19.5,32.5]2=[20.5,32.5]3=[21.5,32.5]
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：同口可见按A→B→C吞入三件原货，才提交真实栈；原库存在吞入处移动，不复制
- **物理绑定**：三槽要原物大小匹配且放下可达；吸带安全侧拉1.5/放1.5分窗，零体力可完成。
- **主步骤**：pull_c：从最后一结拉出原物C [1.5秒原值] → place_c：把同一C放实际槽3 [1.5秒原值] → pull_b：从当前最后一结拉出原物B [1.5秒原值] → place_b：把同一B放实际槽2 [1.5秒原值] → pull_a：最后取回最先吞入的原物A [1.5秒原值] → place_a：把同一A放实际槽1 [1.5秒原值]
- **NPC/世界回应**：只绑定这三件，不能吞钥匙、肉或承诺瓶；真实逆序C→B→A，已回收永不重吞。
- **有效修订/恢复**：预兆准备先物化原货和槽，再实际吞入，未吞不预写队列；缺放槽不开始拉取，已持原物不得克隆空位。
- **终态**：三件已实际吞入的原物按真实栈的逆序逐件取回并放入各自预留外槽，队列为空；不把最后收绳旧动作当自动清除巨口生命池。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/53/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/53/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/53)

### F55 护夜犬卡德霍

- **模块/结局**：`escort` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实原交接物、非保底食物和三段合法路线；原合法接货人有预约窗口。
- **原物与供应**：非保底食物1；原交接物1@pickup_shelf；三个干线节点
- **不能补造的前史**：ESCORT_ORDER：已有订单/原货/授权接收者与路线
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：节点.25秒只是交互，所有重载出程+空手返程真实另算；离线2格3秒提示，连续6秒失护送资格。
- **主步骤**：give_food：在门内把实际一份非保底食物交给犬 [1.5秒原值] → take_cargo：取同一交接物 [1.5秒原值] → walk_node_one：持原物到第一干线节点 [0.25秒原值] → walk_node_two：沿干线到第二节点 [0.25秒原值] → walk_node_three：沿干线到原预约末节点 [0.25秒原值] → deliver_real_receiver：向现场合法接货人交同一物 [1.5秒原值] → return_empty：实际空手沿原线返店 [0.25秒原值]
- **NPC/世界回应**：犬实际逐节点同行，食物交付停扑一次；接货人等6秒按真实到场时钟，无人就原货返店。
- **有效修订/恢复**：未交物不结销售；护送完成返店另唯一原奖键；不得让6秒接货窗口从怪根到场就开始耗尽。
- **终态**：原食物已真实交付，沿三段已登记合法路线完成实际出返；原货已交合法接收者或迟到保留原货返店，均按同一根封连扑，未交物不结订单收入。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/54/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/54/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/54)

### F56 深水邦耶普

- **模块/结局**：`aisle_depth` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：WET_AISLE支路真实连通且原货落在登记浅水末端，工具有实际领取源。
- **原物与供应**：原货1；定长尺1+干布1@mop_station；真实[8,17]割点
- **不能补造的前史**：LOW_CARGO_DROPPED：同原低层货实际在[8.5,19.5]
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：[7.5,19.5]干侧测与退，擦点路径实走；出水/取货前检查真实干燥连通。
- **主步骤**：probe_depth：从干站点插固定尺读湿边 [1.5秒原值] → cut_branch：沿可达干侧到[8,17]割点擦2秒 [2秒原值] → take_original：从已排干原末端拿原货 [1.5秒原值] → put_original：把同一原货放回原货格 [1.5秒原值]
- **NPC/世界回应**：误踏仅一次把原货滑到[8.5,18.5]可达槽，别再随机移远；本体只从合法水潜点出水。
- **有效修订/恢复**：提前断水可以跳测深，绝不为重演技能重新生水；普通上架只原job收入一次。
- **终态**：本卡真实目标水支路已排干，登记原物从干侧实际取回；若此前已正确断水可跳过测深，不能重复造水。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/55/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/55/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/55)

### F57 水路守护塔尼瓦

- **模块/结局**：`channel_crossing` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：主渠永久真实通水，原过渠箱在ATT15近侧，杂物仅有才移；北绕先画成真实地面。
- **原物与供应**：原踏板1；本地8秒弹簧维护杆；原箱1；可选原杂物1
- **不能补造的前史**：CHANNEL_CARGO_STAGED：原箱实际到[26.5,-3.5]缓冲槽
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：本地放板.6取.6+跨程实际/2.4+放.25+空返/3+收.6+复流.5及起杆.5必须≤8；北绕无时限但必须实际可走。
- **主步骤**：clear_real_debris：把现有一件杂物移到近侧普通杂物槽 [1.5秒原值] → pause_local：本地杆启动最多8秒维护 [0.5秒原值] → place_bridge：把原踏板放到本地跨点 [0.6秒原值] → take_box：从原近侧缓冲槽拿同一箱 [0.6秒原值] → cross_place：经原维护跨点把原箱放对岸登记点 [0.25秒原值] → remove_bridge：空手返回收原踏板 [0.6秒原值] → restore_flow：在原本地杆恢复主渠水流 [0.5秒原值] → claim_maintenance：原箱经完整维护过渠且复流后领取一次SAN+4 [0.5秒原值]
- **NPC/世界回应**：守护体不离水追入干区；8秒自动复流不自动收板/移动箱，超时保原位置并安全收板。
- **有效修订/恢复**：cold_branch不能代rear_source；干绕仍解根但无维护SAN+4；主渠不能永久断水当解法。
- **终态**：同一原箱通过合法8秒维护或既有北侧干绕实际到对岸登记点，主渠通水畅通、原踏板已收起。只有完整维护链额外结原SAN+4，干绕仍可解怪。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/56/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/56/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/56)

### F58 雾笛访客

- **模块/结局**：`warm_fog` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：已有普通冷区业务、原暂停牌与实际可退安全侧；本根30秒雾景退去时点公开。热食是独立可选分支，缺热食不阻止免费封区。
- **原物与供应**：必需原冷区暂停牌@[24.5,15.5]及安全侧@[21.5,15.5]，任务冰柜/逃生门独立。可选原热食与保温盖只读真实生产、库存及剩余品质回执；不因怪物抽选或提示生成。
- **不能补造的前史**：`COLD_SERVICE_ACTIVE`，真实普通冷区业务尚未暂停；早期v06整卡必需热食的旧门被MD01成功条件和v010免费分支覆盖。
- **本次实际到场动作**：原牌/通道先实际预约、同一怪物真实到场，才提交本根；预先做普通停业不产生怪物成功奖。
- **物理绑定**：挂牌点[24.5,15.5]与安全侧[21.5,15.5]之间，现有StoreMap测得真实3格、身体可通过。首段到挂牌点的真实路程另算；这只证明该静态通道，尚未证明F58的完整动态AI。
- **免费主步骤**：原牌实际挂牌0.5秒 → 沿3格地面通道走到安全侧 → 退出提交0.5秒。Lv1普通行走3格/秒时，从牌开始共2世界秒；不能用位置写入代替行走，也不能漏掉最后0.5秒。
- **可选暖食步骤**：同一原热食盖好1.5秒 → 保持原暖源到本根既定退雾时点。`wait_fog_end`的0秒动作字段表示等真实截止，并非瞬间退雾；暖食40秒品质、雾景30秒、最后暖源移走后的3秒补救各自按世界钟。
- **前兆与食品时钟**：普通20秒OMEN不会延长40秒品质。commit必须复核真实剩余足够覆盖分支尚余退雾、盖食及路线；预兆前刚做好的40秒食物也不能默认满足。没有后续已实际发生且获准的真实生产来源，就走免费封区，不强迫战斗中补餐、不发900秒保温包代替原规则。
- **NPC/世界回应**：MA01主机制工作窗保护已列挂牌和实际撤离；玩家实际退出后同根立即`resolved_by_rule`，取消未提交攻击并非敌对离场。缺餐、过期或错过3秒补救都会保留这条可重复尝试的免费路线，不无限冻结怪物。
- **终态与奖励**：免费封区并真实安全退出，或原暖源有效维持到既定退雾，任一独立分支均为MD01的真实`rule_leave`成功；只结原根一次。封区只暂停普通业务，任务冰柜和逃生门始终可用。
- **图验证**：显式`requires_any`表达两条终态分支；删除所有热源输入仍能走免费分支，但再删除挂牌、实际走路或退出提交任一步，免费分支都不可达。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/57/mechanism), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/57), [mechanism_cases_v010_b.json](../content/mechanism_cases_v010_b.json#/cases/27/actions)

### F59 梅内胡内工队

- **模块/结局**：`repair_worksite` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：已有E019真实损坏件工单且该可选设备实际存在，3份原维修材料足够才出现工队。
- **原物与供应**：普通材料3份@storage_shelf；三个施工槽；局部任务灯开关；原设备检修面
- **不能补造的前史**：OPTIONAL_DEVICE_FAULT：原device_id/fault_id仍停用，初始闪烁结束不消故障
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：逐份1秒投材；局部暗且未看8秒实际累计→唯一fault_id组件→实拿1.5→安装2→测试1；组件初始0。
- **主步骤**：take_three_materials：实际取现有3份维修材料 [1.5秒原值] → place_material_1：将第1份同批原材料放对应施工槽 [1秒原值] → place_material_2：将第2份同批原材料放对应施工槽 [1秒原值] → place_material_3：将第3份同批原材料放对应施工槽 [1秒原值] → turn_away_dark：关局部灯并转开注视 [0.5秒原值] → construct_first_four：世界运行且未注视施工4秒 [4秒原值] → construct_last_four：继续累计最后4秒产同故障组件 [4秒原值] → take_component：取刚制造的同一组件 [1.5秒原值] → install_component：去原故障配电位装同一组件2秒 [2秒原值] → test_device：在原操作位真实测试1秒 [1秒原值]
- **NPC/世界回应**：施工/待收件/安装阶段停攻；看见仅暂停不重扣；故障已外修则取回未用材料，成品不转万能件。
- **有效修订/恢复**：与BC01可选战术电闸区分，主电恢复不自动修该故障；所有普通修复只安全状态。
- **终态**：同damaged_component_id的三份原材料已真实转成唯一组件，组件实际装回原可选设备且测试成功，原电量/次数不变；原故障已先修好只取消邀请。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/58/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/58/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/58)

### F60 马面引路者

- **模块/结局**：`gaze_curtain` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：原凸镜、实体中间帘与侧提示现场存在，同一马面到镜景真实位置。
- **原物与供应**：原帘线段[18.5,23]–[20.5,23]；凸镜1；服务停用牌
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：读取真实朝向/实体线段遮挡，镜像不算直视；本体到同侧帘不再有效，改锁背向。
- **主步骤**：notice_turn：看可见头影并获得8秒转身预告 [1秒原值] → read_mirror（可选）：保持身体西向，拨镜看1秒准备图 [1秒原值] → pull_curtain：在实际近侧控制位拉原帘 [1秒原值] → close_service：实际挂此服务位停用牌 [0.5秒原值] → second_distinct_gaze_miss：等下一已编号凝视，保持背向或用实际中间帘让它落空 [0秒原值]
- **NPC/世界回应**：两个不同attack_id已实际提交凝视payload且被帘/背向阻断才累计2次；冻结/诅咒取消不是回应。
- **有效修订/恢复**：维持BC01的真实凝视观察与MA01伤害去重；无需反复开帘把自己暴露，镜面不是瞬移端点。
- **终态**：两个不同attack_id的真实凝视分别因中间帘有效遮挡或玩家锁背向而落空；每次都有独立开始/结束，第二次永久封追踪转头。同一帘反复切换不刷计数。
- **原来源**：[monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/59/mechanism), [monster_folklore_md01.json](../content/monster_folklore_md01.json#/monsters/59/movement), [monster_attacks_folklore_ma01.json](../content/monster_attacks_folklore_ma01.json#/monsters/59)

### S01 凝视塑像

- **模块/结局**：`containment_cage` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控异常货运在安全装载期把同一塑像带入已预约笼前场地；没有“看提示生成笼”。
- **原物与供应**：塑像本体1；固定笼1+侧手闸+尾隔栏+玩家侧门+地面引导线；独立手压任务观察灯1@安全侧控制位；真实照亮原实体，不计电器buff/电图节点
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×5任务位：笼内2×2、侧控与笼内直视、尾隔栏诱点、玩家侧门独立回控线；实际体型/门扇扫掠不可夹人。 任务手压观察灯照明必须覆盖同体和安全控制视线；MAIN停电时仍可观察，不能用字幕替代真实凝视。
- **主步骤**：S01:step1：在保持直视的侧置控制位打开收容笼 [1秒原值] → S01:step2：玩家从笼尾隔栏诱导位短暂转视，让本体沿真实追逐路线进入笼区，再经玩家侧门移到回控线；移动时间另计真实路径，不以本步1秒代替行走。 [1秒原值] → S01:step3：恢复直视并压下侧置闸柄，关门提交笼内实体检测 [1秒原值]
- **NPC/世界回应**：直视停止同体，玩家短暂转视诱导实际走入；侧门允许玩家退出，门闭须同体完整在内且无人被夹。
- **有效修订/恢复**：笼未真正进体不能提交；失视误入可走侧门恢复，固定笼与手闸断电可用。
- **终态**：同一塑像在收容笼内部、笼门锁闭、无玩家/顾客被夹在笼内。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/0/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/0/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/0)

### S02 腐蚀穿墙者

- **模块/结局**：`containment_tray` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：班前密闭槽装好有限任务液体、双层封板和机械诱振器；腐痕由本次同体实际接触登记表面产生。
- **原物与供应**：同体1；液槽1+铅衬双板2；机械诱振器1；已登记腐痕表面2
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×5槽位与≥2格宽实体入槽路线，控制面在侧挡板后；诱振端只在槽内安全landing，外部腐痕不写任意新点。
- **主步骤**：S02:step1：在收货区装入铅衬封板，完成可见双层隔离槽 [1秒原值] → S02:step2：用机械诱振器预约槽内落点并退到旁侧安全线 [1秒原值] → S02:step3：本体真实到槽后合拢两块隔离板并锁闸 [1秒原值]
- **NPC/世界回应**：诱振使实际转场端点锁槽内，1.5预告+入槽后3秒检查；两板合1秒前重验身体完整和退出线。
- **有效修订/恢复**：无合法腐痕则步行，不能强制瞬移；封闭任务液永不变普通清洁水或血源。
- **终态**：同一显化体实际进入隔离槽，液槽与双层封板均完成物理锁闭。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/1/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/1/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/1)

### S03 遮面追逐者

- **模块/结局**：`containment_cage` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送把遮面本体、唯一事故屏和实体照片带到已锁运输舱；图像只游戏内源。
- **原物与供应**：同体1；运输舱1+非成像在位器；不透明面罩1；事故屏1+实体照片1；遮光返程连杆
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×5笼模块含尾隔栏、玩家侧门、侧向不见脸控端、真实暗返程路线；非成像检测不能把画面当面对视。
- **主步骤**：S03:step1：关闭本事件唯一事故影像屏并封存实体照片 [1秒原值] → S03:step2：本体仍在舱内时直接从侧位拉下遮面罩；若已暴怒出舱，玩家用笼尾隔栏诱导位与侧门回控路线引它真实入舱；若未激怒但已出舱，免费遮光返程连杆展开一条真实暗路线，本作事件约定其以2.0步行返舱。 [1秒原值] → S03:step3：在本体真实留舱时锁闭舱门并提交非成像在位检测 [1秒原值]
- **NPC/世界回应**：未激怒且出舱时以2.0实际沿暗路返舱；暴怒仍要真实诱入，不因盖脸清已成立暴怒；舱内3秒拘束允许1秒闸。
- **有效修订/恢复**：停屏/封照片原物保留，所有影像源关闭才可收容；不要求先看脸为主解造前提。
- **终态**：影像源已隔离，同一实体在本事件运输舱内且舱门锁闭。已经目击的暴怒不会因遮脸就被抹掉；是实体重新收容结束门店威胁。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/2/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/2/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/2)

### S04 诊疫医者

- **模块/结局**：`quarantine_hatch` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：来客实际交出一个非人事件样品；雇主检疫工具与薰衣草工作份在岗位。
- **原物与供应**：原事件样品1；长夹1；薰衣草封袋1；检疫盒1+退回口
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：2×2侧台：样品长夹操作点距样品≤1.5且人体不进接触线，封盒实际搬到return_hatch。
- **主步骤**：S04:step1：用长夹把事件样品放入检疫盒 [1秒原值] → S04:step2：在盒外固定薰衣草袋并封闭原样品 [1秒原值] → S04:step3：把封盒送入退回口，在其安静检查时确认离场 [1秒原值]
- **NPC/世界回应**：看薰衣草每次停3秒，接同一封盒后沿真实返程边界离场；需原盒转移回执。
- **有效修订/恢复**：薰衣草任务份不能卖/吃/转玩家药物；已交袋不免费再给第二份。
- **终态**：真实样品已隔离，薰衣草袋在封盒外，本体接受返程并通过离场边界。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/3/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/3/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/3)

### S05 拟声猎群

- **模块/结局**：`staff_ventilation` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：本班两真实人员（玩家+同事）实际位置有两个独立物理采集通道；拟声本体从预装隔离走道到场。
- **原物与供应**：人员位置板双路；气流隔断；隔离核验窗；唯一红色无眼体
- **不能补造的前史**：TWO_REAL_STAFF_POSITIONS：两人当前位置传感回执，不是隐含存在额外员工
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：双路不能都抄同一缓存，读当前时刻有效且不同根采集；柜台侧开关/验窗安全面有真实LOS。
- **主步骤**：S05:step1：同时查看两个真实人员位置指示，定位不可能的求救声 [1秒原值] → S05:step2：关闭该走道连到柜台的气流隔断 [1秒原值] → S05:step3：在隔离窗确认红色无眼实体并登记同一敌人 [1秒原值]
- **NPC/世界回应**：拟声停2.5秒，假救声对比人员事实；无同事在场则该双人题不准入，不造受困人。
- **有效修订/恢复**：气雾只本root提示延迟，不抹真实订单；当前设备失效时保守封区无假身份奖。
- **终态**：两路人员位置证据与本体目击对应，同一事件气流隔断关闭；取消拟声假提示与本事件提示雾，按post_rule降低移动和攻击。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/4/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/4/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/4)

### S06 不灭爬行者

- **模块/结局**：`large_containment` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送预装大型回收槽、返程诱导及密闭循环，明确最大体型通路再让同体到场。
- **原物与供应**：大型体1；回收槽+防回流闸；密闭任务循环；机械返程诱导
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：8×6大型任务位，原装置至少3格宽入槽通道、侧控不在4格扑线、独立玩家回控出口；不可挤掉玩家已造塔。
- **主步骤**：S06:step1：在安全侧关闭回收槽外泄支路 [1秒原值] → S06:step2：开启槽内返程诱导，让本体沿真实通道跨过在位线 [1秒原值] → S06:step3：本体真实入槽后合拢防回流闸并恢复密闭循环 [1.5秒原值]
- **NPC/世界回应**：目标≤4格才重扑2秒预告，落空3秒内1.5关闸；诱导实际入槽，整身通过在位线。
- **有效修订/恢复**：密闭循环用任务独立机械储压，主电故障不关免费解法；收容不宣称永久杀死实体。
- **终态**：同一实体完整入槽、门锁与密闭循环均正常；完成本次收容而非杀死SCP-682。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/5/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/5/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/5)

### S07 附面假人

- **模块/结局**：`mannequin_clamp` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控货运携同一面具附着的非人假人到固定支架，禁止拿真人宿主替代。
- **原物与供应**：非人假人1+面具1；固定支架1；长柄夹1；不透明封匣1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×3支架位含侧控/夹取线和外侧撤离路线；封匣放在可手达的quarantine_counter。
- **主步骤**：S07:step1：在支架侧打开固定扣，保持撤离通道 [1秒原值] → S07:step2：诱使假人抓空后，用长柄夹具把面具摘入封匣 [1秒原值] → S07:step3：合上不透明封匣并把原假人留在固定架上 [1秒原值]
- **NPC/世界回应**：同假人抓空3秒或支架固定3秒可摘1秒；面具实际脱离进匣后合盖1秒。
- **有效修订/恢复**：假人/面具共root，无人类伤害目标；支架固定是必要任务响应，不产生通用陷阱库存。
- **终态**：面具实际脱离同一非人假人并封入匣；本体与污染占用终结，假人不另发击杀奖。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/6/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/6/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/6)

### S08 燃料分身

- **模块/结局**：`fuel_mist` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控异常货运把两份不可售燃料及唯一火形源放入限定防火模块，任务冷凝水提前储备。
- **原物与供应**：燃料原份A/B各1；独立供料阀；原盖板2；任务喷口+有限冷凝水；初始火形1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：5×4防火模块，燃料两侧各.75秒盖；玩家安全侧能启喷，喷区横跨每个现存火形必经返程，不要求主电。
- **主步骤**：S08:step1：关闭本事件供料支路，切断继续取燃料 [1秒原值] → S08:step2：逐一盖住两份可见任务燃料，保留原物ID [1.5秒原值] → S08:step3：打开固定冷凝喷口，让当前全部火形通过已见湿区 [1秒原值]
- **NPC/世界回应**：HP60%一次真实守恒分裂，最多两个池；断料+封两燃料后固定任务诱热盘使所有活火形依次实际走过喷区。
- **有效修订/恢复**：BC02补全“全部现存火形冷凝”的驱动：安全侧诱热盘只本root、原有限热量不可消费出售，遗漏一池不解锁。
- **终态**：供料已截断，两份燃料真实封盖，全部现存火形获得本次冷凝标记；解除整个根谱系的致死门槛。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/7/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/7/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/7)

### S09 失眠潜猎者

- **模块/结局**：`infrared_gate` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：沿BC01固定红外门装置实际交付本体，门梁、手摇传感器和侧按钮先存在。
- **原物与供应**：同潜猎体1；BC01_IR_GATE三侧控；唯一轮廓标签
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：实际检测线x6..10/y20，无地柱；玩家诱导到infrared_lure侧闪，检测tag只在同body真正过线。
- **主步骤**：S09:step1：在红外窗确认同一足印对应的真实实体 [1秒原值] → S09:step2：关闭该走道遮波挡片，阻断本事件干扰源 [1秒原值] → S09:step3：让目标真实通过检测门并提交轮廓标记 [1秒原值]
- **NPC/世界回应**：距玩家≤5且8秒冷却才3秒监听窗；远处不站桩等玩家；红外标记只针对原体。
- **有效修订/恢复**：手摇任务电源不产生buff/电荷；如果挡片已关仍要实际过门，不自动显形。
- **终态**：同一猎者经过真实红外门，轮廓标签提交且遮波挡片闭合；永久取消本事件隐匿与干扰波。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/8/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/8/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/8)

### S10 余光攀行者

- **模块/结局**：`dual_observation` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送同一攀行者进入有编号双窗与中间检测门的专用货架边线。
- **原物与供应**：同体1；固定左右观察窗；红外动作器；编号跟踪牌1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×3边线模块；左右窗可连续覆盖同一过栏轨迹，玩家走侧道不穿货架；两次观测要同body与有序时刻。
- **主步骤**：S10:step1：先看左侧固定窗记录其真实过栏时刻 [1秒原值] → S10:step2：在右侧固定窗确认同一对象，不追着余光转圈 [1秒原值] → S10:step3：目标实际越过中间检测门时压下跟踪牌锁定器 [1秒原值]
- **NPC/世界回应**：真实攀越后2秒抓附恢复，逐窗1秒；检测门实际跨线且2证链一致才锁牌。
- **有效修订/恢复**：只有看到影子不算已拿证据；失去对应关系后重新观察本体可重试，不重刷新怪。
- **终态**：两路真实观测与同一次过门对象一致，跟踪牌锁定提交；解除本作显化体死亡门槛并封闭避视改锁。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/9/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/9/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/9)

### S11 铃声后的瘦影

- **模块/结局**：`sound_box` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控货运送同一原铃，打开运输外盖实际响铃形成本次局部听觉显化。
- **原物与供应**：原铃1；钟舌夹1；隔音填料1；不透明运输箱1；独立手压任务观察灯1@安全侧控制位；真实照亮原实体，不计电器buff/电图节点
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：2×2侧台有实体挡板；固定钟舌与填料不需抬铃，封箱搬原铃要真实路径。 任务手压观察灯照明必须覆盖同体和安全控制视线；MAIN停电时仍可观察，不能用字幕替代真实凝视。
- **主步骤**：S11:step1：从带侧挡板的位置夹住原铃钟舌 [1秒原值] → S11:step2：在不晃动铃体的情况下填入隔音材料 [1秒原值] → S11:step3：把同一固定铃放入运输箱并锁盖 [1秒原值]
- **NPC/世界回应**：被正视后沿真实路线退行3秒，玩家逐次1秒动作；同瘦影不能镜穿。
- **有效修订/恢复**：隔音材料留原箱，不按每次点击补；铃响源封后取消本局显化，不把旁边镜面当通用传送端。
- **终态**：原铃钟舌被真实固定且全铃封箱；本店局部听觉显化随源隔离离场。并非宣称原作暴露后果能普遍被封箱治愈。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/10/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/10/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/10)

### S12 棘触心核

- **模块/结局**：`sludge_recovery` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控异常配送在任务隔污盘实际装有限黏液并带本体/外膜，独立黏液支路不接普通水。
- **原物与供应**：本体1+共享触须；原黏液一批；封闭吸附筒1；隔污栅1；专用截止板
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×3侧台，长鞭3格线不覆盖筒侧控；吸附1.5、插栅1，各有真实槽位。
- **主步骤**：S12:step1：关闭事件黏液支路，保留普通排水 [1秒原值] → S12:step2：在抽打落空后把原黏液吸入封闭筒 [1.5秒原值] → S12:step3：将带柄隔污栅插入棘触回收槽，锁住强化外膜 [1秒原值]
- **NPC/世界回应**：2秒锁线落空3秒回收，原黏液通过真实吸管入筒，外膜真实卡入槽；非所有触须瞬间消失。
- **有效修订/恢复**：无额外回血；断黏液支路不能误断普通排水，封筒永久保原物ID。
- **终态**：本次黏液原物完成封存、事件支路关闭、棘触外膜被回收槽实际夹住；取消长鞭并降低表内黏液外膜防御。本版没有额外回血能力。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/11/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/11/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/11)

### S13 楼梯口无面影

- **模块/结局**：`service_door` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：永久检修门外模块已封闭真实楼梯入口，只开放可见门槛局部；声源本次真实启动。
- **原物与供应**：检修门1+锁杆；原隔音垫1；测距标线；门内占用传感
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×2门外模块，不扩建无限可走楼梯；门外三个1秒控制均在攻击半径1.5外的侧面可达。
- **主步骤**：S13:step1：在门外测距标线确认声源距离不随下探改变 [1秒原值] → S13:step2：保持在门外，把隔音垫卡入原检修门槽 [1秒原值] → S13:step3：退出门槛并锁闭原门，确认无人留在内侧 [1秒原值]
- **NPC/世界回应**：门口范围2秒预告后3秒静默；绝无真实受困儿童，玩家无需走进门内。
- **有效修订/恢复**：门内任何真人/玩家占用阻止关锁，先实际撤离；封门不影响原便利店唯一出口。
- **终态**：原检修门闭合、隔音垫固定且门内没有玩家/普通顾客；局部门口显化终结。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/12/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/12/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/12)

### S14 缝材造物熊

- **模块/结局**：`finite_crafting` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送母体、工作台和编号三份非人缝材，出生预算绑定各材料。
- **原物与供应**：母体1；三原缝材A/B/C各1；免费封材盒3；长柄夹；断扣；残片槽
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×3工作模块：原料、在制、造物、残片每种有槽；存放三盒不可阻回撤。
- **主步骤**：S14:step1：用长柄夹取走尚未消耗的带标签缝材，或工作台同ID已扣料半成品，逐份封盒；每份仅一次，已成造物的材料转步骤2处理。 [1.5秒原值] → S14:step2：若某份材料已制成造物，先击退该造物并封存其真实残片 [1秒原值] → S14:step3：切断工作台原断扣，核对三份材料去向全部闭合 [1秒原值]
- **NPC/世界回应**：每10秒最多消耗一份、3秒装配；每份只处于原料/半成品/活造物/残片/封存一种；活造物须先真实击退。
- **有效修订/恢复**：没有子体必须先等生成；先封材料合法抑制出生，已成子体不被关台凭空删；3份都封才解母体死亡锁。
- **终态**：三份材料分别处于已封原料、已封半成品、或已击退造物的已封残片之一，工作台断扣关闭。子体原本可正常死亡；仅母体的致死门槛此时解开。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/13/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/13/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/13)

### S15 孵卵拟人群

- **模块/结局**：`finite_incubator` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送母体与两枚外卵，内部唯一备用卵属于同体生物预算，免费三格冷封盒先落位。
- **原物与供应**：母体1+内备用卵1；外卵A/B；三格冷封盒；捕卵漏斗+备用落托盘；任务断温片
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×3外侧控，外卵第10/20秒孵化有3秒预告；每份冷封.75分段，漏斗不与玩家重叠。
- **主步骤**：S15:step1：关闭本事件供温，阻止两个外卵继续孵化 [1秒原值] → S15:step2：逐格封存未孵化外卵；已孵化者击退后收走真实备用卵 [1.5秒原值] → S15:step3：母体吐卵预告后，用固定漏斗把内部备用卵导入第三格并封盖 [1秒原值]
- **NPC/世界回应**：两外源都已封且供温断→母体必发3秒吐卵预告→同内卵入漏斗或原备用盘；3秒恢复封1秒。
- **有效修订/恢复**：必要吐卵属于任务生产，不被普通封技取消；漏接卵不再孵化、不复制，可长夹同卵封第三格。
- **终态**：本次三份繁殖源均实际冷封；已经孵化的子体均已击退。母体失去本作复起门槛，可以被后续伤害击退。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/14/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/14/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/14)

### S16 刀肢蟹队

- **模块/结局**：`shallow_pack` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送四个原编号蟹到预装浅水运输区，水量和排口是真实有限任务载荷。
- **原物与供应**：蟹1–4；浅水盘+排水盖；挡水片；侧翼低挡板
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：5×4浅水模块，干侧3按钮、排水真实高程与出水路径；4个池都有身体容纳和至少一条退出水区路。
- **主步骤**：S16:step1：从安全侧打开本事件浅水排口 [1秒原值] → S16:step2：把挡水片落下，阻止同一小水区再次连通 [1秒原值] → S16:step3：合上侧翼通道的矮挡板，确认四只都离开藏身积水 [1秒原值]
- **NPC/世界回应**：最多2蟹同时预告；排净后存活蟹真实走上干侧，已死蟹由真实death_receipt闭合编号。
- **有效修订/恢复**：不要求死蟹复活出水；消协同只弱化活池，所有必要池真实终结才根结。
- **终态**：对应浅水区排净且隔水、侧翼挡板到位；四个原编号中，存活者已离开藏身积水，死者有同根真实击退回执；对存活池取消协同围切并减速。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/15/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/15/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/15)

### S17 塑料火烈鸟群

- **模块/结局**：`territory_frame` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控物流带原运输框、原物流牌和六只编号塑料鸟，数量固定。
- **原物与供应**：原框1；物流牌1；原鸟1–6；免费领地隔栏
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×4领地模块，框3次.5秒真实推行，每次位置保留；外侧闸有玩家对外口，不关人在内。
- **主步骤**：S17:step1：把同一运输框沿合法路线推回领地标线 [1.5秒原值] → S17:step2：在外侧固定原物流牌，核对六个原编号；已死亡的塑料鸟用实际残片/死亡回执核对，不要求复活或回到框边。 [1秒原值] → S17:step3：从玩家侧合拢领地隔栏，留下对外撤离口 [1秒原值]
- **NPC/世界回应**：鸟返护框每次停2秒；六原编号逐个对照活体或死残片/真实击退回执。
- **有效修订/恢复**：禁止为了核齐编号重生死鸟；弱化只存活池，框牌不可刷出补鸟。
- **终态**：原框原牌与六个原编号及其存活/击退状态匹配，隔栏到位；只对仍存活的鸟取消全店追击并降低数值。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/16/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/16/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/16)

### S18 双灯猎行者

- **模块/结局**：`paired_lanes` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送两枚原编号灯头实体及本次真实到货记录，分流板/遮光闸班前已装。
- **原物与供应**：原两实体A/B；原到货板；反光分流板1；遮光闸+两编号检测位
- **不能补造的前史**：DELIVERY_MANIFEST：本次真实清单与两物编号吻合
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：双实际同向直道长≤10格，侧闪线与侧控独立，配对冲锋预约原子成功才启动；空间不足截短，不补瞬移。
- **主步骤**：S18:step1：核对原到货记录与门口实体，确认两个灯头不是车辆 [1秒原值] → S18:step2：在走道侧放下固定反光挡板，使两实体走不同真实路线 [1秒原值] → S18:step3：存活两池已分离时合上遮光闸并记录两牌；如已死一只，保留其真实击退回执，仅让存活者经过本侧检测位。 [1秒原值]
- **NPC/世界回应**：两实体走不同真实路；一只死则其真实击退回执代追踪，存活者到检测位；双方准备好才双冲。
- **有效修订/恢复**：.5秒冲后恢复不足1秒操作，使用侧挡板安全控，不声称收招全覆盖。
- **终态**：两枚原编号均由真实追踪或同根击退回执闭合，挡板/遮光闸到位；对存活者取消同步冲锋并按post_rule弱化。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/17/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/17/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/17)

### S19 食宴巨客

- **模块/结局**：`banquet_service` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控任务配给不可售非人试餐，巨客真实到服务隔栏外，余份有限。
- **原物与供应**：事件试餐份1+密封备用余餐1；长柄推餐盘；服务隔栏；余餐封盒
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×3隔台工作区，盘有食才触发一次4秒进食；三个1秒动作需分段与实际搬盘核时。
- **主步骤**：S19:step1：核对原试餐封签，把指定盘送到服务隔栏外侧 [1秒原值] → S19:step2：在巨客真正进食时关上侧向服务隔栏 [1秒原值] → S19:step3：收走本事件剩余试餐并封存，结束追加索食 [1秒原值]
- **NPC/世界回应**：同体真正吃原份，4秒服务停攻；余份原物收回封盒，没余份时核数量0而非造一份。
- **有效修订/恢复**：试餐不能给玩家回血、卖钱或产设施支援；吃完不无限加料刷新4秒。
- **终态**：同一试餐实际交付并被消费，服务隔栏闭合，余餐封存；取消暴食扑咬并降低体型外甲优势。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/18/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/18/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/18)

### S20 沼液伏客

- **模块/结局**：`organic_waste` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实营业有机废物或受控异常样品废料已在原盘，明确事件回流口，只对该一批摄食。
- **原物与供应**：原有机废料1批；无机隔污盘；长夹；事件排污封帽；密闭废物柜
- **不能补造的前史**：ORGANIC_WASTE_RECEIPT：真实废物制作或受控样品清退回执
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×3长夹侧控在毒斑外，盘到封柜可重搬；普通排水不被任务封帽全断。
- **主步骤**：S20:step1：用长夹把事件有机废料收进无机隔污盘 [1秒原值] → S20:step2：盖住该事件排污口，阻断摄食回流 [1秒原值] → S20:step3：把原废料盘送入封闭废物柜，确认地上无该份残留 [1秒原值]
- **NPC/世界回应**：未威胁/饥饿时受限访客不敌对；吐斑最多1片、2秒预告3秒留斑，实际清原食源。
- **有效修订/恢复**：无真实废料不补历史；封柜只产原废物保管/清运待办，不能生成可出售产品。
- **终态**：唯一事件有机废料真实隔离、对应回流口关闭；取消吐沼攻击和黏液外层，保持当前HP。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/19/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/19/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/19)

### S21 九尾伪装客

- **模块/结局**：`double_window` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：伪装体携带当场假订单及一件由雇主隔离库存借出的展示物，真订单历史不被替换。
- **原物与供应**：原展示物1；假订单纸1；两侧固定验窗；原退单盘；身份牌
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：两侧视窗须独立物理视角能看同体，柜台侧1秒动作；距本体≤5才有3秒说服窗。
- **主步骤**：S21:step1：把原订单实物放入固定验货窗，不接受口头改写 [1秒原值] → S21:step2：从另一个不受遮挡的侧窗确认同一对象的狐形特征 [1秒原值] → S21:step3：撤回实际假订单并封入退单盘，给本体记录身份牌 [1秒原值]
- **NPC/世界回应**：假订单实际撤销、展示原物归隔离盘；伪装共一个池，外观变化不洗毒/塔锁。
- **有效修订/恢复**：假订单不是sale或正常顾客付款；无真实证据不能给身份牌，已知塔锁不被外貌欺骗。
- **终态**：两个独立物理证据绑定同一来客，原假订单已撤回；取消外观干扰与提示暗示，按post_rule降低数值；不改变既有真实工单历史，外观本身不洗掉已确认塔锁。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/20/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/20/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/20)

### S22 畏光烟影

- **模块/结局**：`three_shadow_lamps` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：永久登记三个暗节点与三盏独立任务灯，受控本体从其中合法点到场。
- **原物与供应**：A/B/C三任务灯及独立900秒电池；安全有线控端；C同体在位器+封牌
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：采用ENV坐标A[20.5,18.5]B[22.5,18.5]C[24.5,18.5]、控端[19.5,19.5]；先亮A/B留C，必须有C更远于玩家的驱光几何。 三节点需原遮光筒/局部照明控制实际挡开MAIN入射；所有真实有LOS灯累加照度，节点总照度<0.2才为暗点。不能只模拟任务灯就断言环境常照为0。
- **主步骤**：S22:step1：先打开并锁定A、B两处持续任务灯，保留C为唯一暗节点。 [1.5秒原值] → S22:step2：从安全侧照向本体，等它真实转至C；若本已在C，则通过同一实体在位检测，触发一次1.5秒公开防御确认停顿（共享8秒冷却）。必须保证玩家可站在使C更远的安全控制位；原位确认不是转场事件。 [1秒原值] → S22:step3：在C真实到达后的1.5秒恢复，或原位确认的1.5秒停顿内，从同一安全有线控制位用1秒同时提交C灯亮起与封牌闭合。 [1秒原值]
- **NPC/世界回应**：真实到C恢复1.5秒；初始就在C则真实在位确认给同样1.5秒（共8秒CD）；1秒同时亮C+封牌。
- **有效修订/恢复**：失败末步C仍暗，A/B保持，不能先全亮再等暗点；原位确认不发movement/跨区伤。
- **终态**：A、B持续任务灯已锁定；本体真实在C且C灯亮起/封牌同时提交；三节点均受持续照明，解除本次局部显化致死门槛并禁用逃光转场。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/21/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/21/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/21)

### S23 路口焰眼犬

- **模块/结局**：`crossroad_gaze` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：永久前场十字路口有两真实通道、返程与可遮反射面，犬从受控来访路径真实进入。
- **原物与供应**：原犬1；长柄套罩器；眼罩2片；两导栏；反射遮帘；返程闸
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×6十字模块不能只是贴十字地纹；至少四可走臂，侧控不直面眼；反射段必须实际可见、总光程≤5。
- **主步骤**：S23:step1：把十字路口两条真实通道的引导栏放到原标线 [1秒原值] → S23:step2：犬只在路口停驻后用长柄套罩器依次装上两枚不透明眼罩片 [1.5秒原值] → S23:step3：确认两片到位并关闭前场反射面遮帘，放行返程通道 [1秒原值]
- **NPC/世界回应**：犬离路口才预告2秒回原路口，到场停4秒足够两次.75罩；占用落点取消不改贴脸点。
- **有效修订/恢复**：封两眼并遮真实反射面才放行实际返程；已遮眼不生成新反射光或镜穿。
- **终态**：同一犬只真实停在合法十字路口，两眼均遮蔽且相关反射面遮帘关闭，经预定返程通道离场。
- **原来源**：[monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/22/mechanism), [monster_scp_a_md01.json](../content/monster_scp_a_md01.json#/monsters/22/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/22)

### S24 黑刃复归者

- **模块/结局**：`blade_stop` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控货运原空箱和门外挡板就位，黑刃体在原箱线外实际留下本次可观划痕。
- **原物与供应**：原空货箱1；卸货挡板；外侧止动闸；同体黑刃1（共享部件）
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：同刃本次真实在原见证边留下可观划痕，读取不生成痕迹
- **物理绑定**：4×3直刺模块：4格锁线穿箱口、玩家真实侧移点、控闸不在刺线；箱体固定不可被普通撞毁。
- **主步骤**：S24_step_1：在货运门外确认本次黑刃划痕并拉开卸货挡板 [1秒原值] → S24_step_2：诱使一次锁定直刺穿入已登记空货箱口，侧移避开 [0.5秒原值] → S24_step_3：在直刺落空恢复期关闭箱体外侧止动闸 [1秒原值]
- **NPC/世界回应**：诱同刃真实插箱口，落空固定3秒，外闸1秒夹住同刃后永久禁刺。
- **有效修订/恢复**：没有实际刺入不能点闸成功；误时等下一完整预告，原空箱不需要一次性重复购买。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S24_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/0/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/0/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/23)

### S25 吞影小像

- **模块/结局**：`shadow_capture` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：固定全向任务灯与两反光板先落位，真实玩家影由同灯投射，同小像从影区到场。
- **原物与供应**：小像1；固定灯1；两反光板；透明罩+外闩
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×4补光模块，两反射入射/法线要计算真实交叠；两侧控在影区外，设无影圈和邻接玩家影诱位。
- **主步骤**：S25_step_1：在影区外转动第一面已安装反光板消去柜侧黑边 [1秒原值] → S25_step_2：转动对面的第二反光板补齐轮廓缺口 [1秒原值] → S25_step_3：等目标进入无影圈后合上透明罩外闩 [0.8秒原值]
- **NPC/世界回应**：补两边后用圈外玩家真实投影诱本体沿公开地面线进入圈；失影后在圈内2.5秒疑惑停顿供.8秒关罩。
- **有效修订/恢复**：BC02补足“等目标入无影圈”驱动；本体非瞬移，灯断电以独立任务电源保免费主解，不把没有影当死锁。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S25_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/1/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/1/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/24)

### S26 幼猫幻相虎

- **模块/结局**：`evidence_delivery` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控运输笼实际承受同体重量；运输过程本体咬原见证封条，两个事件有独立时间/物ID。
- **原物与供应**：承重板1；同体咬痕原封条1；齿距尺1；证据夹+同体档案
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：LOAD_PLATE_SAMPLE：同body真实压板记录；TOOTH_WITNESS：同body实际咬运输见证条，非直接注入齿距答案
- **物理绑定**：离体读板.8、原咬条比尺1、双证锁档.8；原观察记录可回看，但玩家未读不授知识。
- **主步骤**：S26_step_1：从安全侧读取被压下的承重板刻度 [0.8秒原值] → S26_step_2：把本次深齿痕封条置入比对槽 [1秒原值] → S26_step_3：将重量与齿距两份证据锁到同一异常个体档案 [0.8秒原值]
- **NPC/世界回应**：扑空2.5秒供侧台1秒；若封条丢失可同体咬模块固定无机见证条一次，实际生成新证据不伤玩家。
- **有效修订/恢复**：拒绝以卡面写有深齿痕就当世界已产；两个证据绑定同body且不同事件根。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S26_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/2/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/2/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/25)

### S27 红池支口

- **模块/结局**：`pool_cap` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：班前service_yard密闭运输支口模块装好两截流板与排空柄，异常红液只任务介质非人体血。
- **原物与供应**：本地支口1；两预装截流板；排空柄；有限出生预算6
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：5×4干侧模块，两控点始终不进液区，第二条玩家逃路不能被子体占尽；每10秒2秒出池预告。
- **主步骤**：S27_step_1：闭合支口外围已安装的第一截流板 [1秒原值] → S27_step_2：在下次出池预告间隙闭合第二截流板 [1秒原值] → S27_step_3：从干侧拉下排空柄，封住本店局部支口 [1.2秒原值]
- **NPC/世界回应**：最多同时3只、总6；封源后停止排队出生，已出子体先取消敌对，沿同root召回线返池再排空。
- **有效修订/恢复**：BC02补封源后回收流程：不能关板按钮瞬删离池子体；路径阻则保持停攻等待清路，死子体读真实回执。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S27_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/3/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/3/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/26)

### S28 离体肉殖团

- **模块/结局**：`tissue_cargo` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控异常配送同批污染包装与两真实脐索到货，货物不是正常顾客食品。
- **原物与供应**：原包装1批；两脐索；双夹具；隔离匣
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×3侧台，各脐索.6秒夹闭单独提交，包装到packing隔离匣需真实推动路线。
- **主步骤**：S28_step_1：确认两处连到货物批次的组织脐索 [0.8秒原值] → S28_step_2：用预置夹具先夹闭第一条再封第二条 [1.2秒原值] → S28_step_3：把同批污染包装推入既有密闭隔离匣 [1秒原值]
- **NPC/世界回应**：根首次≤60%且脐索未封才守恒分裂一次；两后继同root，原包装封闭对全部存活后继弱化。
- **有效修订/恢复**：死根不能先分裂逃死；只一条夹住不会复制第二工具/新脐索；原污染包装不能销售。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S28_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/4/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/4/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/27)

### S29 暗育蜈群

- **模块/结局**：`light_capture` / `rule_weaken`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：固定BC01任务灯和反光板已有，受控运输物实际遮光袋挂到灯前，产生本次暗区。
- **原物与供应**：遮光袋1；BC01_TASK_LIGHT；反射板；清障钩；同体1
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：受控配送把同袋真实挂到任务灯前形成实遮挡，不能只写dark=true
- **物理绑定**：采用真实lit_rect[6,13,4,5]，目标[8.5,15.5]、侧闪[9.5,16.5]；完整体型在光内连续4秒。
- **主步骤**：S29_step_1：清掉本次挂在任务灯前的遮光袋 [0.8秒原值] → S29_step_2：转动常备补光反射板照满它占据的暗区 [1秒原值] → S29_step_3：保持本体连续处于可见补光区4s，等待体节回缩完成 [0秒原值]
- **NPC/世界回应**：首次完整光区咬击2秒+落空2.5秒保持原位共4.5秒；玩家可侧闪，无须购冻结塔。
- **有效修订/恢复**：袋真正挂上才暗；清袋不等于身体已回缩；离光计时重新从0，灯手摇保持不受主电停电影响。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S29_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/5/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/5/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/28)

### S30 银丝猎婆

- **模块/结局**：`silk_recovery` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同体在已预约两地线实际吐两段原丝，侧灯照见；8秒只是危险活性，不是原物销毁。
- **原物与供应**：两同源原丝ID；侧光板；长柄线轴；隔离筒
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：两线各≤2格、宽.25；丝源到安全侧收卷点可达，摆丝不封唯一路；侧光反射真实计算。
- **主步骤**：S30_step_1：把侧光板转向已出现反光的货架缝 [0.8秒原值] → S30_step_2：从安全侧用长柄线轴收起两段同源发丝 [1.2秒原值] → S30_step_3：将线轴锁入隔离筒，切断本次丝网牵引 [0.8秒原值]
- **NPC/世界回应**：铺丝后3秒梳理；危险丝8秒后变同ID惰性残丝留原地可卷，收一段记一段不可再生。
- **有效修订/恢复**：BC02修复TTL软锁：过期不能消失导致永远缺两段；若异常回抽则同ID回线轴源槽，长柄仍可收。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S30_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/6/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/6/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/29)

### S31 鹿骨饥壳

- **模块/结局**：`skull_limiter` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送无人佩戴的原头骨入单向陈列柜；不存在逼玩家戴头骨的前置。
- **原物与供应**：原头骨1；观察挡片；长夹；限位架+硬壳箱
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：3×3柜侧模块，固定扑域1.8格和玩家侧退路；夹取1.2的操作点在扑线外。
- **主步骤**：S31_step_1：关上陈列柜的单向观察挡片，保留外侧视窗 [0.8秒原值] → S31_step_2：用外侧长柄夹将无人佩戴的头骨引入限位架 [1.2秒原值] → S31_step_3：闭合架外封扣并将同一实物归入硬壳箱 [1秒原值]
- **NPC/世界回应**：扑空摇2.5秒可夹同骨入限位；同骨进箱再封扣，不是读取hidden状态直接封。
- **有效修订/恢复**：已封不再扑；人体不能成为宿主或被塔攻击，头骨未入架不能关空箱算成功。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S31_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/7/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/7/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/30)

### S32 涌兽陶瓮

- **模块/结局**：`jar_chamber` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送原陶瓮到预装扶正架、恒温舱；出生预算8、同时6预登记，舱内声源独立任务设备。
- **原物与供应**：陶瓮1；扶正架；定温隔离舱；固定本根诱声源；子体预算8
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：6×5舱模块，侧控外置、所有活子体能沿真实通道回舱，门1.2秒扫掠不得夹玩家；原瓮不受伤。
- **主步骤**：S32_step_1：从外侧操作预装扶正架，让瓮保持竖直 [1秒原值] → S32_step_2：将隔离舱温控锁到公开稳定档并停止震动 [1秒原值] → S32_step_3：引回余下独立子体至舱内后合拢外门 [1.2秒原值]
- **NPC/世界回应**：扶正+稳定停出生；声源令每个原活子体真实返舱，进舱后停止攻击保持在内，全部活体在内才关门。
- **有效修订/恢复**：死者以真实击退回执闭合，不重生；刺激只提前预算出生，召回失败不新增子体补数。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S32_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/8/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/8/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/31)

### S33 镜头霉巢

- **模块/结局**：`camera_mold` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：永久监控已有且正常实际开机，本格有限污染包装在受控配送中渗出两处同源霉斑。
- **原物与供应**：同污染包装1；两原霉斑；原监控终端及绑定摄像头；小型湿出口阀；封口夹
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：低层货格边缘连接可走地面，镜头真视线能同时定位两斑；外侧阀/封夹不在孢子半径内。
- **主步骤**：S33_step_1：在实际监控画面确认两处同源霉斑 [1秒原值] → S33_step_2：关闭对应商品格的小型加湿出口 [0.8秒原值] → S33_step_3：把定位框投回同一格并密闭污染包装口 [1.2秒原值]
- **NPC/世界回应**：2秒预告+1.5危区+4秒静默；观测保留，关真正湿源再封原包装。
- **有效修订/恢复**：监控属必要任务观察时配置独立手摇镜头旁路；主电掉不强迫修普通设备；不同怪F59可选摄像机故障不共抢此主解源。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S33_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/9/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/9/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/32)

### S34 寻声线团

- **模块/结局**：`sound_box` / `rule_leave`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：原线团真实送到BC01打包台，有限有声实体与硬盒同台先落位。
- **原物与供应**：原线团1@[17.5,7.5]；长夹；消音挡片；原硬盒
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：BC01 sound_side[17.5,6.5]、sound_safe[21.5,6.5]；实体挡片仅截实际声线，不全图免伤。
- **主步骤**：S34_step_1：从箱外折下消音挡片，减少扬声方向 [0.8秒原值] → S34_step_2：待本轮音符结束，以长夹把线团推入原位硬盒 [1.2秒原值] → S34_step_3：从盒外锁闭双扣，保留完整线团不剪断 [1秒原值]
- **NPC/世界回应**：6拍后3秒静默，每步1.2或1分次完成；真实推同线团进原盒，再锁双扣。
- **有效修订/恢复**：不剪线、不把静默当终态；原有声根封后清传播区与排队爆音。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S34_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/10/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/10/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/33)

### S35 失控重载玩具车

- **模块/结局**：`remote_vehicle_lane` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：真实配送带配对遥控器与原玩具车，透明运输盖实际压卡键，车在固定止动端车道。
- **原物与供应**：原车1；同配对号遥控器1；透明盖；机械断电杆；原止动端
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：最长25.2格实际车道不是保证存在；平行安全控端+侧闪路，撞首次阻挡即停止该次，不继续同attack。
- **主步骤**：S35_step_1：在遥控盒外读出与车底相同的配对编号 [0.8秒原值] → S35_step_2：打开卡住按钮的透明运输盖 [1秒原值] → S35_step_3：松开按钮并拨动机械断电杆，确认车辆已停稳 [0.7秒原值]
- **NPC/世界回应**：到止动端停2.5秒，读号.8/开盖1/松键断电.7分别保留；不是靠玩家诱导秘密AI追人。
- **有效修订/恢复**：遥控器不可从别车替换，主电无关；断电后车实际速度0且驻车才终态。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S35_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/11/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/11/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/34)

### S36 惊笑偶像

- **模块/结局**：`idol_blackout_box` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：原陈列偶像由受控配送上原格，侧遮帘/长夹/遮光盒预备；不默认玩家已盯12秒。
- **原物与供应**：原偶像1；原帘；长夹；遮光盒
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：陈列到packing原盒必须实体滑槽/长夹通道或玩家搬运，不能在packing远程夹goods_shelf；选相邻同模块别名。
- **主步骤**：S36_step_1：从侧面放下原陈列位的遮视帘，停止继续凝视 [0.8秒原值] → S36_step_2：确认同一偶像仍在原格，用长夹推入遮光盒 [1秒原值] → S36_step_3：扣紧盒盖与两侧遮光缝 [1秒原值]
- **NPC/世界回应**：真实主动凝视12秒+3秒笑声才显唯一低空惊吓池；.6慢行、1格1.5秒预告，退2格实走后才再攻。
- **有效修订/恢复**：常态封存不造危险/根奖励；已显情况下同偶像封盒取消显化，不能拆坏刷影。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S36_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/12/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/12/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/35)

### S37 噬口排水虫

- **模块/结局**：`pipe_clamp` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：永久清洁支管模块中本次假排口由实体实际收缩可见；唯一阀和外箍班前已装。
- **原物与供应**：同虫体1；检漏片1；唯一支管阀；外箍；可达吐出托台
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：阀到虫口≥2.5格；2秒出管预告+2.5秒展开，玩家先在侧控位，外箍远程机械连杆1秒，不要求2.5格冲进咬区。
- **主步骤**：S37_step_1：用既有检漏片确认一处会收缩的假排口 [0.8秒原值] → S37_step_2：从干侧关闭该支管唯一阀门 [1秒原值] → S37_step_3：在虫体完全吐出后压下外侧防回缩箍 [1秒原值]
- **NPC/世界回应**：断阀真实迫出同体，完全展开后箍锁；露头/身共享池，无回血缩管。
- **有效修订/恢复**：过窗可保持阀关，虫按同一2秒预告再次展开，CD不刷新原HP；未展开点箍无效但可重试。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S37_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/13/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/13/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/36)

### S38 立体镜旁观者

- **模块/结局**：`glasses_storage` / `rule_leave`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：本事件原纸框镜从任务柜实际领取，旁观者是同一未受干涉访客。
- **原物与供应**：纸框镜1；原收纳槽+盖@verification_desk
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：沿BC01_MIRROR_CASE原位置，实际从所有佩戴者取回同镜，不能存在第二复制镜。
- **主步骤**：S38_step_1：在地面安全标记外停止触碰旁观者，放下手中非必要操作 [0.5秒原值] → S38_step_2：把本事件纸框镜取下放入对应收纳槽 [0.8秒原值] → S38_step_3：合上收纳槽遮光盖，确认没有第二名佩戴者 [0.8秒原值]
- **NPC/世界回应**：平时封存无追逐；只有真实触碰/攻击才同体敌对，落空2.5秒分步封镜。
- **有效修订/恢复**：未干涉妥善收纳明确无根奖；禁止反复戴镜/摘镜生成普通顾客支付/广告翻倍基数。
- **终态**：同一纸框镜已放回槽内、遮光盖实际闭合、没有真实佩戴者；若此前没有干涉危险则为无奖妥善保管，不能刷根结算。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/14/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/14/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/37)

### S39 游走骨龙

- **模块/结局**：`sample_foot_limiter` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控配送骨架与原任务非食用样本盘，止动台/脚圈班前装好。
- **原物与供应**：同骨架1；非食用样本盘1；脚部限位圈；外侧脱扣柄
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：5×4大体模块，样本盘靠实际台缘，咬台点与脚圈对齐且玩家侧控可退；原路径足体型。
- **主步骤**：S39_step_1：把本次货运样本盘送到已登记止动台边 [0.8秒原值] → S39_step_2：在骨架咬住台缘的2.5s动作中扣住脚部限位圈 [1秒原值] → S39_step_3：拉下限位圈外侧脱扣柄，使其改用缓步姿态 [0.8秒原值]
- **NPC/世界回应**：原盘诱使实际咬台2.5秒，扣圈1秒后脱扣.8只改缓步姿态，不让共享四肢变4池。
- **有效修订/恢复**：引导失时可同盘重试但不消耗/复制餐食，任务盘没有一般诱饵/销售功能。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S39_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/15/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/15/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/38)

### S40 取述影客

- **模块/结局**：`original_paper_take` / `rule_leave`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：已存在唯一描述纸与实际正在播报的原终端源；若是受控配送须先交纸到原槽再实际播放。
- **原物与供应**：原纸1；播报终端；BC01_PAPER_TRAY；图形告示牌
- **不能补造的前史**：ORIGINAL_TEXT_CREATED：唯一原文载体生产与当前持有链可查
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：沿BC01 paper_load/paper_take/paper_wait真实位置，盘.5秒移路径；NPC4格到取位+2.5秒拿原纸另计。
- **主步骤**：S40_step_1：关闭本次正在播报文字内容的终端声音 [0.8秒原值] → S40_step_2：把已存在的描述纸原件装入取件盘，不新打印副本 [1秒原值] → S40_step_3：将原件取件盘推出交接槽并退到界外；该.8s操作只提交摆盘，随后等待同一影客实际取走原件，满足三条件才完成。 [0.8秒原值]
- **NPC/世界回应**：静音+原纸在外盘+玩家界外时进入SA02有界同根非战斗取纸，实际转移原ID才成功。
- **有效修订/恢复**：不新打印副本替原件；原件被拿走后封源，持续毒不把取纸无限重置。
- **终态**：播报终端已静音；同一描述纸原件ID已被同一影客从外侧取件盘实际取走；玩家已退出交接界。三条件同时成立才发S40_rule_complete；推出托盘本身不发终态回执。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/16/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/16/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/39)

### S41 地窖食客群

- **模块/结局**：`burrow_light` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：受控模块预装真实货运洞口、原隔栅和白昼灯面；领猎者实际过洞留下本批足迹。
- **原物与供应**：领猎者1；有限援手预算2；同批足迹；洞口隔栅；独立任务灯
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：5×4洞口模块，两侧控有独立退路；第12/24秒援手仅从洞后实际空位生成，照亮覆盖真实整个猎区。
- **主步骤**：S41_step_1：从地面侧确认本批异常足迹来自哪一个货运洞口 [0.8秒原值] → S41_step_2：拉下该洞口预装隔栅，截断尚未进场的援手 [1秒原值] → S41_step_3：展开已安装白昼灯面，把本根猎区照亮 [1秒原值]
- **NPC/世界回应**：关栅取消未提交援手，现存援手继续真实战斗；领猎3格黑暗扑落空2.5秒可1秒灯。
- **有效修订/恢复**：脚印由实际行走产生，不把未知暗处当无限出生点；白昼灯不是电图节点，不因主电掉让解法失效。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S41_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/17/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/17/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/40)

### S42 断拍窥猎者

- **模块/结局**：`rhythm_tracking` / `kill_unlocked`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同体在任务观测区真实发连续两组颈响并踩原粉迹地面；听振板/显迹幕预装。
- **原物与供应**：同体1；听振板；足印登记板；预装粉幕有限一幕
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×3观测模块，声方向与足印同body/连续时刻对应；拉幕侧控不在2.4格锁扑线。
- **主步骤**：S42_step_1：通过已放置的听振板辨明连续两组颈响方向 [1秒原值] → S42_step_2：将同方向的真实足印轮廓登记到定位板 [0.8秒原值] → S42_step_3：在断拍扑空的恢复期拉下预装显迹粉幕 [0.8秒原值]
- **NPC/世界回应**：真实停声触发断拍扑，落空2.5秒拉幕.8显同体；普通低效音不是新怪或全图索敌证据。
- **有效修订/恢复**：粉幕未落可取消不耗，已落保持本根显迹，不反复补粉造新伤害/收入。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S42_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/18/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/18/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/41)

### S43 闭店巡场员

- **模块/结局**：`source_link` / `rule_leave`；已有 BC01 有限几何参考，仍未接客户端。
- **真实来源**：原接驳卖场确实处于闭店，连接门/源场景ID存在；本地面板只发请求不是写源真相。
- **原物与供应**：原巡场体1；接驳面板；源营业/照明双回执；原后门外闩
- **不能补造的前史**：SOURCE_MALL_CLOSED：连接源场景真实营业状态与通路回执
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：BC01 s43_panel→源3秒ack，巡场12格实际返程到s43_exit，再玩家1秒外闩；后门通路被占不能直接终态。
- **主步骤**：S43_step_1：沿既有出口标识确认本次接入卖场的唯一通路 [0.8秒原值] → S43_step_2：在本地接驳面板完成已显示的开店流程复位 [1秒原值] → S43_step_3：等原接驳卖场的照明与营业指示同时恢复，再关闭本店接驳门 [1秒原值]
- **NPC/世界回应**：源真实开店先撤敌对，即使出口暂阻也不能继续攻击；按SA02同root真实退出回应。
- **有效修订/恢复**：本店主电恢复不等于源开店；阻路只等实际清路，不造新门/传送人；面板重按不刷回执。
- **终态**：同一接驳卖场实际开店状态回执已收到，无面巡场员停止攻击并沿原门完成退场，接驳门外闩关闭；不是仅按面板按钮就完成。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/19/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/19/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/42)

### S44 双灯影幕

- **模块/结局**：`dual_projector` / `rule_leave`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：两独立任务投影灯和白幕门班前已装；本次一侧真实检修故障引起影像越幕，不造普通电网故障。
- **原物与供应**：原双灯2+独立检修电源；原白幕1；外侧转柄；幕外遮断门
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：4×3影幕模块，两真实光束交叠与幕面尺寸吻合；控面全部在2.5格威胁区外，轮换保持一灯。
- **主步骤**：S44_step_1：在界外检查两灯指示，只检修故障侧并维持另一侧供电 [1秒原值] → S44_step_2：把预装白幕转到两个光束真正交叠的位置 [1秒原值] → S44_step_3：从幕外扣合遮断门，隔离已经完整落在白幕上的本次影像 [1秒原值]
- **NPC/世界回应**：先仅修故障灯1秒，再真实转幕1秒接住全部影像，再外门1秒遮断；两攻击剪影共享池。
- **有效修订/恢复**：两灯独立储能，不随便利店MAIN故障全灭；同时拔灯无主解，至少一灯维持才能继续检修。
- **终态**：按顺序完成同一根实例、同一任务物件的全部步骤；最后一步实际提交才生成S44_rule_complete。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/20/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/20/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/43)

### S45 缝合外科客

- **模块/结局**：`tool_return` / `rule_weaken`；具体模块规格已写，实际装配/连续玩法验收待做。
- **真实来源**：同外科显体带原两器具/工具盘/有限镜片，实际开盘和取械均有物件ID。
- **原物与供应**：切割器具A/B各1；原工具盘；回收槽锁；碎屑夹；本次镜片残片（实际出现才要求）
- **不能补造的前史**：无必须伪装成过去事件的前史；仍须真实库存、安装与到场。
- **本次实际到场动作**：原物实际送到已预约位置、同一实体真实到场；不由提示按钮生产。
- **物理绑定**：packing盘后安全面与cleaning回收槽必须同模块相邻/真实搬运，不能远程销毁手中器具；回盘路径持续可达。
- **主步骤**：S45_step_1：从安全面核对本次被打开的工具盘清单 [0.8秒原值] → S45_step_2：将盘上两件实际切割器具逐一推入回收槽 [1.2秒原值] → S45_step_3：锁住回收槽，并收拢已出现的镜片碎屑到同一槽 [1秒原值]
- **NPC/世界回应**：长线落空后同体持原工具实际走回盘→放下→整理2.5秒，玩家每件.6秒推入回收；当前手持不能回收。
- **有效修订/恢复**：BC02补原物保管：碎片没产生数量0可通过，已产须全收；只对实际工具回盘有界响应保护，不为主角提供无敌。
- **终态**：同一工具盘的两件切割器具及已登记镜片碎屑均实际入锁闭回收槽，且当前持械状态已解除；正在取械时无法凭空收走手中器具，需等其一次攻击落空回盘放械的2.5s窗口。
- **原来源**：[monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/21/mechanism), [monster_scp_b_md01.json](../content/monster_scp_b_md01.json#/monsters/21/movement), [monster_attacks_scp_ma01.json](../content/monster_attacks_scp_ma01.json#/monsters/44)

## 6. 检查怎样读

运行：`python scripts/check_bc02_prerequisites.py`。检查执行依赖拓扑/每一必要来源的删除反例、真实历史与当前到场行为的分类、原物唯一性、预约失败原子性、物化后取消保位置、截止前复验、普通顾客身份、主解与真实死亡分离、原物补发去重、F21跨期血源不成立、53秒提前量、30秒血迹、S30残丝保留、F38先核A后到B、模块夜容量与开门后冻结等。

本轮报告：928项通过；564次来源删除；105条设计、406个规则动作节点。结构图的外部叶节点仍要由真实适配器提交观测，不能把图遍历的可达结果写回游戏世界当作这些事实已发生。

本脚本没有重新证明 12 条既有几何，更没有证明 93 个新模块都已装入地图；这是明确保留的运行验收门。Codex 应按第4节把每张卡的具体源/物件/路径/时窗真正接入，出具动态反例与可玩录像后再逐批开放。
