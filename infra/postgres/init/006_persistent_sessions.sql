CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL REFERENCES users(username),
    expires_at DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

INSERT INTO schema_migrations(version, name, checksum)
VALUES (5, 'persistent_sessions', md5('persistent_sessions'))
ON CONFLICT (version) DO NOTHING;
