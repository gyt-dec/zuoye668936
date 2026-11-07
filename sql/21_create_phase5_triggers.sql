-- 阶段 5：创建充值记录校验触发器和充值卡状态维护触发器。
-- 语法按 OceanBase MySQL 兼容模式准备，实际兼容性等待本地 CE 5.0.1.0 验证。

USE phone_recharge_db;

DELIMITER $$

CREATE TRIGGER trg_recharge_record_validate
BEFORE INSERT ON recharge_record
FOR EACH ROW
BEGIN
    DECLARE v_card_count INT DEFAULT 0;
    DECLARE v_card_status VARCHAR(16) DEFAULT NULL;
    DECLARE v_face_value DECIMAL(10,2) DEFAULT NULL;

    SELECT COUNT(*), MAX(card_status), MAX(face_value)
      INTO v_card_count, v_card_status, v_face_value
      FROM recharge_card
     WHERE card_id = NEW.card_id;

    IF v_card_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'P5_CARD_NOT_FOUND';
    END IF;

    IF v_card_status <> 'UNUSED' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'P5_CARD_NOT_UNUSED';
    END IF;

    IF NEW.recharge_amount <> v_face_value THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'P5_AMOUNT_MISMATCH';
    END IF;
END$$

CREATE TRIGGER trg_recharge_record_mark_card_used
AFTER INSERT ON recharge_record
FOR EACH ROW
BEGIN
    UPDATE recharge_card
       SET card_status = 'USED',
           used_at = NEW.recharged_at
     WHERE card_id = NEW.card_id;
END$$

DELIMITER ;
