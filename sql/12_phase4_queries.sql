-- 阶段 4：适合报告展示的单表、聚合和多表 JOIN 查询。

USE phone_recharge_db;

-- Q01：用户状态分布（单表聚合）。
SELECT user_status, COUNT(*) AS user_count
FROM app_user
WHERE login_name LIKE 'p4_user_%'
GROUP BY user_status
ORDER BY user_status;

-- Q02：充值卡状态和面额分布（单表聚合）。
SELECT card_status, face_value, COUNT(*) AS card_count
FROM recharge_card
WHERE card_no LIKE 'P4-CARD-%'
GROUP BY card_status, face_value
ORDER BY card_status, face_value;

-- Q03：用户购卡明细，展示一次订单包含多个明细。
SELECT u.login_name, po.order_no, po.total_amount,
       oi.denomination, oi.quantity, rc.card_no, rc.card_status
FROM app_user u
JOIN purchase_order po ON po.user_id=u.user_id
JOIN order_item oi ON oi.order_id=po.order_id
JOIN recharge_card rc ON rc.item_id=oi.item_id
WHERE po.order_no='P4-ORDER-01'
ORDER BY oi.denomination;

-- Q04：手机号充值历史。
SELECT o.owner_name, mn.phone_number, rc.card_no,
       rr.recharge_amount, rr.recharged_at
FROM owner o
JOIN mobile_number mn ON mn.owner_id=o.owner_id
JOIN recharge_record rr ON rr.mobile_id=mn.mobile_id
JOIN recharge_card rc ON rc.card_id=rr.card_id
WHERE rc.card_no LIKE 'P4-CARD-%'
ORDER BY rr.recharged_at
LIMIT 10;

-- Q05：一个机主拥有多个号码。
SELECT o.owner_name, COUNT(mn.mobile_id) AS mobile_count,
       GROUP_CONCAT(mn.phone_number ORDER BY mn.phone_number) AS phone_numbers
FROM owner o
JOIN mobile_number mn ON mn.owner_id=o.owner_id
WHERE o.owner_name='P4_OWNER_01'
GROUP BY o.owner_id, o.owner_name;

-- Q06：一个订单包含多个订单明细。
SELECT po.order_no, COUNT(oi.item_id) AS item_count,
       SUM(oi.denomination * oi.quantity) AS calculated_total,
       po.total_amount
FROM purchase_order po
JOIN order_item oi ON oi.order_id=po.order_id
WHERE po.order_no='P4-ORDER-01'
GROUP BY po.order_id, po.order_no, po.total_amount;
