import json
import os
import re
import subprocess
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from subimage_collectors import __version__

COMMAND_TIMEOUT_SECONDS = 60
_IDENTIFIER = re.compile(r"[a-zA-Z0-9]{26}\Z")
_PERMISSION = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class CollectorError(Exception):
    pass


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CollectorError("1Password returned an invalid object.")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise CollectorError(f"1Password returned an invalid {field}.")
    if any(ord(character) < 32 for character in value):
        raise CollectorError(f"1Password returned an invalid {field}.")
    return value


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CollectorError("A valid 26-character 1Password ID is required.")
    return value.lower()


def _record_id(record: dict[str, Any], *, user_ids: bool) -> str:
    candidates = [record["id"]] if "id" in record else []
    if user_ids:
        candidates.extend(
            record[field] for field in ("user_id", "user_uuid") if field in record
        )
        if "user" in record:
            candidates.append(_object(record["user"]).get("id"))
    identifiers = {_identifier(candidate) for candidate in candidates}
    if len(identifiers) != 1:
        raise CollectorError("1Password returned a missing or ambiguous record ID.")
    return identifiers.pop()


def _records(value: Any, *, user_ids: bool = False) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise CollectorError("1Password returned an invalid list.")
    records: dict[str, dict[str, Any]] = {}
    for entry in value:
        record = _object(entry)
        identifier = _record_id(record, user_ids=user_ids)
        if identifier in records:
            raise CollectorError("1Password returned duplicate records.")
        records[identifier] = record
    return records


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CollectorError("1Password returned ambiguous JSON.")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise CollectorError("1Password returned invalid JSON.")


class OpClient:
    def __init__(self, op_path: str, account: str | None) -> None:
        self.op_path = _text(op_path, "CLI executable")
        self.account = (
            _text(account, "account selector") if account is not None else None
        )
        self.environment = os.environ.copy()
        if self.environment.get("OP_CONNECT_HOST") or self.environment.get(
            "OP_CONNECT_TOKEN"
        ):
            raise CollectorError(
                "Unset OP_CONNECT_HOST and OP_CONNECT_TOKEN before collecting."
            )
        self.environment["OP_DEBUG"] = "false"

    def read(self, arguments: list[str], operation: str) -> Any:
        command = [
            self.op_path,
            *arguments,
            "--format=json",
            "--iso-timestamps",
            "--cache=false",
            "--no-color",
            "--encoding=UTF-8",
        ]
        if self.account is not None:
            command.append(f"--account={self.account}")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                stdin=subprocess.DEVNULL,
                shell=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
                env=self.environment,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise CollectorError(f"1Password {operation} timed out.") from None
        except (OSError, ValueError, UnicodeError):
            raise CollectorError(f"Could not run 1Password {operation}.") from None
        if result.returncode != 0:
            raise CollectorError(
                f"1Password {operation} failed. Check authentication and permissions."
            )
        if not isinstance(result.stdout, str):
            raise CollectorError(f"1Password {operation} returned invalid JSON.")
        try:
            return json.loads(
                result.stdout,
                object_pairs_hook=_json_object,
                parse_constant=_reject_json_constant,
            )
        except CollectorError:
            raise
        except (ValueError, RecursionError):
            raise CollectorError(
                f"1Password {operation} returned invalid JSON."
            ) from None


