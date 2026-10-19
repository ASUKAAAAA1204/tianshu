from __future__ import annotations

import json
import sqlite3
import hashlib
import hmac
import os
import secrets
from urllib.parse import unquote, urlparse
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "platform.db"
DEMO_DIR = ROOT / "data" / "demo"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB.as_posix()}")
PASSWORD_ITERATIONS = 310_000


MIGRATIONS = [
    (1, "audit actor", "ALTER TABLE audit_logs ADD COLUMN actor_username TEXT"),
    (2, "login attempts", "ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"),
    (3, "account lock", "ALTER TABLE users ADD COLUMN locked_until REAL NOT NULL DEFAULT 0"),
    (4, "route replans", "CREATE TABLE IF NOT EXISTS route_replans (id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL REFERENCES missions(id), event_id INTEGER REFERENCES events(id), route_id INTEGER NOT NULL REFERENCES routes(id), reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed', actor_username TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, confirmed_at TEXT)"),
    (5, "persistent sessions", "CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT UNIQUE NOT NULL, username TEXT NOT NULL REFERENCES users(username), expires_at REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ip_address TEXT, user_agent TEXT)"),
    (6, "mission time windows", "ALTER TABLE missions ADD COLUMN time_window_start TEXT"),
    (7, "mission time window end", "ALTER TABLE missions ADD COLUMN time_window_end TEXT"),
    (8, "telemetry samples", "CREATE TABLE IF NOT EXISTS telemetry_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL REFERENCES missions(id), flight_session_id INTEGER NOT NULL REFERENCES flight_sessions(id), sequence INTEGER NOT NULL, timestamp TEXT NOT NULL, longitude REAL NOT NULL, latitude REAL NOT NULL, altitude REAL NOT NULL, speed REAL NOT NULL DEFAULT 0, heading REAL NOT NULL DEFAULT 0, battery REAL NOT NULL, link_quality REAL NOT NULL DEFAULT 100, status TEXT NOT NULL, source TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(flight_session_id, sequence))"),
    (9, "airspace cells", "CREATE TABLE IF NOT EXISTS airspace_cells (cell_id TEXT PRIMARY KEY, geometry_json TEXT NOT NULL, min_altitude_m REAL, max_altitude_m REAL, valid_from TEXT, valid_to TEXT, status TEXT NOT NULL DEFAULT 'published', risk_level TEXT NOT NULL DEFAULT 'low', rule_version TEXT, data_version TEXT, source_kind TEXT NOT NULL DEFAULT 'synthetic_demo', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"),
    (10, "facilities master data", "CREATE TABLE IF NOT EXISTS facilities (facility_id TEXT PRIMARY KEY, facility_type TEXT NOT NULL, name TEXT NOT NULL, longitude REAL NOT NULL, latitude REAL NOT NULL, elevation_m REAL, capacity INTEGER, service_radius_m REAL, opening_hours TEXT, compatible_vehicles_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active', source_kind TEXT NOT NULL DEFAULT 'synthetic_demo', data_version TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"),
    (11, "route decisions", "CREATE TABLE IF NOT EXISTS route_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL REFERENCES missions(id), route_id INTEGER NOT NULL REFERENCES routes(id), decision TEXT NOT NULL CHECK (decision IN ('adopted','returned','revoked')), reason TEXT, actor_username TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"),
    (12, "mission via points", "ALTER TABLE missions ADD COLUMN via_points_json TEXT NOT NULL DEFAULT '[]'"),
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
    time_window_start TEXT,
    time_window_end TEXT,
    via_points_json TEXT NOT NULL DEFAULT '[]',
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
CREATE TABLE IF NOT EXISTS route_replans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    event_id INTEGER REFERENCES events(id),
    route_id INTEGER NOT NULL REFERENCES routes(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    actor_username TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TEXT
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
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL REFERENCES users(username),
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS airspace_cells (
    cell_id TEXT PRIMARY KEY, geometry_json TEXT NOT NULL, min_altitude_m REAL, max_altitude_m REAL,
    valid_from TEXT, valid_to TEXT, status TEXT NOT NULL DEFAULT 'published', risk_level TEXT NOT NULL DEFAULT 'low',
    rule_version TEXT, data_version TEXT, source_kind TEXT NOT NULL DEFAULT 'synthetic_demo', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS facilities (
    facility_id TEXT PRIMARY KEY, facility_type TEXT NOT NULL, name TEXT NOT NULL, longitude REAL NOT NULL, latitude REAL NOT NULL,
    elevation_m REAL, capacity INTEGER, service_radius_m REAL, opening_hours TEXT, compatible_vehicles_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active', source_kind TEXT NOT NULL DEFAULT 'synthetic_demo', data_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS route_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    route_id INTEGER NOT NULL REFERENCES routes(id),
    decision TEXT NOT NULL CHECK (decision IN ('adopted','returned','revoked')),
    reason TEXT,
    actor_username TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """返回(是否匹配, 是否为旧 SHA-256 格式)。"""
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
            return hmac.compare_digest(digest.hex(), digest_hex), False
        except (ValueError, TypeError):
            return False, False
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored), True


def database_config(url: str = DATABASE_URL) -> dict:
    parsed = urlparse(url)
    if parsed.scheme in ("sqlite", ""):
        return {"backend": "sqlite", "url": url, "ready": True, "driver": "sqlite3"}
    if parsed.scheme in ("postgres", "postgresql"):
        try:
            import psycopg  # type: ignore
        except ImportError:
            return {"backend": "postgresql", "url": url, "ready": False, "driver": None, "reason": "psycopg未安装"}
        return {"backend": "postgresql", "url": url, "ready": True, "driver": "psycopg"}
    return {"backend": "unknown", "url": url, "ready": False, "driver": None, "reason": "不支持的数据库协议"}


def sqlite_path_from_url(url: str | None = None) -> Path:
    """Resolve SQLite URLs consistently for initialization and request sessions."""
    url = url or DATABASE_URL
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return DEFAULT_DB
    raw_path = unquote(url[len(prefix):].split("?", 1)[0])
    if not raw_path:
        return DEFAULT_DB
    # RFC-style Windows URLs may encode an absolute drive as /D:/... .
    if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]
    path = Path(raw_path)
    return path if path.is_absolute() or str(path) == ":memory:" else ROOT / path


def database_capabilities() -> dict:
    config = database_config()
    backend = config["backend"]
    return {
        "backend": backend,
        "spatial_engine": "postgis" if backend == "postgresql" and config["ready"] else "polygon_python",
        "configured": config["ready"],
        "driver": config["driver"],
        "message": "SQLite离线模式已启用，使用严格Polygon计算" if backend == "sqlite" else ("PostgreSQL驱动已就绪，连接尚未执行" if config["ready"] else config.get("reason", "数据库未就绪")),
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
def session(path: Path | None = None):
    config = database_config()
    if config["backend"] == "postgresql":
        from postgres_compat import PostgresConnection
        from repository import PostgresStorage

        storage = PostgresStorage(config["url"])
        with storage.session() as raw_connection:
            yield PostgresConnection(raw_connection)
        return
    database = connect(path or sqlite_path_from_url(config["url"]))
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def init_db(path: Path | None = None, reset: bool = False) -> None:
    path = path or sqlite_path_from_url()
    if reset and path.exists():
        path.unlink()
    db = connect(path)
    try:
        db.executescript(SCHEMA)
        apply_migrations(db)
        if db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
            seed(db)
        seed_airspace_cells(db)
        seed_facilities(db)
        password_hash = hash_password(os.environ.get("LP_BOOTSTRAP_PASSWORD", "admin123"))
        db.executemany("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", [("admin", password_hash, "admin"), ("dispatcher", password_hash, "dispatcher"), ("observer", password_hash, "observer"), ("auditor", password_hash, "auditor")])
        db.commit()
    finally:
        db.close()


def seed_airspace_cells(db: sqlite3.Connection) -> None:
    source = DEMO_DIR / "airspace_cells.json"
    if not source.exists() or db.execute("SELECT COUNT(*) FROM airspace_cells").fetchone()[0] > 0:
        return
    cells = json.loads(source.read_text(encoding="utf-8"))
    db.executemany("INSERT OR IGNORE INTO airspace_cells(cell_id, geometry_json, min_altitude_m, max_altitude_m, valid_from, valid_to, status, risk_level, rule_version, data_version, source_kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)", [(
        item["cell_id"], json.dumps(item["geometry"], ensure_ascii=False), item.get("min_altitude_m"), item.get("max_altitude_m"), item.get("valid_from"), item.get("valid_to"), item.get("status", "published"), item.get("risk_level", "low"), item.get("rule_version"), item.get("data_version"), item.get("source_kind", "synthetic_demo")
    ) for item in cells])


def seed_facilities(db: sqlite3.Connection) -> None:
    source = DEMO_DIR / "facilities.json"
    if not source.exists() or db.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] > 0:
        return
    facilities = json.loads(source.read_text(encoding="utf-8"))
    db.executemany("INSERT OR IGNORE INTO facilities(facility_id, facility_type, name, longitude, latitude, elevation_m, capacity, service_radius_m, opening_hours, compatible_vehicles_json, status, source_kind, data_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", [(
        item["facility_id"], item["facility_type"], item["name"], item["longitude"], item["latitude"], item.get("elevation_m"), item.get("capacity"), item.get("service_radius_m"), item.get("opening_hours"), json.dumps(item.get("compatible_vehicles", []), ensure_ascii=False), item.get("status", "active"), item.get("source_kind", "synthetic_demo"), item.get("data_version")
    ) for item in facilities])


def seed(db: sqlite3.Connection) -> None:
    layers = json.loads((DEMO_DIR / "layers.json").read_text(encoding="utf-8"))
    vehicles = json.loads((DEMO_DIR / "vehicles.json").read_text(encoding="utf-8"))
    missions = json.loads((DEMO_DIR / "missions.json").read_text(encoding="utf-8"))
    for item in missions:
        item.setdefault("time_window_start", None)
        item.setdefault("time_window_end", None)
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
        """INSERT INTO missions(id,name,vehicle_id,route_name,start_lng,start_lat,end_lng,end_lat,planned_altitude,time_window_start,time_window_end,status,status_label)
        VALUES(:id,:name,:vehicle_id,:route_name,:start_lng,:start_lat,:end_lng,:end_lat,:planned_altitude,:time_window_start,:time_window_end,:status,:status_label)""",
        missions,
    )


def rows(db: sqlite3.Connection, query: str, params=()) -> list[dict]:
    return [dict(item) for item in db.execute(query, params).fetchall()]
