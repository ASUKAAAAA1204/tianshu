INSERT INTO users(username, password_hash, role)
VALUES
    ('admin', encode(digest('admin123', 'sha256'), 'hex'), 'admin'),
    ('dispatcher', encode(digest('admin123', 'sha256'), 'hex'), 'dispatcher'),
    ('observer', encode(digest('admin123', 'sha256'), 'hex'), 'observer'),
    ('auditor', encode(digest('admin123', 'sha256'), 'hex'), 'auditor')
ON CONFLICT (username) DO NOTHING;