def _permissions(record: dict[str, Any]) -> list[str]:
    permissions = record.get("permissions")
    if isinstance(permissions, str):
        permissions = permissions.split(",")
    if not isinstance(permissions, list):
        raise CollectorError("1Password returned invalid vault permissions.")
    result = [
        _text(permission, "vault permission").strip() for permission in permissions
    ]
    if any(_PERMISSION.fullmatch(permission) is None for permission in result):
        raise CollectorError("1Password returned invalid vault permissions.")
    if len(result) != len(set(result)):
        raise CollectorError("1Password returned duplicate vault permissions.")
    return sorted(result)


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise CollectorError("1Password returned an invalid timestamp.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        raise CollectorError("1Password returned an invalid timestamp.") from None


def _item(
    identifier: str,
    raw: dict[str, Any],
    vault_id: str,
    include_titles: bool,
) -> dict[str, Any]:
    if "vault" in raw:
        reported_vault_id = _identifier(_object(raw["vault"]).get("id"))
        if reported_vault_id != vault_id:
            raise CollectorError("1Password returned an item from another vault.")
    item: dict[str, Any] = {"id": identifier, "vault_id": vault_id}
    for field in ("category", "state"):
        if field in raw:
            item[field] = _text(raw[field], f"item {field}")
    for field in ("created_at", "updated_at"):
        if field in raw:
            item[field] = _timestamp(raw[field])
    if "version" in raw:
        if type(raw["version"]) is not int or raw["version"] < 0:
            raise CollectorError("1Password returned an invalid item version.")
        item["version"] = raw["version"]
    if include_titles:
        item["title"] = _text(raw.get("title"), "item title", allow_empty=True)
    return item


def collect(
    vault_ids: list[str],
    *,
    account_id: str,
    op_path: str = "op",
    account: str | None = None,
    include_titles: bool = False,
) -> dict[str, Any]:
    expected_account_id = _identifier(account_id)
    if not isinstance(vault_ids, list) or not vault_ids:
        raise CollectorError("At least one explicit vault ID is required.")
    requested_vault_ids = sorted(_identifier(vault_id) for vault_id in vault_ids)
    if len(requested_vault_ids) != len(set(requested_vault_ids)):
        raise CollectorError("Vault IDs must not be repeated.")
    if not isinstance(include_titles, bool):
        raise CollectorError("include_titles must be a boolean.")

    client = OpClient(op_path, account)
    identity = _object(client.read(["whoami"], "account identity"))
    actual_account_id = _identifier(identity.get("account_uuid"))
    _identifier(identity.get("user_uuid"))
    if actual_account_id != expected_account_id:
        raise CollectorError("The authenticated 1Password account does not match.")
    if client.account is None and not client.environment.get(
        "OP_SERVICE_ACCOUNT_TOKEN"
    ):
        client.account = actual_account_id

    readable_vaults = _records(client.read(["vault", "list"], "vault listing"))
    if not set(requested_vault_ids).issubset(readable_vaults):
        raise CollectorError("The credential cannot read every configured vault.")
    raw_users = _records(client.read(["user", "list"], "user listing"), user_ids=True)
    raw_groups = _records(client.read(["group", "list"], "group listing"))
    users: list[dict[str, Any]] = []
    for identifier, raw in sorted(raw_users.items()):
        user = {
            "id": identifier,
            "name": _text(raw.get("name"), "user name", allow_empty=True),
            "email": _text(raw.get("email"), "user email"),
            "state": _text(raw.get("state"), "user state"),
        }
        if "type" in raw:
            user["type"] = _text(raw["type"], "user type")
        users.append(user)

    groups: list[dict[str, Any]] = []
    group_memberships: list[dict[str, str]] = []
    for group_id, raw in sorted(raw_groups.items()):
        groups.append({"id": group_id, "name": _text(raw.get("name"), "group name")})
        members = _records(
            client.read(["group", "user", "list", group_id], "group membership"),
            user_ids=True,
        )
        for user_id in sorted(members):
            if user_id not in raw_users:
                raise CollectorError("A group member is missing from the user list.")
            group_memberships.append({"group_id": group_id, "user_id": user_id})

    vaults: list[dict[str, str]] = []
    user_grants: list[dict[str, Any]] = []
    group_grants: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for vault_id in requested_vault_ids:
        vault = {"id": vault_id}
        if include_titles:
            vault["name"] = _text(
                readable_vaults[vault_id].get("name"), "vault name", allow_empty=True
            )
        vaults.append(vault)
        raw_user_grants = _records(
            client.read(["vault", "user", "list", vault_id], "vault user grants"),
            user_ids=True,
        )
        for user_id, raw in sorted(raw_user_grants.items()):
            if user_id not in raw_users:
                raise CollectorError("A vault user is missing from the user list.")
            user_grants.append(
                {
                    "vault_id": vault_id,
                    "user_id": user_id,
                    "permissions": _permissions(raw),
                }
            )
        raw_group_grants = _records(
            client.read(["vault", "group", "list", vault_id], "vault group grants")
        )
        for group_id, raw in sorted(raw_group_grants.items()):
            if group_id not in raw_groups:
                raise CollectorError("A vault group is missing from the group list.")
            group_grants.append(
                {
                    "vault_id": vault_id,
                    "group_id": group_id,
                    "permissions": _permissions(raw),
                }
            )
        raw_items = _records(
            client.read(
                ["item", "list", f"--vault={vault_id}", "--include-archive"],
                "item listing",
            )
        )
        for item_id, raw in sorted(raw_items.items()):
            if item_id in seen_item_ids:
                raise CollectorError("An item appeared in more than one vault.")
            seen_item_ids.add(item_id)
            items.append(_item(item_id, raw, vault_id, include_titles))

    return {
        "schema_version": "1.0",
        "collector": {"name": "subimage-collectors", "version": __version__},
        "provider": "onepassword",
        "account_id": actual_account_id,
        "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "snapshot_id": str(uuid4()),
        "scope": {
            "kind": "configured_vaults",
            "vault_ids": requested_vault_ids,
            "include_archived": True,
        },
        "status": "complete",
        "users": users,
        "groups": groups,
        "group_memberships": group_memberships,
        "vaults": vaults,
        "vault_user_grants": user_grants,
        "vault_group_grants": group_grants,
        "items": items,
    }
