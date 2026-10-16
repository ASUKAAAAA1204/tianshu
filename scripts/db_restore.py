from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "platform.db"


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--confirm":
        print("用法: python scripts/db_restore.py --confirm <backup-file>")
        return 2
    source = Path(sys.argv[2]).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB.as_posix()}")
    if database_url.startswith("sqlite:///"):
        target = Path(database_url[len("sqlite:///"):])
        if not target.is_absolute():
            target = (ROOT / target).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        with sqlite3.connect(target) as db:
            db.execute("PRAGMA integrity_check")
    elif database_url.startswith(("postgres://", "postgresql://")):
        subprocess.run(["pg_restore", "--clean", "--if-exists", "--dbname", database_url, str(source)], check=True)
    else:
        raise RuntimeError("不支持的 DATABASE_URL")
    print(f"restore_completed={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
