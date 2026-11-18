#!/usr/bin/env python3
"""Render the current contracts without silently preserving old card summaries."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / 'content/condition_lifecycle_v06.json').read_text())
cards = {x['id']: x for x in json.loads((ROOT / 'content/encounters_v05.json').read_text())['encounters']}

def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')

lines = [
    '# V0.8：60只怪物的条件与结束矩阵', '',
    '本表由当前条件合同生成。每行同时列出真实必要来源、正确提前处理、完成、来源失效及拒绝边界。历史缺口保存在JSON的 `original_gaps_reviewed`，不是仍要求客户端实现的规则。', '',
    '权威数据：[条件合同](../content/condition_lifecycle_v06.json)、[时间与资源补充合同](../content/temporal_resource_contract_v07.json)、[消费者合同](../content/consumer_closure_v08.json)、[依赖见证模型](../content/condition_reachability_v06.json)、[当前怪物卡](21_monster_gameplay_v05.md)。本轮问题与修正见[第三轮审计](26_third_consistency_audit_v08.md)。**全部60只的客户端仍未实现，本表不是60个实玩通过报告。**', '',
    '| 怪物 | 必要来源与准入 | 提前处理 | 完成条件 | 来源到期／拒绝 |',
    '| --- | --- | --- | --- | --- |',
]
for row in data['encounter_contracts']:
    values = [row['id']+' '+cards[row['id']]['name'], '；'.join(row['requires_before_omen']),
              row['on_player_prevented'], row['normal_resolution'],
              row['on_source_expired']+' '+row['on_refused']]
    lines.append('| '+' | '.join(cell(x) for x in values)+' |')
lines += ['', '## 规则与事件覆盖', '',
    '20条规则的触发来源、免费教学和结束条件在 [rules.json](../content/rules.json) 的 `v06_condition_contract`；72项事件目录的相同字段记录输入与失效处理，其中E051因没有真实维修目标暂停，当前设计候选71项。字段名为兼容保留，不代表仍使用旧数据。120个当前怪物变体必须核对实际事件子型，不得补造缺失历史。', '',
    '生产依赖图从每只怪物的独立开班状态搜索，证明声明前提有无循环和生产链；时间补充检查角色实际到场、历史记录早于首兆、完整执行预算、物品种类与消费关系。这两层都不是完整客户端、所有随机组合或动态追逐的通关证明。', '',
    '同一动作不能同时消费同一物件两次。准备、到场、提交和到期都复核对象编号；正确预防占用原波次，拒绝可选交易不等于完成交易，也不能解除已生效的强制追逐。', '',
    'F12/F13继续由[精确蓝图](../content/encounter_blueprints.json)约束；本轮没有改成吞铁成长或消失的生肉。',
]
(ROOT / 'docs/24_condition_matrix_v06.md').write_text('\n'.join(lines)+'\n')
print('Rendered current 60-card condition matrix')
