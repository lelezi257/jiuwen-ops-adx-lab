#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=verify_password="$(cat /run/secrets/verify_db_password)" <<'SQL'
CREATE ROLE verifier LOGIN PASSWORD :'verify_password';
GRANT CONNECT ON DATABASE orders TO verifier;
GRANT USAGE ON SCHEMA public TO verifier;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO verifier;
ALTER DEFAULT PRIVILEGES FOR ROLE orders IN SCHEMA public GRANT SELECT ON TABLES TO verifier;
SQL
