-- 阶段10：在10万级充值记录表上增加可空业务字段。
-- 由阶段10自动化在确认字段不存在后执行；不要单独重复运行。
USE phone_recharge_db;

ALTER TABLE recharge_record
    ADD COLUMN recharge_source VARCHAR(16) NULL
    COMMENT '充值来源，阶段10在线结构变更实验';
