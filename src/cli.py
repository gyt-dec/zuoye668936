#!/usr/bin/env python3
"""简单Python CLI，不包含Web框架或前端。"""

from __future__ import annotations

import argparse
import getpass
import sys
from decimal import Decimal, InvalidOperation

from src.db import connect, transaction
from src.db_config import load_database_config
from src.errors import BusinessError
from src.services.mobile_service import create_owner_with_phones
from src.services.purchase_service import PurchaseLine, create_purchase
from src.services.query_service import (
    get_mobile_recharge_history,
    get_user_purchase_details,
)
from src.services.recharge_service import recharge_card
from src.services.user_service import register_user


def parse_lines(values: list[str], card_prefix: str, card_password: str) -> list[PurchaseLine]:
    lines: list[PurchaseLine] = []
    sequence = 1
    for value in values:
        try:
            denomination_text, quantity_text = value.split(":", 1)
            denomination = Decimal(denomination_text)
            quantity = int(quantity_text)
        except (ValueError, InvalidOperation) as exc:
            raise BusinessError("INVALID_LINE", "购卡明细格式应为面额:数量") from exc
        if denomination <= 0 or quantity <= 0:
            raise BusinessError("INVALID_LINE", "面额和数量必须大于0")
        card_numbers = tuple(
            f"{card_prefix}-{sequence + index:04d}" for index in range(quantity)
        )
        sequence += quantity
        lines.append(PurchaseLine(denomination, card_numbers, card_password))
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="手机话费充值卡管理系统CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    register = commands.add_parser("register", help="注册网络用户")
    register.add_argument("--login-name", required=True)
    register.add_argument("--display-name", required=True)

    owner = commands.add_parser("create-owner", help="创建机主和手机号")
    owner.add_argument("--owner-name", required=True)
    owner.add_argument("--contact-info")
    owner.add_argument("--phone", action="append", required=True)

    purchase = commands.add_parser("purchase", help="一次购买多张充值卡")
    purchase.add_argument("--login-name", required=True)
    purchase.add_argument("--order-no", required=True)
    purchase.add_argument("--line", action="append", required=True, help="面额:数量")
    purchase.add_argument("--card-prefix", required=True)

    recharge = commands.add_parser("recharge", help="使用充值卡充值")
    recharge.add_argument("--card-no", required=True)
    recharge.add_argument("--phone-number", required=True)

    purchase_history = commands.add_parser("purchase-history", help="查询用户购卡明细")
    purchase_history.add_argument("--login-name", required=True)

    recharge_history = commands.add_parser("recharge-history", help="查询手机号充值历史")
    recharge_history.add_argument("--phone-number", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_database_config()
    read_only = args.command in {"purchase-history", "recharge-history"}
    connection = connect(config, autocommit=read_only)
    try:
        if args.command == "register":
            user_password = getpass.getpass("请输入用户密码：")
            with transaction(connection):
                user_id = register_user(
                    connection, args.login_name, user_password, args.display_name
                )
            print(f"用户注册成功：user_id={user_id}")
        elif args.command == "create-owner":
            with transaction(connection):
                owner_id, mobile_ids = create_owner_with_phones(
                    connection, args.owner_name, args.contact_info, args.phone
                )
            print(f"机主和手机号创建成功：owner_id={owner_id}, mobile_count={len(mobile_ids)}")
        elif args.command == "purchase":
            card_password = getpass.getpass("请输入本批充值卡测试密码：")
            lines = parse_lines(args.line, args.card_prefix, card_password)
            with transaction(connection):
                result = create_purchase(
                    connection, args.login_name, args.order_no, lines
                )
            print(
                f"购卡成功：order_no={result['order_no']}, "
                f"card_count={len(result['card_ids'])}, total={result['total_amount']}"
            )
        elif args.command == "recharge":
            card_password = getpass.getpass("请输入充值卡密码：")
            with transaction(connection):
                result = recharge_card(
                    connection, args.card_no, card_password, args.phone_number
                )
            print(
                f"充值成功：recharge_id={result['recharge_id']}, "
                f"amount={result['amount']}, status={result['card_status']}"
            )
        elif args.command == "purchase-history":
            rows = get_user_purchase_details(connection, args.login_name)
            for row in rows:
                print(
                    f"{row['order_no']} | {row['card_no']} | "
                    f"{row['face_value']} | {row['card_status']}"
                )
            print(f"购卡明细数量：{len(rows)}")
        elif args.command == "recharge-history":
            rows = get_mobile_recharge_history(connection, args.phone_number)
            for row in rows:
                print(
                    f"{row['phone_number']} | {row['card_no']} | "
                    f"{row['recharge_amount']} | {row['recharged_at']}"
                )
            print(f"充值记录数量：{len(rows)}")
        return 0
    except BusinessError as exc:
        print(f"业务失败：{exc}", file=sys.stderr)
        return 2
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
