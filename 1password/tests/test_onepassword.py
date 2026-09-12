import copy
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from onepassword_collector import vault_access
from onepassword_collector.onepassword import (
    COMMAND_TIMEOUT_SECONDS,
    CollectorError,
    OpClient,
    collect,
)

ACCOUNT = "a" * 26
USER = "u" * 26
SERVICE_ACCOUNT = "s" * 26
AUTHENTICATED_SERVICE_ACCOUNT = "c" * 26
GROUP = "g" * 26
VAULT = "v" * 26
OTHER_VAULT = "w" * 26
ITEM = "i" * 26
OTHER_ID = "x" * 26
CANARY = "SECRET_CANARY_DO_NOT_EXPORT"


def provider_responses() -> dict[tuple[str, ...], Any]:
    return {
        ("whoami",): {
            "account_uuid": ACCOUNT,
            "user_uuid": AUTHENTICATED_SERVICE_ACCOUNT,
            "user_type": "SERVICE_ACCOUNT",
            "url": CANARY,
            "token": CANARY,
        },
        ("vault", "list"): [
            {"id": OTHER_VAULT, "name": CANARY},
            {"id": VAULT, "name": "Engineering", "description": CANARY},
        ],
        ("user", "list"): [
            {
                "id": USER,
                "name": "Example User",
                "email": "user@example.com",
                "state": "ACTIVE",
                "type": "USER",
                "secret_key": CANARY,
            }
        ],
        ("group", "list"): [{"id": GROUP, "name": "Engineering", "notes": CANARY}],
        ("group", "user", "list", GROUP): [
            {"id": USER, "name": CANARY, "email": CANARY, "token": CANARY}
        ],
        ("sdk", "vault", "get", VAULT): {
            "id": VAULT,
            "title": CANARY,
            "description": CANARY,
            "access": [
                {
                    "vault_uuid": VAULT,
                    "accessor_type": "user",
                    "accessor_uuid": USER,
                    "permissions": 32,
                },
                {
                    "vault_uuid": VAULT,
                    "accessor_type": "user",
                    "accessor_uuid": AUTHENTICATED_SERVICE_ACCOUNT,
                    "permissions": 48,
                },
                {
                    "vault_uuid": VAULT,
                    "accessor_type": "group",
                    "accessor_uuid": GROUP,
                    "permissions": 34,
                },
            ],
        },
        ("item", "list", f"--vault={VAULT}", "--include-archive"): [
            {
                "id": ITEM,
                "vault": {"id": VAULT, "name": CANARY},
                "title": "Example credential",
                "category": "LOGIN",
                "state": "ARCHIVED",
                "created_at": "2026-01-01T12:00:00-08:00",
                "updated_at": "2026-02-01T20:00:00Z",
                "version": 3,
                "fields": [{"id": "password", "value": CANARY}],
                "notesPlain": CANARY,
                "additional_information": CANARY,
                "urls": [{"href": CANARY}],
                "tags": [CANARY],
                "document": {"content": CANARY},
            }
        ],
    }


@pytest.fixture
def transport(monkeypatch):
    responses = provider_responses()
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.delenv("OP_CONNECT_HOST", raising=False)
    monkeypatch.delenv("OP_CONNECT_TOKEN", raising=False)
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", CANARY)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        arguments = tuple(
            value
            for value in command[1:]
            if value
            not in {
                "--format=json",
                "--iso-timestamps",
                "--cache=false",
                "--no-color",
            }
            and not value.startswith("--account=")
        )
        assert arguments in responses, f"Unexpected command: {arguments}"
        payload = responses[arguments]
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, subprocess.CompletedProcess):
            return payload
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), CANARY)

    monkeypatch.setattr(subprocess, "run", run)

    async def get_vault(vault_id, params):
        assert params.accessors is True
        payload = responses[("sdk", "vault", "get", vault_id)]
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(model_dump=lambda **kwargs: copy.deepcopy(payload))

    async def authenticate(**kwargs):
        assert kwargs["auth"] == CANARY
        return SimpleNamespace(vaults=SimpleNamespace(get=get_vault))

    monkeypatch.setattr(vault_access.sdk.Client, "authenticate", authenticate)
    return responses, calls


