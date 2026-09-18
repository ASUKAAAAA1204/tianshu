$ErrorActionPreference = "Stop"
docker-compose -f .\docker-compose.postgres.yml up -d
docker-compose -f .\docker-compose.postgres.yml ps
