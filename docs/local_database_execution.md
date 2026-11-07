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

下一小步使用仓库脚本交互式设置密码并自动重新连接验证。在仓库根目录只执行：

```bash
bash scripts/set_coursework_root_password.sh
```

脚本会隐藏输入新密码两次，通过标准输入执行官方语法 `ALTER USER root IDENTIFIED BY '...'`，然后调用 `obclient -p`。此时再输入一次新密码，脚本会自动输出当前账户、版本和兼容模式。密码不会成为命令行参数，也不会写入仓库文件。

执行该脚本时不要录屏、不要开启 `script` 终端日志。若 `ALTER USER` 已成功但重新连接失败，不得重复运行整个脚本，应单独使用 `obclient ... -p` 排查。密码设置和重新连接实际验证成功后，才进入建库步骤。

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

## 6. 按顺序执行 SQL

假设 `pwd` 输出 `/home/student/zuoye668936`，则执行：

```sql
source /home/student/zuoye668936/sql/00_create_database.sql;
source /home/student/zuoye668936/sql/01_create_schema.sql;
source /home/student/zuoye668936/sql/02_verify_schema.sql;
```

把示例路径替换成自己的真实路径。前三个脚本不删除或清空数据。

随后执行两个约束测试脚本：

```sql
source /home/student/zuoye668936/sql/03_verify_constraints.sql;
source /home/student/zuoye668936/sql/04_verify_foreign_keys.sql;
```

这两个脚本故意插入非法数据，出现重复键、CHECK 或外键错误属于预期结果。成功插入的测试数据最终通过 `ROLLBACK` 撤销。若 obclient 遇到首个错误后停止，应在交互会话中逐段执行，确保最终执行 `ROLLBACK`。

## 7. 检查结果

`02_verify_schema.sql` 的主要预期结果：

- 数据库为 `phone_recharge_db`，字符集 `utf8mb4`，排序规则 `utf8mb4_bin`；
- 7 张业务表全部为 `present`；
- 主键 7 个、其他候选键对应的 UNIQUE 6 个、外键 6 个、CHECK 18 个；
- 物理字段类型与 `docs/design_baseline.md` 一致；
- 没有主动建立后续性能实验用普通索引。

`03` 和 `04` 脚本结束后的测试行计数应全部为 0。AUTO_INCREMENT 因回滚产生编号间隔属于正常现象。

## 8. 保存实验结果

可以在启动 obclient 前录制终端：

```bash
cd ~/zuoye668936
mkdir -p results
script -q -a results/phase3_execution.txt
```

执行完所有命令并退出 obclient 后，再输入一次 `exit` 结束录制。检查文本中没有密码后再保留。截图按照 `docs/phase3_experiment_record.md` 中的 S01—S10 保存。密码输入和 `ALTER USER` 语句不得截图。

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

本阶段没有任何 DROP、TRUNCATE 或自动清空脚本。

## 11. 后续自动化原则

从建库开始，仓库将优先提供可重复执行的 SQL 文件和 Bash/Python 包装脚本，由用户执行一条入口命令并保存完整日志。约束测试会明确区分预期错误与真实故障；大数据、索引和并发实验会自动输出原始结果文件。每次仍按阶段拆分，不会把建库、建表、CRUD、性能和并发实验一次全部执行。
