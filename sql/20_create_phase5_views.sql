-- 阶段 5：创建两个业务视图。
-- 不暴露用户密码摘要或充值卡密码摘要。

USE phone_recharge_db;

CREATE VIEW v_user_card_purchase_detail AS
SELECT
    u.user_id,
    u.login_name,
    u.display_name,
    po.order_id,
    po.order_no,
    po.created_at AS order_created_at,
    po.order_status,
    po.total_amount,
    oi.item_id,
    oi.denomination,
    oi.quantity,
    rc.card_id,
    rc.card_no,
    rc.face_value,
    rc.card_status
FROM app_user AS u
JOIN purchase_order AS po ON po.user_id = u.user_id
JOIN order_item AS oi ON oi.order_id = po.order_id
JOIN recharge_card AS rc ON rc.item_id = oi.item_id;

CREATE VIEW v_mobile_recharge_history AS
SELECT
    o.owner_id,
    o.owner_name,
    mn.mobile_id,
    mn.phone_number,
    mn.number_status,
    rr.recharge_id,
    rc.card_id,
    rc.card_no,
    rc.card_status,
    rr.recharge_amount,
    rr.recharged_at
FROM owner AS o
JOIN mobile_number AS mn ON mn.owner_id = o.owner_id
JOIN recharge_record AS rr ON rr.mobile_id = mn.mobile_id
JOIN recharge_card AS rc ON rc.card_id = rr.card_id;
