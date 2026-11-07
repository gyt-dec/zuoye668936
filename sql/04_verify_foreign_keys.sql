-- 阶段 3：验证 6 个外键的定义和 RESTRICT 行为
-- 本脚本会故意产生外键错误，错误是预期结果；测试数据最终回滚。

USE phone_recharge_db;

-- 元数据应列出 6 条外键，引用目标应与权威设计一致。
SELECT kcu.TABLE_NAME,
       kcu.CONSTRAINT_NAME,
       kcu.COLUMN_NAME,
       kcu.REFERENCED_TABLE_NAME,
       kcu.REFERENCED_COLUMN_NAME,
       rc.UPDATE_RULE,
       rc.DELETE_RULE
FROM information_schema.KEY_COLUMN_USAGE AS kcu
JOIN information_schema.REFERENTIAL_CONSTRAINTS AS rc
  ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
 AND rc.TABLE_NAME = kcu.TABLE_NAME
 AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
WHERE kcu.CONSTRAINT_SCHEMA = 'phone_recharge_db'
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME;

START TRANSACTION;

INSERT INTO app_user (login_name, password_hash)
VALUES ('__p3_fk_user__', 'fake_hash_for_fk_test');
SET @fk_user_id = LAST_INSERT_ID();

INSERT INTO owner (owner_name) VALUES ('阶段3外键测试机主');
SET @fk_owner_id = LAST_INSERT_ID();

INSERT INTO mobile_number (owner_id, phone_number)
VALUES (@fk_owner_id, '+8613900000401');
SET @fk_mobile_id = LAST_INSERT_ID();

INSERT INTO purchase_order (user_id, order_no)
VALUES (@fk_user_id, '__P3_FK_ORDER__');
SET @fk_order_id = LAST_INSERT_ID();

INSERT INTO order_item (order_id, denomination, quantity)
VALUES (@fk_order_id, 50.00, 2);
SET @fk_item_id = LAST_INSERT_ID();

INSERT INTO recharge_card (item_id, card_no, password_hash, face_value)
VALUES
  (@fk_item_id, '__P3_FK_CARD_1__', 'fake_card_hash_1', 50.00),
  (@fk_item_id, '__P3_FK_CARD_2__', 'fake_card_hash_2', 50.00);
SELECT card_id INTO @fk_card_id_1
FROM recharge_card WHERE card_no = '__P3_FK_CARD_1__';
SELECT card_id INTO @fk_card_id_2
FROM recharge_card WHERE card_no = '__P3_FK_CARD_2__';

INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (@fk_card_id_1, @fk_mobile_id, 50.00);

-- F01：子表引用不存在的父记录，应失败。
SELECT 'EXPECT_FAIL|F01|mobile missing owner' AS expected_failure;
INSERT INTO mobile_number (owner_id, phone_number)
VALUES (18446744073709551615, '+8613900000499');

SELECT 'EXPECT_FAIL|F02|order missing user' AS expected_failure;
INSERT INTO purchase_order (user_id, order_no)
VALUES (18446744073709551615, '__P3_BAD_FK_ORDER__');

SELECT 'EXPECT_FAIL|F03|item missing order' AS expected_failure;
INSERT INTO order_item (order_id, denomination, quantity)
VALUES (18446744073709551615, 100.00, 1);

SELECT 'EXPECT_FAIL|F04|card missing item' AS expected_failure;
INSERT INTO recharge_card (item_id, card_no, password_hash, face_value)
VALUES (18446744073709551615, '__P3_BAD_FK_CARD__', 'fake_hash', 50.00);

SELECT 'EXPECT_FAIL|F05|record missing card' AS expected_failure;
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (18446744073709551615, @fk_mobile_id, 50.00);

SELECT 'EXPECT_FAIL|F06|record missing mobile' AS expected_failure;
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (@fk_card_id_2, 18446744073709551615, 50.00);

-- F02：父记录已经被历史数据引用，RESTRICT 应阻止删除。
SELECT 'EXPECT_FAIL|R01|delete referenced owner' AS expected_failure;
DELETE FROM owner WHERE owner_id = @fk_owner_id;
SELECT 'EXPECT_FAIL|R02|delete referenced user' AS expected_failure;
DELETE FROM app_user WHERE user_id = @fk_user_id;
SELECT 'EXPECT_FAIL|R03|delete referenced order' AS expected_failure;
DELETE FROM purchase_order WHERE order_id = @fk_order_id;
SELECT 'EXPECT_FAIL|R04|delete referenced item' AS expected_failure;
DELETE FROM order_item WHERE item_id = @fk_item_id;
SELECT 'EXPECT_FAIL|R05|delete referenced card' AS expected_failure;
DELETE FROM recharge_card WHERE card_id = @fk_card_id_1;
SELECT 'EXPECT_FAIL|R06|delete referenced mobile' AS expected_failure;
DELETE FROM mobile_number WHERE mobile_id = @fk_mobile_id;

ROLLBACK;

SELECT
  (SELECT COUNT(*) FROM app_user WHERE login_name = '__p3_fk_user__') AS user_rows,
  (SELECT COUNT(*) FROM purchase_order WHERE order_no = '__P3_FK_ORDER__') AS order_rows,
  (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE '__P3_FK_CARD_%') AS card_rows;
