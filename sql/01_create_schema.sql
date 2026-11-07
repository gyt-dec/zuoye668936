-- 阶段 3：创建手机话费充值卡管理系统的 7 张业务表
-- 前置条件：已在普通 MySQL 兼容租户执行 00_create_database.sql。
-- 可重复执行：已有表不会被删除或清空；IF NOT EXISTS 不会修复已有错误结构。
-- 本阶段不建立性能实验用普通索引，只保留主键、候选键和外键需要的结构。

USE phone_recharge_db;

CREATE TABLE IF NOT EXISTS app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_name VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL COMMENT '只保存密码摘要，禁止明文',
    registered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    user_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    display_name VARCHAR(100) NULL,
    CONSTRAINT pk_app_user PRIMARY KEY (user_id),
    CONSTRAINT uk_app_user_login_name UNIQUE (login_name),
    CONSTRAINT ck_app_user_login_name CHECK (login_name <> ''),
    CONSTRAINT ck_app_user_password_hash CHECK (password_hash <> ''),
    CONSTRAINT ck_app_user_status CHECK (user_status IN ('ACTIVE', 'DISABLED'))
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE TABLE IF NOT EXISTS owner (
    owner_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_name VARCHAR(100) NOT NULL,
    contact_info VARCHAR(255) NULL,
    CONSTRAINT pk_owner PRIMARY KEY (owner_id),
    CONSTRAINT ck_owner_name CHECK (owner_name <> '')
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS mobile_number (
    mobile_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    number_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    registered_at DATETIME(6) NULL,
    CONSTRAINT pk_mobile_number PRIMARY KEY (mobile_id),
    CONSTRAINT uk_mobile_number_phone UNIQUE (phone_number),
    CONSTRAINT fk_mobile_number_owner
        FOREIGN KEY (owner_id) REFERENCES owner (owner_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_mobile_number_phone CHECK (phone_number <> ''),
    CONSTRAINT ck_mobile_number_status
        CHECK (number_status IN ('ACTIVE', 'INACTIVE'))
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS purchase_order (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    order_status VARCHAR(16) NOT NULL DEFAULT 'CREATED',
    total_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    completed_at DATETIME(6) NULL,
    CONSTRAINT pk_purchase_order PRIMARY KEY (order_id),
    CONSTRAINT uk_purchase_order_no UNIQUE (order_no),
    CONSTRAINT fk_purchase_order_user
        FOREIGN KEY (user_id) REFERENCES app_user (user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_purchase_order_no CHECK (order_no <> ''),
    CONSTRAINT ck_purchase_order_status
        CHECK (order_status IN ('CREATED', 'COMPLETED', 'CANCELLED')),
    CONSTRAINT ck_purchase_order_amount CHECK (total_amount >= 0),
    CONSTRAINT ck_purchase_order_completed_at CHECK (
        (order_status = 'COMPLETED' AND completed_at IS NOT NULL)
        OR
        (order_status IN ('CREATED', 'CANCELLED') AND completed_at IS NULL)
    )
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS order_item (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    denomination DECIMAL(10,2) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 1,
    CONSTRAINT pk_order_item PRIMARY KEY (item_id),
    CONSTRAINT uk_order_item_order_denomination UNIQUE (order_id, denomination),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id) REFERENCES purchase_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_order_item_denomination CHECK (denomination > 0),
    CONSTRAINT ck_order_item_quantity CHECK (quantity > 0)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS recharge_card (
    card_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    item_id BIGINT UNSIGNED NOT NULL,
    card_no VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL COMMENT '只保存卡密码摘要，禁止明文',
    face_value DECIMAL(10,2) NOT NULL,
    card_status VARCHAR(16) NOT NULL DEFAULT 'UNUSED',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    used_at DATETIME(6) NULL,
    CONSTRAINT pk_recharge_card PRIMARY KEY (card_id),
    CONSTRAINT uk_recharge_card_no UNIQUE (card_no),
    CONSTRAINT fk_recharge_card_item
        FOREIGN KEY (item_id) REFERENCES order_item (item_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_recharge_card_no CHECK (card_no <> ''),
    CONSTRAINT ck_recharge_card_password_hash CHECK (password_hash <> ''),
    CONSTRAINT ck_recharge_card_face_value CHECK (face_value > 0),
    CONSTRAINT ck_recharge_card_status CHECK (card_status IN ('UNUSED', 'USED')),
    CONSTRAINT ck_recharge_card_used_at CHECK (
        (card_status = 'UNUSED' AND used_at IS NULL)
        OR
        (card_status = 'USED' AND used_at IS NOT NULL)
    )
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS recharge_record (
    recharge_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    card_id BIGINT UNSIGNED NOT NULL,
    mobile_id BIGINT UNSIGNED NOT NULL,
    recharge_amount DECIMAL(10,2) NOT NULL,
    recharged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_recharge_record PRIMARY KEY (recharge_id),
    CONSTRAINT uk_recharge_record_card UNIQUE (card_id),
    CONSTRAINT fk_recharge_record_card
        FOREIGN KEY (card_id) REFERENCES recharge_card (card_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_recharge_record_mobile
        FOREIGN KEY (mobile_id) REFERENCES mobile_number (mobile_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_recharge_record_amount CHECK (recharge_amount > 0)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
