-- 阶段 3：创建 coursework 普通 MySQL 租户
-- 执行账户：root@sys；当前数据库：oceanbase。
-- 用途：仅供“从零部署的新环境”参考和复现。
-- 当前本地环境已经成功创建同名 unit、pool 和 tenant，严禁再次执行本文件。
-- 在真正的全新环境中执行前，也必须确认下列名称不存在、资源余量满足方案。
-- 本脚本不创建 phone_recharge_db、不创建业务表、不设置或保存任何密码。

SELECT VERSION() AS oceanbase_version;
SELECT CURRENT_USER() AS current_account, DATABASE() AS current_database;

-- 执行前复核：以下三个查询均应返回 0 行。
SELECT *
FROM oceanbase.DBA_OB_UNIT_CONFIGS
WHERE NAME = 'unit_coursework';

SELECT *
FROM oceanbase.DBA_OB_RESOURCE_POOLS
WHERE NAME = 'pool_coursework';

SELECT TENANT_ID, TENANT_NAME, TENANT_TYPE, COMPATIBILITY_MODE, STATUS
FROM oceanbase.DBA_OB_TENANTS
WHERE TENANT_NAME = 'coursework';

-- 资源单元：2 核上限、1 核保证、2 GiB 内存、4 GiB 日志盘。
-- IOPS 参数有意省略，避免用未经磁盘基准验证的固定上限影响性能实验。
CREATE RESOURCE UNIT unit_coursework
  MEMORY_SIZE = '2G',
  MAX_CPU = 2,
  MIN_CPU = 1,
  LOG_DISK_SIZE = '4G';

-- 单节点 zone1 只能放置一个 unit。
CREATE RESOURCE POOL pool_coursework
  UNIT = 'unit_coursework',
  UNIT_NUM = 1,
  ZONE_LIST = ('zone1');

-- 创建 MySQL 兼容租户。该最小语法已由用户在 OceanBase CE 5.0.1.0
-- 本地环境真实执行成功；副本位置由 zone1 上的 pool_coursework 决定。
CREATE TENANT coursework
  PRIMARY_ZONE = 'zone1',
  RESOURCE_POOL_LIST = ('pool_coursework')
  SET ob_compatibility_mode = 'mysql';

-- 创建后验证：必须返回 USER / MYSQL / NORMAL。
SELECT TENANT_ID,
       TENANT_NAME,
       TENANT_TYPE,
       COMPATIBILITY_MODE,
       STATUS
FROM oceanbase.DBA_OB_TENANTS
WHERE TENANT_NAME = 'coursework';

-- 核对 unit、pool、实际落点及创建后的资源余量。
SELECT *
FROM oceanbase.DBA_OB_UNIT_CONFIGS
WHERE NAME = 'unit_coursework';

SELECT *
FROM oceanbase.DBA_OB_RESOURCE_POOLS
WHERE NAME = 'pool_coursework';

SELECT u.*
FROM oceanbase.DBA_OB_UNITS AS u
JOIN oceanbase.DBA_OB_RESOURCE_POOLS AS p
  ON p.RESOURCE_POOL_ID = u.RESOURCE_POOL_ID
WHERE p.NAME = 'pool_coursework';

SELECT *
FROM oceanbase.GV$OB_SERVERS
ORDER BY ZONE, SVR_IP, SVR_PORT;
