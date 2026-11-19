"""Manage SimuLearn product accounts (invite-only; there is no sign-up page).

Passwords are typed at a hidden prompt (getpass), never passed as arguments, so they stay out of shell history
and the process list. Talks to MongoDB through MONGODB_URI / MONGODB_DATABASE, from the shell or the repo's
`.env` (backend/app/env.py).

    python scripts/create_user.py create jdoe --name "J. Doe" [--role admin|educator]
    python scripts/create_user.py disable jdoe        # also signs out every open session
    python scripts/create_user.py enable jdoe
    python scripts/create_user.py reset-password jdoe # signs out every open session
    python scripts/create_user.py list
    python scripts/create_user.py has-admin           # exit 0 if an active admin exists (scripts/serve_product.sh)
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.product.auth import ROLES, Auth  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an account (asks for the password)")
    create.add_argument("username")
    create.add_argument("--name", default="", help="display name (default: the username)")
    create.add_argument("--role", choices=ROLES, default="educator")
    for name, help_text in (("disable", "block logins and end open sessions"), ("enable", "allow logins again"),
                            ("reset-password", "set a new password (asks for it)")):
        sub.add_parser(name, help=help_text).add_argument("username")
    sub.add_parser("list", help="list accounts")
    sub.add_parser("has-admin", help="exit 0 when at least one active admin exists, else 1 (prints no accounts)")
    return parser


def ask_new_password() -> Optional[str]:
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat it: "):
        print("Passwords don't match.", file=sys.stderr)
        return None
    return first


def auth_from_env() -> Auth:
    from pymongo import MongoClient

    from backend.app.env import load_env_file

    load_env_file()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        sys.exit("MONGODB_URI is not set (shell or .env).")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as e:
        sys.exit(f"Can't reach MongoDB ({type(e).__name__}). Is it running? (docker compose up -d)")
    return Auth(client[os.getenv("MONGODB_DATABASE", "simulearn")])


def main(argv: Optional[list[str]] = None, auth: Optional[Auth] = None) -> int:
    args = build_parser().parse_args(argv)
    auth = auth or auth_from_env()

    if args.command == "list":
        print(f"{'username':<24} {'role':<9} {'status':<9} {'created':<17} name")
        for u in auth.list_users():
            state = "disabled" if u.get("disabled") else "active"
            created = u["created_at"].strftime("%Y-%m-%d %H:%M")
            print(f"{u['username']:<24} {u['role']:<9} {state:<9} {created:<17} {u['display_name']}")
        return 0

    if args.command == "has-admin":
        if any(u["role"] == "admin" and not u.get("disabled") for u in auth.list_users()):
            return 0
        print("No active admin account. Create one: python scripts/create_user.py create <username> --role admin",
              file=sys.stderr)
        return 1

    if args.command != "create" and auth.get_user(args.username) is None:
        print(f"No user {args.username!r}.", file=sys.stderr)
        return 1

    try:
        if args.command == "create":
            password = ask_new_password()
            if password is None:
                return 1
            user = auth.create_user(args.username, args.name, password, role=args.role)
            print(f"Created {user['username']} ({user['role']}).")
        elif args.command in ("disable", "enable"):
            auth.set_disabled(args.username, args.command == "disable")
            print(f"{args.command.capitalize()}d {args.username}.")
        elif args.command == "reset-password":
            password = ask_new_password()
            if password is None:
                return 1
            auth.set_password(args.username, password)
            print(f"Password reset for {args.username}; their open sessions were signed out.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
