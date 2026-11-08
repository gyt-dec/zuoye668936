# OceanBase 本地建库与验证步骤

## 1. 打开终端

在 Windows 开始菜单打开 **Windows Terminal**，点击标签页旁的下拉箭头并选择 **Ubuntu**。也可以在 PowerShell 标签页执行：

```powershell
wsl
```

进入 Ubuntu 后，命令提示符通常会显示 Linux 用户名和主机名。

## 2. 确认 OceanBase 正在运行

先查看 OBD 部署名称：

```bash
obd cluster list
```

用列表中的真实名称替换 `<部署名称>`：

```bash
obd cluster display <部署名称>
ss -lnt | grep ':2881'
```

observer 应为运行状态，2881 端口应处于监听状态。如果状态异常，先保存完整输出，不要重新部署或删除现有集群。

## 3. 用 sys 租户确认版本和普通租户

已验证的连接命令为：

```bash
obclient -h127.0.0.1 -P2881 -uroot@sys -p -Doceanbase -A
```

在 `Enter password:` 提示后输入本地密码。密码输入时不显示字符，不要把密码写进命令或项目文件。

连接后执行：

```sql
SELECT VERSION();
SELECT TENANT_ID, TENANT_NAME, TENANT_TYPE, COMPATIBILITY_MODE, STATUS
FROM oceanbase.DBA_OB_TENANTS
ORDER BY TENANT_ID;
```

初次资源检查时只有 `sys`。此后用户已真实成功创建 `unit_coursework`、`pool_coursework`，并执行 `CREATE TENANT coursework`，返回 `Query OK, 0 rows affected (12.591 sec)`。后续回查已确认 `coursework` 为 USER / MYSQL / NORMAL，且正确绑定 `pool_coursework`、`unit_coursework` 和 `zone1`。

`sys` 只用于管理，7 张业务表不得创建在 sys 租户。资源检查已经完成，历史检查脚本为：

```sql
source /你的实际仓库路径/sql/00_check_tenant_resources.sql;
```

该脚本只读查询 zone、observer 容量、现有 resource unit、resource pool、unit 分配和资源参数。请返回完整输出，再确定 `coursework` 租户所需数值。WSL 总内存约 9.7 GiB 不能直接当作 observer 剩余可分配内存。

### 3.1 coursework 租户的资源与创建结构

创建普通租户需要依次完成三步：

1. 创建一个适合当前剩余资源的 resource unit 配置；
2. 在真实 zone 上创建 `UNIT_NUM=1` 的 resource pool；
3. 使用该 resource pool 创建 `coursework`，显式指定 MySQL 兼容模式和真实 primary zone。

资源查询已经完成，最终建议值见 `docs/tenant_resource_plan.md`：

- `MAX_CPU=2`、`MIN_CPU=1`；
- `MEMORY_SIZE=2G`；
- `LOG_DISK_SIZE=4G`；
- IOPS 参数不显式设置；
- `UNIT_NUM=1`、`ZONE_LIST=('zone1')`；
- `LOCALITY='F@zone1'`、`PRIMARY_ZONE='zone1'`。

`sql/00_create_coursework_tenant.sql` 现在只作为从零部署的复现脚本。当前环境中的三个对象已经存在，不得再次执行该文件。

### 3.2 创建后的验证和首次密码处理

租户状态和资源绑定通过以下只读脚本完成验证：

```sql
source /你的实际仓库路径/sql/00_verify_coursework_tenant.sql;
```

实际租户查询返回一行：`TENANT_TYPE=USER`、`COMPATIBILITY_MODE=MYSQL`、`STATUS=NORMAL`；资源查询显示 `pool_coursework` 归属于该租户，并使用 `unit_coursework`。

上述租户和资源绑定已经由本地真实查询验证通过。OceanBase 官方租户创建说明确认：新建 MySQL 租户的 `root` 初始密码为空。用户已经完成首次无密码连接和只读验证：

```bash
obclient -h127.0.0.1 -P2881 -uroot@coursework -A
```

