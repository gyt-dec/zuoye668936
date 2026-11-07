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
| 初始租户 | 资源检查时只有 sys（SYS/MYSQL/NORMAL） | 用户已提供真实查询结果 |
| resource unit | unit_coursework | 已验证由 pool_coursework 使用 |
| resource pool | pool_coursework，ID=1001，UNIT_COUNT=1，zone1 | 归属验证成功 |
| 普通租户 | coursework，ID=1002，USER/MYSQL/NORMAL | 状态验证成功 |
| 业务数据库 | phone_recharge_db | 自动创建并验证成功 |

Codex 云端不能访问本地 WSL 数据库。本文件中的成功结果均来自用户返回的本地真实日志和截图摘要；未由本地执行证明的内容不得写成成功。

## 3. 数据库版本与兼容模式

用户真实执行 `SELECT VERSION()`，结果为 `5.7.25-OceanBase_CE-v5.0.1.0`。初次查询 `DBA_OB_TENANTS` 时只有 sys。随后用户成功创建 `unit_coursework` 和 `pool_coursework`，并真实执行 `CREATE TENANT coursework PRIMARY_ZONE='zone1', RESOURCE_POOL_LIST=('pool_coursework') SET ob_compatibility_mode='mysql'`，结果为 `Query OK, 0 rows affected (12.591 sec)`。

随后用户完成只读回查：`coursework` 的 `TENANT_ID=1002`、`TENANT_TYPE=USER`、`COMPATIBILITY_MODE=MYSQL`、`STATUS=NORMAL`，查询返回 1 行，耗时 0.029 秒。资源绑定查询确认 `RESOURCE_POOL_ID=1001`、`RESOURCE_POOL_NAME=pool_coursework`、`UNIT_COUNT=1`、`ZONE_LIST=zone1`、`UNIT_CONFIG_NAME=unit_coursework`，返回 1 行，耗时 0.019 秒。

因此租户状态和资源绑定已经验证成功。用户随后以空密码成功连接 `root@coursework`，再次确认 OceanBase 版本和 MySQL 兼容模式。之后运行安全改密脚本成功，使用 `obclient -p` 重新连接验证通过。最后运行阶段 3 自动化脚本，数据库、7 张表及全部设计约束验证均为 PASS。

### 3.1 普通租户准备状态

- WSL2 Ubuntu 22.04，总内存约 9.7 GiB；
- OceanBase 为单节点 demo 集群；
- observer 地址为 127.0.0.1:2881；
- 普通租户名为 `coursework`；
- `sql/00_check_tenant_resources.sql` 已在本地成功执行；
- `unit_coursework`：创建并绑定成功；
- `pool_coursework`：创建成功，绑定到 TENANT_ID 1002；
- `coursework`：TENANT_ID 1002，USER / MYSQL / NORMAL；
- `root@coursework`：空密码首次连接成功，账户、版本和兼容模式验证通过；
- `root@coursework`：密码设置成功，`obclient -p` 重新连接验证通过；
- `sql/00_create_coursework_tenant.sql` 仅保留为从零部署脚本，当前不得重复执行；
- `phone_recharge_db` 和 7 张表：创建及验证成功。

资源检查确认：observer 的租户内存容量为 5 GiB、已分配 1 GiB；CPU 容量 8、已分配 2；日志盘容量 14 GiB、已分配 2 GiB；数据盘容量 8 GiB、已分配约 2 GiB。真实 zone 为 `zone1`，最小完整 resource pool 内存为 1 GiB。

### 3.2 资源检查结果与租户方案

以 `root@sys` 执行：

```sql
source /实际仓库路径/sql/00_check_tenant_resources.sql;
```

真实结果已经返回并用于形成 `docs/tenant_resource_plan.md`。resource unit、resource pool、租户创建及绑定验证均已完成。`root@coursework` 无密码连接成功：`CURRENT_USER()=root@%`，查询耗时 0.003 秒；版本为 `5.7.25-OceanBase_CE-v5.0.1.0`，耗时 0.003 秒；兼容模式为 `MYSQL`，耗时 0.019 秒。随后 `scripts/set_coursework_root_password.sh` 执行成功，密码未进入 Git 或截图，`obclient -p` 重新连接后再次得到相同账户、版本和兼容模式。

### 3.3 Schema 自动化执行设计

`scripts/run_phase3_schema_setup.sh` 是一次性初始化入口：交互读取一次密码，确认数据库不存在后，按顺序执行 5 个 SQL 文件，自动断言 7 表、7 主键、6 UNIQUE、18 CHECK、6 外键和 6 个 RESTRICT 规则。预期失败测试通过标记与 ERROR 配对识别，标记外错误会导致整体 FAIL。所有验证数据最终回滚，日志保存到 `results/phase3/`。

### 3.4 Schema 自动化真实结果

用户在本地实际运行 `scripts/run_phase3_schema_setup.sh`，最终状态为 PASS：

