from pathlib import Path
from uuid import UUID, uuid4


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        name = UUID(key).hex
        path = (self.root / name).resolve()
        if path.parent != self.root:
            raise ValueError("文件路径超出存储目录")
        return path

    def put(self, content: bytes) -> str:
        key = uuid4().hex
        path = self._path(key)

        with path.open("xb") as file:
            try:
                file.write(content)
            except BaseException:
                file.close()
                path.unlink(missing_ok=True)
                raise

        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)