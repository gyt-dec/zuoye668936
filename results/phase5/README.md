# 阶段 5 结果目录

本地运行 `scripts/run_phase5_views_triggers.sh` 后会产生：

- `phase5_views_triggers_YYYYMMDD_HHMMSS.txt`：完整主日志；
- `phase5_trigger_tests_YYYYMMDD_HHMMSS.txt`：触发器测试及预期失败日志。

原始日志由 `.gitignore` 排除，不直接提交。阶段 5 尚未本地执行；运行后需先检查日志不含密码或敏感信息，再把真实结果和日志文件名写入实验记录。