- `phone_recharge_db` 创建成功；
- 7 张业务表创建成功；
- 7 PK / 6 UNIQUE / 18 CHECK 验证成功；
- 6 FK 的 `UPDATE_RULE`、`DELETE_RULE` 均为 RESTRICT；
- 11 个 UNIQUE/CHECK 预期失败全部正确识别；
- 12 个 FK/RESTRICT 预期失败全部正确识别；
- ERROR 1452 表示子记录引用不存在的父记录，属于预期拒绝；
- ERROR 1451 表示 RESTRICT 阻止删除被引用父记录，属于预期拒绝；
- 两个事务测试均无残留数据，`user_rows=0`、`order_rows=0`、`card_rows=0`；
- 最终输出为 `最终状态：PASS`。

真实日志文件名为 `phase3_schema_setup_20261108_024830.txt`，保存在本地仓库的 `results/phase3/`。Git 中保存经确认的摘要；原始日志未经云端完整敏感信息检查，暂不直接提交。

### 3.5 建库建表脚本与实际执行复核

本阶段重新读取并检查了仓库中的 5 个实际文件：

- `00_create_database.sql`：创建 `phone_recharge_db`，使用 `utf8mb4/utf8mb4_bin`，无 DROP/TRUNCATE；执行成功。
- `01_create_schema.sql`：按依赖顺序创建 7 张表，含 7 个主键、6 个 UNIQUE、6 个 RESTRICT 外键和 18 个 CHECK；未建立普通性能索引；执行成功。
- `02_verify_schema.sql`：只读检查数据库、字段、表、约束和索引；执行成功。
- `03_verify_constraints.sql`：通过预期失败测试 UNIQUE/CHECK，最后 ROLLBACK；执行和自动分类成功。
- `04_verify_foreign_keys.sql`：检查 6 个外键并用事务测试错误引用和 RESTRICT，最后 ROLLBACK；执行和自动分类成功。

静态结构与设计基线一致，随后已在 OceanBase CE 5.0.1.0 中完成真实执行。CHECK、UNIQUE、外键和 RESTRICT 行为均由自动化用例验证，最终无测试数据残留。

## 4. 物理设计说明

物理结构严格采用 `docs/design_baseline.md` 中的 7 个关系。代理主键使用 `BIGINT UNSIGNED AUTO_INCREMENT`；金额采用定点 DECIMAL；时间采用 `DATETIME(6)`；状态采用 `VARCHAR(16) + CHECK`；手机号、卡号和订单号按字符串保存；密码字段只保存摘要。

6 个外键全部使用 `ON DELETE RESTRICT ON UPDATE RESTRICT`，避免删除用户、机主、订单、卡等父记录时级联丢失历史数据。本阶段不创建性能实验用普通索引。

### 4.1 OceanBase CE 5.0.1.0 兼容性核查

下表结合官方语法核查与本地 OceanBase CE 5.0.1.0 真实执行结果。

| 能力 | 静态核查结论 | 本地验证方法或兼容方案 |
| --- | --- | --- |
| BIGINT UNSIGNED | 7 个代理主键创建成功 | PASS |
| DECIMAL | 订单、面额和充值金额字段创建成功 | PASS |
| DATETIME(6) | 时间字段及默认表达式创建成功 | PASS |
| VARCHAR | 手机号、卡号、订单号和状态字段创建成功 | PASS |
| CHECK | 18 个 CHECK 创建成功，5 个非法值用例被拒绝 | PASS |
| AUTO_INCREMENT | 7 个代理主键自增定义创建成功，测试事务可取得 ID | PASS |
| 外键 | 6 个外键创建成功，ERROR 1451/1452 行为符合设计 | PASS |
| UNIQUE | 6 个候选键唯一约束创建成功，重复值被拒绝 | PASS |
| utf8mb4 / utf8mb4_bin | 数据库和字符列按设计创建 | PASS |

兼容性结论：本阶段所用字段类型、字符集、默认值、主键、UNIQUE、CHECK 和外键语法已在 OceanBase CE 5.0.1.0 MySQL 模式真实执行通过。

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

实际验证得到 7 个主键、6 个 UNIQUE；`03_verify_constraints.sql` 中 6 个重复键用例均被正确拒绝。

## 8. 外键验证

| 子表字段 | 引用目标 | 删除/更新规则 | 实际结果 |
| --- | --- | --- | --- |
| mobile_number.owner_id | owner.owner_id | RESTRICT / RESTRICT | PASS |
| purchase_order.user_id | app_user.user_id | RESTRICT / RESTRICT | PASS |
| order_item.order_id | purchase_order.order_id | RESTRICT / RESTRICT | PASS |
| recharge_card.item_id | order_item.item_id | RESTRICT / RESTRICT | PASS |
| recharge_record.card_id | recharge_card.card_id | RESTRICT / RESTRICT | PASS |
| recharge_record.mobile_id | mobile_number.mobile_id | RESTRICT / RESTRICT | PASS |

