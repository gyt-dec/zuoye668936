-- 阶段 4：插入多样化基础测试数据
-- 共建立 12 条完整业务链，并为 Owner 01 增加第 2 个号码、为 Order 01 增加第 2 个明细。
-- 所有数据使用 P4/p4 标记或 1994000 专用号码段，与后续实验隔离。

USE phone_recharge_db;
START TRANSACTION;

INSERT INTO app_user
    (login_name, password_hash, registered_at, user_status, display_name)
VALUES
('p4_user_01','p4_user_hash_01','2026-01-01 09:00:00.000001','ACTIVE','阶段4用户01'),
('p4_user_02','p4_user_hash_02','2026-01-02 09:00:00.000002','ACTIVE','阶段4用户02'),
('p4_user_03','p4_user_hash_03','2026-01-03 09:00:00.000003','ACTIVE','阶段4用户03'),
('p4_user_04','p4_user_hash_04','2026-01-04 09:00:00.000004','ACTIVE','阶段4用户04'),
('p4_user_05','p4_user_hash_05','2026-01-05 09:00:00.000005','DISABLED','阶段4用户05'),
('p4_user_06','p4_user_hash_06','2026-01-06 09:00:00.000006','ACTIVE','阶段4用户06'),
('p4_user_07','p4_user_hash_07','2026-01-07 09:00:00.000007','ACTIVE','阶段4用户07'),
('p4_user_08','p4_user_hash_08','2026-01-08 09:00:00.000008','ACTIVE','阶段4用户08'),
('p4_user_09','p4_user_hash_09','2026-01-09 09:00:00.000009','ACTIVE','阶段4用户09'),
('p4_user_10','p4_user_hash_10','2026-01-10 09:00:00.000010','ACTIVE','阶段4用户10'),
('p4_user_11','p4_user_hash_11','2026-01-11 09:00:00.000011','ACTIVE','阶段4用户11'),
('p4_user_12','p4_user_hash_12','2026-01-12 09:00:00.000012','ACTIVE','阶段4用户12');

INSERT INTO owner (owner_name, contact_info) VALUES
('P4_OWNER_01','p4_owner01@example.test'),('P4_OWNER_02','p4_owner02@example.test'),
('P4_OWNER_03','p4_owner03@example.test'),('P4_OWNER_04','p4_owner04@example.test'),
('P4_OWNER_05',NULL),('P4_OWNER_06','p4_owner06@example.test'),
('P4_OWNER_07','p4_owner07@example.test'),('P4_OWNER_08','p4_owner08@example.test'),
('P4_OWNER_09','p4_owner09@example.test'),('P4_OWNER_10','p4_owner10@example.test'),
('P4_OWNER_11','p4_owner11@example.test'),('P4_OWNER_12','p4_owner12@example.test');

INSERT INTO mobile_number (owner_id, phone_number, number_status, registered_at)
SELECT o.owner_id, d.phone_number, d.number_status, d.registered_at
FROM owner AS o
JOIN (
 SELECT 'P4_OWNER_01' owner_name,'19940000001' phone_number,'ACTIVE' number_status,'2026-02-01 10:00:00.000001' registered_at
 UNION ALL SELECT 'P4_OWNER_02','19940000002','ACTIVE','2026-02-02 10:00:00.000002'
 UNION ALL SELECT 'P4_OWNER_03','19940000003','ACTIVE','2026-02-03 10:00:00.000003'
 UNION ALL SELECT 'P4_OWNER_04','19940000004','ACTIVE','2026-02-04 10:00:00.000004'
 UNION ALL SELECT 'P4_OWNER_05','19940000005','INACTIVE','2026-02-05 10:00:00.000005'
 UNION ALL SELECT 'P4_OWNER_06','19940000006','ACTIVE','2026-02-06 10:00:00.000006'
 UNION ALL SELECT 'P4_OWNER_07','19940000007','ACTIVE','2026-02-07 10:00:00.000007'
 UNION ALL SELECT 'P4_OWNER_08','19940000008','ACTIVE','2026-02-08 10:00:00.000008'
 UNION ALL SELECT 'P4_OWNER_09','19940000009','ACTIVE','2026-02-09 10:00:00.000009'
 UNION ALL SELECT 'P4_OWNER_10','19940000010','ACTIVE','2026-02-10 10:00:00.000010'
 UNION ALL SELECT 'P4_OWNER_11','19940000011','ACTIVE','2026-02-11 10:00:00.000011'
 UNION ALL SELECT 'P4_OWNER_12','19940000012','ACTIVE','2026-02-12 10:00:00.000012'
 UNION ALL SELECT 'P4_OWNER_01','19940000101','ACTIVE','2026-02-13 10:00:00.000013'
) AS d ON d.owner_name = o.owner_name;

