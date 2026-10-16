CREATE TABLE IF NOT EXISTS route_decisions (
    id SERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    route_id INTEGER NOT NULL REFERENCES routes(id),
    decision TEXT NOT NULL CHECK (decision IN ('adopted','returned','revoked')),
    reason TEXT,
    actor_username TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_route_decisions_mission ON route_decisions(mission_id, id DESC);
