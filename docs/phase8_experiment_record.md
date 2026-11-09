# 阶段8索引性能实验记录

## 1. 当前状态

自动化脚本、SQL和代码级测试已经准备，**尚未在本地OceanBase执行**，不得标记PASS。阶段7由用户确认已真实完成并达到目标数据量；阶段7的最终日志文件名、耗时和空间数据尚未提供，本文不猜测。

## 2. 实验环境与固定条件

- OceanBase CE 5.0.1.0，`coursework` MySQL租户；
- 数据库：`phone_recharge_db`；
- P7固定数据量：6张表各100000条，`recharge_card` 120000条；
- 查询预热1次、正式重复5次，比较中位数；
- 索引前后使用相同SQL、参数和数据。

## 3. 待填写真实结果

| 项目 | 实际结果 |
|---|---|
| 阶段8日志文件 | 待本地执行 |
| 三个索引创建及定义 | 待验证 |
| Q1索引前/后中位数 | 待验证 |
| Q2索引前/后中位数 | 待验证 |
| Q3索引前/后中位数 | 待验证 |
| 三组EXPLAIN变化 | 待验证 |
| 写入测试索引前/后中位数 | 待验证 |
| INDEX_LENGTH前/后 | 待验证 |
| P8最终残留 | 预期0，待验证 |
| 最终状态 | 待验证 |

## 4. 结果文件

- `phase8_index_performance_YYYYMMDD_HHMMSS.txt`：完整控制台日志；
- `phase8_index_detail_YYYYMMDD_HHMMSS.json`：样本、查询结果和EXPLAIN；
- `phase8_index_comparison_YYYYMMDD_HHMMSS.csv`：报告用索引前后对比；
- `phase8_baseline_state.json`：DDL完成后中断时使用的无索引基线恢复状态。

原始结果不含密码。真实执行后再摘录数据和结论。