INSERT INTO purchase_order
    (user_id, order_no, created_at, order_status, total_amount, completed_at)
SELECT u.user_id, d.order_no, d.created_at, 'COMPLETED', d.total_amount, d.completed_at
FROM app_user AS u
JOIN (
 SELECT 'p4_user_01' login_name,'P4-ORDER-01' order_no,'2026-03-01 11:00:00.000001' created_at,80.00 total_amount,'2026-03-01 11:05:00.000001' completed_at
 UNION ALL SELECT 'p4_user_02','P4-ORDER-02','2026-03-02 11:00:00.000002',20.00,'2026-03-02 11:05:00.000002'
 UNION ALL SELECT 'p4_user_03','P4-ORDER-03','2026-03-03 11:00:00.000003',30.00,'2026-03-03 11:05:00.000003'
 UNION ALL SELECT 'p4_user_04','P4-ORDER-04','2026-03-04 11:00:00.000004',50.00,'2026-03-04 11:05:00.000004'
 UNION ALL SELECT 'p4_user_05','P4-ORDER-05','2026-03-05 11:00:00.000005',100.00,'2026-03-05 11:05:00.000005'
 UNION ALL SELECT 'p4_user_06','P4-ORDER-06','2026-03-06 11:00:00.000006',20.00,'2026-03-06 11:05:00.000006'
 UNION ALL SELECT 'p4_user_07','P4-ORDER-07','2026-03-07 11:00:00.000007',30.00,'2026-03-07 11:05:00.000007'
 UNION ALL SELECT 'p4_user_08','P4-ORDER-08','2026-03-08 11:00:00.000008',50.00,'2026-03-08 11:05:00.000008'
 UNION ALL SELECT 'p4_user_09','P4-ORDER-09','2026-03-09 11:00:00.000009',100.00,'2026-03-09 11:05:00.000009'
 UNION ALL SELECT 'p4_user_10','P4-ORDER-10','2026-03-10 11:00:00.000010',20.00,'2026-03-10 11:05:00.000010'
 UNION ALL SELECT 'p4_user_11','P4-ORDER-11','2026-03-11 11:00:00.000011',30.00,'2026-03-11 11:05:00.000011'
 UNION ALL SELECT 'p4_user_12','P4-ORDER-12','2026-03-12 11:00:00.000012',50.00,'2026-03-12 11:05:00.000012'
) AS d ON d.login_name = u.login_name;

INSERT INTO order_item (order_id, denomination, quantity)
SELECT po.order_id, d.denomination, 1
FROM purchase_order AS po
JOIN (
 SELECT 'P4-ORDER-01' order_no,50.00 denomination UNION ALL SELECT 'P4-ORDER-01',30.00
 UNION ALL SELECT 'P4-ORDER-02',20.00 UNION ALL SELECT 'P4-ORDER-03',30.00
 UNION ALL SELECT 'P4-ORDER-04',50.00 UNION ALL SELECT 'P4-ORDER-05',100.00
 UNION ALL SELECT 'P4-ORDER-06',20.00 UNION ALL SELECT 'P4-ORDER-07',30.00
 UNION ALL SELECT 'P4-ORDER-08',50.00 UNION ALL SELECT 'P4-ORDER-09',100.00
 UNION ALL SELECT 'P4-ORDER-10',20.00 UNION ALL SELECT 'P4-ORDER-11',30.00
 UNION ALL SELECT 'P4-ORDER-12',50.00
) AS d ON d.order_no = po.order_no;

INSERT INTO recharge_card
    (item_id, card_no, password_hash, face_value, card_status, created_at, used_at)
SELECT oi.item_id, d.card_no, d.password_hash, d.face_value, d.card_status,
       d.created_at, d.used_at
