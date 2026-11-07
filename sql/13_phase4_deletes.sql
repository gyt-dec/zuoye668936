-- 阶段 4：逐表 DELETE。
-- 按子表到父表顺序删除编号 11、12 两条完整链，不关闭外键。

USE phone_recharge_db;
START TRANSACTION;

DELETE rr
FROM recharge_record rr
JOIN recharge_card rc ON rc.card_id=rr.card_id
WHERE rc.card_no IN ('P4-CARD-11','P4-CARD-12');

DELETE FROM recharge_card
WHERE card_no IN ('P4-CARD-11','P4-CARD-12');

DELETE oi
FROM order_item oi
JOIN purchase_order po ON po.order_id=oi.order_id
WHERE po.order_no IN ('P4-ORDER-11','P4-ORDER-12');

DELETE FROM purchase_order
WHERE order_no IN ('P4-ORDER-11','P4-ORDER-12');

DELETE FROM app_user
WHERE login_name IN ('p4_user_11','p4_user_12');

DELETE FROM mobile_number
WHERE phone_number IN ('19940000011','19940000012');

DELETE FROM owner
WHERE owner_name IN ('P4_OWNER_11','P4_OWNER_12');

COMMIT;

SELECT 'delete_targets_remaining' AS check_name,
 (SELECT COUNT(*) FROM app_user WHERE login_name IN ('p4_user_11','p4_user_12')) AS users,
 (SELECT COUNT(*) FROM owner WHERE owner_name IN ('P4_OWNER_11','P4_OWNER_12')) AS owners,
 (SELECT COUNT(*) FROM mobile_number WHERE phone_number IN ('19940000011','19940000012')) AS mobiles,
 (SELECT COUNT(*) FROM purchase_order WHERE order_no IN ('P4-ORDER-11','P4-ORDER-12')) AS orders,
 (SELECT COUNT(*) FROM recharge_card WHERE card_no IN ('P4-CARD-11','P4-CARD-12')) AS cards;
