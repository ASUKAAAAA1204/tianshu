"""Storage adapter boundary.

The current implementation uses SQLite for offline and competition modes.
The interface is intentionally small so PostgreSQL/PostGIS can be added
without changing HTTP handlers or domain services.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from db import DATABASE_URL, DEFAULT_DB, database_config, connect


@dataclass(frozen=True)
class StorageInfo:
    backend: str
    ready: bool
    driver: str | None
    spatial_engine: str
    message: str


class StorageAdapter:
    @property
    def info(self) -> StorageInfo:
        raise NotImplementedError

    @contextmanager
    def session(self) -> Iterator[object]:
        raise NotImplementedError


class SQLiteStorage(StorageAdapter):
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = path

    @property
    def info(self) -> StorageInfo:
        return StorageInfo("sqlite", True, "sqlite3", "polygon_python", "SQLite离线模式已启用，使用严格Polygon计算")

    @contextmanager
    def session(self):
        db = connect(self.path)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
                db.close()


class PostgresStorage(StorageAdapter):
    def __init__(self, url: str = DATABASE_URL):
        self.url = url
        try:
            import psycopg  # type: ignore
        except ImportError as error:
            raise RuntimeError("PostgreSQL适配器需要安装 psycopg[binary]") from error
        self._driver = psycopg

    @property
    def info(self) -> StorageInfo:
        return StorageInfo("postgresql", True, "psycopg", "postgis", "PostgreSQL驱动已就绪")

    @contextmanager
    def session(self):
        connection = self._driver.connect(self.url)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def build_storage(url: str | None = None) -> StorageAdapter:
    config = database_config(url) if url else database_config()
    if config["backend"] == "sqlite":
        if config["url"].startswith("sqlite:///"):
            raw_path = config["url"][len("sqlite:///"):]
            path = Path(raw_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            return SQLiteStorage(path)
        return SQLiteStorage()
    if config["backend"] == "postgresql":
        return PostgresStorage(config["url"])
    raise RuntimeError("当前版本尚未启用PostgreSQL适配器，请继续使用SQLite或完成驱动部署")
