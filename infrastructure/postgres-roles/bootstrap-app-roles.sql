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
--                  The append-only tables are narrowed further below: audit and
--                  event rows take only the columns the code writes, the
--                  migration ledger is read-only, and tenant rows are read-only
--                  apart from seed inserts.
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
\c :"db"
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
-- Only cooperating bootstrap jobs share this transaction-scoped lock.
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(1868911986, 1);
-- Password SQL must not enter PostgreSQL's statement/error/duration logs.
-- These settings are transaction-local; external audit plugins must likewise
-- avoid logging credential-bearing SQL. The client suppresses its diagnostics.
SET LOCAL log_statement = 'none';
SET LOCAL log_min_error_statement = 'panic';
SET LOCAL log_min_duration_statement = -1;
SET LOCAL log_min_duration_sample = -1;
SET LOCAL log_transaction_sample_rate = 0;
SET LOCAL log_parameter_max_length_on_error = 0;

SELECT 'CREATE ROLE ue_rls_bypass NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_rls_bypass') \gexec
ALTER ROLE ue_rls_bypass WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

SELECT 'CREATE ROLE ue_migrator LOGIN SUPERUSER'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_migrator') \gexec
ALTER ROLE ue_migrator WITH LOGIN SUPERUSER PASSWORD :'migrator_password';

SELECT 'CREATE ROLE ue_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_app') \gexec
ALTER ROLE ue_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
SELECT 'REVOKE ue_rls_bypass FROM ue_app'
WHERE EXISTS (
    SELECT 1 FROM pg_auth_members
    WHERE member = 'ue_app'::regrole AND roleid = 'ue_rls_bypass'::regrole
) \gexec

SELECT 'CREATE ROLE ue_worker LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_worker') \gexec
ALTER ROLE ue_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'worker_password';
GRANT ue_rls_bypass TO ue_worker WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;

-- Unknown memberships and ownership are not ours to remove. Fail the whole
-- transaction instead of silently preserving inherited/SET ROLE escalation or
-- reassigning an operator's objects. Inspect direct edges: every indirect path
-- necessarily starts with one, including a parent of the bypass group.
DO $guard$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_auth_members
        WHERE member IN ('ue_app'::regrole, 'ue_worker'::regrole, 'ue_rls_bypass'::regrole)
          AND NOT (member = 'ue_worker'::regrole AND roleid = 'ue_rls_bypass'::regrole
                   AND NOT admin_option AND inherit_option AND NOT set_option)
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members
        WHERE roleid IN ('ue_rls_bypass'::regrole, 'ue_worker'::regrole)
          AND NOT (roleid = 'ue_rls_bypass'::regrole AND member = 'ue_worker'::regrole)
    ) THEN
        RAISE EXCEPTION 'Unexpected runtime role membership; operator review required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_shdepend
        WHERE refclassid = 'pg_authid'::regclass
          AND refobjid IN ('ue_app'::regrole, 'ue_worker'::regrole, 'ue_rls_bypass'::regrole)
          AND deptype = 'o'
    ) THEN
        RAISE EXCEPTION 'Runtime roles must not own database objects';
    END IF;
END
$guard$;

-- Alembic creates alembic_version during the first migration, which runs after
-- this bootstrap. Create the same empty table as its owner now, so the default
-- privileges granted below never reach a table that only the migrator may write.
-- Alembic's own create is checkfirst and therefore a no-op. Never touches rows.
SELECT 'SET LOCAL ROLE ue_migrator; CREATE TABLE public.alembic_version (version_num varchar(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)); RESET ROLE'
WHERE to_regclass('public.alembic_version') IS NULL \gexec

-- Converge the runtime grants on every start: revoke everything first, so a
-- privilege granted by an earlier launcher revision cannot survive, then grant
-- the exact DML set. Later migrations inherit the same grants through default
-- privileges for the migrator role, which owns every table it creates.
REVOKE ALL ON DATABASE :"db" FROM ue_app, ue_worker;
REVOKE ALL ON SCHEMA public FROM ue_app, ue_worker;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ue_app, ue_worker;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ue_app, ue_worker;
GRANT CONNECT ON DATABASE :"db" TO ue_app, ue_worker;
GRANT USAGE ON SCHEMA public TO ue_app, ue_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ue_app, ue_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ue_app, ue_worker;

-- Schema defaults add to global defaults; reset both scopes, without CASCADE.
-- Dependent grants therefore fail atomically and require explicit owner review.
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator
    REVOKE ALL ON TABLES FROM ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator
    REVOKE ALL ON SEQUENCES FROM ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    REVOKE ALL ON TABLES FROM ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ue_app, ue_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ue_app, ue_worker;