def test_snapshot_is_scoped_and_contains_only_allowlisted_metadata(transport, capsys):
    _, calls = transport
    snapshot = collect([VAULT], account_id=ACCOUNT)
    schema_path = Path(__file__).parents[1] / "schemas/v1.json"
    Draft202012Validator(
        json.loads(schema_path.read_text()), format_checker=FormatChecker()
    ).validate(snapshot)

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["collector"]["name"] == "subimage-collector-onepassword"
    assert snapshot["account_id"] == ACCOUNT
    assert snapshot["status"] == "complete"
    assert snapshot["scope"] == {
        "kind": "configured_vaults",
        "vault_ids": [VAULT],
        "include_archived": True,
    }
    assert (
        datetime.fromisoformat(snapshot["collected_at"].replace("Z", "+00:00")).tzinfo
        == UTC
    )
    UUID(snapshot["snapshot_id"])
    assert snapshot["users"] == [
        {"id": AUTHENTICATED_SERVICE_ACCOUNT, "type": "SERVICE_ACCOUNT"},
        {
            "id": USER,
            "name": "Example User",
            "email": "user@example.com",
            "state": "ACTIVE",
            "type": "USER",
        },
    ]
    assert snapshot["groups"] == [{"id": GROUP, "name": "Engineering"}]
    assert snapshot["group_memberships"] == [{"group_id": GROUP, "user_id": USER}]
    assert snapshot["vaults"] == [{"id": VAULT}]
    assert snapshot["vault_user_grants"] == [
        {
            "vault_id": VAULT,
            "user_id": AUTHENTICATED_SERVICE_ACCOUNT,
            "permissions": ["read_items", "reveal_item_password"],
            "permissions_bitmask": 48,
        },
        {
            "vault_id": VAULT,
            "user_id": USER,
            "permissions": ["read_items"],
            "permissions_bitmask": 32,
        },
    ]
    assert snapshot["vault_group_grants"] == [
        {
            "vault_id": VAULT,
            "group_id": GROUP,
            "permissions": ["manage_vault", "read_items"],
            "permissions_bitmask": 34,
        }
    ]
    assert snapshot["items"] == [
        {
            "id": ITEM,
            "vault_id": VAULT,
            "category": "LOGIN",
            "state": "ARCHIVED",
            "created_at": "2026-01-01T20:00:00Z",
            "updated_at": "2026-02-01T20:00:00Z",
            "version": 3,
        }
    ]
    assert OTHER_VAULT not in json.dumps(snapshot)
    assert CANARY not in json.dumps(snapshot)
    assert capsys.readouterr() == ("", "")
    assert all("get" not in command for command, _ in calls)
    assert all(
        "grant" not in command and "revoke" not in command for command, _ in calls
    )


def test_titles_require_explicit_opt_in(transport):
    snapshot = collect([VAULT], account_id=ACCOUNT, include_titles=True)
    assert snapshot["vaults"] == [{"id": VAULT, "name": "Engineering"}]
    assert snapshot["items"][0]["title"] == "Example credential"
    assert CANARY not in json.dumps(snapshot)


def test_null_group_membership_preserves_the_group_and_vault_grant(transport):
    responses, _ = transport
    responses[("group", "user", "list", GROUP)] = None

    snapshot = collect([VAULT], account_id=ACCOUNT)

    assert snapshot["group_memberships"] == []
    assert snapshot["groups"] == [{"id": GROUP, "name": "Engineering"}]
    assert snapshot["vault_group_grants"] == [
        {
            "vault_id": VAULT,
            "group_id": GROUP,
            "permissions": ["manage_vault", "read_items"],
            "permissions_bitmask": 34,
        }
    ]


