-- 阶段 3：创建课程业务数据库
-- 适用环境：OceanBase CE 5.0.1.0，普通 MySQL 兼容租户。
-- 禁止在 root@sys 中执行；sys 是系统租户，不用于保存课程业务表。
-- 本脚本只在数据库不存在时创建，不删除、覆盖或清空任何已有数据。

SELECT VERSION() AS oceanbase_version;
SELECT CURRENT_USER() AS current_account;
SHOW VARIABLES LIKE 'ob_compatibility_mode';

CREATE DATABASE IF NOT EXISTS phone_recharge_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_bin;

SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'phone_recharge_db';
