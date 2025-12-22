"""implement_partitioning

Revision ID: 6a898bba5589
Revises: 31e81f57c53d
Create Date: 2025-12-21 22:19:22.939616

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6a898bba5589"
down_revision: str | None = "31e81f57c53d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # --- 1. Data Access Logs ---
    op.execute("ALTER TABLE data_access_logs RENAME TO data_access_logs_old")
    op.execute(
        """
        CREATE TABLE data_access_logs (
            id SERIAL,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            subject_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resource_type VARCHAR(64) NOT NULL,
            resource_id VARCHAR(128),
            action VARCHAR(64) NOT NULL,
            context JSON,
            ip_address VARCHAR(64),
            user_agent VARCHAR(512),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            signature VARCHAR(512),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """
    )
    # Create initial partition
    op.execute(
        """
        CREATE TABLE data_access_logs_default PARTITION OF data_access_logs DEFAULT;
    """
    )
    # Migrate data
    op.execute(
        """
        INSERT INTO data_access_logs (id, actor_user_id, subject_user_id, resource_type, resource_id, action, context, ip_address, user_agent, created_at, signature)
        SELECT id, actor_user_id, subject_user_id, resource_type, resource_id, action, context, ip_address, user_agent, created_at, signature
        FROM data_access_logs_old;
    """
    )
    op.execute("DROP TABLE data_access_logs_old")

    # --- 2. Notifications ---
    op.execute("ALTER TABLE notifications RENAME TO notifications_old")
    op.execute(
        """
        CREATE TABLE notifications (
            id SERIAL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR NOT NULL,
            title_en VARCHAR,
            body TEXT,
            body_en TEXT,
            type VARCHAR,
            url VARCHAR,
            dedupe_key VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            read BOOLEAN DEFAULT false,
            read_at TIMESTAMPTZ,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """
    )
    op.execute(
        """
        CREATE TABLE notifications_default PARTITION OF notifications DEFAULT;
    """
    )
    op.execute(
        """
        INSERT INTO notifications (id, user_id, title, title_en, body, body_en, type, url, dedupe_key, created_at, read, read_at)
        SELECT id, user_id, title, title_en, body, body_en, type, url, dedupe_key, created_at, read, read_at
        FROM notifications_old;
    """
    )

    # --- 3. Notification Deliveries ---
    op.execute(
        "ALTER TABLE notification_deliveries RENAME TO notification_deliveries_old"
    )
    op.execute(
        """
        CREATE TABLE notification_deliveries (
            id SERIAL,
            notification_id INTEGER NOT NULL,
            notification_created_at TIMESTAMPTZ NOT NULL,
            channel VARCHAR NOT NULL DEFAULT 'inapp',
            status VARCHAR NOT NULL DEFAULT 'delivered',
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            delivered_at TIMESTAMPTZ,
            status_code INTEGER,
            detail TEXT,
            PRIMARY KEY (id, attempted_at),
            FOREIGN KEY (notification_id, notification_created_at) REFERENCES notifications(id, created_at) ON DELETE CASCADE
        ) PARTITION BY RANGE (attempted_at);
    """
    )
    op.execute(
        """
        CREATE TABLE notification_deliveries_default PARTITION OF notification_deliveries DEFAULT;
    """
    )
    # Migrate data with join
    op.execute(
        """
        INSERT INTO notification_deliveries (id, notification_id, notification_created_at, channel, status, attempted_at, delivered_at, status_code, detail)
        SELECT d.id, d.notification_id, n.created_at, d.channel, d.status, d.attempted_at, d.delivered_at, d.status_code, d.detail
        FROM notification_deliveries_old d
        JOIN notifications_old n ON d.notification_id = n.id;
    """
    )

    # Cleanup
    op.execute("DROP TABLE notification_deliveries_old")
    # We drop notifications_old AFTER deliveries as it was referenced
    op.execute("DROP TABLE notifications_old")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Basic downgrade logic would involve recreating non-partitioned tables
    # For a high-impact migration like this, often downgrade is a restore from backup.
    # However, to be nice:

    op.execute(
        "ALTER TABLE notification_deliveries RENAME TO notification_deliveries_part"
    )
    op.execute("ALTER TABLE notifications RENAME TO notifications_part")
    op.execute("ALTER TABLE data_access_logs RENAME TO data_access_logs_part")

    # Recreate notifications
    op.execute(
        """
        CREATE TABLE notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR NOT NULL,
            title_en VARCHAR,
            body TEXT,
            body_en TEXT,
            type VARCHAR,
            url VARCHAR,
            dedupe_key VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            read BOOLEAN DEFAULT false,
            read_at TIMESTAMPTZ
        );
    """
    )
    op.execute("INSERT INTO notifications SELECT * FROM notifications_part")

    # Recreate deliveries
    op.execute(
        """
        CREATE TABLE notification_deliveries (
            id SERIAL PRIMARY KEY,
            notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            channel VARCHAR NOT NULL DEFAULT 'inapp',
            status VARCHAR NOT NULL DEFAULT 'delivered',
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            delivered_at TIMESTAMPTZ,
            status_code INTEGER,
            detail TEXT
        );
    """
    )
    op.execute(
        """
        INSERT INTO notification_deliveries (id, notification_id, channel, status, attempted_at, delivered_at, status_code, detail)
        SELECT id, notification_id, channel, status, attempted_at, delivered_at, status_code, detail
        FROM notification_deliveries_part;
    """
    )

    # Recreate logs
    op.execute(
        """
        CREATE TABLE data_access_logs (
            id SERIAL PRIMARY KEY,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            subject_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resource_type VARCHAR(64) NOT NULL,
            resource_id VARCHAR(128),
            action VARCHAR(64) NOT NULL,
            context JSON,
            ip_address VARCHAR(64),
            user_agent VARCHAR(512),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            signature VARCHAR(512)
        );
    """
    )
    op.execute("INSERT INTO data_access_logs SELECT * FROM data_access_logs_part")

    op.execute("DROP TABLE notification_deliveries_part")
    op.execute("DROP TABLE notifications_part")
    op.execute("DROP TABLE data_access_logs_part")
