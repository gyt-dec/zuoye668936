-- 阶段 4：最终只读验证。

USE phone_recharge_db;

SELECT 'final_counts' AS check_name,
 (SELECT COUNT(*) FROM app_user WHERE login_name LIKE 'p4_user_%') AS users,
 (SELECT COUNT(*) FROM owner WHERE owner_name LIKE 'P4_OWNER_%') AS owners,
 (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE '1994000%') AS mobiles,
 (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE 'P4-ORDER-%') AS orders,
 (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%') AS items,
 (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE 'P4-CARD-%') AS cards,
 (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%') AS records;

-- 所有 orphan 数量均应为 0。
SELECT 'orphan_counts' AS check_name,
 (SELECT COUNT(*) FROM mobile_number mn LEFT JOIN owner o ON o.owner_id=mn.owner_id WHERE mn.phone_number LIKE '1994000%' AND o.owner_id IS NULL) AS mobile_owner,
 (SELECT COUNT(*) FROM purchase_order po LEFT JOIN app_user u ON u.user_id=po.user_id WHERE po.order_no LIKE 'P4-ORDER-%' AND u.user_id IS NULL) AS order_user,
 (SELECT COUNT(*) FROM order_item oi LEFT JOIN purchase_order po ON po.order_id=oi.order_id WHERE po.order_id IS NULL) AS item_order,
 (SELECT COUNT(*) FROM recharge_card rc LEFT JOIN order_item oi ON oi.item_id=rc.item_id WHERE rc.card_no LIKE 'P4-CARD-%' AND oi.item_id IS NULL) AS card_item,
 (SELECT COUNT(*) FROM recharge_record rr LEFT JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_id IS NULL) AS record_card,
 (SELECT COUNT(*) FROM recharge_record rr LEFT JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE mn.mobile_id IS NULL) AS record_mobile;

-- 金额、状态和一卡一记录异常数均应为 0。
SELECT 'business_rule_errors' AS check_name,
 (SELECT COUNT(*) FROM recharge_card rc JOIN order_item oi ON oi.item_id=rc.item_id WHERE rc.card_no LIKE 'P4-CARD-%' AND rc.face_value<>oi.denomination) AS card_item_amount,
 (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%' AND rr.recharge_amount<>rc.face_value) AS record_card_amount,
 (SELECT COUNT(*) FROM purchase_order po JOIN (SELECT order_id,SUM(denomination*quantity) amount FROM order_item GROUP BY order_id) x ON x.order_id=po.order_id WHERE po.order_no LIKE 'P4-ORDER-%' AND po.total_amount<>x.amount) AS order_total,
 (SELECT COUNT(*) FROM recharge_card rc LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id WHERE rc.card_no LIKE 'P4-CARD-%' AND ((rc.card_status='USED' AND rr.recharge_id IS NULL) OR (rc.card_status='UNUSED' AND rr.recharge_id IS NOT NULL))) AS card_record_status,
 (SELECT COUNT(*) FROM (SELECT card_id,COUNT(*) c FROM recharge_record GROUP BY card_id HAVING COUNT(*)>1) d) AS duplicate_card_record;

SELECT 'one_to_many_examples' AS check_name,
 (SELECT COUNT(*) FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE o.owner_name='P4_OWNER_01') AS owner01_mobile_count,
 (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE po.order_no='P4-ORDER-01') AS order01_item_count;