`04_verify_foreign_keys.sql` 同时检查元数据、无父记录插入失败和被引用父记录删除失败。实际 ERROR 1452、1451 均按预期出现并被自动分类，最终回滚无残留。

## 9. 唯一约束验证

预期：重复登录名、手机号、订单号、同订单同面额、卡号和同一卡第二条充值记录均被拒绝。其中 `recharge_record.card_id` 唯一约束在数据库层保证一卡最多一条成功充值记录。

实际结果：PASS。6 个重复候选键用例均被拒绝，一卡第二条充值记录未能插入。

## 10. CHECK 约束验证

建表脚本声明 18 个 CHECK，覆盖非空字符串、状态取值、非负订单金额、正数面额和数量、卡状态与使用时间一致等规则。`03_verify_constraints.sql` 提供非法状态、负金额、零数量等代表性失败用例。

OceanBase CE 5.0.1.0 已实际创建并报告 18 个 CHECK；5 个代表性非法值用例均被拒绝。实际结果：PASS。

## 11. 预期结果

1. `phone_recharge_db` 使用 `utf8mb4/utf8mb4_bin`。
2. 7 张表全部存在，字段类型与基线一致。
3. 7 个主键、6 个 UNIQUE、6 个外键、18 个 CHECK 出现在元数据中。
4. 重复候选键、非法 CHECK 数据和错误外键均被拒绝。
5. RESTRICT 阻止删除已经被历史记录引用的父记录。
6. 约束测试回滚后，不保留 `__p3_` 测试数据。

## 12. 实际结果填写区

- 执行日期：2026-11-08
- OBD 部署名称：本次结果未记录具体部署名，不影响数据库内版本和租户证据
- 普通 MySQL 租户名称：coursework，ID=1002，USER/MYSQL/NORMAL，已验证
- 租户资源检查结果：用户已提供，详见 3.1—3.2 节
- resource unit / resource pool：unit_coursework / pool_coursework，绑定已验证
- `root@coursework` 首次连接：空密码连接及只读验证成功
- `root@coursework` 密码：已设置，带 `-p` 重新连接验证成功；密码未记录
- `SELECT VERSION()`：`5.7.25-OceanBase_CE-v5.0.1.0`
- 数据库创建结果：PASS
- 7 张表创建结果：PASS
- 主键/UNIQUE 统计：7 / 6，PASS
- 外键统计和行为：6，全部 RESTRICT，PASS
- CHECK 统计和行为：18，代表性非法值均被拒绝，PASS
- 回滚后计数：两组均为 0，PASS
- 原始日志：`phase3_schema_setup_20261108_024830.txt`（本地保存）
- 发生的错误及修复：ERROR 1451/1452 为设计中的预期失败，不属于实验故障

## 13. 实验分析

真实结果表明物理类型和完整性约束能够在 OceanBase CE 5.0.1.0 MySQL 模式中执行。UNIQUE 阻止重复业务键和一卡多记录，CHECK 拒绝非法状态与金额，外键拒绝孤儿记录，RESTRICT 防止误删历史父记录。主键和候选键形成的约束索引属于当前结构的一部分，后续性能实验不会把它们误写为新增普通索引。

## 14. 截图清单

| 编号 | 截图内容 | 报告用途 | 状态 |
| --- | --- | --- | --- |
| S01 | `SELECT VERSION()` 和兼容模式 | 证明使用 OceanBase CE 5.0.1.0 MySQL 模式 | 已有环境证据，无需重截 |
| S02 | `CREATE TENANT coursework` 及 `Query OK, 0 rows affected (12.591 sec)` | 证明普通租户创建命令真实完成；放在“数据库物理设计—租户创建” | 已完成，待归档 |
| S03 | coursework 类型、MYSQL 模式、NORMAL 状态和资源池归属 | 证明租户最终状态符合设计 | 已完成，待归档 |
| S04 | `root@coursework` 无密码连接、`CURRENT_USER()`、版本和兼容模式 | 证明首次进入业务租户及 MySQL 模式，不显示密码 | 已完成，待归档 |
| S05 | 设置密码后使用 `-p` 重新连接，并显示账户、版本和兼容模式 | 证明 root 密码保护和重新认证成功；不得截取密码输入或 ALTER USER | 已完成，待归档 |
| S06 | 阶段 3 最终 PASS 汇总、FK/RESTRICT 预期失败分类及回滚为 0 | 合并证明建库建表、约束行为和最终状态 | 已完成，待归档 |
| S07 | 关键表实际定义，建议 `SHOW CREATE TABLE recharge_record`，清楚显示 PK、UNIQUE、FK 和 CHECK | 用一张图补充物理结构的数据库原始证据 | 建议补截 1 张 |

现有 S06 已覆盖最终 PASS、外键预期失败和回滚无残留。最少只需再补 S07 一张关键表实际定义；若最终报告直接采用清晰的日志片段且版面足够，可由教师报告排版时决定是否保留 S07，不再要求无意义的 S08—S10。
