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

`sys` 是系统租户，只用于管理。必须找到 `TENANT_TYPE=USER`、`COMPATIBILITY_MODE=MYSQL` 且状态正常的普通租户，记下其名称。7 张业务表不得创建在 sys 租户。如果没有普通 MySQL 租户，停止建表并保存查询结果。

## 4. 进入项目目录

退出 obclient 后，在 Ubuntu 中进入本地仓库。路径因电脑而异：

```bash
cd ~/zuoye668936
pwd
ls sql docs
```

若仓库在 Windows 磁盘，路径可能位于 `/mnt/c/...`。后续 `source` 命令应使用 `pwd` 显示的真实绝对路径。

## 5. 连接普通 MySQL 租户

将占位符替换成第 3 节查到的租户名：

```bash
obclient -h127.0.0.1 -P2881 -uroot@<普通MySQL租户名> -p -A
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

执行完所有命令并退出 obclient 后，再输入一次 `exit` 结束录制。检查文本中没有密码后再保留。截图按照 `docs/phase3_experiment_record.md` 中的 S01—S07 保存。

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
