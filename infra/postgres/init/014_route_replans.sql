CREATE TABLE IF NOT EXISTS route_replans (
    id SERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    event_id INTEGER REFERENCES events(id),
    route_id INTEGER NOT NULL REFERENCES routes(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    actor_username TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_route_replans_mission ON route_replans(mission_id, id DESC);
