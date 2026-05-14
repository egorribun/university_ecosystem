"""
Seed script — creates admin user + sample data for /admin pages.

Run AFTER `scripts/seed_demo_data.py` (this script depends on the base group
existing). Safe to re-run: each section catches unique-constraint violations.

Usage:
    python scripts/seed_admin_data.py

Creates:
- 1 admin user: admin@university.dev / Admin@2024test
- 6 additional users (mix of students + teachers across 3 groups) for AdminUsers
- 12 audit log entries for AdminAudit (signed via SecureAuditService)
- 4 dead-letter notification jobs for AdminNotifications
- Feature flags: 4 hardcoded entries already shown by `feature_flags.list_flags()` — no seeding needed
- Stories: created by seed_demo_data.py — no seeding needed here
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

# Match seed_demo_data.py pattern: replace docker hostname with localhost when
# running from the host (.env DATABASE_URL has @postgres:).
_loaded_from_dotenv = False
if "DATABASE_URL" not in os.environ:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        _loaded_from_dotenv = True
    except ImportError:
        pass

if _loaded_from_dotenv:
    _db_url = os.environ.get("DATABASE_URL", "")
    if "@postgres:" in _db_url:
        os.environ["DATABASE_URL"] = _db_url.replace("@postgres:", "@localhost:")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.auth.security import get_password_hash_sync  # noqa: E402
from app.core.database import async_session, init_database  # noqa: E402
from app.models.dead_letter import DeadLetterJob, JobStatus  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.schedule import Group  # noqa: E402
from app.models.users import EducationPath, User, UserProfile  # noqa: E402
from app.services.audit_service import SecureAuditService  # noqa: E402

# ---------------------------------------------------------------------------
# Admin user credentials (no `!` per CLAUDE.md docker gotcha)
# ---------------------------------------------------------------------------

ADMIN_EMAIL = "admin@university.dev"
ADMIN_PASSWORD = "Admin@2024test"  # noqa: S105 — dev-only test credential

# ---------------------------------------------------------------------------
# Additional users for AdminUsers page (mix of roles + groups)
# ---------------------------------------------------------------------------

EXTRA_USERS = [
    # (email, password, full_name, role, telegram, institute, course, group_name)
    (
        "anna.petrova@university.dev",
        "Student@2024test",
        "Анна Петрова",
        UserRole.STUDENT,
        "@anna_petrova",
        "Институт информационных технологий",
        "2",
        "ЗИ-201",
    ),
    (
        "ivan.sokolov@university.dev",
        "Student@2024test",
        "Иван Соколов",
        UserRole.STUDENT,
        "@ivan_sokolov",
        "Институт информационных технологий",
        "3",
        "ЗИ-301",
    ),
    (
        "maria.kuznetsova@university.dev",
        "Student@2024test",
        "Мария Кузнецова",
        UserRole.STUDENT,
        "@maria_k",
        "Институт экономики и финансов",
        "4",
        "ЭК-401",
    ),
    (
        "dmitry.volkov@university.dev",
        "Student@2024test",
        "Дмитрий Волков",
        UserRole.STUDENT,
        "@dmitry_v",
        "Институт менеджмента",
        "1",
        "МН-101",
    ),
    (
        "olga.morozova@university.dev",
        "Teacher@2024test",
        "Ольга Морозова",
        UserRole.TEACHER,
        "@olga_morozova",
        "Институт информационных технологий",
        None,
        None,
    ),
    (
        "sergey.lebedev@university.dev",
        "Teacher@2024test",
        "Сергей Лебедев",
        UserRole.TEACHER,
        "@sergey_lebedev",
        "Институт экономики и финансов",
        None,
        None,
    ),
]

# Additional groups (besides ЗИ-301 from seed_demo_data.py)
EXTRA_GROUPS = [
    ("ЗИ-201", 2, "Институт информационных технологий"),
    ("ЭК-401", 4, "Институт экономики и финансов"),
    ("МН-101", 1, "Институт менеджмента"),
]

# ---------------------------------------------------------------------------
# Audit log entries — span resource types + actions for filter UI testing
# ---------------------------------------------------------------------------

AUDIT_ACTIONS = [
    ("user", "user.login", "Successful login from web client"),
    ("user", "user.update", "Profile fields updated: telegram, about"),
    ("user", "user.delete", "Account scheduled for deletion (cooling-off)"),
    ("event", "event.create", "Created event 'Хакатон ИИТ 2026'"),
    ("event", "event.update", "Event location changed: ауд. 405 → ауд. 502"),
    ("news", "news.create", "Published news article 'Зимний семестр 2026'"),
    ("news", "news.delete", "Soft-deleted news article id=42"),
    ("story", "story.create", "Created story 'День открытых дверей'"),
    ("auth", "auth.password_reset", "Password reset link sent to email"),
    ("auth", "auth.mfa_enable", "TOTP enrolled — 8 recovery codes generated"),
    ("feature_flag", "feature_flag.update", "Flag 'push_batching' toggled enabled"),
    ("session", "session.revoke_all", "Revoked 3 active sessions across devices"),
]

# ---------------------------------------------------------------------------
# Dead-letter notification jobs for AdminNotifications page
# ---------------------------------------------------------------------------

DEAD_LETTER_JOBS = [
    {
        "job_type": "send_email",
        "payload": {
            "to": "user.unreachable@example.com",
            "subject": "Welcome to GUU",
            "template": "welcome_email_ru",
        },
        "error_message": "SMTPRecipientsRefused: 550 5.1.1 Recipient address rejected",
        "retry_count": 3,
        "status": JobStatus.FAILED.value,
    },
    {
        "job_type": "push_notification",
        "payload": {
            "user_id": "01234567-89ab-cdef-0123-456789abcdef",
            "title": "Новое мероприятие",
            "body": "Хакатон ИИТ 2026 — регистрация открыта",
        },
        "error_message": "WebPushException: 410 Gone — subscription expired",
        "retry_count": 2,
        "status": JobStatus.RETRYING.value,
    },
    {
        "job_type": "send_email",
        "payload": {
            "to": "ivan.sokolov@university.dev",
            "subject": "Reminder: Завтра дедлайн курсовой",
            "template": "deadline_reminder_ru",
        },
        "error_message": "ConnectionTimeout: SMTP server did not respond in 30s",
        "retry_count": 1,
        "status": JobStatus.PENDING.value,
    },
    {
        "job_type": "spotify_sync",
        "payload": {
            "user_id": "01234567-89ab-cdef-0123-456789abcdef",
            "operation": "refresh_currently_playing",
        },
        "error_message": "401 Unauthorized: refresh token expired",
        "retry_count": 3,
        "status": JobStatus.FAILED.value,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def find_or_create_admin(db) -> User:
    """Create or fetch the admin user."""
    existing = await db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if existing:
        if existing.role != UserRole.ADMIN:
            existing.role = UserRole.ADMIN
            print(f"  ↻ Promoted {ADMIN_EMAIL} → admin")
        else:
            print(f"  ⊙ Admin {ADMIN_EMAIL} already exists")
        return existing

    hashed = get_password_hash_sync(ADMIN_PASSWORD)
    user = User.create(
        email=ADMIN_EMAIL,
        hashed_password=hashed,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    profile = UserProfile(
        user_id=user.id,
        full_name="Платформенный администратор",
        about="Учётная запись для управления системой ГУУ — тестовая для W150 polish-arc.",
        telegram="@guu_admin",
        status="Online — мониторинг системы",
        avatar_url="https://picsum.photos/seed/avatar_admin/256/256",
    )
    db.add(profile)
    await db.flush()
    print(f"  ✓ Admin: {user.email} (id={user.id})")
    return user


async def seed_extra_groups(db) -> dict[str, Group]:
    """Create additional groups + return map of name → Group."""
    by_name: dict[str, Group] = {}

    # Pick up the pre-existing group from seed_demo_data.py
    existing = await db.scalars(select(Group))
    for grp in existing.all():
        by_name[grp.name] = grp

    for name, course, faculty in EXTRA_GROUPS:
        if name in by_name:
            continue
        grp = Group(name=name, course=course, faculty=faculty)
        db.add(grp)
        await db.flush()
        by_name[name] = grp
        print(f"  ✓ Group: {name}")

    return by_name


async def seed_extra_users(db, groups: dict[str, Group]) -> list[User]:
    """Create additional users for AdminUsers page."""
    created = []
    for (
        email,
        password,
        full_name,
        role,
        telegram,
        institute,
        course,
        group_name,
    ) in EXTRA_USERS:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            print(f"  ⊙ User {email} already exists")
            created.append(existing)
            continue

        hashed = get_password_hash_sync(password)
        user = User.create(
            email=email,
            hashed_password=hashed,
            role=role,
            is_active=True,
        )
        if group_name and group_name in groups:
            user.group_id = groups[group_name].id
        db.add(user)
        await db.flush()

        profile = UserProfile(
            user_id=user.id,
            full_name=full_name,
            telegram=telegram,
            avatar_url=f"https://picsum.photos/seed/avatar_{email.split('@')[0]}/256/256",
        )
        db.add(profile)

        if institute and course:
            edu = EducationPath(
                user_id=user.id,
                institute=institute,
                course=course,
                education_level="Бакалавриат",
            )
            db.add(edu)

        await db.flush()
        created.append(user)
        print(f"  ✓ User: {email} ({role.value})")
    return created


async def seed_audit_logs(db, admin: User, others: list[User]) -> None:
    """Create signed audit log entries for AdminAudit page."""
    audit_secret = os.environ.get(
        "AUDIT_LOG_SECRET", "dev-audit-secret-key-for-local-testing"
    )
    if not audit_secret:
        print("  ⚠ AUDIT_LOG_SECRET not set — skipping audit log seed")
        return

    service = SecureAuditService(signing_key=audit_secret.encode("utf-8"))

    # Audit service stamps created_at server-side; timestamps spread naturally
    actors = [admin, *others]

    created = 0
    for idx, (resource_type, action, ctx_msg) in enumerate(AUDIT_ACTIONS):
        actor = actors[idx % len(actors)]
        subject = actors[(idx + 1) % len(actors)] if "user." in action else None
        try:
            await service.create_log(
                db,
                actor_user_id=actor.id,
                subject_user_id=subject.id if subject else None,
                resource_type=resource_type,
                resource_id=f"{resource_type}-{idx + 100}",
                action=action,
                context={"message": ctx_msg, "demo_seed": True},
                ip_address=f"10.0.0.{50 + idx}",
                user_agent="Mozilla/5.0 (W150 admin polish seed)",
            )
            created += 1
        except Exception as exc:
            print(f"  ⚠ Audit log {idx} failed: {exc}")
    print(f"  ✓ Audit logs: {created} entries created")


async def seed_dead_letter_jobs(db) -> None:
    """Create dead-letter notification jobs for AdminNotifications page."""
    import hashlib

    now = datetime.now(UTC)
    created = 0
    for idx, job_spec in enumerate(DEAD_LETTER_JOBS):
        # Compute deterministic job_hash for idempotency on re-run
        payload_str = json.dumps(job_spec["payload"], sort_keys=True)
        job_hash = hashlib.sha256(
            f"{job_spec['job_type']}|{payload_str}|seed-{idx}".encode()
        ).hexdigest()

        existing = await db.scalar(
            select(DeadLetterJob).where(DeadLetterJob.job_hash == job_hash)
        )
        if existing:
            print(f"  ⊙ Dead-letter job {idx} already exists (hash={job_hash[:10]}…)")
            continue

        job = DeadLetterJob(
            job_type=job_spec["job_type"],
            job_hash=job_hash,
            payload=payload_str,
            error_message=job_spec["error_message"],
            retry_count=job_spec["retry_count"],
            max_retries=3,
            status=job_spec["status"],
            created_at=now - timedelta(hours=idx + 1),
            updated_at=now - timedelta(minutes=idx * 10),
        )
        if job_spec["status"] == JobStatus.RETRYING.value:
            job.next_retry_at = now + timedelta(minutes=15)
        db.add(job)
        await db.flush()
        created += 1
        print(f"  ✓ Dead-letter job: {job_spec['job_type']} ({job_spec['status']})")
    print(f"  ✓ Dead-letter jobs: {created} created")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print("Initialising database connection…")
    init_database()

    async with async_session() as db:
        try:
            print("\n[1/5] Admin user")
            admin = await find_or_create_admin(db)

            print("\n[2/5] Extra groups")
            groups = await seed_extra_groups(db)

            print("\n[3/5] Extra users")
            others = await seed_extra_users(db, groups)

            print("\n[4/5] Audit logs")
            await seed_audit_logs(db, admin, others)

            print("\n[5/5] Dead-letter notification jobs")
            await seed_dead_letter_jobs(db)

            await db.commit()
            print("\n" + "=" * 60)
            print("Admin seed data committed successfully.")
            print("=" * 60)
            print(f"\n  Admin login:    {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
            print("  Student login:  test@university.dev / TestPass@2024x")
            print(
                f"  Other users:    {len(EXTRA_USERS)} created (mix of student/teacher)"
            )
            print(f"  Audit entries:  {len(AUDIT_ACTIONS)} signed logs")
            print(
                f"  Dead-letter:    {len(DEAD_LETTER_JOBS)} jobs (mix of pending/retrying/failed)"
            )
            print("\n  Open: http://localhost:5173/admin/audit (or your dev URL)")
        except IntegrityError as exc:
            await db.rollback()
            msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                print("\n⚠ Some data already exists — partial run committed.")
            else:
                print(f"\n✗ IntegrityError: {exc}")
                raise


if __name__ == "__main__":
    asyncio.run(main())
