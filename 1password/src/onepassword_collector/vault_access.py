import asyncio
from typing import Any

import onepassword as sdk

from onepassword_collector import __version__
from onepassword_collector.validation import CollectorError, identifier

SDK_TIMEOUT_SECONDS = 60
MAX_PERMISSION_MASK = (1 << 32) - 1
PERMISSIONS = {
    name.lower(): getattr(sdk, name)
    for name in (
        "ARCHIVE_ITEMS",
        "CREATE_ITEMS",
        "DELETE_ITEMS",
        "EXPORT_ITEMS",
        "IMPORT_ITEMS",
        "MANAGE_VAULT",
        "PRINT_ITEMS",
        "READ_ITEMS",
        "RECOVER_VAULT",
        "REVEAL_ITEM_PASSWORD",
        "SEND_ITEMS",
        "UPDATE_ITEMS",
        "UPDATE_ITEM_HISTORY",
    )
}


def project_vault_access(
    metadata: Any, expected_vault_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(metadata, dict):
        raise CollectorError("1Password returned invalid vault metadata.")
    vault_id = identifier(metadata.get("id"))
    if vault_id != expected_vault_id:
        raise CollectorError("1Password returned a different vault's metadata.")
    access = metadata.get("access")
    if not isinstance(access, list):
        raise CollectorError("1Password did not return the vault access list.")
    users: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in access:
        if not isinstance(entry, dict):
            raise CollectorError("1Password returned an invalid vault accessor.")
        if identifier(entry.get("vault_uuid")) != vault_id:
            raise CollectorError("1Password returned access for a different vault.")
        accessor_type = entry.get("accessor_type")
        if accessor_type not in ("user", "group"):
            raise CollectorError("1Password returned an unknown vault accessor type.")
        accessor_id = identifier(entry.get("accessor_uuid"))
        key = (accessor_type, accessor_id)
        if key in seen:
            raise CollectorError("1Password returned duplicate vault accessors.")
        seen.add(key)
        mask = entry.get("permissions")
        if type(mask) is not int or not 0 <= mask <= MAX_PERMISSION_MASK:
            raise CollectorError("1Password returned an invalid permission bitmask.")
        grant = {
            "vault_id": vault_id,
            f"{accessor_type}_id": accessor_id,
            "permissions": sorted(
                name for name, bit in PERMISSIONS.items() if mask & bit
            ),
            "permissions_bitmask": mask,
        }
        (users if accessor_type == "user" else groups).append(grant)
    users.sort(key=lambda row: row["user_id"])
    groups.sort(key=lambda row: row["group_id"])
    return users, groups


async def _read_vault_access(
    vault_ids: list[str], token: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        client = await asyncio.wait_for(
            sdk.Client.authenticate(
                auth=token,
                integration_name="SubImage Collectors",
                integration_version=__version__,
            ),
            timeout=SDK_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise CollectorError("1Password SDK authentication timed out.") from None
    except Exception:
        raise CollectorError("1Password SDK authentication failed.") from None
    users: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for vault_id in vault_ids:
        try:
            vault = await asyncio.wait_for(
                client.vaults.get(vault_id, sdk.VaultGetParams(accessors=True)),
                timeout=SDK_TIMEOUT_SECONDS,
            )
            metadata = vault.model_dump(mode="json")
        except TimeoutError:
            raise CollectorError("1Password SDK vault access timed out.") from None
        except Exception:
            raise CollectorError("1Password SDK vault access failed.") from None
        vault_users, vault_groups = project_vault_access(metadata, vault_id)
        users.extend(vault_users)
        groups.extend(vault_groups)
    return users, groups


def collect_vault_access(
    vault_ids: list[str], token: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return asyncio.run(_read_vault_access(vault_ids, token))
