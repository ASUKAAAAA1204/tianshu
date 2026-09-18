INSERT INTO schema_migrations(version, name, checksum)
VALUES
    (1, 'initial_schema', md5('initial_schema')),
    (2, 'spatial_columns', md5('spatial_columns')),
    (3, 'spatial_indexes', md5('spatial_indexes')),
    (4, 'seed_roles', md5('seed_roles'))
ON CONFLICT (version) DO NOTHING;
