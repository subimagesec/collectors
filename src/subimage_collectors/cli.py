from __future__ import annotations

import argparse
import json
import sys

from subimage_collectors import __version__
from subimage_collectors.onepassword import CollectorError, collect
from subimage_collectors.output import (
    PublicationError,
    check_dependencies,
    destination,
    publish,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="subimage-collector",
        description="Collect metadata locally and publish a complete snapshot.",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="provider", required=True)
    onepassword = commands.add_parser("onepassword", help="Collect 1Password metadata")
    onepassword.add_argument(
        "--account-id", required=True, help="Expected 1Password account UUID"
    )
    onepassword.add_argument(
        "--vault-id",
        action="append",
        required=True,
        help="Vault UUID; repeat per vault",
    )
    onepassword.add_argument(
        "--output",
        required=True,
        help="Local file path, s3://bucket/key, or gs://bucket/key",
    )
    onepassword.add_argument(
        "--account", help="Optional 1Password CLI account selector"
    )
    onepassword.add_argument(
        "--include-titles",
        action="store_true",
        help="Include vault names and item titles (may contain sensitive text)",
    )
    onepassword.add_argument("--op-path", default="op", help="1Password CLI executable")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        target = destination(args.output)
        check_dependencies(target)
        snapshot = collect(
            args.vault_id,
            account_id=args.account_id,
            op_path=args.op_path,
            account=args.account,
            include_titles=args.include_titles,
        )
        data = (
            json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        publish(target, data)
    except (CollectorError, PublicationError) as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Collection interrupted.", file=sys.stderr)
        return 130
    except Exception:
        print(
            "Collection failed unexpectedly; raw provider data has been suppressed.",
            file=sys.stderr,
        )
        return 1
    print(
        "Published a complete snapshot for the configured vault scope.", file=sys.stderr
    )
    return 0
