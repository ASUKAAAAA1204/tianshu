CREATE TABLE IF NOT EXISTS telemetry_samples (
    id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    flight_session_id BIGINT REFERENCES flight_sessions(id),
    sequence INTEGER NOT NULL,
    telemetry_json JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(mission_id, flight_session_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_telemetry_samples_mission_sequence
    ON telemetry_samples(mission_id, flight_session_id, sequence);
INSERT INTO schema_migrations(version, name, checksum)
VALUES (17, 'telemetry_samples', md5('telemetry_samples'))
ON CONFLICT (version) DO NOTHING;
