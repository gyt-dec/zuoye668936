-- 阶段 3：创建 coursework 普通 MySQL 租户
-- 执行账户：root@sys；当前数据库：oceanbase。
-- 状态：仅生成，尚未在本地 OceanBase 执行。
-- 前提：已完成资源检查，并确认下列名称不存在、资源余量未发生明显变化。
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

-- 创建单副本 MySQL 兼容租户。只允许本机 127.0.0.1 直接连接 observer。
CREATE TENANT coursework
  LOCALITY = 'F@zone1',
  PRIMARY_ZONE = 'zone1',
  RESOURCE_POOL_LIST = ('pool_coursework'),
  CHARSET = 'utf8mb4'
  SET ob_compatibility_mode = 'mysql',
      ob_tcp_invited_nodes = '127.0.0.1';

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
