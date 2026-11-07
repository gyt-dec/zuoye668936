# 阶段 3 实验记录：OceanBase 物理结构实现

## 1. 实验目的

在 OceanBase CE 5.0.1.0 的普通 MySQL 兼容租户中创建手机话费充值卡管理系统数据库和 7 张业务表，验证字段类型、主键、候选键、外键及 CHECK 约束，为后续数据和业务实验提供可复现结构。

## 2. 实验环境

| 项目 | 内容 | 证据状态 |
| --- | --- | --- |
| 宿主环境 | Windows + WSL2 | 用户已确认，部署截图已有 |
| 数据库 | OceanBase CE 5.0.1.0 | 用户已提供真实版本输出 |
| 客户端 | obclient | 用户已确认可连接 |
| 地址与端口 | 127.0.0.1:2881 | 用户已确认 |
| 已验证账户 | root@sys | 用户已确认，仅用于系统管理 |
| 当前租户 | 只有 sys（SYS/MYSQL/NORMAL） | 用户已提供真实查询结果 |
| 计划普通 MySQL 租户 | coursework | 资源检查后再创建，当前不存在 |
| 业务数据库 | phone_recharge_db | 待创建/验证 |

Codex 云端不能访问本地 WSL 数据库。下文所有“实际结果”必须由用户运行后填写，当前不得写成成功。

## 3. 数据库版本与兼容模式

用户真实执行 `SELECT VERSION()`，结果为 `5.7.25-OceanBase_CE-v5.0.1.0`。`DBA_OB_TENANTS` 当前只有一行：sys 租户，类型 SYS，兼容模式 MYSQL，状态 NORMAL。因此数据库服务可用，但尚不具备隔离的普通业务租户，不能执行建库建表脚本。

### 3.1 普通租户准备状态

- WSL2 Ubuntu 22.04，总内存约 9.7 GiB；
- OceanBase 为单节点 demo 集群；
- observer 地址为 127.0.0.1:2881；
- 计划租户名为 `coursework`；
- `sql/00_check_tenant_resources.sql` 已在本地成功执行；
- `sql/00_create_coursework_tenant.sql` 已生成但未执行；
- resource unit、resource pool、tenant 尚未创建；
- `phone_recharge_db` 和 7 张表尚未创建。

资源检查确认：observer 的租户内存容量为 5 GiB、已分配 1 GiB；CPU 容量 8、已分配 2；日志盘容量 14 GiB、已分配 2 GiB；数据盘容量 8 GiB、已分配约 2 GiB。真实 zone 为 `zone1`，最小完整 resource pool 内存为 1 GiB。

### 3.2 资源检查结果与租户方案

以 `root@sys` 执行：

```sql
source /实际仓库路径/sql/00_check_tenant_resources.sql;
```

真实结果已经返回并用于形成 `docs/tenant_resource_plan.md`。建议 unit 为 `MAX_CPU=2`、`MIN_CPU=1`、`MEMORY_SIZE=2G`、`LOG_DISK_SIZE=4G`；单节点 pool 使用 `UNIT_NUM=1` 和 `zone1`。当前没有执行 resource unit、resource pool 或 tenant 创建。

## 4. 物理设计说明

物理结构严格采用 `docs/design_baseline.md` 中的 7 个关系。代理主键使用 `BIGINT UNSIGNED AUTO_INCREMENT`；金额采用定点 DECIMAL；时间采用 `DATETIME(6)`；状态采用 `VARCHAR(16) + CHECK`；手机号、卡号和订单号按字符串保存；密码字段只保存摘要。

6 个外键全部使用 `ON DELETE RESTRICT ON UPDATE RESTRICT`，避免删除用户、机主、订单、卡等父记录时级联丢失历史数据。本阶段不创建性能实验用普通索引。

### 4.1 OceanBase CE 5.0.1.0 兼容性核查

下表是基于 OceanBase MySQL 模式语法和官方资料所做的静态核查，不等于已在用户本地执行成功。

| 能力 | 静态核查结论 | 本地验证方法或兼容方案 |
| --- | --- | --- |
| BIGINT UNSIGNED | MySQL 模式支持方向明确，适合非负代理 ID | 通过 `information_schema.COLUMNS.COLUMN_TYPE` 核对 |
| DECIMAL | 支持定点数，适合金额，避免 FLOAT/DOUBLE 误差 | 插入边界金额并核对精度；本阶段只验证结构 |
| DATETIME(6) | MySQL 模式支持带小数秒的时间设计 | 核对 `SHOW CREATE TABLE` 和默认时间；若默认表达式报错，保存原错后改为程序赋值 |
| VARCHAR | 支持，手机号、卡号和订单号按字符串保存 | 核对长度、字符集和排序规则 |
| CHECK | 官方 MySQL 模式提供 CHECK 能力，但具体 5.0.1.0 的创建和执行必须实测 | 运行 `03_verify_constraints.sql`；若版本行为有差异，保留错误并在后续用事务、触发器或程序校验补充，不删除业务规则 |
| AUTO_INCREMENT | MySQL 模式支持自增列 | 插入测试行并检查 `LAST_INSERT_ID()`；回滚后编号可能不连续 |
| 外键 | MySQL 模式支持外键；本设计使用 RESTRICT 防止级联误删 | 运行 `04_verify_foreign_keys.sql` 核对元数据和失败行为 |
| UNIQUE | 支持唯一约束，用于 6 个其他候选键 | 运行 6 个重复键用例 |
| utf8mb4 / utf8mb4_bin | MySQL 模式使用该字符集和二进制排序规则的设计合理 | 在 `information_schema.SCHEMATA/COLUMNS` 中核对；若本地无该排序规则，先保存 `SHOW COLLATION` 输出再选择该版本实际提供的 utf8mb4 二进制排序规则 |

