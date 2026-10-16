from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "platform.db"


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/db_backup.py <backup-file>")
        return 2
    target = Path(sys.argv[1]).expanduser().resolve()
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB.as_posix()}")
    if database_url.startswith("sqlite:///"):
        source = Path(database_url[len("sqlite:///"):])
        if not source.is_absolute():
            source = (ROOT / source).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        with tempfile.NamedTemporaryFile(prefix="lp-backup-", suffix=".db", delete=False, dir=target.parent) as handle:
            temp_path = Path(handle.name)
        try:
            sqlite_backup(source, temp_path)
            shutil.move(str(temp_path), str(target))
        finally:
            temp_path.unlink(missing_ok=True)
    elif database_url.startswith(("postgres://", "postgresql://")):
        subprocess.run(["pg_dump", "--format=custom", "--file", str(target), database_url], check=True)
    else:
        raise RuntimeError("不支持的 DATABASE_URL")
    print(f"backup_created={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