实际结果为：

```text
current_account = root@%
oceanbase_version = 5.7.25-OceanBase_CE-v5.0.1.0
ob_compatibility_mode = MYSQL
```

三条查询分别返回 1 行，耗时 0.003 秒、0.003 秒和 0.019 秒，随后正常退出。`root@%` 是当前租户内 root 账户的显示形式，本次连接已确认发生在 `coursework` 租户。

用户已执行以下脚本：

```bash
bash scripts/set_coursework_root_password.sh
```

脚本成功设置密码，并通过 `obclient -p` 重新连接；验证结果仍为 `root@%`、OceanBase CE 5.0.1.0 和 `MYSQL`。密码没有写入 Git 或截图。

后续不再重复运行改密脚本。密码输入仍不得录屏或写入日志。

## 4. 进入项目目录

退出 obclient 后，在 Ubuntu 中进入本地仓库。路径因电脑而异：

```bash
cd ~/zuoye668936
pwd
ls sql docs
```

若仓库在 Windows 磁盘，路径可能位于 `/mnt/c/...`。后续 `source` 命令应使用 `pwd` 显示的真实绝对路径。

## 5. 连接普通 MySQL 租户

租户状态和资源池绑定验证通过，并完成首次密码设置后，本项目使用：

```bash
obclient -h127.0.0.1 -P2881 -uroot@coursework -p -A
```

进入后再次检查：

```sql
SELECT VERSION();
SELECT CURRENT_USER();
SHOW VARIABLES LIKE 'ob_compatibility_mode';
```

只有兼容模式为 MySQL 时才继续。

## 6. 阶段 3 自动建库、建表和验证

本项目使用一次性初始化脚本。用户已在本地成功执行，`phone_recharge_db` 和 7 张表均已创建。该脚本检测到数据库已经存在时会立即停止，因此当前不得重复运行。

```bash
cd ~/zuoye668936
git pull origin work
bash scripts/run_phase3_schema_setup.sh
```

实际运行中，脚本交互式读取一次 `root@coursework` 密码，然后自动执行仓库中的 5 个 SQL 文件。密码未出现在命令参数、仓库、日志或截图中。

执行流程：

1. 验证账户、OceanBase 版本和 MYSQL 模式；
2. 确认 `phone_recharge_db` 不存在，否则安全停止；
3. 创建数据库和 7 张表；
4. 输出完整 Schema 元数据；
5. 断言表、主键、UNIQUE、CHECK、外键和 RESTRICT 数量；
6. 运行 11 个 UNIQUE/CHECK 预期失败用例；
7. 运行 12 个外键/RESTRICT 预期失败用例；
8. 验证两个事务回滚后没有测试数据残留；
9. 输出 PASS/FAIL 汇总并保存日志到 `results/phase3/`。

`03` 和 `04` 中的每个预期错误都有 `EXPECT_FAIL` 标记。辅助程序要求标记与数据库 ERROR 一一对应；无标记错误、缺少预期错误、数量不符或回滚残留都会判为 FAIL。测试数据只存在于阶段 3 验证事务中，不属于阶段 4 业务数据。

本地最终结果为 PASS：数据库和 7 张表创建成功，7 PK / 6 UNIQUE / 18 CHECK / 6 RESTRICT 外键全部验证通过，11 个 UNIQUE/CHECK 与 12 个 FK/RESTRICT 预期失败正确分类，两组回滚均无残留。ERROR 1451、1452 是预期约束拒绝，不是脚本故障。

## 7. 检查结果

`02_verify_schema.sql` 的主要预期结果：

- 数据库为 `phone_recharge_db`，字符集 `utf8mb4`，排序规则 `utf8mb4_bin`；
- 7 张业务表全部为 `present`；
- 主键 7 个、其他候选键对应的 UNIQUE 6 个、外键 6 个、CHECK 18 个；
- 物理字段类型与 `docs/design_baseline.md` 一致；
- 没有主动建立后续性能实验用普通索引。

