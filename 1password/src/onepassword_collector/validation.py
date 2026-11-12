import re
from typing import Any

_IDENTIFIER = re.compile(r"[a-zA-Z0-9]{26}\Z")


class CollectorError(Exception):
    pass


def identifier(value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CollectorError("A valid 26-character 1Password ID is required.")
    return value.lower()
