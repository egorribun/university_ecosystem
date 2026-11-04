-- Reconciles the login roles of the SpiceDB and Temporal services. Run by
-- run-bootstrap.sh after bootstrap-app-roles.sql, inside the same
-- `postgres-roles-init` one-shot, before any of those services start.
--
-- Roles and authority:
--   ue_spicedb   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
--                NOBYPASSRLS. OWNER of the `spicedb` database only. Runs the
--                SpiceDB datastore migration and server.
--   ue_temporal  LOGIN with the same attributes. OWNER of the `temporal` and
--                `temporal_visibility` databases only. Runs temporal-sql-tool
--                and the Temporal server.
--
-- Neither role may connect to the application database or to another service
-- database: CONNECT is revoked from PUBLIC on every database here, and the
-- application database is revoked from PUBLIC too. Each role is granted CONNECT
-- only on its own databases. Neither holds any role membership.
--
-- The authenticated bootstrap superuser remains the owner of the cluster.
-- Relations that this login created in a service database before reconciliation
-- (fresh volumes have none) are reassigned to that database's owner, so the
-- service's own schema migrations can alter them. Other owners are untouched.
-- Missing service databases fail closed: postgres-databases-init creates them
-- before this job starts.
--
-- Required psql variables: db, spicedb_password, temporal_password.
\set ON_ERROR_STOP on
\c postgres
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
-- Only cooperating bootstrap jobs share this transaction-scoped lock.
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(1868911986, 1);
-- Password SQL must not enter PostgreSQL's statement/error/duration logs.
SET LOCAL log_statement = 'none';
SET LOCAL log_min_error_statement = 'panic';
SET LOCAL log_min_duration_statement = -1;
SET LOCAL log_min_duration_sample = -1;
SET LOCAL log_transaction_sample_rate = 0;
SET LOCAL log_parameter_max_length_on_error = 0;

SELECT 'CREATE ROLE ue_spicedb LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_spicedb') \gexec
ALTER ROLE ue_spicedb WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'spicedb_password';

SELECT 'CREATE ROLE ue_temporal LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_temporal') \gexec
ALTER ROLE ue_temporal WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'temporal_password';

-- Fail closed on any membership edge touching a service role. Membership would
-- let a service inherit another login's privileges, including the app or
-- migrator grants, so an unexpected edge is an operator decision.
DO $guard$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_auth_members
        WHERE member IN ('ue_spicedb'::regrole, 'ue_temporal'::regrole)
           OR roleid IN ('ue_spicedb'::regrole, 'ue_temporal'::regrole)
    ) THEN
        RAISE EXCEPTION 'Unexpected service role membership; operator review required';
    END IF;
END
$guard$;

-- The application database must not be reachable by the service roles. PUBLIC
-- holds CONNECT on every new database by default; the runtime roles it must keep
-- are granted explicitly by bootstrap-app-roles.sql. The maintenance database is
-- closed the same way: no runtime service connects to it (pgbouncer routes only
-- POSTGRES_DB), and the bootstrap superuser is unaffected.
REVOKE CONNECT ON DATABASE :"db" FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE :"db" FROM ue_spicedb, ue_temporal;
REVOKE ALL ON DATABASE postgres FROM ue_spicedb, ue_temporal;

-- Each service database: owned by its service role, with CONNECT withheld from
-- PUBLIC. The owner keeps ALL on its database (CONNECT, CREATE, TEMPORARY):
-- CREATE EXTENSION of a trusted extension, such as btree_gin in the Temporal
-- visibility schema, needs it. The existence check is a hard requirement, never
-- a silent skip.
DO $owner$
DECLARE
    target record;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('spicedb', 'ue_spicedb'),
            ('temporal', 'ue_temporal'),
            ('temporal_visibility', 'ue_temporal')
        ) AS service_database(database_name, owner_role)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = target.database_name) THEN
            RAISE EXCEPTION 'Service database % is missing; postgres-databases-init must run first', target.database_name;
        END IF;
        EXECUTE format('ALTER DATABASE %I OWNER TO %I', target.database_name, target.owner_role);
        EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', target.database_name);
        EXECUTE format('GRANT ALL ON DATABASE %I TO %I', target.database_name, target.owner_role);
    END LOOP;
END
$owner$;
COMMIT;

-- Relations owned by the authenticated bootstrap login follow the database owner.
-- This runs per database because a relation can be altered only from a session
-- connected to it. session_user supports any configured POSTGRES_USER without
-- granting authority over objects owned by other roles.
\c spicedb
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(1868911986, 1);
DO $relations$
DECLARE
    service_owner name;
    relation record;
BEGIN
    SELECT pg_get_userbyid(datdba) INTO STRICT service_owner
    FROM pg_database WHERE datname = current_database();
    FOR relation IN
        SELECT class.relname, class.relkind
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public'
          AND class.relowner = (SELECT oid FROM pg_roles WHERE rolname = session_user)
          AND class.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
    LOOP
        IF relation.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'v' THEN
            EXECUTE format('ALTER VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'm' THEN
            EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'f' THEN
            EXECUTE format('ALTER FOREIGN TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSE
            EXECUTE format('ALTER TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        END IF;
    END LOOP;
END
$relations$;
COMMIT;

\c temporal
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(1868911986, 1);
DO $relations$
DECLARE
    service_owner name;
    relation record;
BEGIN
    SELECT pg_get_userbyid(datdba) INTO STRICT service_owner
    FROM pg_database WHERE datname = current_database();
    FOR relation IN
        SELECT class.relname, class.relkind
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public'
          AND class.relowner = (SELECT oid FROM pg_roles WHERE rolname = session_user)
          AND class.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
    LOOP
        IF relation.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'v' THEN
            EXECUTE format('ALTER VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'm' THEN
            EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'f' THEN
            EXECUTE format('ALTER FOREIGN TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSE
            EXECUTE format('ALTER TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        END IF;
    END LOOP;
END
$relations$;
COMMIT;

\c temporal_visibility
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(1868911986, 1);
DO $relations$
DECLARE
    service_owner name;
    relation record;
BEGIN
    SELECT pg_get_userbyid(datdba) INTO STRICT service_owner
    FROM pg_database WHERE datname = current_database();
    FOR relation IN
        SELECT class.relname, class.relkind
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public'
          AND class.relowner = (SELECT oid FROM pg_roles WHERE rolname = session_user)
          AND class.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
    LOOP
        IF relation.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'v' THEN
            EXECUTE format('ALTER VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'm' THEN
            EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO %I', relation.relname, service_owner);
        ELSIF relation.relkind = 'f' THEN
            EXECUTE format('ALTER FOREIGN TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        ELSE
            EXECUTE format('ALTER TABLE public.%I OWNER TO %I', relation.relname, service_owner);
        END IF;
    END LOOP;
END
$relations$;
COMMIT;
