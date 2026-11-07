-- 阶段 3：创建 coursework 普通租户前的资源检查
-- 执行账户：root@sys；当前数据库：oceanbase。
-- 本脚本全部为只读查询，不创建租户、资源单元或资源池，也不修改参数。
-- 请保存完整输出并返回，之后才能确定适合当前单节点的资源值。

SELECT VERSION() AS oceanbase_version;
SELECT CURRENT_USER() AS current_account, DATABASE() AS current_database;

-- 1. 确认当前租户。现阶段预期只有 sys；不得在 sys 中创建业务表。
SELECT TENANT_ID,
       TENANT_NAME,
       TENANT_TYPE,
       COMPATIBILITY_MODE,
       STATUS
FROM oceanbase.DBA_OB_TENANTS
ORDER BY TENANT_ID;

-- 2. 检查 zone。后续 RESOURCE POOL 的 ZONE_LIST 和租户 PRIMARY_ZONE
-- 必须使用这里返回的真实 zone 名称，不能假定一定叫 zone1。
SELECT *
FROM oceanbase.DBA_OB_ZONES
ORDER BY ZONE;

-- 3. 检查 observer 总容量、已分配量和磁盘使用情况。
-- 单节点环境重点关注 CPU_CAPACITY/CPU_ASSIGNED、MEM_CAPACITY/MEM_ASSIGNED、
-- LOG_DISK_CAPACITY/LOG_DISK_ASSIGNED；请返回完整的一行输出。
SELECT *
FROM oceanbase.GV$OB_SERVERS
ORDER BY ZONE, SVR_IP, SVR_PORT;

-- 4. 查看已有 resource unit 配置，避免重名并参考 demo 集群允许的下限。
SELECT *
FROM oceanbase.DBA_OB_UNIT_CONFIGS
ORDER BY UNIT_CONFIG_ID;

-- 5. 查看已有 resource pool 及其租户归属、unit 数量和 zone 列表。
SELECT *
FROM oceanbase.DBA_OB_RESOURCE_POOLS
ORDER BY RESOURCE_POOL_ID;

-- 6. 查看 unit 实际落在哪个 observer，核对单节点的当前分配情况。
SELECT *
FROM oceanbase.DBA_OB_UNITS
ORDER BY UNIT_ID;

-- 7. 读取影响可分配内存/资源计算的 observer 参数。
-- 某些隐藏参数在当前版本可能不显示；无返回行也需要如实记录。
SHOW PARAMETERS LIKE 'memory_limit';
SHOW PARAMETERS LIKE 'system_memory';
SHOW PARAMETERS LIKE 'resource_hard_limit';
SHOW PARAMETERS LIKE 'resource_soft_limit';
SHOW PARAMETERS LIKE '__min_full_resource_pool_memory';
