import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from onepassword_collector import vault_access
from onepassword_collector.validation import CollectorError

VAULT = "v" * 26
OTHER_VAULT = "w" * 26
USER = "u" * 26
GROUP = "g" * 26
CANARY = "SECRET_CANARY_DO_NOT_EXPORT"


def metadata():
    return {
        "id": VAULT,
        "title": CANARY,
        "description": CANARY,
        "access": [
            {
                "vault_uuid": VAULT,
                "accessor_type": "user",
                "accessor_uuid": USER,
                "permissions": 32,
                "secret": CANARY,
            },
            {
                "vault_uuid": VAULT,
                "accessor_type": "group",
                "accessor_uuid": GROUP,
                "permissions": 3,
                "description": CANARY,
            },
        ],
    }


def test_sdk_projection_preserves_direct_and_group_permissions_without_free_text():
    users, groups = vault_access.project_vault_access(metadata(), VAULT)
    assert users == [
        {
            "vault_id": VAULT,
            "user_id": USER,
            "permissions": ["read_items"],
            "permissions_bitmask": 32,
        }
    ]
    assert groups == [
        {
            "vault_id": VAULT,
            "group_id": GROUP,
            "permissions": ["manage_vault", "recover_vault"],
            "permissions_bitmask": 3,
        }
    ]
    assert CANARY not in json.dumps([users, groups])


@pytest.mark.parametrize("mask", [0, 1 << 31, (1 << 31) | 32, (1 << 32) - 1])
def test_all_permission_bits_survive_without_inventing_unknown_flag_meanings(mask):
    payload = metadata()
    payload["access"][0]["permissions"] = mask
    users, _ = vault_access.project_vault_access(payload, VAULT)
    assert users[0]["permissions_bitmask"] == mask
    assert users[0]["permissions"] == sorted(
        name for name, bit in vault_access.PERMISSIONS.items() if mask & bit
    )


@pytest.mark.parametrize("access", [None, {}, "[]", [None]])
def test_absent_or_malformed_access_cannot_be_reported_as_empty(access):
    payload = metadata()
    payload["access"] = access
    with pytest.raises(CollectorError):
        vault_access.project_vault_access(payload, VAULT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vault_uuid", OTHER_VAULT),
        ("vault_uuid", None),
        ("accessor_uuid", CANARY),
        ("accessor_type", "role"),
        ("accessor_type", []),
        ("permissions", -1),
        ("permissions", True),
        ("permissions", "32"),
        ("permissions", None),
        ("permissions", 1 << 32),
    ],
)
def test_invalid_accessor_fields_are_rejected_without_echoing_values(field, value):
    payload = metadata()
    payload["access"][0][field] = value
    with pytest.raises(CollectorError) as error:
        vault_access.project_vault_access(payload, VAULT)
    assert CANARY not in str(error.value)


def test_wrong_vault_and_duplicate_accessors_are_rejected():
    with pytest.raises(CollectorError, match="different vault"):
        vault_access.project_vault_access(metadata(), OTHER_VAULT)
    payload = metadata()
    payload["access"].append(copy.deepcopy(payload["access"][0]))
    with pytest.raises(CollectorError, match="duplicate"):
        vault_access.project_vault_access(payload, VAULT)


def test_explicit_empty_sdk_access_list_is_preserved():
    assert vault_access.project_vault_access({"id": VAULT, "access": []}, VAULT) == (
        [],
        [],
    )


def test_sdk_authenticates_once_and_reads_only_configured_vault_metadata(monkeypatch):
    calls = []

    async def get(vault_id, params):
        assert params.accessors is True
        calls.append(vault_id)
        return SimpleNamespace(
            model_dump=lambda **kwargs: {"id": vault_id, "access": []}
        )

    async def authenticate(**kwargs):
        assert kwargs["auth"] == CANARY
        calls.append("authenticate")
        return SimpleNamespace(vaults=SimpleNamespace(get=get))

    monkeypatch.setattr(vault_access.sdk.Client, "authenticate", authenticate)

    assert vault_access.collect_vault_access([VAULT, OTHER_VAULT], CANARY) == ([], [])
    assert calls == ["authenticate", VAULT, OTHER_VAULT]


@pytest.mark.parametrize("stage", ["authentication", "vault access"])
@pytest.mark.parametrize("timeout", [False, True])
def test_sdk_failures_and_timeouts_are_sanitized(monkeypatch, capsys, stage, timeout):
    monkeypatch.setattr(vault_access, "SDK_TIMEOUT_SECONDS", 0.01)

    async def fail():
        if timeout:
            await asyncio.sleep(1)
        raise RuntimeError(CANARY)

    async def get(*args):
        return await fail()

    async def authenticate(**kwargs):
        if stage == "authentication":
            return await fail()
        return SimpleNamespace(vaults=SimpleNamespace(get=get))

    monkeypatch.setattr(vault_access.sdk.Client, "authenticate", authenticate)

    with pytest.raises(CollectorError) as error:
        vault_access.collect_vault_access([VAULT], CANARY)
    assert stage in str(error.value)
    assert ("timed out" if timeout else "failed") in str(error.value)
    assert CANARY not in str(error.value)
    assert capsys.readouterr() == ("", "")
