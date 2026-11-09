# 阶段10：在线结构变更、数据校验、备份与恢复计划

本阶段在10万级`recharge_record`上新增可空`recharge_source`字段。DDL期间两个独立连接持续执行SELECT和P10记录的无值UPDATE，记录成功、失败、错误码和最大延迟。实验只能据此说明DDL期间数据库仍可访问；延迟可能包含元数据锁等待，不能声称完全无阻塞。

所有P10逻辑备份数据在同一个`REPEATABLE READ / START TRANSACTION WITH CONSISTENT SNAPSHOT`事务内读取七张表。备份保存原始主键、外键、字段、行数和表级SHA-256，文件及manifest权限为0600且被Git忽略。

实验真实删除P10数据，再在一个事务中显式恢复原始ID。USED卡先以UNUSED恢复，随后插入原始充值记录，由阶段5触发器恢复USED及`used_at`。恢复后重新从一致性快照导出，比较主键集合、外键、数量和SHA-256。只有全部一致才清理P10；失败保留备份、状态文件和数据库现场。

执行前后验证P4—P9、两个视图、两个触发器和阶段8三个索引。不会修改阶段3建表脚本、P7数据、触发器、索引或OceanBase资源参数。

唯一入口：

```bash
bash scripts/run_phase10_ddl_backup_restore.sh
```
