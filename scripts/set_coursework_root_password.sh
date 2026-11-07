#!/usr/bin/env bash
# 为 root@coursework 交互式设置密码，并使用 -p 重新连接验证。
# 密码只保存在当前 shell 变量和 obclient 标准输入中，不写入文件或命令行参数。

set -euo pipefail

OB_HOST="127.0.0.1"
OB_PORT="2881"
OB_USER="root@coursework"

cleanup() {
    unset new_password confirm_password
}
trap cleanup EXIT INT TERM

if ! command -v obclient >/dev/null 2>&1; then
    echo "错误：未找到 obclient，请先确认客户端已安装并加入 PATH。" >&2
    exit 1
fi

echo "本脚本只修改 root@coursework 密码，不创建数据库或业务表。"
read -r -s -p "请输入新密码（至少12位，含大小写字母、数字和特殊字符）：" new_password
printf '\n'
read -r -s -p "请再次输入新密码：" confirm_password
printf '\n'

if [[ "${new_password}" != "${confirm_password}" ]]; then
    echo "错误：两次输入不一致，未执行任何 SQL。" >&2
    exit 1
fi

if (( ${#new_password} < 12 )) \
    || [[ ! "${new_password}" =~ [[:upper:]] ]] \
    || [[ ! "${new_password}" =~ [[:lower:]] ]] \
    || [[ ! "${new_password}" =~ [[:digit:]] ]] \
    || [[ ! "${new_password}" =~ [^[:alnum:]] ]]; then
    echo "错误：密码不满足本项目的最低复杂度要求，未执行任何 SQL。" >&2
    exit 1
fi

# 为避免构造 SQL 时出现转义歧义，本脚本不接受单引号或反斜杠。
if [[ "${new_password}" == *"'"* || "${new_password}" == *"\\"* ]]; then
    echo "错误：请不要在本次密码中使用单引号或反斜杠，未执行任何 SQL。" >&2
    exit 1
fi

echo "正在通过当前空密码连接设置新密码……"
if ! printf '%s\n' "ALTER USER root IDENTIFIED BY '${new_password}';" \
    | obclient -h"${OB_HOST}" -P"${OB_PORT}" -u"${OB_USER}" -A --batch; then
    echo "错误：ALTER USER 执行失败，密码设置状态未知。请停止并保存完整输出。" >&2
    exit 1
fi

unset new_password confirm_password

echo "ALTER USER 已执行。请在 obclient 提示时输入刚设置的新密码，以验证重新连接。"
if ! obclient -h"${OB_HOST}" -P"${OB_PORT}" -u"${OB_USER}" -p -A \
    --table -e "SELECT CURRENT_USER() AS current_account; SELECT VERSION() AS oceanbase_version; SHOW VARIABLES LIKE 'ob_compatibility_mode';"; then
    echo "错误：带密码重新连接验证失败。密码可能已经修改；不要重复运行本脚本。" >&2
    echo "请单独执行：obclient -h127.0.0.1 -P2881 -uroot@coursework -p -A" >&2
    exit 1
fi

echo "成功：root@coursework 密码已设置，带 -p 重新连接及只读验证通过。"
