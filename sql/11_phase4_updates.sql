-- 阶段 4：逐表 UPDATE。所有修改保留业务一致性。

USE phone_recharge_db;
START TRANSACTION;

UPDATE app_user
SET display_name = '阶段4用户01-已更新'
WHERE login_name = 'p4_user_01';

UPDATE owner
SET contact_info = 'p4_owner01_updated@example.test'
WHERE owner_name = 'P4_OWNER_01';

UPDATE mobile_number
SET number_status = 'INACTIVE'
WHERE phone_number = '19940000001';

-- 同一事务同步调整订单01的一张卡面额快照及相关历史金额。
UPDATE purchase_order
SET total_amount = 90.00
WHERE order_no = 'P4-ORDER-01';

UPDATE order_item AS oi
JOIN purchase_order AS po ON po.order_id = oi.order_id
SET oi.denomination = 60.00
WHERE po.order_no = 'P4-ORDER-01' AND oi.denomination = 50.00;

UPDATE recharge_card
SET face_value = 60.00, password_hash = 'p4_card_hash_01_updated'
WHERE card_no = 'P4-CARD-01';

UPDATE recharge_record AS rr
JOIN recharge_card AS rc ON rc.card_id = rr.card_id
SET rr.recharge_amount = 60.00
WHERE rc.card_no = 'P4-CARD-01';

COMMIT;

SELECT 'updated_values' AS check_name,
 u.display_name, o.contact_info, mn.number_status,
 po.total_amount, oi.denomination, rc.face_value, rr.recharge_amount
FROM app_user u
JOIN purchase_order po ON po.user_id=u.user_id AND po.order_no='P4-ORDER-01'
JOIN order_item oi ON oi.order_id=po.order_id AND oi.denomination=60.00
JOIN recharge_card rc ON rc.item_id=oi.item_id AND rc.card_no='P4-CARD-01'
JOIN recharge_record rr ON rr.card_id=rc.card_id
JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id
JOIN owner o ON o.owner_id=mn.owner_id
WHERE u.login_name='p4_user_01';
