-- Reconciles the login roles that separate the MVP runtime from migrations and
-- from row-level-security bypass. Run by the `postgres-roles-init` one-shot
-- service as the bootstrap superuser before every `alembic upgrade head`, so
-- fresh and pre-existing volumes converge on the same grants.
--
-- Mounted from infrastructure/postgres-roles, NOT infrastructure/postgres-init:
-- files in the initdb directory run automatically at first start without the
-- psql variables below.
--
-- Roles and authority:
--   ue_rls_bypass  NOLOGIN. Membership is the only database authority that lifts
--                  the tenant_isolation policies. A session GUC cannot grant it.
--   ue_migrator    LOGIN SUPERUSER. Owns the schema and runs Alembic only. The
--                  superuser attribute is required: the baseline creates the
--                  non-trusted pgvector extension and comments on it, and
--                  PostgreSQL allows neither step to a non-superuser. No runtime
--                  service receives this credential.
--   ue_app         LOGIN NOSUPERUSER NOBYPASSRLS, no bypass membership. Backend
--                  API and outbox worker. Receives DML only: no DDL, TRUNCATE,
--                  REFERENCES or TRIGGER. Tenant scope comes from the session.
--   ue_worker      LOGIN NOSUPERUSER NOBYPASSRLS, member of ue_rls_bypass.
--                  Notifications worker. Its schedule-reminder scan reads every
--                  tenant, so it cannot be confined to one tenant's session.
--
-- Maintenance is not provisioned here. A pg_dump login needs the BYPASSRLS
-- attribute, not membership: pg_dump runs with row_security off, and PostgreSQL
-- rejects a policy-subject role that dumps an RLS table even when membership
-- would make the policy true. The operator provisions that login.
--
-- Required psql variables: db, migrator_password, app_password, worker_password.
\set ON_ERROR_STOP on

SELECT 'CREATE ROLE ue_rls_bypass NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_rls_bypass') \gexec

SELECT 'CREATE ROLE ue_migrator LOGIN SUPERUSER'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_migrator') \gexec
ALTER ROLE ue_migrator WITH LOGIN SUPERUSER PASSWORD :'migrator_password';

SELECT 'CREATE ROLE ue_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_app') \gexec
ALTER ROLE ue_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
SELECT 'REVOKE ue_rls_bypass FROM ue_app'
WHERE pg_has_role('ue_app', 'ue_rls_bypass', 'MEMBER') \gexec

SELECT 'CREATE ROLE ue_worker LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_worker') \gexec
ALTER ROLE ue_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'worker_password';
GRANT ue_rls_bypass TO ue_worker;

\c :"db"

-- Converge the runtime grants on every start: revoke everything first, so a
-- privilege granted by an earlier launcher revision cannot survive, then grant
-- the exact DML set. Later migrations inherit the same grants through default
-- privileges for the migrator role, which owns every table it creates.
REVOKE CREATE ON SCHEMA public FROM ue_app, ue_worker;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ue_app, ue_worker;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ue_app, ue_worker;
GRANT CONNECT ON DATABASE :"db" TO ue_app, ue_worker;
GRANT USAGE ON SCHEMA public TO ue_app, ue_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ue_app, ue_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ue_app, ue_worker;

ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ue_app, ue_worker;
