import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from onepassword_collector import cli

ACCOUNT = "a" * 26
VAULT = "v" * 26
USER = "u" * 26
SERVICE_ACCOUNT = "c" * 26
GROUP = "g" * 26
ITEM = "i" * 26
CANARY = "synthetic-secret-must-not-leave-process"


@pytest.fixture
def collector_process(tmp_path):
    responses = {
        "whoami": {
            "account_uuid": ACCOUNT,
            "user_uuid": SERVICE_ACCOUNT,
            "user_type": "SERVICE_ACCOUNT",
        },
        "vault list": [{"id": VAULT, "name": "Example vault"}],
        "user list": [
            {
                "id": USER,
                "name": "Example User",
                "email": "user@example.invalid",
                "state": "ACTIVE",
            }
        ],
        "group list": [{"id": GROUP, "name": "Example group"}],
        f"group user list {GROUP}": [{"id": USER}],
        f"sdk vault get {VAULT}": {
            "id": VAULT,
            "title": CANARY,
            "access": [
                {
                    "vault_uuid": VAULT,
                    "accessor_uuid": USER,
                    "accessor_type": "user",
                    "permissions": 32,
                },
                {
                    "vault_uuid": VAULT,
                    "accessor_uuid": SERVICE_ACCOUNT,
                    "accessor_type": "user",
                    "permissions": 48,
                },
                {
                    "vault_uuid": VAULT,
                    "accessor_uuid": GROUP,
                    "accessor_type": "group",
                    "permissions": 34,
                },
            ],
        },
        f"item list --vault={VAULT} --include-archive": [
            {
                "id": ITEM,
                "vault": {"id": VAULT},
                "title": "Example item",
                "fields": [{"value": CANARY}],
                "notesPlain": CANARY,
                "urls": [{"href": CANARY}],
                "tags": [CANARY],
                "additional_information": CANARY,
            }
        ],
    }
    responses_path = tmp_path / "provider.json"
    responses_path.write_text(json.dumps(responses))
    executable = tmp_path / "synthetic-op"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "flags = {'--format=json', '--iso-timestamps', '--cache=false', "
        "'--no-color'}\n"
        "command = ' '.join(arg for arg in sys.argv[1:] if arg not in flags)\n"
        "data = json.loads(Path(os.environ['COLLECTOR_TEST_RESPONSES']).read_text())\n"
        "if command == os.environ.get('COLLECTOR_TEST_FAILURE'):\n"
        f"    print({CANARY!r}, file=sys.stderr)\n"
        f"    print({CANARY!r})\n"
        "    sys.exit(1)\n"
        "if command not in data:\n"
        "    sys.exit(64)\n"
        "print(json.dumps(data[command]))\n"
    )
    executable.chmod(0o700)
    environment = {
        key: val for key, val in os.environ.items() if not key.startswith("OP_")
    }
    environment["COLLECTOR_TEST_RESPONSES"] = str(responses_path)
    environment["OP_SERVICE_ACCOUNT_TOKEN"] = CANARY
    environment["PYTHONPATH"] = str(Path(__file__).parent / "fakes")
    target = tmp_path / "snapshot.json"

    def run(*, failure=None, account_id=ACCOUNT, include_titles=False):
        env = environment.copy()
        if failure is not None:
            env["COLLECTOR_TEST_FAILURE"] = failure
        command = [
            sys.executable,
            "-m",
            "onepassword_collector",
            "--account-id",
            account_id,
            "--vault-id",
            VAULT,
            "--output",
            str(target),
            "--op-path",
            str(executable),
        ]
        if include_titles:
            command.append("--include-titles")
        return subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=20
        )

    return run, target


def test_complete_command_publishes_valid_schema_without_secret_fields(
    collector_process,
):
    run, target = collector_process
    result = run()

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    content = target.read_text()
    assert CANARY not in content + result.stdout + result.stderr
    snapshot = json.loads(content)
    assert snapshot["collector"] == {
        "name": "subimage-collector-onepassword",
        "version": version("subimage-collector-onepassword"),
    }
    schema_path = Path(__file__).parents[1] / "schemas/v1.json"
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(snapshot)
    assert snapshot["items"] == [{"id": ITEM, "vault_id": VAULT}]
    assert snapshot["scope"]["vault_ids"] == [VAULT]
    assert snapshot["vault_group_grants"][0]["permissions"] == [
        "manage_vault",
        "read_items",
    ]
    assert snapshot["vault_group_grants"][0]["permissions_bitmask"] == 34


@pytest.mark.parametrize(
    "failure",
    [
        "whoami",
        "vault list",
        "user list",
        "group list",
        f"group user list {GROUP}",
        "sdk authenticate",
        f"sdk vault get {VAULT}",
        f"item list --vault={VAULT} --include-archive",
    ],
)
def test_failed_provider_command_preserves_last_snapshot(collector_process, failure):
    run, target = collector_process
    target.write_bytes(b"previous-complete-snapshot")

    result = run(failure=failure)

    assert result.returncode == 1
    assert target.read_bytes() == b"previous-complete-snapshot"
    assert result.stdout == ""
    assert CANARY not in result.stderr
    assert "Traceback" not in result.stderr


def test_wrong_account_does_not_publish(collector_process):
    run, target = collector_process
    result = run(account_id="b" * 26)
    assert result.returncode == 1
    assert not target.exists()
    assert "account does not match" in result.stderr


def test_titles_only_appear_when_requested(collector_process):
    run, target = collector_process
    result = run(include_titles=True)
    assert result.returncode == 0
    snapshot = json.loads(target.read_text())
    assert snapshot["items"][0]["title"] == "Example item"
    assert snapshot["vaults"][0]["name"] == "Example vault"
    assert CANARY not in target.read_text()


def test_unexpected_error_does_not_print_exception_payload(
    monkeypatch, capsys, tmp_path
):
    def fail(*args, **kwargs):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(cli, "collect", fail)
    code = cli.main(
        [
            "--account-id",
            ACCOUNT,
            "--vault-id",
            VAULT,
            "--output",
            str(tmp_path / "snapshot.json"),
        ]
    )
    assert code == 1
    assert CANARY not in capsys.readouterr().err


def test_installed_cli_version_matches_distribution():
    result = subprocess.run(
        ["onepassword-collector", "--version"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == version("subimage-collector-onepassword")
    assert result.stderr == ""


def test_installed_cli_help_works_without_required_arguments():
    result = subprocess.run(
        ["onepassword-collector", "--help"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert "--account-id" in result.stdout
    assert "--vault-id" in result.stdout
    assert "--output" in result.stdout
    assert result.stderr == ""


def test_installed_cli_missing_arguments_exits_with_usage_error():
    result = subprocess.run(
        ["onepassword-collector"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "--account-id" in result.stderr
    assert "Traceback" not in result.stderr
