-- 阶段 3：验证业务唯一约束和 CHECK 约束
-- 本脚本会故意产生重复键和 CHECK 失败错误，这些错误是预期结果。
-- 成功插入的测试行最后统一 ROLLBACK，不保留业务数据。
-- 若客户端遇到第一条错误便停止，请逐段执行并保存每条真实错误。

USE phone_recharge_db;
START TRANSACTION;

-- 建立一条最小有效数据链。测试字符串不是实际密码，只用于摘要字段占位。
INSERT INTO app_user (login_name, password_hash, user_status, display_name)
VALUES ('__p3_user__', 'fake_hash_for_constraint_test', 'ACTIVE', '阶段3测试用户');
SET @p3_user_id = LAST_INSERT_ID();

INSERT INTO owner (owner_name, contact_info)
VALUES ('阶段3测试机主', NULL);
SET @p3_owner_id = LAST_INSERT_ID();

INSERT INTO mobile_number (owner_id, phone_number, number_status)
VALUES (@p3_owner_id, '+8613900000301', 'ACTIVE');
SET @p3_mobile_id = LAST_INSERT_ID();

INSERT INTO purchase_order (user_id, order_no, order_status, total_amount)
VALUES (@p3_user_id, '__P3_ORDER__', 'CREATED', 100.00);
SET @p3_order_id = LAST_INSERT_ID();

INSERT INTO order_item (order_id, denomination, quantity)
VALUES (@p3_order_id, 50.00, 2);
SET @p3_item_id = LAST_INSERT_ID();

INSERT INTO recharge_card
    (item_id, card_no, password_hash, face_value, card_status)
VALUES
    (@p3_item_id, '__P3_CARD_1__', 'fake_card_hash_1', 50.00, 'UNUSED'),
    (@p3_item_id, '__P3_CARD_2__', 'fake_card_hash_2', 50.00, 'UNUSED');

SELECT card_id INTO @p3_card_id_1
FROM recharge_card WHERE card_no = '__P3_CARD_1__';
SELECT card_id INTO @p3_card_id_2
FROM recharge_card WHERE card_no = '__P3_CARD_2__';

INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (@p3_card_id_1, @p3_mobile_id, 50.00);

-- U01：以下 6 条语句应分别被候选键对应的 UNIQUE 拒绝。
INSERT INTO app_user (login_name, password_hash)
VALUES ('__p3_user__', 'another_fake_hash');

INSERT INTO mobile_number (owner_id, phone_number)
VALUES (@p3_owner_id, '+8613900000301');

INSERT INTO purchase_order (user_id, order_no)
VALUES (@p3_user_id, '__P3_ORDER__');

INSERT INTO order_item (order_id, denomination, quantity)
VALUES (@p3_order_id, 50.00, 1);

INSERT INTO recharge_card (item_id, card_no, password_hash, face_value)
VALUES (@p3_item_id, '__P3_CARD_1__', 'another_fake_hash', 50.00);

INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (@p3_card_id_1, @p3_mobile_id, 50.00);

-- C01：以下语句应分别被 CHECK 拒绝。
INSERT INTO app_user (login_name, password_hash, user_status)
VALUES ('__p3_bad_user__', 'fake_hash', 'UNKNOWN');

INSERT INTO purchase_order (user_id, order_no, total_amount)
VALUES (@p3_user_id, '__P3_NEGATIVE_ORDER__', -1.00);

INSERT INTO order_item (order_id, denomination, quantity)
VALUES (@p3_order_id, 100.00, 0);

INSERT INTO recharge_card
    (item_id, card_no, password_hash, face_value, card_status)
VALUES (@p3_item_id, '__P3_BAD_STATUS__', 'fake_hash', 50.00, 'INVALID');

INSERT INTO recharge_record (card_id, mobile_id, recharge_amount)
VALUES (@p3_card_id_2, @p3_mobile_id, -1.00);

ROLLBACK;

-- 回滚后以下计数均应为 0。
SELECT
  (SELECT COUNT(*) FROM app_user WHERE login_name = '__p3_user__') AS user_rows,
  (SELECT COUNT(*) FROM purchase_order WHERE order_no = '__P3_ORDER__') AS order_rows,
  (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE '__P3_CARD_%') AS card_rows;