@pytest.mark.parametrize(
    "operation",
    [
        ("vault", "list"),
        ("user", "list"),
        ("group", "list"),
        ("item", "list", f"--vault={VAULT}", "--include-archive"),
    ],
)
def test_null_other_lists_are_rejected(transport, operation):
    responses, _ = transport
    responses[operation] = None

    with pytest.raises(CollectorError):
        collect([VAULT], account_id=ACCOUNT)


def test_subprocess_is_noninteractive_and_never_carries_auth_tokens_in_arguments(
    transport, monkeypatch
):
    _, calls = transport
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", CANARY)
    monkeypatch.setenv("OP_DEBUG", "true")
    collect([VAULT], account_id=ACCOUNT, op_path="/opt/bin/op")
    for command, options in calls:
        assert command[0] == "/opt/bin/op"
        assert CANARY not in " ".join(command)
        assert not any(argument.startswith("--account=") for argument in command)
        assert options["stdin"] == subprocess.DEVNULL
        assert options["shell"] is False
        assert options["timeout"] == COMMAND_TIMEOUT_SECONDS
        assert options["env"]["OP_DEBUG"] == "false"
        assert options["env"]["OP_SERVICE_ACCOUNT_TOKEN"] == CANARY


def test_installed_cli_accepts_global_flags_with_an_empty_configuration(
    tmp_path, monkeypatch
):
    op_path = shutil.which("op")
    if op_path is None:
        pytest.skip("1Password CLI is not installed")
    monkeypatch.setattr(
        "onepassword_collector.onepassword.os.environ",
        {
            "OP_CONFIG_DIR": str(tmp_path),
            "OP_BIOMETRIC_UNLOCK_ENABLED": "false",
        },
    )

    client = OpClient(op_path)

    assert client.read(["account", "list"], "local account listing") == []


def test_service_account_token_is_required_before_any_provider_call(
    transport, monkeypatch
):
    _, calls = transport
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    with pytest.raises(CollectorError, match="OP_SERVICE_ACCOUNT_TOKEN is required"):
        collect([VAULT], account_id=ACCOUNT)
    assert calls == []


@pytest.mark.parametrize("variable", ["OP_CONNECT_HOST", "OP_CONNECT_TOKEN"])
def test_connect_authentication_is_rejected_without_disclosing_value(
    transport, monkeypatch, variable
):
    _, calls = transport
    monkeypatch.setenv(variable, CANARY)
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)
    assert not calls


@pytest.mark.parametrize("vault_ids", [[], [VAULT, VAULT], ["-"], ["--help"], "all"])
def test_scope_must_be_explicit_unique_vault_ids(transport, vault_ids):
    _, calls = transport
    with pytest.raises(CollectorError):
        collect(vault_ids, account_id=ACCOUNT)
    assert not calls


@pytest.mark.parametrize(
    "identity",
    [
        {},
        {"account_uuid": ACCOUNT},
        {"account_uuid": OTHER_ID, "user_uuid": USER},
        {"account_uuid": [ACCOUNT], "user_uuid": USER},
    ],
)
def test_missing_or_mismatched_account_identity_fails_before_inventory(
    transport, identity
):
    responses, calls = transport
    responses[("whoami",)] = identity
    with pytest.raises(CollectorError):
        collect([VAULT], account_id=ACCOUNT)
    assert len(calls) == 1


def test_unreadable_requested_vault_never_becomes_an_empty_snapshot(transport):
    responses, calls = transport
    responses[("vault", "list")] = [{"id": OTHER_VAULT}]
    with pytest.raises(CollectorError, match="cannot read every configured vault"):
        collect([VAULT], account_id=ACCOUNT)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "operation", [key for key in provider_responses() if key[0] != "sdk"]
)
def test_any_required_command_failure_aborts_without_leaking_provider_output(
    transport, operation, capsys
):
    responses, _ = transport
    responses[operation] = subprocess.CompletedProcess([], 1, CANARY, CANARY)
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired(CANARY, 60, output=CANARY, stderr=CANARY),
        OSError(CANARY),
        UnicodeError(CANARY),
    ],
)
def test_transport_errors_are_sanitized(transport, failure):
    responses, _ = transport
    responses[("whoami",)] = failure
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [CANARY, '{"token":"' + CANARY + '","token":1}', "NaN", "null", '"' + CANARY + '"'],
)
def test_malformed_or_ambiguous_json_cannot_escape_in_errors(transport, raw):
    responses, _ = transport
    responses[("whoami",)] = subprocess.CompletedProcess([], 0, raw, CANARY)
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)


