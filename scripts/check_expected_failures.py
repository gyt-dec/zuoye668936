#!/usr/bin/env python3
"""检查 obclient 日志中的预期失败标记与 ERROR 是否一一对应。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


MARKER_RE = re.compile(r"^EXPECT_FAIL\|([A-Z][0-9]{2})\|")
ERROR_RE = re.compile(r"^ERROR\s+\d+")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--expected", required=True, help="逗号分隔的用例编号")
    args = parser.parse_args()

    expected = args.expected.split(",")
    seen_markers: list[str] = []
    passed: list[str] = []
    unexpected_errors: list[str] = []
    pending: str | None = None

    for raw_line in args.log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        marker = MARKER_RE.match(line)
        if marker:
            if pending is not None:
                unexpected_errors.append(f"{pending} 后没有出现 ERROR")
            pending = marker.group(1)
            seen_markers.append(pending)
            continue

        if ERROR_RE.match(line):
            if pending is None:
                unexpected_errors.append(f"标记之外的数据库错误：{line}")
            else:
                passed.append(pending)
                pending = None

    if pending is not None:
        unexpected_errors.append(f"{pending} 后没有出现 ERROR")

    if seen_markers != expected:
        unexpected_errors.append(
            f"用例标记不匹配：expected={expected}, actual={seen_markers}"
        )
    if passed != expected:
        unexpected_errors.append(
            f"预期失败未全部触发：expected={expected}, passed={passed}"
        )

    if unexpected_errors:
        print("FAIL：预期失败日志检查未通过。")
        for item in unexpected_errors:
            print(f"- {item}")
        return 1

    print(f"PASS：{len(passed)} 个预期失败用例均被数据库拒绝，未发现标记外错误。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
