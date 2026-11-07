-- 阶段 3：验证数据库、7 张表、字段类型和全部约束元数据
-- 本脚本只查询，不修改数据。必须在普通 MySQL 兼容租户执行。

SELECT VERSION() AS oceanbase_version;
SELECT CURRENT_USER() AS current_account;
SHOW VARIABLES LIKE 'ob_compatibility_mode';

SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'phone_recharge_db';

USE phone_recharge_db;
SELECT DATABASE() AS current_database;
SHOW CREATE DATABASE phone_recharge_db;

-- 应返回 7。
SELECT COUNT(*) AS business_table_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'phone_recharge_db'
  AND TABLE_TYPE = 'BASE TABLE';

SHOW TABLES;

-- 每一行都应为 present。
SELECT expected.table_name,
       CASE WHEN actual.TABLE_NAME IS NULL THEN 'missing' ELSE 'present' END AS table_status
FROM (
    SELECT 'app_user' AS table_name
    UNION ALL SELECT 'owner'
    UNION ALL SELECT 'mobile_number'
    UNION ALL SELECT 'purchase_order'
    UNION ALL SELECT 'order_item'
    UNION ALL SELECT 'recharge_card'
    UNION ALL SELECT 'recharge_record'
) AS expected
LEFT JOIN information_schema.TABLES AS actual
  ON actual.TABLE_SCHEMA = 'phone_recharge_db'
 AND actual.TABLE_NAME = expected.table_name
 AND actual.TABLE_TYPE = 'BASE TABLE'
ORDER BY expected.table_name;

-- 核对字段类型、可空性、默认值、自增、字符集和排序规则。
SELECT TABLE_NAME,
       ORDINAL_POSITION,
       COLUMN_NAME,
       COLUMN_TYPE,
       IS_NULLABLE,
       COLUMN_DEFAULT,
       EXTRA,
       CHARACTER_SET_NAME,
       COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'phone_recharge_db'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SHOW CREATE TABLE app_user;
SHOW CREATE TABLE owner;
SHOW CREATE TABLE mobile_number;
SHOW CREATE TABLE purchase_order;
SHOW CREATE TABLE order_item;
SHOW CREATE TABLE recharge_card;
SHOW CREATE TABLE recharge_record;

-- 预期：PRIMARY KEY=7、UNIQUE=6、FOREIGN KEY=6、CHECK=18。
SELECT CONSTRAINT_TYPE, COUNT(*) AS constraint_count
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'phone_recharge_db'
GROUP BY CONSTRAINT_TYPE
ORDER BY CONSTRAINT_TYPE;

SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'phone_recharge_db'
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;

-- 核对约束相关索引；不应出现人为添加的普通性能索引。
SHOW INDEX FROM app_user;
SHOW INDEX FROM owner;
SHOW INDEX FROM mobile_number;
SHOW INDEX FROM purchase_order;
SHOW INDEX FROM order_item;
SHOW INDEX FROM recharge_card;
SHOW INDEX FROM recharge_record;
