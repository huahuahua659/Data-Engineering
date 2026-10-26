# 用户购买倾向预测

截至 2024-11-01 给每个用户做一次快照，预测他在未来两个月（2024-11-01 ~ 2024-12-31）是否下单。

> 目录原名"用户预测流失"，但标签定义是"未来有购买"，实际预测的是**购买/复购倾向**，不是流失。流失应定义为"本该买却没买"，需要按历史购买周期建模，这里没做。

## 口径

- **特征窗口**：2024-05-01 ~ 2024-11-01（6 个月历史）
- **标签窗口**：2024-11-01 ~ 2025-01-01
- 两个窗口不重叠，无时间泄漏
- 只保留 2024-11-01 前注册的用户，保证每个人都至少有历史可看
- 每用户一行，正样本 = 标签窗口内有 `Paid / Shipped / Delivered` 订单，占 41.97%

## 特征（25 个）

`sql/features.sql` 一段 CTE 生成：

- RFM：`recency_days`、`order_count`、`total_amount`、`avg_amount`、`max_amount`
- 30/60/90 天：`order_cnt_{30,60,90}d`、`amount_{30,90}d`
- 行为广度：`active_days`、`product_cnt`、`category_cnt`、`brand_cnt`、`total_quantity`
- 营销：`promotion_rate`、`hot_rate`
- 订单质量：`cancel_rate`、`avg_fulfillment`
- 画像：`gender`、`age`、`register_channel`、`user_region_level`、`user_province_name`

有两条衍生比例在 `src/train.py` 里算：`recent_order_ratio = 30d/90d`、`recent_amount_ratio = 30d/90d`。

## 模型与结果

60/20/20 分层划分，验证集用于 CatBoost 早停，测试集只评估一次。16,431 条测试样本：

| 模型 | AUC | AP | Acc | Precision | Recall | F1 |
|------|-----|----|-----|-----------|--------|----|
| Logistic Regression | 0.6812 | 0.6055 | 0.6567 | 0.6182 | 0.4761 | 0.5379 |
| CatBoost | 0.7012 | 0.6255 | 0.6662 | 0.6476 | 0.4490 | 0.5303 |

Top 10% 高倾向用户命中率 74.88%，整体 41.97%，**Lift 1.78**。

特征重要性 Top 5：`recency_days` 15.2、`order_cnt_60d` 14.0、`order_cnt_90d` 11.9、`order_count` 7.4、`active_days` 7.2。近期行为类特征贡献过半，用户画像类（`gender` 0.55、`age` 0.56、`register_channel` 0.63）几乎没有增量。

## 结论与局限

- CatBoost 比逻辑回归高 2 个点 AUC（0.7012 vs 0.6812），提升来自非线性交互，但**绝对水平不高**：这份模拟数据的信号本身就有限。
- 阈值固定 0.5，没有按业务成本选点；正样本 42%，如果按投放成本优化，运营侧会选更高精度、更低召回的阈值。
- 单次划分、单 seed，没做交叉验证；数据量够，但结论的稳定性未验证。
- 没有做特征稳定性/漂移检查，也没有上线后的效果回流设计。

## 复现

1. MySQL 中导入 `order`、`user` 两张表
2. 执行 `sql/features.sql`，导出结果为 `user_features.csv`（约 13 MB，8.2 万行）
3. 修改 `src/train.py` 顶部的 `FILE_PATH` 指向该文件，`python src/train.py`

脚本会输出指标、混淆矩阵、Top 10% Lift，并把测试集预测、全量重训模型、特征重要性写到数据文件同目录。

以下产物刻意没有提交：`user_features.csv`、`测试集预测结果.csv`、`CatBoost用户购买预测模型.cbm`。它们能由上面三步重新生成，且包含逐用户明细。
