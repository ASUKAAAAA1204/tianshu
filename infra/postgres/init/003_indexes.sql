CREATE INDEX IF NOT EXISTS idx_layers_geometry_gist ON layers USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_layers_status_version ON layers (status, version);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_mission_status ON events (mission_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);
