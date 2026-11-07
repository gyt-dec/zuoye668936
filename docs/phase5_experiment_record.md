# 阶段 5 视图与触发器实验记录

## 1. 当前状态

SQL、日志检查程序和自动化入口已经准备，**尚未在本地 OceanBase 执行**。以下均为设计和预期结果，不能作为真实实验结果。

## 2. 实验对象

视图：

- `v_user_card_purchase_detail`：用户、订单、订单明细和充值卡的购买明细；
- `v_mobile_recharge_history`：机主、手机号、充值记录和充值卡的充值历史。

触发器：

- `trg_recharge_record_validate`：BEFORE INSERT，检查卡存在、状态为 UNUSED，且充值金额等于卡面额；
- `trg_recharge_record_mark_card_used`：AFTER INSERT，把卡改为 USED，并把 `used_at` 设置为本次记录的 `recharged_at`。

## 3. 预期验证

| 项目 | 预期结果 | 实际结果 |
|---|---|---|
| 视图数量 | 2 | 待本地验证 |
| 两个视图列数 | 15、11 | 待本地验证 |
| 阶段4购卡/充值视图行数 | 11、10 | 待本地验证 |
| 触发器数量 | 2 | 待本地验证 |
| BEFORE/AFTER INSERT元数据 | 各1条 | 待本地验证 |
| 正常充值记录数 | 1 | 待本地验证 |
| 正常充值后的卡状态 | USED | 待本地验证 |
| used_at | 等于recharged_at | 待本地验证 |
| 金额不符 | `P5_AMOUNT_MISMATCH` | 待本地验证 |
| 已使用卡 | `P5_CARD_NOT_UNUSED` | 待本地验证 |
| 同一卡重复充值 | `P5_CARD_NOT_UNUSED` | 待本地验证 |
| P5测试数据残留 | 0 | 待本地验证 |
| 阶段4最终行数 | `10,10,11,10,11,11,10` | 待本地验证 |
| 自动化最终状态 | PASS | 待本地验证 |

## 4. 事务与清理策略

P5用户、机主、号码、订单、明细、卡和充值记录全部在一个事务中创建。正常插入和三个失败用例完成后执行 ROLLBACK，再由新连接核对P5残留为0和阶段4计数未改变。视图和触发器是本阶段要保留的数据库对象，不在事务中回滚。

如果对象创建阶段发生真正错误，脚本会停止。DDL可能已经自动提交，因此不得盲目重跑，应先查询 `information_schema.VIEWS` 和 `information_schema.TRIGGERS` 判断是否部分创建。

## 5. AFTER INSERT 与现有约束的静态审核

AFTER触发器只更新被新充值记录引用的 `recharge_card` 行，不改变主键、`item_id`或`card_id`，因此不改变现有FK关系。它在一个UPDATE中同时把 `card_status` 设为USED、把 `used_at`设为非空的 `NEW.recharged_at`，与 `ck_recharge_card_status` 和 `ck_recharge_card_used_at` 一致。`recharged_at`本身为NOT NULL，所以不会把空时间写入USED卡。

`recharge_record.card_id`的UNIQUE仍保留。一卡重复充值通常会先被BEFORE触发器以 `P5_CARD_NOT_UNUSED` 拒绝；即使业务校验出现并发竞态，UNIQUE仍是数据库层的最后防线。上述结论已完成静态审核，真实触发器执行顺序与OceanBase行为仍待本地验证。

## 6. OceanBase待验证点

OceanBase CE 5.0.1.0 MySQL模式是否完整支持本脚本使用的 `DELIMITER`、多语句触发器、局部变量、`SELECT ... INTO`、`SIGNAL SQLSTATE '45000'`，以及AFTER INSERT触发器更新关联父表，均必须以本地真实执行为准。脚本没有把MySQL兼容等同于已经验证成功。

## 7. 对后续实验的影响

两个视图只执行查询，不改变数据。两个触发器会对每次 `recharge_record` 插入增加卡查询和卡更新：

- 10万级数据生成时，应区分“通过真实充值业务插入”和“为查询性能准备历史数据”两种数据集；不得无说明地禁用触发器；
- 索引性能实验应固定触发器状态，并在报告中记录，避免把触发器成本误算为索引成本；
- 并发重复充值实验应保留触发器，同时单独比较事务锁/条件更新方案；UNIQUE(card_id)仍是最终数据库约束防线；
- 若批量历史数据需要绕过业务触发器，应另建明确的实验装载流程，并在执行前获得阶段确认，不能直接在自动化脚本中删除触发器。

## 8. 本地执行入口

ChatGPT审核通过后，在仓库根目录只执行：

```bash
bash scripts/run_phase5_views_triggers.sh
```

脚本隐藏读取一次 `root@coursework` 密码。当前文档不包含任何本地执行结果。
