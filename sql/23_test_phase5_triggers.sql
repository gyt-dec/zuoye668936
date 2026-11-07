-- 阶段 5：触发器正常路径及预期失败测试。
-- 所有 P5 业务数据均在本事务内创建，最后 ROLLBACK，不污染阶段 4 数据。

USE phone_recharge_db;
START TRANSACTION;

INSERT INTO app_user
    (login_name, password_hash, registered_at, user_status, display_name)
VALUES
    ('p5_user_01', 'p5_test_hash_user_01',
     '2026-05-01 08:00:00.000001', 'ACTIVE', '阶段5测试用户');

INSERT INTO owner (owner_name, contact_info)
VALUES ('P5_OWNER_01', 'p5_owner01@example.test');

INSERT INTO mobile_number
    (owner_id, phone_number, number_status, registered_at)
SELECT owner_id, '19950000001', 'ACTIVE', '2026-05-01 08:01:00.000001'
FROM owner WHERE owner_name = 'P5_OWNER_01';

INSERT INTO purchase_order
    (user_id, order_no, created_at, order_status, total_amount, completed_at)
SELECT user_id, 'P5-ORDER-01', '2026-05-01 08:02:00.000001',
       'COMPLETED', 90.00, '2026-05-01 08:03:00.000001'
FROM app_user WHERE login_name = 'p5_user_01';

INSERT INTO order_item (order_id, denomination, quantity)
SELECT order_id, 20.00, 1 FROM purchase_order WHERE order_no = 'P5-ORDER-01'
UNION ALL
SELECT order_id, 30.00, 1 FROM purchase_order WHERE order_no = 'P5-ORDER-01'
UNION ALL
SELECT order_id, 40.00, 1 FROM purchase_order WHERE order_no = 'P5-ORDER-01';

INSERT INTO recharge_card
    (item_id, card_no, password_hash, face_value, card_status, created_at, used_at)
SELECT oi.item_id, 'P5-CARD-OK', 'p5_card_hash_ok', 20.00,
       'UNUSED', '2026-05-01 08:04:00.000001', NULL
FROM order_item oi JOIN purchase_order po ON po.order_id = oi.order_id
WHERE po.order_no = 'P5-ORDER-01' AND oi.denomination = 20.00
UNION ALL
SELECT oi.item_id, 'P5-CARD-AMOUNT', 'p5_card_hash_amount', 30.00,
       'UNUSED', '2026-05-01 08:04:00.000002', NULL
FROM order_item oi JOIN purchase_order po ON po.order_id = oi.order_id
WHERE po.order_no = 'P5-ORDER-01' AND oi.denomination = 30.00
UNION ALL
SELECT oi.item_id, 'P5-CARD-USED', 'p5_card_hash_used', 40.00,
       'USED', '2026-05-01 08:04:00.000003', '2026-05-01 08:05:00.000003'
FROM order_item oi JOIN purchase_order po ON po.order_id = oi.order_id
WHERE po.order_no = 'P5-ORDER-01' AND oi.denomination = 40.00;

-- 正常充值：BEFORE 校验通过，AFTER 自动把卡改为 USED 并写入同一充值时间。
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount, recharged_at)
SELECT rc.card_id, mn.mobile_id, 20.00, '2026-05-01 09:00:00.123456'
FROM recharge_card rc CROSS JOIN mobile_number mn
WHERE rc.card_no = 'P5-CARD-OK' AND mn.phone_number = '19950000001';

SELECT CONCAT('NORMAL_RESULT|',
              (SELECT COUNT(*) FROM recharge_record rr
                JOIN recharge_card rc ON rc.card_id = rr.card_id
               WHERE rc.card_no = 'P5-CARD-OK'), '|',
              (SELECT card_status FROM recharge_card WHERE card_no = 'P5-CARD-OK'), '|',
              DATE_FORMAT((SELECT used_at FROM recharge_card
                            WHERE card_no = 'P5-CARD-OK'), '%Y-%m-%d %H:%i:%s.%f'));

SELECT 'EXPECT_FAIL|T01|P5_AMOUNT_MISMATCH';
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount, recharged_at)
SELECT rc.card_id, mn.mobile_id, 29.00, '2026-05-01 09:01:00.000001'
FROM recharge_card rc CROSS JOIN mobile_number mn
WHERE rc.card_no = 'P5-CARD-AMOUNT' AND mn.phone_number = '19950000001';

SELECT 'EXPECT_FAIL|T02|P5_CARD_NOT_UNUSED';
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount, recharged_at)
SELECT rc.card_id, mn.mobile_id, 40.00, '2026-05-01 09:02:00.000001'
FROM recharge_card rc CROSS JOIN mobile_number mn
WHERE rc.card_no = 'P5-CARD-USED' AND mn.phone_number = '19950000001';

-- 对刚刚正常充值的同一卡再次充值，应由 BEFORE 触发器拒绝。
SELECT 'EXPECT_FAIL|T03|P5_CARD_NOT_UNUSED';
INSERT INTO recharge_record (card_id, mobile_id, recharge_amount, recharged_at)
SELECT rc.card_id, mn.mobile_id, 20.00, '2026-05-01 09:03:00.000001'
FROM recharge_card rc CROSS JOIN mobile_number mn
WHERE rc.card_no = 'P5-CARD-OK' AND mn.phone_number = '19950000001';

SELECT CONCAT('FAILURE_STATE|',
              (SELECT COUNT(*) FROM recharge_record rr
                JOIN recharge_card rc ON rc.card_id = rr.card_id
               WHERE rc.card_no = 'P5-CARD-OK'), '|',
              (SELECT card_status FROM recharge_card WHERE card_no = 'P5-CARD-AMOUNT'), '|',
              (SELECT COUNT(*) FROM recharge_record rr
                JOIN recharge_card rc ON rc.card_id = rr.card_id
               WHERE rc.card_no = 'P5-CARD-AMOUNT'), '|',
              (SELECT card_status FROM recharge_card WHERE card_no = 'P5-CARD-USED'), '|',
              (SELECT COUNT(*) FROM recharge_record rr
                JOIN recharge_card rc ON rc.card_id = rr.card_id
               WHERE rc.card_no = 'P5-CARD-USED'));

ROLLBACK;

SELECT CONCAT('ROLLBACK_RESULT|',
    (SELECT COUNT(*) FROM app_user WHERE login_name LIKE 'p5_user_%') +
    (SELECT COUNT(*) FROM owner WHERE owner_name LIKE 'P5_OWNER_%') +
    (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE '1995000%') +
    (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE 'P5-ORDER-%') +
    (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE 'P5-CARD-%'));
