$ErrorActionPreference = "Stop"
docker exec liangping-postgis psql -U liangping -d liangping -v ON_ERROR_STOP=1 -c "SELECT postgis_full_version();"
docker exec liangping-postgis psql -U liangping -d liangping -v ON_ERROR_STOP=1 -c "SELECT id, name, level FROM layers WHERE status='published' AND ST_Intersects(geometry, ST_SetSRID(ST_MakeLine(ST_MakePoint(107.745,30.638), ST_MakePoint(107.780,30.657)),4326)) ORDER BY id;"
