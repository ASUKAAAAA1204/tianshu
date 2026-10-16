ALTER TABLE missions
    ADD COLUMN IF NOT EXISTS time_window_start TIMESTAMPTZ;

ALTER TABLE missions
    ADD COLUMN IF NOT EXISTS time_window_end TIMESTAMPTZ;

INSERT INTO schema_migrations(version, name, checksum)
VALUES (6, 'mission_time_windows', md5('mission_time_windows'))
ON CONFLICT (version) DO NOTHING;
