# 反事实样本生成契约

## 目标

测试仅改变宝宝的已知牛奶过敏状态时，系统能否把同一个含奶候选食物从 `caution` 调整为 `avoid`。

## A/B 契约

- A：`known_allergens=[]`，标准决策为 `caution`。含奶食物属于潜在过敏原，需要谨慎引入。
- B：`known_allergens=["milk"]`，标准决策为 `avoid`，必须触发 `R_ALLERGY_MILK`。
- 除 `known_allergens` 外，A/B 的结构化画像、候选食物和文本模板必须一致。
- A/B 是两个独立样本，必须分开调用被测系统。

## 自动验证

`04_validate_evaluation_cases.py` 和 `05_sanity_check_evaluation_cases.py` 检查：

- 每组恰好两个样本。
- A/B 只在 `known_allergens` 上有差异。
- 候选食物相同。
- 决策满足 A=`caution`、B=`avoid`。
- B 触发 `R_ALLERGY_MILK`。