`03` 和 `04` 脚本结束后的测试行计数应全部为 0。AUTO_INCREMENT 因回滚产生编号间隔属于正常现象。

## 8. 保存实验结果

自动化脚本生成的真实主日志为 `results/phase3/phase3_schema_setup_20261108_024830.txt`。原始日志保留在用户本地；Git 仅提交经确认的结果摘要，除非用户完成敏感信息复核。截图只截取非敏感的结构结果和最终汇总。

## 9. 错误信息收集

出现错误时保存：

1. SQL 文件名和失败语句；
2. 完整错误代码和错误文本；
3. `SELECT VERSION()`、`CURRENT_USER()` 和兼容模式；
4. 对应表的 `SHOW CREATE TABLE 表名`；
5. 连接问题发生时的 `obd cluster display <部署名称>` 输出。

SQL 报错后可立即执行：

```sql
SHOW WARNINGS;
```

## 10. 常见问题

| 现象 | 处理方法 |
| --- | --- |
| `Access denied` | 检查租户名和密码；sys 与普通租户的账户不能混用 |
| `Unknown database` | 先执行 `00_create_database.sql` |
| `Can't connect` | 检查 OBD 状态和 2881 端口 |
| `source` 找不到文件 | 使用 `pwd` 得到的绝对路径，不照抄示例路径 |
| CHECK 或元数据查询报语法错误 | 保存版本和原始错误，不得改用 MySQL 结果冒充 |
| 约束测试出现错误 | 先判断是否为脚本注明的预期失败，再确认最终已回滚 |
| 表已存在但结构不符 | `IF NOT EXISTS` 不会修复旧表；先保存结构并停止，不执行 DROP |

本阶段没有执行任何 DROP、TRUNCATE 或自动清空操作。阶段 3 状态：完成。

## 11. 阶段 4 CRUD 自动化结果

用户已在本地执行：

```bash
bash scripts/run_phase4_crud.sh
```

真实日志为 `phase4_crud_20261108_031254.txt`，最终状态 PASS。初始行数为 `12,12,13,12,13,13,12`；7 张表更新均验证成功；各表删除 2 条后最终行数为 `10,10,11,10,11,11,10`。6 类孤儿记录和 5 类业务规则异常全部为 0，一对多联系验证结果均为 2。

该脚本是一次性入口，当前数据库已经存在阶段 4 标记数据，不得重复执行。原始日志保留在本地，未完成敏感信息复核前不提交 Git。详细结果见 `docs/phase4_experiment_record.md`。

阶段 4 状态：完成。

## 12. 阶段 5 视图与触发器结果

阶段5修复版已在本地真实执行并最终PASS。数据库中保留2个业务视图和2个充值触发器；正常充值、金额错误、已使用卡和同一卡重复充值均完成验证，P5测试数据最终回滚为0，阶段4基准未改变。

首次运行的数据库主体成功，但日志解析器因obclient重复输出标记而误判FAIL；修复后脚本复用并严格验证已有对象，没有删除或重复创建对象。首次日志为 `phase5_views_triggers_20261108_032918.txt`，最终PASS日志文件名待补充。详细过程见 `docs/phase5_experiment_record.md`。

阶段5状态：完成。当前不得重复运行阶段5入口，除非后续明确要求做只读复核。

## 13. 后续自动化原则

仓库优先提供SQL文件和Bash/Python包装脚本，由用户执行一条入口命令并保存完整日志。阶段3 Schema、阶段4 CRUD、阶段5视图/触发器和阶段6 Python业务均已完成；后续大数据、索引和并发使用各自独立入口，不跨阶段一次执行。

阶段6已在本地最终执行成功：

```bash
bash scripts/run_phase6_python_business.sh
```

该入口使用项目专用虚拟环境和权限600的临时密码文件。最终日志为`phase6_python_business_20261108_165812.txt`，P6残留为0，P4基准和P5对象未改变，阶段6状态为完成。
