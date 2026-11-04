-- Never interpolate credentials into process arguments or shell commands.
\getenv db POSTGRES_DB
\getenv migrator_password UE_MIGRATOR_DB_PASSWORD
\getenv app_password UE_APP_DB_PASSWORD
\getenv worker_password UE_WORKER_DB_PASSWORD
\getenv spicedb_password UE_SPICEDB_DB_PASSWORD
\getenv temporal_password UE_TEMPORAL_DB_PASSWORD
\ir bootstrap-app-roles.sql
\ir bootstrap-service-roles.sql