FROM (
 SELECT 'P4-ORDER-01' order_no,50.00 denomination,'P4-CARD-01' card_no,'p4_card_hash_01' password_hash,50.00 face_value,'USED' card_status,'2026-03-01 11:06:00.000001' created_at,'2026-04-01 12:00:00.000001' used_at
 UNION ALL SELECT 'P4-ORDER-01',30.00,'P4-CARD-01B','p4_card_hash_01b',30.00,'UNUSED','2026-03-01 11:06:00.000002',NULL
 UNION ALL SELECT 'P4-ORDER-02',20.00,'P4-CARD-02','p4_card_hash_02',20.00,'USED','2026-03-02 11:06:00.000002','2026-04-02 12:00:00.000002'
 UNION ALL SELECT 'P4-ORDER-03',30.00,'P4-CARD-03','p4_card_hash_03',30.00,'USED','2026-03-03 11:06:00.000003','2026-04-03 12:00:00.000003'
 UNION ALL SELECT 'P4-ORDER-04',50.00,'P4-CARD-04','p4_card_hash_04',50.00,'USED','2026-03-04 11:06:00.000004','2026-04-04 12:00:00.000004'
 UNION ALL SELECT 'P4-ORDER-05',100.00,'P4-CARD-05','p4_card_hash_05',100.00,'USED','2026-03-05 11:06:00.000005','2026-04-05 12:00:00.000005'
 UNION ALL SELECT 'P4-ORDER-06',20.00,'P4-CARD-06','p4_card_hash_06',20.00,'USED','2026-03-06 11:06:00.000006','2026-04-06 12:00:00.000006'
 UNION ALL SELECT 'P4-ORDER-07',30.00,'P4-CARD-07','p4_card_hash_07',30.00,'USED','2026-03-07 11:06:00.000007','2026-04-07 12:00:00.000007'
 UNION ALL SELECT 'P4-ORDER-08',50.00,'P4-CARD-08','p4_card_hash_08',50.00,'USED','2026-03-08 11:06:00.000008','2026-04-08 12:00:00.000008'
 UNION ALL SELECT 'P4-ORDER-09',100.00,'P4-CARD-09','p4_card_hash_09',100.00,'USED','2026-03-09 11:06:00.000009','2026-04-09 12:00:00.000009'
 UNION ALL SELECT 'P4-ORDER-10',20.00,'P4-CARD-10','p4_card_hash_10',20.00,'USED','2026-03-10 11:06:00.000010','2026-04-10 12:00:00.000010'
 UNION ALL SELECT 'P4-ORDER-11',30.00,'P4-CARD-11','p4_card_hash_11',30.00,'USED','2026-03-11 11:06:00.000011','2026-04-11 12:00:00.000011'
 UNION ALL SELECT 'P4-ORDER-12',50.00,'P4-CARD-12','p4_card_hash_12',50.00,'USED','2026-03-12 11:06:00.000012','2026-04-12 12:00:00.000012'
) AS d
JOIN purchase_order AS po ON po.order_no = d.order_no
JOIN order_item AS oi ON oi.order_id = po.order_id AND oi.denomination = d.denomination;

INSERT INTO recharge_record (card_id, mobile_id, recharge_amount, recharged_at)
SELECT rc.card_id, mn.mobile_id, rc.face_value, rc.used_at
FROM recharge_card AS rc
JOIN mobile_number AS mn
  ON mn.phone_number = CONCAT('199400000', RIGHT(rc.card_no, 2))
WHERE rc.card_no IN ('P4-CARD-01','P4-CARD-02','P4-CARD-03','P4-CARD-04',
                     'P4-CARD-05','P4-CARD-06','P4-CARD-07','P4-CARD-08',
                     'P4-CARD-09','P4-CARD-10','P4-CARD-11','P4-CARD-12');

COMMIT;

SELECT 'seed_counts' AS check_name,
 (SELECT COUNT(*) FROM app_user WHERE login_name LIKE 'p4_user_%') AS users,
 (SELECT COUNT(*) FROM owner WHERE owner_name LIKE 'P4_OWNER_%') AS owners,
 (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE '1994000%') AS mobiles,
 (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE 'P4-ORDER-%') AS orders,
 (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%') AS items,
 (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE 'P4-CARD-%') AS cards,
 (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%') AS records;
