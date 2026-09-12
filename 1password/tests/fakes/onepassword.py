import json
import os
from pathlib import Path
from types import SimpleNamespace

ARCHIVE_ITEMS = 256
CREATE_ITEMS = 128
DELETE_ITEMS = 512
EXPORT_ITEMS = 4194304
IMPORT_ITEMS = 2097152
MANAGE_VAULT = 2
PRINT_ITEMS = 8388608
READ_ITEMS = 32
RECOVER_VAULT = 1
REVEAL_ITEM_PASSWORD = 16
SEND_ITEMS = 1048576
UPDATE_ITEMS = 64
UPDATE_ITEM_HISTORY = 1024


def fail_if_requested(operation):
    if operation == os.environ.get("COLLECTOR_TEST_FAILURE"):
        raise RuntimeError(os.environ["OP_SERVICE_ACCOUNT_TOKEN"])


class VaultGetParams:
    def __init__(self, *, accessors):
        self.accessors = accessors


class Vaults:
    async def get(self, vault_id, params):
        assert params.accessors is True
        operation = f"sdk vault get {vault_id}"
        fail_if_requested(operation)
        data = json.loads(Path(os.environ["COLLECTOR_TEST_RESPONSES"]).read_text())
        return SimpleNamespace(model_dump=lambda **kwargs: data[operation])


class Client:
    @classmethod
    async def authenticate(cls, *, auth, integration_name, integration_version):
        assert auth == os.environ["OP_SERVICE_ACCOUNT_TOKEN"]
        assert integration_name and integration_version
        fail_if_requested("sdk authenticate")
        return SimpleNamespace(vaults=Vaults())