兼容性结论目前为“SQL 已按 OceanBase MySQL 模式准备，真实 5.0.1.0 结果待本地验证”。不得把普通 MySQL 的执行结果作为替代证据。

## 5. 建库 SQL

完整脚本：`sql/00_create_database.sql`。

核心语句为：

```sql
CREATE DATABASE IF NOT EXISTS phone_recharge_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_bin;
```

该语句不会删除或清空已有数据库。

## 6. 建表 SQL

完整脚本：`sql/01_create_schema.sql`。脚本按外键依赖顺序创建：

`app_user → owner → mobile_number → purchase_order → order_item → recharge_card → recharge_record`。

其中 Owner 与 User 相互独立；前两个表之间的箭头只表示创建顺序，不表示外键。实际外键关系以第 8 节为准。

## 7. 主键和候选键验证

| 表 | 主键 | 其他候选键 | 预期约束 |
| --- | --- | --- | --- |
| app_user | user_id | login_name | PK + UNIQUE |
| owner | owner_id | 无 | PK |
| mobile_number | mobile_id | phone_number | PK + UNIQUE |
| purchase_order | order_id | order_no | PK + UNIQUE |
| order_item | item_id | (order_id, denomination) | PK + UNIQUE |
| recharge_card | card_id | card_no | PK + UNIQUE |
| recharge_record | recharge_id | card_id | PK + UNIQUE |

预期数量：7 个主键、6 个 UNIQUE。实际数量：待填写。`03_verify_constraints.sql` 中的 6 个重复键用例实际结果：待验证。

## 8. 外键验证

| 子表字段 | 引用目标 | 删除/更新规则 | 实际结果 |
| --- | --- | --- | --- |
| mobile_number.owner_id | owner.owner_id | RESTRICT / RESTRICT | 待验证 |
| purchase_order.user_id | app_user.user_id | RESTRICT / RESTRICT | 待验证 |
| order_item.order_id | purchase_order.order_id | RESTRICT / RESTRICT | 待验证 |
| recharge_card.item_id | order_item.item_id | RESTRICT / RESTRICT | 待验证 |
| recharge_record.card_id | recharge_card.card_id | RESTRICT / RESTRICT | 待验证 |
| recharge_record.mobile_id | mobile_number.mobile_id | RESTRICT / RESTRICT | 待验证 |

`04_verify_foreign_keys.sql` 同时检查元数据、无父记录插入失败和被引用父记录删除失败。实际错误代码与结果：待填写。

## 9. 唯一约束验证

预期：重复登录名、手机号、订单号、同订单同面额、卡号和同一卡第二条充值记录均被拒绝。其中 `recharge_record.card_id` 唯一约束在数据库层保证一卡最多一条成功充值记录。

实际结果：待验证。

## 10. CHECK 约束验证

建表脚本声明 18 个 CHECK，覆盖非空字符串、状态取值、非负订单金额、正数面额和数量、卡状态与使用时间一致等规则。`03_verify_constraints.sql` 提供非法状态、负金额、零数量等代表性失败用例。

OceanBase CE 5.0.1.0 是否接受并实际执行全部 CHECK，必须以本地运行结果为准。实际结果：待验证。

## 11. 预期结果

1. `phone_recharge_db` 使用 `utf8mb4/utf8mb4_bin`。
2. 7 张表全部存在，字段类型与基线一致。
3. 7 个主键、6 个 UNIQUE、6 个外键、18 个 CHECK 出现在元数据中。
4. 重复候选键、非法 CHECK 数据和错误外键均被拒绝。
5. RESTRICT 阻止删除已经被历史记录引用的父记录。
6. 约束测试回滚后，不保留 `__p3_` 测试数据。

## 12. 实际结果填写区

- 执行日期：待填写
- OBD 部署名称：待填写
- 普通 MySQL 租户名称：计划为 coursework，当前不存在
- 租户资源检查结果：用户已提供，详见 3.1—3.2 节
- resource unit / resource pool 参数：已设计，尚未执行
- `SELECT VERSION()` 原始输出：待填写
- 数据库创建结果：待验证
- 7 张表创建结果：待验证
- 主键/UNIQUE 统计：待验证
- 外键统计和行为：待验证
- CHECK 统计和行为：待验证
- 回滚后计数：待验证
- 原始日志：待填写
- 发生的错误及修复：待填写

## 13. 实验分析填写提示

实际执行后应分析：物理类型是否与业务语义一致；CHECK 是否由 5.0.1.0 实际执行；RESTRICT 是否避免历史数据误删；唯一约束是否阻止一卡多次记录；约束产生的索引与后续性能索引有何区别。没有运行证据时不能填写“全部通过”。

## 14. 截图清单

| 编号 | 截图内容 | 报告用途 | 状态 |
| --- | --- | --- | --- |
| S01 | `SELECT VERSION()` 和兼容模式 | 证明使用 OceanBase CE 5.0.1.0 MySQL 模式 | TODO |
| S02 | 普通 MySQL 租户连接、`CURRENT_USER()` | 证明业务环境连接成功，不显示密码 | TODO |
| S03 | `phone_recharge_db` 创建及字符集查询 | 证明业务数据库创建成功 | TODO |
| S04 | 7 张业务表创建执行记录 | 展示数据库实施过程 | TODO |
| S05 | `SHOW TABLES` 和表数量 7 | 证明表集合完整 | TODO |
| S06 | 关键表 `SHOW CREATE TABLE` 与字段查询 | 展示物理结构和 CHECK | TODO |
| S07 | 主键、UNIQUE、6 个外键及 RESTRICT 查询 | 证明完整性约束符合设计 | TODO |

用户已有的环境部署截图不要求重新生成；以上清单只记录课程报告仍需保留的数据库证据。
