from pathlib import Path
from unittest.mock import Mock

import pytest

from subimage_collectors import output


def test_file_replacement_is_private_and_contains_exact_snapshot(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"previous snapshot")
    path.chmod(0o644)

    output.publish(output.destination(str(path)), b'{"status":"complete"}\n')

    assert path.read_bytes() == b'{"status":"complete"}\n'
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replacement_preserves_previous_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"previous snapshot")

    def failed_replace(*args):
        raise OSError("synthetic-private-provider-error")

    monkeypatch.setattr(output.os, "replace", failed_replace)
    with pytest.raises(output.PublicationError) as raised:
        output.publish(output.destination(str(path)), b"new snapshot")

    assert path.read_bytes() == b"previous snapshot"
    assert list(tmp_path.iterdir()) == [path]
    assert "synthetic-private-provider-error" not in str(raised.value)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/snapshot.json",
        "s3://example-bucket",
        "gs://example-bucket/",
        "s3://credential@example-bucket/snapshot.json",
        "s3://example-bucket:443/snapshot.json",
        "gs://example-bucket/snapshot.json?token=synthetic",
        "s3://example-bucket/snapshot.json#fragment",
        "-",
        "",
    ],
)
def test_invalid_destinations_are_rejected(value):
    with pytest.raises(output.PublicationError):
        output.destination(value)


def test_directory_is_not_a_snapshot_target(tmp_path):
    with pytest.raises(output.PublicationError):
        output.destination(str(tmp_path))


def test_s3_upload_has_only_projected_snapshot_and_no_public_acl(monkeypatch):
    sdk = Mock()
    monkeypatch.setattr(output, "_sdk", lambda *args: sdk)
    output.publish(
        output.destination("s3://example-bucket/scoped/latest.json"), b"{}\n"
    )
    sdk.client.assert_called_once_with("s3")
    sdk.client.return_value.put_object.assert_called_once_with(
        Bucket="example-bucket",
        Key="scoped/latest.json",
        Body=b"{}\n",
        ContentType="application/json",
    )


def test_gcs_upload_replaces_object_with_complete_content(monkeypatch):
    sdk = Mock()
    monkeypatch.setattr(output, "_sdk", lambda *args: sdk)
    output.publish(
        output.destination("gs://example-bucket/scoped/latest.json"), b"{}\n"
    )
    sdk.Client.return_value.bucket.assert_called_once_with("example-bucket")
    blob = sdk.Client.return_value.bucket.return_value.blob
    blob.assert_called_once_with("scoped/latest.json")
    blob.return_value.upload_from_string.assert_called_once_with(
        b"{}\n", content_type="application/json", timeout=60
    )


@pytest.mark.parametrize(
    "url", ["s3://example-bucket/latest.json", "gs://example-bucket/latest.json"]
)
def test_cloud_provider_errors_do_not_reveal_sensitive_data(url, monkeypatch):
    sdk = Mock()
    sdk.client.side_effect = RuntimeError("synthetic-secret-provider-error")
    sdk.Client.side_effect = RuntimeError("synthetic-secret-provider-error")
    monkeypatch.setattr(output, "_sdk", lambda *args: sdk)
    with pytest.raises(output.PublicationError) as raised:
        output.publish(output.destination(url), b"{}\n")
    assert "synthetic-secret-provider-error" not in str(raised.value)


def test_optional_sdk_error_is_actionable(monkeypatch):
    def unavailable(name):
        raise ImportError("synthetic-private-python-path")

    monkeypatch.setattr(output.importlib, "import_module", unavailable)
    with pytest.raises(output.PublicationError, match=r"subimage-collectors\[aws\]"):
        output.check_dependencies(
            output.destination("s3://example-bucket/snapshot.json")
        )


def test_local_output_does_not_load_cloud_sdks(tmp_path, monkeypatch):
    sdk = Mock(side_effect=AssertionError("local output loaded a cloud SDK"))
    monkeypatch.setattr(output, "_sdk", sdk)
    target = output.destination(str(tmp_path / "snapshot.json"))
    output.check_dependencies(target)
    output.publish(target, b"{}\n")
    assert Path(target.location).read_bytes() == b"{}\n"
