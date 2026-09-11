from __future__ import annotations

import importlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class PublicationError(Exception):
    pass


@dataclass(frozen=True)
class Destination:
    kind: str
    location: str
    key: str | None = None


def destination(value: str) -> Destination:
    if not value or value == "-":
        raise PublicationError("Use a local file path, s3:// URL, or gs:// URL.")
    if "://" not in value:
        path = Path(value).expanduser()
        if not path.name or path.is_dir():
            raise PublicationError("The output must name a file.")
        return Destination("file", str(path))

    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"s3", "gs"}
        or not parsed.netloc
        or "@" in parsed.netloc
        or ":" in parsed.netloc
        or not parsed.path.strip("/")
        or parsed.query
        or parsed.fragment
    ):
        raise PublicationError("Use a bucket and object key without URL credentials.")
    return Destination(parsed.scheme, parsed.netloc, parsed.path[1:])


def _sdk(module: str, extra: str):
    try:
        return importlib.import_module(module)
    except ImportError:
        raise PublicationError(
            f"Install subimage-collectors[{extra}] for this output destination."
        ) from None


def check_dependencies(target: Destination) -> None:
    if target.kind == "s3":
        _sdk("boto3", "aws")
    elif target.kind == "gs":
        _sdk("google.cloud.storage", "gcp")


def publish(target: Destination, data: bytes) -> None:
    try:
        if target.kind == "file":
            _publish_file(Path(target.location), data)
        elif target.kind == "s3":
            _sdk("boto3", "aws").client("s3").put_object(
                Bucket=target.location,
                Key=target.key,
                Body=data,
                ContentType="application/json",
            )
        elif target.kind == "gs":
            _sdk("google.cloud.storage", "gcp").Client().bucket(target.location).blob(
                target.key
            ).upload_from_string(data, content_type="application/json", timeout=60)
        else:
            raise PublicationError("Unsupported output destination.")
    except PublicationError:
        raise
    except Exception:
        # Provider errors can contain credential material and request payloads.
        raise PublicationError(
            "Could not publish the snapshot. Check destination access and retry."
        ) from None


def _publish_file(path: Path, data: bytes) -> None:
    temporary_path: str | None = None
    try:
        fd, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)
