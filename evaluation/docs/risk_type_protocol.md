# 统一风险类型协议

## 原则

BabyBites 与纯 LLM 基线都先输出 provider-neutral `risk_types`。评测器使用同一个确定性函数将风险类型转换为 canonical rule ID。

模型不再直接决定 canonical rule ID，避免“基线看到规则目录、BabyBites 依赖内部规则名称映射”造成的不公平。

## 决策政策

- `avoid`：当前候选不应选择。包括不足 6 月龄、已知过敏冲突、低于该食物最低推荐月龄、明确禁止成分。
- `caution`：候选可以在满足处理或观察条件后使用。包括可通过切碎/压泥解决的窒息风险、潜在过敏原、新食物、糖盐高钠、配料不足、质地需调整。
- `safe`：没有 avoid 或 caution 信号。

`avoid` 表示“当前不选择”，不等于永久禁止该食材。

## Risk Types

- `under_6_complementary_food`
- `known_allergy_milk`, `known_allergy_egg`, `known_allergy_wheat`, `known_allergy_soy`, `known_allergy_peanut`
- `potential_allergen`
- `added_sugar`
- `high_sodium`
- `age_below_food_min`
- `texture_mismatch`
- `choking_requires_preparation`
- `forbidden_ingredient`
- `insufficient_info`
- `new_food`

## 确定性 Rule ID 映射

| Risk type | Canonical rule ID |
|---|---|
| `under_6_complementary_food` | `R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD` |
| `known_allergy_*` | 对应 `R_ALLERGY_*` |
| `added_sugar` | `R_ADDED_SUGAR_CAUTION` |
| `high_sodium` | `R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION` |
| `age_below_food_min` / `texture_mismatch` / `choking_requires_preparation` | `R_TEXTURE_STAGE_MISMATCH` |
| `insufficient_info` | `R_INSUFFICIENT_INGREDIENT_INFO` |
| `new_food` | `R_NEW_FOOD_INTRODUCTION` |

`potential_allergen` 和 `forbidden_ingredient` 当前没有独立 canonical ID，保留在风险类型指标中，不强制映射到错误的规则 ID。

## 评测报告

正式报告应分别展示：

1. 决策分类性能：safe/caution/avoid Accuracy、Macro-F1、分类别 Precision/Recall/F1。
2. 风险类型性能：各 risk type 的 Precision/Recall/F1。
3. Canonical rule ID 性能：由统一确定性映射生成后计算 Micro-F1。
