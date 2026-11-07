-- 阶段 3：验证 coursework 租户和资源池归属
-- 执行账户：root@sys；当前数据库：oceanbase。
-- 本脚本只包含 SELECT，不创建、修改或删除任何对象。

-- V01：应返回一行，且 TENANT_TYPE=USER、COMPATIBILITY_MODE=MYSQL、STATUS=NORMAL。
SELECT TENANT_ID,
       TENANT_NAME,
       TENANT_TYPE,
       COMPATIBILITY_MODE,
       STATUS
FROM oceanbase.DBA_OB_TENANTS
WHERE TENANT_NAME = 'coursework';

-- V02：应返回 pool_coursework，并显示其归属于 coursework。
SELECT t.TENANT_ID,
       t.TENANT_NAME,
       p.RESOURCE_POOL_ID,
       p.NAME AS RESOURCE_POOL_NAME,
       p.UNIT_COUNT,
       p.ZONE_LIST,
       u.NAME AS UNIT_CONFIG_NAME
FROM oceanbase.DBA_OB_TENANTS AS t
LEFT JOIN oceanbase.DBA_OB_RESOURCE_POOLS AS p
  ON p.TENANT_ID = t.TENANT_ID
LEFT JOIN oceanbase.DBA_OB_UNIT_CONFIGS AS u
  ON u.UNIT_CONFIG_ID = p.UNIT_CONFIG_ID
WHERE t.TENANT_NAME = 'coursework';