-- Narrow the table-wide grants above for the append-only and registry tables.
-- ue_app cannot rewrite audit rows, rewrite or delete event-store rows, change
-- tenant rows, or write the migration ledger:
--   data_access_logs  INSERT and SELECT; the signature write-back is the only
--                     UPDATE, and it is column-limited. DELETE stays on the
--                     parent table for the retention prune that the backend
--                     scheduler runs as ue_app. Partitions take no direct DML:
--                     PostgreSQL checks the parent's grant for routed statements.
--   stored_events     INSERT and SELECT; the outbox worker and DLQ requeue
--                     update only the delivery-state columns. No DELETE.
--   tenants           SELECT for tenant resolution; INSERT is kept for the
--                     owner-verified disposable seed entry points, which run as
--                     the application role. No UPDATE, DELETE or TRUNCATE.
--   alembic_version   SELECT only, for the health probe and startup head check.
-- ue_worker keeps its DML on the audit and event tables so retention jobs remain
-- possible, but it never writes the migration ledger or the tenant registry.
-- Tables created by a migration do not exist on a fresh volume until Alembic has
-- run, so each block applies only when its relation is present. Every start
-- reapplies the set, and a run after the migrations converges the new tables.
DO $narrow$
DECLARE
    partition_oid regclass;
BEGIN
    IF to_regclass('public.data_access_logs') IS NOT NULL THEN
        REVOKE UPDATE, TRUNCATE ON public.data_access_logs FROM ue_app;
        GRANT UPDATE (signature) ON public.data_access_logs TO ue_app;
        FOR partition_oid IN
            SELECT inheritance.inhrelid::regclass
            FROM pg_inherits AS inheritance
            WHERE inheritance.inhparent = 'public.data_access_logs'::regclass
        LOOP
            EXECUTE format('REVOKE ALL ON %s FROM ue_app', partition_oid);
        END LOOP;
    END IF;
    IF to_regclass('public.stored_events') IS NOT NULL THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON public.stored_events FROM ue_app;
        GRANT UPDATE (processed_at, error_count, last_error, status)
            ON public.stored_events TO ue_app;
    END IF;
    IF to_regclass('public.tenants') IS NOT NULL THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON public.tenants FROM ue_app, ue_worker;
        REVOKE INSERT ON public.tenants FROM ue_worker;
    END IF;
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        REVOKE ALL ON public.alembic_version FROM ue_app, ue_worker;
        GRANT SELECT ON public.alembic_version TO ue_app;
    END IF;
END
$narrow$;

-- Direct revocation cannot remove PUBLIC or bypass-group privileges. Reject
-- those unexpected effective grants rather than changing unrelated principals.
-- CASE guards the ACL calls by relation kind: WHERE conjuncts may be reordered,
-- and has_sequence_privilege raises wrong_object_type for a non-sequence OID.
DO $guard$
DECLARE
    runtime_role text;
BEGIN
    FOREACH runtime_role IN ARRAY ARRAY['ue_app', 'ue_worker'] LOOP
        IF has_database_privilege(runtime_role, current_database(), 'CREATE')
           OR has_schema_privilege(runtime_role, 'public', 'CREATE')
           OR EXISTS (
               SELECT 1 FROM pg_class AS relation
               JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
               WHERE namespace.nspname = 'public'
                 AND CASE WHEN relation.relkind IN ('r', 'p', 'v', 'm', 'f') THEN (
                     has_table_privilege(runtime_role, relation.oid, 'TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
                     OR has_table_privilege(runtime_role, relation.oid, 'SELECT WITH GRANT OPTION,INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION,DELETE WITH GRANT OPTION')
                     OR has_any_column_privilege(runtime_role, relation.oid, 'REFERENCES,SELECT WITH GRANT OPTION,INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION')
                 ) ELSE false END
           ) OR EXISTS (
               SELECT 1 FROM pg_class AS relation
               JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
               WHERE namespace.nspname = 'public'
                 AND CASE WHEN relation.relkind = 'S' THEN
                     has_sequence_privilege(runtime_role, relation.oid, 'UPDATE,USAGE WITH GRANT OPTION,SELECT WITH GRANT OPTION')
                 ELSE false END
           ) THEN
            RAISE EXCEPTION 'Unexpected effective DDL or delegation privilege for %', runtime_role;
        END IF;
    END LOOP;
    IF EXISTS (
        SELECT 1 FROM pg_default_acl AS defaults
        CROSS JOIN LATERAL aclexplode(defaults.defaclacl) AS privilege
        WHERE defaults.defaclrole = 'ue_migrator'::regrole
          AND defaults.defaclnamespace IN (0, 'public'::regnamespace)
          AND privilege.grantee IN (0, 'ue_rls_bypass'::regrole)
          AND (
              (defaults.defaclobjtype = 'r' AND privilege.privilege_type NOT IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE'))
              OR (defaults.defaclobjtype = 'S' AND privilege.privilege_type NOT IN ('USAGE', 'SELECT'))
              OR privilege.is_grantable
          )
    ) THEN
        RAISE EXCEPTION 'Unexpected inherited default privileges; operator review required';
    END IF;
END
$guard$;
COMMIT;
