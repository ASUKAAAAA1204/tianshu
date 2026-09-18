from __future__ import annotations

import json
import sqlite3
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "platform.db"
DEMO_DIR = ROOT / "data" / "demo"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB.as_posix()}")


MIGRATIONS = [
    (1, "audit actor", "ALTER TABLE audit_logs ADD COLUMN actor_username TEXT"),
    (2, "login attempts", "ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"),
    (3, "account lock", "ALTER TABLE users ADD COLUMN locked_until REAL NOT NULL DEFAULT 0"),
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS layers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    layer_type TEXT NOT NULL,
    level TEXT NOT NULL,
    geometry_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    source TEXT NOT NULL DEFAULT 'demo',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    longitude REAL NOT NULL,
    latitude REAL NOT NULL,
    altitude REAL NOT NULL DEFAULT 0,
    battery INTEGER NOT NULL CHECK (battery BETWEEN 0 AND 100),
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    level_label TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
    route_name TEXT NOT NULL,
    start_lng REAL NOT NULL,
    start_lat REAL NOT NULL,
    end_lng REAL NOT NULL,
    end_lat REAL NOT NULL,
    planned_altitude REAL NOT NULL,
    status TEXT NOT NULL,
    status_label TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    actor_username TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mission_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    decision TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    items_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    name TEXT NOT NULL,
    points_json TEXT NOT NULL,
    distance_m REAL NOT NULL,
    duration_s REAL NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS flight_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    status TEXT NOT NULL DEFAULT 'ready',
    progress REAL NOT NULL DEFAULT 0,
    telemetry_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def database_capabilities() -> dict:
    backend = "postgresql" if DATABASE_URL.startswith(("postgresql://", "postgres://")) else "sqlite"
    return {
        "backend": backend,
        "spatial_engine": "postgis" if backend == "postgresql" else "bounding_box",
        "configured": backend == "sqlite",
        "message": "SQLite离线模式已启用" if backend == "sqlite" else "PostgreSQL连接已配置，驱动适配将在下一阶段启用",
    }


def apply_migrations(db: sqlite3.Connection) -> None:
    applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations").fetchall()}
    for version, name, statement in MIGRATIONS:
        if version in applied:
            continue
        try:
            db.execute(statement)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise
        db.execute("INSERT INTO schema_migrations(version,name) VALUES(?,?)", (version, name))


@contextmanager
def session(path: Path = DEFAULT_DB):
    database = connect(path)
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def init_db(path: Path = DEFAULT_DB, reset: bool = False) -> None:
    if reset and path.exists():
        path.unlink()
    db = connect(path)
    try:
        db.executescript(SCHEMA)
        apply_migrations(db)
        if db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
            seed(db)
        password_hash = hashlib.sha256("admin123".encode()).hexdigest()
        db.executemany("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", [("admin", password_hash, "admin"), ("dispatcher", password_hash, "dispatcher"), ("observer", password_hash, "observer"), ("auditor", password_hash, "auditor")])
        db.commit()
    finally:
        db.close()


def seed(db: sqlite3.Connection) -> None:
    layers = json.loads((DEMO_DIR / "layers.json").read_text(encoding="utf-8"))
    vehicles = json.loads((DEMO_DIR / "vehicles.json").read_text(encoding="utf-8"))
    missions = json.loads((DEMO_DIR / "missions.json").read_text(encoding="utf-8"))
    rules = json.loads((DEMO_DIR / "rules.json").read_text(encoding="utf-8"))
    for item in layers["features"]:
        props = item["properties"]
        db.execute(
            "INSERT INTO layers(name, layer_type, level, geometry_json, source) VALUES(?,?,?,?,?)",
            (props["name"], props["type"], props["level"], json.dumps(item["geometry"]), "demo"),
        )
    db.executemany(
        "INSERT INTO vehicles(id,name,model,longitude,latitude,altitude,battery,status) VALUES(:id,:name,:model,:longitude,:latitude,:altitude,:battery,:status)",
        vehicles,
    )
    db.executemany(
        "INSERT INTO rules(code,name,level,level_label) VALUES(:code,:name,:level,:level_label)", rules
    )
    db.executemany(
        """INSERT INTO missions(id,name,vehicle_id,route_name,start_lng,start_lat,end_lng,end_lat,planned_altitude,status,status_label)
        VALUES(:id,:name,:vehicle_id,:route_name,:start_lng,:start_lat,:end_lng,:end_lat,:planned_altitude,:status,:status_label)""",
        missions,
    )


def rows(db: sqlite3.Connection, query: str, params=()) -> list[dict]:
    return [dict(item) for item in db.execute(query, params).fetchall()]
