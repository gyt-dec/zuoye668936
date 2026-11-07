#!/usr/bin/env python3
"""检查阶段 5 触发器日志中的正常结果、预期失败和回滚结果。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


MARKER_RE = re.compile(r"^EXPECT_FAIL\|(T\d{2})\|([A-Z0-9_]+)$")
ERROR_RE = re.compile(r"^ERROR\s+\d+.*:\s*(.*)$")
EXPECTED = [
    ("T01", "P5_AMOUNT_MISMATCH"),
    ("T02", "P5_CARD_NOT_UNUSED"),
    ("T03", "P5_CARD_NOT_UNUSED"),
]


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：check_phase5_trigger_log.py <日志文件>")
        return 2

    lines = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
    stripped = [line.strip() for line in lines]
    normal_ok = any(
        line == "NORMAL_RESULT|1|USED|2026-05-01 09:00:00.123456"
        for line in stripped
    )
    failure_state_ok = "FAILURE_STATE|1|UNUSED|0|USED|0" in stripped
    rollback_ok = "ROLLBACK_RESULT|0" in stripped

    seen: list[tuple[str, str]] = []
    passed: list[tuple[str, str]] = []
    problems: list[str] = []
    pending: tuple[str, str] | None = None

    for line in stripped:
        marker = MARKER_RE.match(line)
        if marker:
            if pending is not None:
                problems.append(f"{pending[0]} 后没有出现 ERROR")
            pending = (marker.group(1), marker.group(2))
            seen.append(pending)
            continue

        error = ERROR_RE.match(line)
        if error:
            if pending is None:
                problems.append(f"标记之外的数据库错误：{line}")
            elif pending[1] not in error.group(1):
                problems.append(
                    f"{pending[0]} 错误消息不匹配：expected={pending[1]}, actual={error.group(1)}"
                )
                pending = None
            else:
                passed.append(pending)
                pending = None

    if pending is not None:
        problems.append(f"{pending[0]} 后没有出现 ERROR")
    if seen != EXPECTED:
        problems.append(f"用例标记不匹配：expected={EXPECTED}, actual={seen}")
    if passed != EXPECTED:
        problems.append(f"预期失败未全部触发：expected={EXPECTED}, passed={passed}")
    if not normal_ok:
        problems.append("缺少正常充值及 AFTER 触发器结果")
    if not failure_state_ok:
        problems.append("失败用例后的卡状态或记录数不符合预期")
    if not rollback_ok:
        problems.append("缺少 P5 数据回滚为 0 的结果")

    if problems:
        print("FAIL：阶段 5 触发器日志检查未通过。")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("PASS：正常充值、卡状态自动更新、3 个预期失败及事务回滚均符合预期。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
