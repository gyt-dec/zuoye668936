# coursework 普通租户资源方案

## 1. 已验证环境

以下数据来自用户在本地 OceanBase CE 5.0.1.0 sys 租户的真实查询：

| 项目 | 总量 | 已分配 | 创建前余量 |
| --- | ---: | ---: | ---: |
| CPU | 8 核 | 2 核 | 6 核 |
| 租户内存 MEM_CAPACITY | 5 GiB | 1 GiB | 4 GiB |
| 日志盘 | 14 GiB | 2 GiB | 12 GiB |
| 数据盘 | 8 GiB | 2 GiB | 约 6 GiB |

其他已验证信息：observer `memory_limit=6G`，`system_memory=1G`，zone 为 `zone1`，`__min_full_resource_pool_memory=1G`，`resource_hard_limit=100`，当前只有 sys 租户。WSL 总内存约 9.7 GiB。

## 2. 可行性结论

当前资源可以创建一个单副本、单 unit 的 `coursework` MySQL 租户。不能把剩余 4 GiB 租户内存全部分配给新租户，否则 observer 没有资源余量，不利于稳定运行和后续调整。采用 2 GiB 内存和 2 核 CPU 的上限，可以满足课程建表、基础业务、10 万级数据和一般并发演示，同时给 observer 留出缓冲。

这是单节点课程实验配置，不具备生产环境高可用性。单节点故障会导致租户不可用。

## 3. 建议资源值

| 参数 | 建议 | 依据 |
| --- | ---: | --- |
| MAX_CPU | 2 | 创建前剩余 6 核；为课程查询和并发实验提供 2 核上限，创建后仍留约 4 核余量 |
| MIN_CPU | 1 | OceanBase 官方限制最小为 1；只保证 1 核，避免在低资源环境中过度预留 |
| MEMORY_SIZE | 2G | 高于本机真实最小值 1G；创建后仍保留 2 GiB 未分配租户内存，兼顾 observer 稳定性和实验规模 |
| LOG_DISK_SIZE | 4G | 官方最小值为 2G；4G 可容纳课程事务日志，创建后仍留约 8 GiB 日志盘余量 |
| DATA_DISK_SIZE | 不设置 | 不是 `CREATE RESOURCE UNIT` 参数；数据盘由 observer 共享，当前约剩 6 GiB |
| MAX_IOPS | 不显式设置 | 未取得磁盘真实 IOPS 基准，不用任意上限干扰后续性能实验；官方规则会给出默认值 |
| MIN_IOPS | 不显式设置 | 与 MAX_IOPS 一并省略；官方最低可显式填写值为 1024，但当前无必要预留固定 IOPS |
| IOPS_WEIGHT | 不显式设置 | MAX/MIN IOPS 均省略时，官方规则默认等于 MIN_CPU，即 1 |
| UNIT_NUM | 1 | `zone1` 只有一个 observer；一个租户在同一节点最多一个 unit |
| ZONE_LIST | ('zone1') | 来自真实 `DBA_OB_ZONES` 查询 |
| LOCALITY | F@zone1 | 单节点只创建一个全功能副本 |
| PRIMARY_ZONE | zone1 | 当前唯一 zone |

创建后预计资源占用为：CPU 上限增加 2，保证 CPU 增加 1，租户内存增加 2 GiB，日志盘配额增加 4 GiB。实际 `GV$OB_SERVERS` 变化应在创建后再次查询确认。

## 4. OceanBase 参数限制核查

- `CREATE RESOURCE UNIT` 只能由 `root@sys` 执行，单个 unit 的资源不能超过对应 observer 可用资源。
- `MAX_CPU` 和 `MIN_CPU` 最小值为 1，且 `MAX_CPU >= MIN_CPU`。
- `MEMORY_SIZE` 受 `__min_full_resource_pool_memory` 控制。本机真实值为 1 GiB，建议值 2 GiB 合法。OceanBase 4.0 以后不支持内存超卖。
- `LOG_DISK_SIZE` 最小值为 2 GiB。不填写时默认是内存的 3 倍；本方案显式设为 4 GiB，避免 2 GiB 内存自动占用 6 GiB 日志盘。
- 显式设置 `MAX_IOPS` 或 `MIN_IOPS` 时，最小值为 1024，且 `MAX_IOPS >= MIN_IOPS`。本方案不显式设置二者。
- resource pool 的 `UNIT_NUM` 是每个 zone 的 unit 数量，不能超过目标 zone 的 observer 数量；单节点使用 1。
- `RESOURCE_POOL_LIST` 是创建租户的必填项；租户兼容模式创建后不能更改。
- `DATA_DISK_SIZE` 不属于 resource unit 语法，不能写入创建语句。

官方通用资料建议完整租户尽量使用至少 4 GiB 内存，但本机只有 4 GiB 未分配租户容量；把 4 GiB 全部分配给 `coursework` 会耗尽余量。这里选择 2 GiB 是低资源课程环境的折中，依据是本机实际隐藏下限为 1 GiB。它不应作为生产配置；若后续 100 万级数据或高并发实验出现内存压力，应先记录现象并评估扩大 WSL/observer 资源，而不是在运行中盲目压缩 sys 内存。

## 5. 是否调整其他系统参数

本阶段不需要调整 `memory_limit`、`system_memory`、`resource_hard_limit` 或隐藏参数。现有 `memory_limit=6G` 与 `system_memory=1G` 已形成 5 GiB 租户容量，当前方案在该容量内保留 2 GiB 余量。

`resource_soft_limit` 查询为空不影响本方案；不为了创建租户临时设置该参数。数据盘约剩 6 GiB，阶段 3 不需要扩容。进入大规模数据实验前必须再次查询数据盘使用量，必要时通过 OBD 配置评估扩容，不能把 `DATA_DISK_SIZE` 错写成租户参数。

## 6. 创建与验证文件

用户已在本地成功创建以下对象：

1. `unit_coursework`；
2. `pool_coursework`；
3. MySQL 模式租户 `coursework`。

`sql/00_create_coursework_tenant.sql` 现在只作为从零部署的完整复现脚本，当前环境不得再次执行。文件不包含密码，也不创建 `phone_recharge_db` 或业务表。当前应改为运行只读的 `sql/00_verify_coursework_tenant.sql`。

## 7. 参考依据

参数语法和限制依据 OceanBase 官方 SQL 参考中的 `CREATE RESOURCE UNIT`、`CREATE RESOURCE POOL` 和 `CREATE TENANT`。实际执行仍以本地 OceanBase CE 5.0.1.0 返回结果为准；Codex 未连接或执行本地数据库。
