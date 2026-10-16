"""Storage adapter boundary for offline SQLite and PostgreSQL/PostGIS modes."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from db import DATABASE_URL, DEFAULT_DB, database_config, connect, sqlite_path_from_url


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

    def deep_health(self) -> dict:
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

    def deep_health(self) -> dict:
        with self.session() as db:
            db.execute("SELECT 1").fetchone()
            migration = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        return {"status": "ready", "connection": "ok", "spatial_extension": "python_polygon", "migration_version": migration, "probe": "ok"}


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

    def deep_health(self) -> dict:
        with self.session() as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT postgis_full_version(), (SELECT MAX(version) FROM schema_migrations)")
                postgis_version, migration_version = cursor.fetchone()
        return {"status": "ready", "connection": "ok", "spatial_extension": postgis_version, "migration_version": migration_version, "probe": "ok"}


def build_storage(url: str | None = None) -> StorageAdapter:
    config = database_config(url) if url else database_config()
    if config["backend"] == "sqlite":
        return SQLiteStorage(sqlite_path_from_url(config["url"]))
    if config["backend"] == "postgresql":
        return PostgresStorage(config["url"])
    raise RuntimeError("当前版本尚未启用PostgreSQL适配器，请继续使用SQLite或完成驱动部署")
