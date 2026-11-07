# 项目设计基线

## 1. 来源与仓库状态

本设计基线由用户在本次阶段 3 任务中提供并确认，不是从仓库中的阶段 1、2 文件读取所得。

开始本阶段时，Git `HEAD` 为 `bc6220a`，受版本控制的文件只有以下两份老师原始资料：

- 《数据库前沿技术》小作业 deadline 2026-11-30.docx
- 数据库实验报告-格式规范.docx

仓库中不存在此前阶段 1、2 的需求分析、E-R 图、关系模式或规范化文档。因此，本文件保存本次收到的权威关系模式，作为后续实现依据。

## 2. 老师原始要求摘要

选课序号为 16，`16 % 10 = 6`，对应“手机话费充值卡管理系统”。原始业务要求包括：注册用户一次可购买多张充值卡；每张卡有唯一编号和密码；卡号与密码用于给手机号码充值；一张卡只能用于一个号码并一次消费全部金额；一个号码只属于一个机主，一个机主可拥有多个号码。

课程作业还要求完成需求分析、E-R 图、关系模式、候选键和外键、CRUD、索引前后性能、大规模关联查询、高并发一致性、在线结构变更、数据校验和恢复，以及 B+ 树、冲突可串行性和 Paxos 的实现与测试。每张表至少插入 10 条数据，关联实验表至少达到 10 万条级；性能查询必须涉及表关联；并发实验需展示业务量扩大约 10 倍、100 倍时的效果及问题解决过程。

报告模板要求关系模式达到 3NF、逐表给出逻辑结构、至少建立并测试 2 个视图和 2 个触发器、增删改查每项不少于 2 个，并保存真实 SQL 结果和截图。最终报告还需遵守学校提供的封面、目录、页眉页码、字体、行距和图表标题格式。

## 3. 权威关系模式

1. User(user_id, login_name, password_hash, registered_at, user_status, display_name)
2. Owner(owner_id, owner_name, contact_info)
3. MobileNumber(mobile_id, owner_id, phone_number, number_status, registered_at)
4. PurchaseOrder(order_id, user_id, order_no, created_at, order_status, total_amount, completed_at)
5. OrderItem(item_id, order_id, denomination, quantity)
6. RechargeCard(card_id, item_id, card_no, password_hash, face_value, card_status, created_at, used_at)
7. RechargeRecord(recharge_id, card_id, mobile_id, recharge_amount, recharged_at)

物理表名依次为 `app_user`、`owner`、`mobile_number`、`purchase_order`、`order_item`、`recharge_card`、`recharge_record`。User 与 Owner 保持独立，不增加无业务依据的外键。

## 4. 主键和其他候选键

| 关系 | 主键 | 其他候选键 |
| --- | --- | --- |
| User | user_id | login_name |
| Owner | owner_id | 无 |
| MobileNumber | mobile_id | phone_number |
| PurchaseOrder | order_id | order_no |
| OrderItem | item_id | (order_id, denomination) |
| RechargeCard | card_id | card_no |
| RechargeRecord | recharge_id | card_id |

所有候选键均非空且唯一。姓名、联系方式、密码摘要和状态不是候选键。

## 5. 外键

1. `mobile_number.owner_id → owner.owner_id`
2. `purchase_order.user_id → app_user.user_id`
3. `order_item.order_id → purchase_order.order_id`
4. `recharge_card.item_id → order_item.item_id`
5. `recharge_record.card_id → recharge_card.card_id`
6. `recharge_record.mobile_id → mobile_number.mobile_id`

所有外键采用 `ON DELETE RESTRICT ON UPDATE RESTRICT`。历史订单、卡和充值记录被引用时，不允许通过级联操作误删或改写父记录。

## 6. 金额和状态设计

`OrderItem.subtotal` 不保存，由 `denomination × quantity` 计算。`purchase_order.total_amount` 是成交金额快照，`recharge_card.face_value` 是发行面额快照，`recharge_record.recharge_amount` 是成功充值事件的历史金额。

状态使用字符串配合 CHECK，不使用 ENUM。充值卡状态为 `UNUSED` 或 `USED`。一张卡最多有一条充值记录，由 `recharge_record.card_id` 的唯一约束保证；“未使用卡才能充值、充值金额等于面额、记录插入与状态更新原子完成”仍需后续事务和业务逻辑共同保证。

## 7. 物理类型基线

- 代理 ID：`BIGINT UNSIGNED AUTO_INCREMENT`
- 数量：`INT UNSIGNED`
- 手机号：`VARCHAR(32)`
- 卡号、订单号：`VARCHAR(64)`
- 密码摘要：`VARCHAR(255)`，禁止保存明文
- 单卡金额：`DECIMAL(10,2)`
- 订单总额：`DECIMAL(18,2)`
- 时间：`DATETIME(6)`
- 状态：`VARCHAR(16) + CHECK`
- 字符集与排序规则：`utf8mb4`、`utf8mb4_bin`

最终 7 个关系的 3NF 结论由用户提供并确认，本阶段不重新改变实体、候选键或函数依赖设计。
