-- 阶段8：性能实验索引。仅在完成无索引基线后执行。
USE phone_recharge_db;

CREATE INDEX idx_p8_card_status_created
    ON recharge_card (card_status, created_at, card_id);
CREATE INDEX idx_p8_record_time_mobile
    ON recharge_record (recharged_at, mobile_id, card_id);
CREATE INDEX idx_p8_order_status_created
    ON purchase_order (order_status, created_at, user_id, order_id);
