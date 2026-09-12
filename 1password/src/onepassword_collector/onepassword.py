import json
import os
import subprocess
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from onepassword_collector import __version__
from onepassword_collector.validation import CollectorError
from onepassword_collector.validation import identifier as _identifier
from onepassword_collector.vault_access import collect_vault_access

COMMAND_TIMEOUT_SECONDS = 60


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
    def __init__(self, op_path: str) -> None:
        self.op_path = _text(op_path, "CLI executable")
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
        ]
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


def _user(identifier: str, raw: dict[str, Any]) -> dict[str, str]:
    user = {"id": identifier}
    for field in ("name", "email", "state"):
        if field in raw or raw.get("type") != "SERVICE_ACCOUNT":
            user[field] = _text(
                raw.get(field), f"user {field}", allow_empty=field == "name"
            )
    if "type" in raw:
        user["type"] = _text(raw["type"], "user type")
    return user


def _include_referenced_user(
    users: dict[str, dict[str, str]], identifier: str, raw: dict[str, Any]
) -> None:
    if identifier in users:
        return
    # Service accounts can appear in relationships but not in the directory list.
    if raw.get("type") != "SERVICE_ACCOUNT":
        raise CollectorError("A referenced user is missing from the user list.")
    users[identifier] = _user(identifier, raw)


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

    client = OpClient(op_path)
    token = client.environment.get("OP_SERVICE_ACCOUNT_TOKEN")
    if not token:
        raise CollectorError("OP_SERVICE_ACCOUNT_TOKEN is required.")
    identity = _object(client.read(["whoami"], "account identity"))
    actual_account_id = _identifier(identity.get("account_uuid"))
    authenticated_user_id = _identifier(identity.get("user_uuid"))
    if identity.get("user_type") != "SERVICE_ACCOUNT":
        raise CollectorError("The authenticated identity must be a service account.")
    if actual_account_id != expected_account_id:
        raise CollectorError("The authenticated 1Password account does not match.")
    readable_vaults = _records(client.read(["vault", "list"], "vault listing"))
    if not set(requested_vault_ids).issubset(readable_vaults):
        raise CollectorError("The credential cannot read every configured vault.")
    raw_users = _records(client.read(["user", "list"], "user listing"), user_ids=True)
    raw_groups = _records(client.read(["group", "list"], "group listing"))
    users = {
        identifier: _user(identifier, raw) for identifier, raw in raw_users.items()
    }
    if authenticated_user_id in users:
        if users[authenticated_user_id].get("type") != "SERVICE_ACCOUNT":
            raise CollectorError("1Password returned a conflicting user identity.")
    else:
        users[authenticated_user_id] = {
            "id": authenticated_user_id,
            "type": "SERVICE_ACCOUNT",
        }

    groups: list[dict[str, Any]] = []
    group_memberships: list[dict[str, str]] = []
    for group_id, raw in sorted(raw_groups.items()):
        groups.append({"id": group_id, "name": _text(raw.get("name"), "group name")})
        raw_members = client.read(
            ["group", "user", "list", group_id], "group membership"
        )
        # The CLI returns JSON null for groups with no members.
        members = _records(
            [] if raw_members is None else raw_members,
            user_ids=True,
        )
        for user_id, raw_member in sorted(members.items()):
            _include_referenced_user(users, user_id, raw_member)
            group_memberships.append({"group_id": group_id, "user_id": user_id})

    user_grants, group_grants = collect_vault_access(requested_vault_ids, token)
    for grant in user_grants:
        user_id = grant["user_id"]
        if user_id not in users:
            raw = _object(client.read(["user", "get", user_id], "user metadata"))
            if _record_id(raw, user_ids=True) != user_id:
                raise CollectorError("1Password returned a different user identity.")
            users[user_id] = _user(user_id, raw)
    for grant in group_grants:
        group_id = grant["group_id"]
        if group_id not in raw_groups:
            raw = _object(client.read(["group", "get", group_id], "group metadata"))
            if _record_id(raw, user_ids=False) != group_id:
                raise CollectorError("1Password returned a different group identity.")
            raw_groups[group_id] = raw
            groups.append(
                {"id": group_id, "name": _text(raw.get("name"), "group name")}
            )
            raw_members = client.read(
                ["group", "user", "list", group_id], "group membership"
            )
            for user_id, member in sorted(
                _records(
                    [] if raw_members is None else raw_members, user_ids=True
                ).items()
            ):
                _include_referenced_user(users, user_id, member)
                group_memberships.append({"group_id": group_id, "user_id": user_id})

    vaults: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for vault_id in requested_vault_ids:
        vault = {"id": vault_id}
        if include_titles:
            vault["name"] = _text(
                readable_vaults[vault_id].get("name"), "vault name", allow_empty=True
            )
        vaults.append(vault)
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
        "collector": {"name": "subimage-collector-onepassword", "version": __version__},
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
        "users": [users[identifier] for identifier in sorted(users)],
        "groups": sorted(groups, key=lambda row: row["id"]),
        "group_memberships": sorted(
            group_memberships, key=lambda row: (row["group_id"], row["user_id"])
        ),
        "vaults": vaults,
        "vault_user_grants": user_grants,
        "vault_group_grants": group_grants,
        "items": items,
    }
