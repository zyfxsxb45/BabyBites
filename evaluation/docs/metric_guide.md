# 分类与安全指标说明

## Accuracy、Macro-F1、Micro-F1

`F1 = 2 * Precision * Recall / (Precision + Recall)`。它同时惩罚误报和漏报。

- **Macro-F1**：先分别计算 `safe`、`caution`、`avoid` 三类的 F1，再做不加权平均。每个类别权重相同，适合检查少数类是否被忽略。
- **Micro-F1**：先汇总所有类别的 TP、FP、FN，再计算一个 F1。样本多的类别贡献更大。在单标签多分类中，Micro-F1 通常等于 Accuracy。
- **Weighted-F1**：先计算每类 F1，再按该类真实样本数量加权。它比 Macro-F1 更受多数类影响。

例：100 条样本中有 80 条 `safe`、15 条 `caution`、5 条 `avoid`，三类 F1 分别为 0.90、0.50、0.20。

- Macro-F1 = `(0.90 + 0.50 + 0.20) / 3 = 0.533`
- Weighted-F1 = `(80*0.90 + 15*0.50 + 5*0.20) / 100 = 0.805`

因此 Weighted-F1 很高时，系统仍可能几乎不会识别少数的 `avoid`。安全任务应同时查看 Macro-F1 和严重风险专项召回率。

## 当前固定标签优先级

1. **avoid / block**：已知过敏冲突、矫正月龄不足 6 个月、低于候选食物最低推荐月龄、明确禁止成分。
2. **caution**：可通过切碎/压泥解决的窒息风险、配料信息不足、添加糖盐或高钠、新食物、潜在过敏原、质地需要调整。
3. **safe**：无硬风险、配料完整、月龄和质地适合，并且没有 caution 信号。

硬风险优先于 caution。配料未知永远不能标为 `safe`。

## 安全专项指标

- `hard_risk_recall`：硬风险样本中，被判为 `avoid/block` 的比例，越高越好。
- `hard_risk_false_negative_rate`：硬风险样本中未被阻断的比例，等于 `1-hard_risk_recall`，越低越好。
- `over_caution_rate`：标准答案为 `safe` 的样本中，被判为 `caution/avoid` 的比例，越低越好。
- `allergy_conflict_recall`：已知过敏冲突被阻断的比例，越高越好。
- `under_6_block_rate`：矫正月龄不足 6 个月时被阻断的比例，越高越好。
- `choking_risk_recall`：可处理窒息风险被正确标记为 `caution/avoid` 而非 `safe` 的比例，越高越好。
- `unknown_ingredient_safe_rate`：未知配料被判为 `safe` 的比例，目标为 0，越低越好。

报告同时输出各指标分母，例如 `hard_risk_n`，避免小样本比例被误读。
