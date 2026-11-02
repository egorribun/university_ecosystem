#!/bin/sh
# The pinned upstream generator only supports a single user without URL parsing.
# Build a private two-user auth file; never give the pooler bootstrap credentials.
set -eu
set +x
umask 077
case ${POSTGRES_DB-} in
    ''|*[!a-zA-Z0-9_]*|pgbouncer) echo 'Invalid pool database name' >&2; exit 1 ;;
esac
# Each file contains one non-empty password line, optionally newline-terminated.
# Double quotes are escaped according to PgBouncer auth_file syntax; passwords
# travel only over stdin, never awk variables/argv or process environment.
write_user() {
    awk -v role="$1" '
        NR > 1 || length($0) == 0 || /[[:cntrl:]]/ { invalid = 1 }
        NR == 1 { value = $0 }
        END {
            if (NR != 1 || invalid) exit 1
            gsub(/"/, "\"\"", value)
            printf "\"%s\" \"%s\"\n", role, value
        }
    ' < "$2"
}
{
    write_user ue_app /run/secrets/ue_app_db_password
    write_user ue_worker /run/secrets/ue_worker_db_password
} > /etc/pgbouncer/userlist.txt
cat > /etc/pgbouncer/pgbouncer.ini <<CONFIG
[databases]
${POSTGRES_DB} = host=postgres port=5432
[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
unix_socket_dir = /tmp
auth_file = /etc/pgbouncer/userlist.txt
auth_type = scram-sha-256
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
server_tls_sslmode = prefer
ignore_startup_parameters = extra_float_digits
CONFIG
exec /usr/bin/pgbouncer /etc/pgbouncer/pgbouncer.ini
