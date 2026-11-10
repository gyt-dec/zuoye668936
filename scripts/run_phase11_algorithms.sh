#!/usr/bin/env bash
# 阶段11单一入口：不连接数据库，执行算法测试与示例。
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv-phase6/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="$(command -v python3)"
RESULT_DIR="${ROOT_DIR}/results/phase11"
LOG_FILE="${RESULT_DIR}/phase11_algorithms_$(date '+%Y%m%d_%H%M%S').txt"
mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1
echo "阶段11算法实验开始：$(date '+%F %T %z')"
echo "本阶段不连接OceanBase。"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m unittest \
  tests.test_bplus_tree tests.test_hash_index tests.test_conflict_serializability \
  tests.test_paxos tests.test_phase11_runner -v
export PYTHONPATH="${ROOT_DIR}" P11_RESULT_DIR="${RESULT_DIR}" PYTHONUNBUFFERED=1
"${PYTHON_BIN}" "${ROOT_DIR}/src/phase11_algorithm_experiments.py"
echo "阶段11入口最终状态：PASS"
