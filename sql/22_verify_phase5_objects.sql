-- 阶段 5：只读检查视图、触发器元数据和阶段 4 数据查询结果。

USE phone_recharge_db;

SELECT TABLE_NAME, TABLE_TYPE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'phone_recharge_db'
  AND TABLE_NAME IN ('v_user_card_purchase_detail', 'v_mobile_recharge_history')
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'phone_recharge_db'
  AND TABLE_NAME IN ('v_user_card_purchase_detail', 'v_mobile_recharge_history')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT TRIGGER_NAME, EVENT_MANIPULATION, ACTION_TIMING, EVENT_OBJECT_TABLE
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'phone_recharge_db'
  AND TRIGGER_NAME IN ('trg_recharge_record_validate',
                       'trg_recharge_record_mark_card_used')
ORDER BY TRIGGER_NAME;

-- 阶段 4 最终数据应分别产生 11 条购卡明细和 10 条充值历史。
SELECT 'view_phase4_counts' AS check_name,
       (SELECT COUNT(*) FROM v_user_card_purchase_detail
         WHERE card_no LIKE 'P4-CARD-%') AS purchase_detail_rows,
       (SELECT COUNT(*) FROM v_mobile_recharge_history
         WHERE card_no LIKE 'P4-CARD-%') AS recharge_history_rows;

SELECT login_name, order_no, denomination, card_no, card_status
FROM v_user_card_purchase_detail
WHERE order_no = 'P4-ORDER-01'
ORDER BY denomination;

SELECT owner_name, phone_number, card_no, recharge_amount, recharged_at
FROM v_mobile_recharge_history
WHERE card_no = 'P4-CARD-01';
