# 阶段11：数据库核心算法实现与测试计划

本阶段使用Python独立实现唯一键B+树、拉链Hash索引、冲突可串行性判别和单值Paxos确定性模拟器，不连接OceanBase。B+树完整覆盖插入、检索、范围查询、叶子/内部分裂、真实删除借位/合并和根收缩；阶数覆盖3、4、5，并用固定随机种子与Python字典差分验证。

冲突可串行性模块识别不同事务在同一数据项上的RW、WR、WW冲突，保存原始操作证据，建立优先图，通过DFS找环，并在无环时输出拓扑序。

Paxos使用5个Acceptor，提议编号为`(round, proposer_id)`，实现Prepare、Promise、Accept、Accepted和多数派。Acceptor、Learner按节点ID去重，覆盖少数/多数故障、Prepare/Accept丢包、过期提议及竞争Proposer继承最高已接受值。实现是单值Paxos教学模拟，不冒充OceanBase内部协议。

Hash索引用于覆盖老师补充说明中的散列表评分点，展示等值访问、冲突链、更新、删除和扩容，并说明它不适合范围查询。

唯一入口：`bash scripts/run_phase11_algorithms.sh`。输出真实文本日志、JSON事件和CSV汇总。
