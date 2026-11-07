# 阶段 3 真实结果归档说明

## 已确认结果

用户于 2026-11-08 在本地 WSL2 的 OceanBase CE 5.0.1.0 中运行：

```text
scripts/run_phase3_schema_setup.sh
```

最终状态为 `PASS`，确认：

- `phone_recharge_db` 创建成功；
- 7 张业务表创建成功；
- 7 个主键、6 个 UNIQUE、18 个 CHECK 验证通过；
- 6 个外键均为 `UPDATE_RULE=RESTRICT`、`DELETE_RULE=RESTRICT`；
- 11 个 UNIQUE/CHECK 预期失败被正确识别；
- 12 个 FK/RESTRICT 预期失败被正确识别；
- 外键错误 1452 和受引用父记录删除错误 1451 均属于预期结果；
- 两个验证事务回滚后均无数据残留；
- 最终汇总为 `最终状态：PASS`。

本地原始日志文件名：

```text
phase3_schema_setup_20261108_024830.txt
```

日志在本地仓库的 `results/phase3/` 目录中保存。Git 摘要不记录用户主目录绝对路径。

## Git 归档规则

原始日志目前只存在用户本地，Codex 未读取其完整内容，不能替用户保证其中没有本机路径、账户信息或其他不宜公开内容。因此本次只提交上述经确认的摘要，不伪造或复制原始日志。

如需把原始日志纳入 Git，应先由用户检查：不含密码、临时凭据、环境变量和不必要的个人路径。可保留 OceanBase 版本、SQL 输出、预期错误、约束统计和 PASS 汇总。