@pytest.mark.parametrize(
    "payload", [{"items": []}, None, "[]", [None], [{"id": USER}, {"id": USER.upper()}]]
)
def test_unexpected_list_types_and_duplicate_ids_are_rejected(transport, payload):
    responses, _ = transport
    responses[("user", "list")] = payload
    with pytest.raises(CollectorError):
        collect([VAULT], account_id=ACCOUNT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vault", {"id": OTHER_VAULT}),
        ("vault", None),
        ("category", {}),
        ("state", []),
        ("created_at", "2026-01-01"),
        ("updated_at", CANARY),
        ("updated_at", "0001-01-01T00:00:00+14:00"),
        ("version", True),
        ("version", -1),
    ],
)
def test_invalid_item_metadata_is_rejected_without_exposing_values(
    transport, field, value
):
    responses, _ = transport
    responses[("item", "list", f"--vault={VAULT}", "--include-archive")][0][field] = (
        value
    )
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)


def test_successfully_observed_empty_vault_is_explicit(transport):
    responses, _ = transport
    responses[("item", "list", f"--vault={VAULT}", "--include-archive")] = []
    snapshot = collect([VAULT], account_id=ACCOUNT)
    assert snapshot["items"] == []
    assert snapshot["vaults"] == [{"id": VAULT}]
    assert snapshot["scope"]["vault_ids"] == [VAULT]


def test_an_item_cannot_appear_in_two_vaults_during_one_snapshot(transport):
    responses, _ = transport
    responses[("sdk", "vault", "get", OTHER_VAULT)] = {"id": OTHER_VAULT, "access": []}
    other_items = copy.deepcopy(
        responses[("item", "list", f"--vault={VAULT}", "--include-archive")]
    )
    other_items[0]["vault"]["id"] = OTHER_VAULT
    responses[("item", "list", f"--vault={OTHER_VAULT}", "--include-archive")] = (
        other_items
    )
    with pytest.raises(CollectorError, match="more than one vault"):
        collect([OTHER_VAULT, VAULT], account_id=ACCOUNT)


def service_account_metadata():
    return {
        "id": SERVICE_ACCOUNT,
        "name": "Example Collector",
        "email": "collector@example.com",
        "state": "ACTIVE",
        "type": "SERVICE_ACCOUNT",
    }


def test_service_account_membership_metadata_closes_sdk_user_reference(transport):
    responses, calls = transport
    service_account = service_account_metadata()
    responses[("group", "user", "list", GROUP)].append(
        {**service_account, "token": CANARY}
    )
    responses[("sdk", "vault", "get", VAULT)]["access"].append(
        {
            "vault_uuid": VAULT,
            "accessor_type": "user",
            "accessor_uuid": SERVICE_ACCOUNT,
            "permissions": 32,
        }
    )

    snapshot = collect([VAULT], account_id=ACCOUNT)

    assert snapshot["users"][1] == service_account
    assert len(snapshot["users"]) == 3
    assert any(
        row["user_id"] == SERVICE_ACCOUNT for row in snapshot["vault_user_grants"]
    )
    assert not any(command[1:3] == ["user", "get"] for command, _ in calls)
    assert CANARY not in json.dumps(snapshot)


@pytest.mark.parametrize("field", ["name", "email", "state", "type"])
def test_missing_service_account_members_require_complete_identity(transport, field):
    responses, _ = transport
    member = service_account_metadata()
    member.pop(field)
    responses[("group", "user", "list", GROUP)].append(member)
    with pytest.raises(CollectorError):
        collect([VAULT], account_id=ACCOUNT)


