from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from backend.files.local import LocalObjectStore


def test_store_keeps_objects_independent(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "private")
    first = store.put(b"first")
    second = store.put(b"second")

    assert first != second
    assert store.get(first) == b"first"
    assert store.get(second) == b"second"

    store.delete(first)
    store.delete(first)
    with pytest.raises(FileNotFoundError):
        store.get(first)
    assert store.get(second) == b"second"


@pytest.mark.parametrize("key", ["../secret", "../../secret", "/secret"])
def test_rejects_paths(tmp_path: Path, key: str) -> None:
    secret = tmp_path / "secret"
    secret.write_bytes(b"private")
    store = LocalObjectStore(tmp_path / "objects")

    with pytest.raises(ValueError):
        store.get(key)
    with pytest.raises(ValueError):
        store.delete(key)
    assert secret.read_bytes() == b"private"


def test_key_collision_does_not_overwrite(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    key = store.put(b"original")

    with patch("backend.files.local.uuid4", return_value=UUID(key)):
        with pytest.raises(FileExistsError):
            store.put(b"replacement")

    assert store.get(key) == b"original"


def test_failed_write_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalObjectStore(tmp_path)
    original_write = Path.open

    def failing_open(path: Path, mode: str):
        file = original_write(path, mode)
        file.write(b"partial")

        def fail_write(content: bytes) -> int:
            raise OSError("disk full")

        monkeypatch.setattr(file, "write", fail_write)
        return file

    with patch.object(Path, "open", failing_open):
        with pytest.raises(OSError, match="disk full"):
            store.put(b"content")

    assert list(tmp_path.iterdir()) == []
