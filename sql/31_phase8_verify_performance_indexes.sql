-- 阶段8：只读核对三个性能索引的列顺序。
USE phone_recharge_db;
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'phone_recharge_db'
  AND INDEX_NAME IN (
    'idx_p8_card_status_created',
    'idx_p8_record_time_mobile',
    'idx_p8_order_status_created'
  )
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
