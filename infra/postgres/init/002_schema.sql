CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS layers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    layer_type TEXT NOT NULL CHECK (layer_type IN ('restricted','operable')),
    level TEXT NOT NULL CHECK (level IN ('hard','soft','temporary','open')),
    geometry_json JSONB NOT NULL,
    geometry geometry(Geometry,4326) NOT NULL,
    min_altitude_m DOUBLE PRECISION,
    max_altitude_m DOUBLE PRECISION,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'published',
    source TEXT NOT NULL DEFAULT 'demo',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    altitude DOUBLE PRECISION NOT NULL DEFAULT 0,
    battery INTEGER NOT NULL CHECK (battery BETWEEN 0 AND 100),
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    level_label TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
    route_name TEXT NOT NULL,
    start_lng DOUBLE PRECISION NOT NULL,
    start_lat DOUBLE PRECISION NOT NULL,
    end_lng DOUBLE PRECISION NOT NULL,
    end_lat DOUBLE PRECISION NOT NULL,
    planned_altitude DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    status_label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    detail_json JSONB NOT NULL,
    actor_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mission_checks (
    id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    decision TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    items_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS routes (
    id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    name TEXT NOT NULL,
    points_json JSONB NOT NULL,
    distance_m DOUBLE PRECISION NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flight_sessions (
    id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    status TEXT NOT NULL DEFAULT 'ready',
    progress DOUBLE PRECISION NOT NULL DEFAULT 0,
    telemetry_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','dispatcher','observer','auditor')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