def test_unknown_ordinary_group_member_still_fails(transport):
    responses, _ = transport
    responses[("group", "user", "list", GROUP)].append(
        {**service_account_metadata(), "type": "USER"}
    )
    with pytest.raises(CollectorError, match="missing from the user list"):
        collect([VAULT], account_id=ACCOUNT)


@pytest.mark.parametrize("field", ["user_id", "user_uuid", "user"])
def test_documented_member_id_aliases_are_normalized(transport, field):
    responses, _ = transport
    member = responses[("group", "user", "list", GROUP)][0]
    member.pop("id")
    member[field] = {"id": USER} if field == "user" else USER
    snapshot = collect([VAULT], account_id=ACCOUNT)
    assert snapshot["group_memberships"] == [{"group_id": GROUP, "user_id": USER}]


def test_conflicting_member_id_aliases_are_rejected(transport):
    responses, _ = transport
    responses[("group", "user", "list", GROUP)][0]["user_id"] = OTHER_ID
    with pytest.raises(CollectorError, match="ambiguous"):
        collect([VAULT], account_id=ACCOUNT)


@pytest.mark.parametrize("principal_type", ["user", "group"])
def test_sdk_only_principal_is_resolved_with_validated_metadata(
    transport, principal_type
):
    responses, _ = transport
    responses[("sdk", "vault", "get", VAULT)]["access"].append(
        {
            "vault_uuid": VAULT,
            "accessor_type": principal_type,
            "accessor_uuid": OTHER_ID,
            "permissions": 1,
        }
    )
    responses[(principal_type, "get", OTHER_ID)] = {
        "id": OTHER_ID,
        "name": "Example Principal",
        "email": "principal@example.com",
        "state": "ACTIVE",
        "type": "USER",
        "description": CANARY,
    }
    if principal_type == "group":
        responses[("group", "user", "list", OTHER_ID)] = None

    snapshot = collect([VAULT], account_id=ACCOUNT)

    assert any(row["id"] == OTHER_ID for row in snapshot[f"{principal_type}s"])
    assert CANARY not in json.dumps(snapshot)


@pytest.mark.parametrize("principal_type", ["user", "group"])
@pytest.mark.parametrize("failure", ["denied", "wrong_id", "missing_name"])
def test_sdk_principal_lookup_failure_or_mismatch_aborts(
    transport, principal_type, failure
):
    responses, _ = transport
    responses[("sdk", "vault", "get", VAULT)]["access"].append(
        {
            "vault_uuid": VAULT,
            "accessor_type": principal_type,
            "accessor_uuid": OTHER_ID,
            "permissions": 1,
        }
    )
    lookup = {
        "id": OTHER_ID,
        "name": "Example",
        "email": "x@example.com",
        "state": "ACTIVE",
    }
    if failure == "denied":
        lookup = subprocess.CompletedProcess([], 1, CANARY, CANARY)
    elif failure == "wrong_id":
        lookup["id"] = USER
    else:
        lookup.pop("name")
    responses[(principal_type, "get", OTHER_ID)] = lookup
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)


def test_whoami_service_account_has_no_invented_identity_attributes(transport):
    snapshot = collect([VAULT], account_id=ACCOUNT)
    assert snapshot["users"][0] == {
        "id": AUTHENTICATED_SERVICE_ACCOUNT,
        "type": "SERVICE_ACCOUNT",
    }


@pytest.mark.parametrize("user_type", [None, "USER", "SERVICE_ACCOUNT_UNKNOWN"])
def test_whoami_must_identify_the_authenticated_service_account(transport, user_type):
    responses, calls = transport
    responses[("whoami",)]["user_type"] = user_type
    with pytest.raises(CollectorError, match="must be a service account"):
        collect([VAULT], account_id=ACCOUNT)
    assert len(calls) == 1
