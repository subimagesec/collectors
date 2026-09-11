import copy
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from subimage_collectors.onepassword import (
    COMMAND_TIMEOUT_SECONDS,
    CollectorError,
    collect,
)

ACCOUNT = "a" * 26
USER = "u" * 26
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
            "user_uuid": USER,
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
        ("vault", "user", "list", VAULT): [
            {"id": USER, "permissions": ["view_items"], "name": CANARY}
        ],
        ("vault", "group", "list", VAULT): [
            {
                "id": GROUP,
                "permissions": ["view_items", "manage_vault"],
                "name": CANARY,
            }
        ],
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
                "--encoding=UTF-8",
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
    return responses, calls


def test_snapshot_is_scoped_and_contains_only_allowlisted_metadata(transport, capsys):
    _, calls = transport
    snapshot = collect([VAULT], account_id=ACCOUNT)
    schema_path = Path(__file__).parents[1] / "schemas/onepassword/v1.json"
    Draft202012Validator(
        json.loads(schema_path.read_text()), format_checker=FormatChecker()
    ).validate(snapshot)

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["collector"]["name"] == "subimage-collectors"
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
        {
            "id": USER,
            "name": "Example User",
            "email": "user@example.com",
            "state": "ACTIVE",
            "type": "USER",
        }
    ]
    assert snapshot["groups"] == [{"id": GROUP, "name": "Engineering"}]
    assert snapshot["group_memberships"] == [{"group_id": GROUP, "user_id": USER}]
    assert snapshot["vaults"] == [{"id": VAULT}]
    assert snapshot["vault_user_grants"] == [
        {"vault_id": VAULT, "user_id": USER, "permissions": ["view_items"]}
    ]
    assert snapshot["vault_group_grants"] == [
        {
            "vault_id": VAULT,
            "group_id": GROUP,
            "permissions": ["manage_vault", "view_items"],
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


def test_account_selector_is_separate_from_verified_account_identity(transport):
    _, calls = transport
    collect([VAULT], account_id=ACCOUNT.upper(), account="example.1password.com")
    assert all("--account=example.1password.com" in command for command, _ in calls)


def test_user_session_is_pinned_after_identity_check(transport, monkeypatch):
    _, calls = transport
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    collect([VAULT], account_id=ACCOUNT)
    assert not any(argument.startswith("--account=") for argument in calls[0][0])
    assert all(f"--account={ACCOUNT}" in command for command, _ in calls[1:])


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


@pytest.mark.parametrize("operation", list(provider_responses()))
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
    "operation",
    [
        ("group", "user", "list", GROUP),
        ("vault", "user", "list", VAULT),
        ("vault", "group", "list", VAULT),
    ],
)
def test_unknown_relationship_endpoints_are_rejected(transport, operation):
    responses, _ = transport
    responses[operation][0]["id"] = OTHER_ID
    with pytest.raises(CollectorError):
        collect([VAULT], account_id=ACCOUNT)


@pytest.mark.parametrize("field", ["user_id", "user_uuid", "user"])
def test_documented_user_id_aliases_are_normalized(transport, field):
    responses, _ = transport
    grant = responses[("vault", "user", "list", VAULT)][0]
    grant.pop("id")
    grant[field] = {"id": USER} if field == "user" else USER
    snapshot = collect([VAULT], account_id=ACCOUNT)
    assert snapshot["vault_user_grants"][0]["user_id"] == USER


def test_conflicting_user_id_aliases_are_rejected(transport):
    responses, _ = transport
    responses[("vault", "user", "list", VAULT)][0]["user_id"] = OTHER_ID
    with pytest.raises(CollectorError, match="ambiguous"):
        collect([VAULT], account_id=ACCOUNT)


def test_comma_delimited_permissions_are_normalized(transport):
    responses, _ = transport
    responses[("vault", "user", "list", VAULT)][0]["permissions"] = (
        " view_items, manage_vault "
    )
    snapshot = collect([VAULT], account_id=ACCOUNT)
    assert snapshot["vault_user_grants"][0]["permissions"] == [
        "manage_vault",
        "view_items",
    ]


@pytest.mark.parametrize(
    "permissions",
    [
        None,
        {},
        True,
        "",
        "view_items,,manage_vault",
        ["view_items", "view_items"],
        [CANARY],
        [1],
        ["view items"],
    ],
)
def test_invalid_permissions_never_become_empty_grants(transport, permissions):
    responses, _ = transport
    responses[("vault", "user", "list", VAULT)][0]["permissions"] = permissions
    with pytest.raises(CollectorError) as error:
        collect([VAULT], account_id=ACCOUNT)
    assert CANARY not in str(error.value)


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
    responses[("vault", "user", "list", OTHER_VAULT)] = []
    responses[("vault", "group", "list", OTHER_VAULT)] = []
    other_items = copy.deepcopy(
        responses[("item", "list", f"--vault={VAULT}", "--include-archive")]
    )
    other_items[0]["vault"]["id"] = OTHER_VAULT
    responses[("item", "list", f"--vault={OTHER_VAULT}", "--include-archive")] = (
        other_items
    )
    with pytest.raises(CollectorError, match="more than one vault"):
        collect([OTHER_VAULT, VAULT], account_id=ACCOUNT)
