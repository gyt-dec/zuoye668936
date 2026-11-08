# 阶段 5 视图与触发器实验记录

## 1. 当前状态与首次执行结论

阶段5已于本地OceanBase CE 5.0.1.0执行一次，真实主日志为 `phase5_views_triggers_20261108_032918.txt`。数据库实验主体成功，但入口脚本最终状态为 **FAIL**，因此阶段5暂不标记为完成。

FAIL的已知原因是日志解析误判：测试会话使用 `--batch` 且未使用 `--skip-column-names`，`SELECT 'EXPECT_FAIL|…'` 的列名和结果值相同，obclient为每个用例输出两个相邻相同标记。旧解析器把第二个标记误认为前一个标记后缺少ERROR。修复版同时关闭测试查询列名，并只允许一对相邻、完全相同的兼容标记。

## 2. 实验对象

视图：

- `v_user_card_purchase_detail`：用户、订单、订单明细和充值卡的购买明细；
- `v_mobile_recharge_history`：机主、手机号、充值记录和充值卡的充值历史。

触发器：

- `trg_recharge_record_validate`：BEFORE INSERT，检查卡存在、状态为 UNUSED，且充值金额等于卡面额；
- `trg_recharge_record_mark_card_used`：AFTER INSERT，把卡改为 USED，并把 `used_at` 设置为本次记录的 `recharged_at`。

## 3. 预期验证

| 项目 | 预期结果 | 首次真实结果 |
|---|---|---|
| 视图数量 | 2 | 2，成功 |
| 两个视图列数 | 15、11 | 15、11，成功 |
| 阶段4购卡/充值视图行数 | 11、10 | 11、10，成功 |
| 触发器数量 | 2 | 2，成功 |
| BEFORE/AFTER INSERT元数据 | 各1条 | 各1条，成功 |
| 正常充值记录数 | 1 | 1，成功 |
| 正常充值后的卡状态 | USED | USED，成功 |
| used_at | 等于recharged_at | `2026-05-01 09:00:00.123456`，成功 |
| 金额不符 | `P5_AMOUNT_MISMATCH` | ERROR 1644，符合预期 |
| 已使用卡 | `P5_CARD_NOT_UNUSED` | ERROR 1644，符合预期 |
| 同一卡重复充值 | `P5_CARD_NOT_UNUSED` | ERROR 1644，符合预期 |
| 失败后的状态 | `1|UNUSED|0|USED|0` | 符合预期 |
| P5测试数据残留 | 0 | `ROLLBACK_RESULT|0` |
| 阶段4执行前基准 | `10,10,11,10,11,11,10` | 符合预期 |
| 自动化最终状态 | PASS | FAIL：日志解析误判，待恢复验证 |

## 4. 事务与清理策略

P5用户、机主、号码、订单、明细、卡和充值记录全部在一个事务中创建。正常插入和三个失败用例完成后执行 ROLLBACK，再由新连接核对P5残留为0和阶段4计数未改变。视图和触发器是本阶段要保留的数据库对象，不在事务中回滚。

首次执行后2个视图和2个触发器已经存在。修复版入口在对象数为4时进入恢复验证模式，不重复创建或删除对象；它会严格核对视图列签名、关联定义、触发器时机、事件、目标表和动作语句。对象数为1—3时仍会停止，避免掩盖部分创建状态。

## 5. AFTER INSERT 与现有约束的静态审核

AFTER触发器只更新被新充值记录引用的 `recharge_card` 行，不改变主键、`item_id`或`card_id`，因此不改变现有FK关系。它在一个UPDATE中同时把 `card_status` 设为USED、把 `used_at`设为非空的 `NEW.recharged_at`，与 `ck_recharge_card_status` 和 `ck_recharge_card_used_at` 一致。`recharged_at`本身为NOT NULL，所以不会把空时间写入USED卡。

`recharge_record.card_id`的UNIQUE仍保留。一卡重复充值会先被BEFORE触发器以 `P5_CARD_NOT_UNUSED` 拒绝；即使业务校验出现并发竞态，UNIQUE仍是数据库层的最后防线。首次真实执行已验证正常插入、AFTER状态更新和三个失败分支。

## 6. OceanBase兼容性结论

首次真实执行证明OceanBase CE 5.0.1.0 MySQL模式支持本脚本使用的 `DELIMITER`、多语句触发器、`DECLARE`、`SELECT ... INTO`、`SIGNAL SQLSTATE '45000'`，以及AFTER INSERT触发器更新 `recharge_card`。当前待验证项只剩修复后入口能否完成全部自动断言并输出最终PASS。

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

脚本隐藏读取一次 `root@coursework` 密码。修复后的恢复验证尚未执行，阶段5仍不能写成PASS。
