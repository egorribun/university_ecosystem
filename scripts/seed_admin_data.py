"""
Seed script — creates admin user + sample data for /admin pages.

Run through the owner-checked live stand command after the demo seed, or from
the narrowly scoped admin-smoke GitHub workflow target. Other direct execution
without a verified seed target fails closed.

Usage:
    python scripts/live_stand.py seed --demo

The script requires TEST_PASSWORD in its process environment. It has no built-in
admin password; CI supplies a unique, masked value for each admin-smoke run.

Creates:
- 1 admin user: admin@university.dev (password supplied via TEST_PASSWORD)
- 6 additional users (mix of students + teachers across 3 groups) for AdminUsers
- 12 audit log entries for AdminAudit (signed via SecureAuditService)
- 4 dead-letter notification jobs for AdminNotifications
- Feature flags: none — the flagd registry is empty until a flag has a call site
- Stories: created by seed_demo_data.py — no seeding needed here
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

if "DATABASE_URL" not in os.environ:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.security import get_password_hash_sync, verify_password_sync
from app.core.database import async_session, init_database
from app.models.dead_letter import DeadLetterJob, JobStatus
from app.models.enums import UserRole
from app.models.logs import DataAccessLog
from app.models.notifications import UserPushTopic
from app.models.schedule import Group, Schedule
from app.models.users import EducationPath, User, UserProfile
from app.services.audit_service import SecureAuditService
from scripts.seed_target import ADMIN_SMOKE_PROJECT, require_owned_live_stand_target

# ---------------------------------------------------------------------------
# Admin user credentials (no `!` per CLAUDE.md docker gotcha)
# ---------------------------------------------------------------------------

ADMIN_EMAIL = "admin@university.dev"

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

# Real-delivery acceptance fixtures may safely enable only the chat topic for
# this exact, synthetic seed roster. Unknown accounts are deliberately left
# untouched so the live spec's all-recipient preflight fails closed.
LIVE_NOTIFICATION_DELIVERY_GROUP_NAME = (
    "University Ecosystem live notification delivery"
)
LIVE_NOTIFICATION_DELIVERY_ROSTER_EMAILS = (
    ADMIN_EMAIL,
    "test@university.dev",
    "demo.peer@example.com",
    "demo.peer.two@example.com",
    *(entry[0] for entry in EXTRA_USERS),
)
LIVE_NOTIFICATION_DELIVERY_TOPICS = ("chat.message.created",)

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


def _required_test_password() -> str:
    """Return the transient admin smoke password or fail before DB access."""
    password = os.environ.get("TEST_PASSWORD")
    if not password or not password.strip():
        raise RuntimeError("TEST_PASSWORD must be set to a non-empty password")
    return password


def _admin_profile(user_id) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        full_name="Платформенный администратор",
        about="Учётная запись для управления системой ГУУ — тестовая для W150 polish-arc.",
        telegram="@guu_admin",
        status="Online — мониторинг системы",
        avatar_url="https://picsum.photos/seed/avatar_admin/256/256",
    )


async def find_or_create_admin(
    db,
    *,
    admin_password: str,
    reconcile_stand_password: bool = False,
) -> User:
    """Create or repair the synthetic admin without changing unrelated accounts."""
    existing = await db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if existing:
        if existing.role != UserRole.ADMIN:
            raise ValueError(
                "refusing to elevate an existing account with a different role"
            )
        if reconcile_stand_password and not verify_password_sync(
            admin_password, existing.hashed_password
        ):
            existing.hashed_password = get_password_hash_sync(admin_password)
            db.add(existing)
        profile_exists = await db.scalar(
            select(UserProfile.user_id).where(UserProfile.user_id == existing.id)
        )
        if profile_exists is None:
            db.add(_admin_profile(existing.id))
        await db.flush()
        print(f"  ⊙ Admin {ADMIN_EMAIL} already exists")
        return existing

    hashed = get_password_hash_sync(admin_password)
    user = User.create(
        email=ADMIN_EMAIL,
        hashed_password=hashed,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    db.add(_admin_profile(user.id))
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
            if existing.role != role:
                raise ValueError(
                    "refusing to modify a demo account with a different role"
                )
            if existing.group_id is None and group_name and group_name in groups:
                existing.group_id = groups[group_name].id

            profile_exists = await db.scalar(
                select(UserProfile.user_id).where(UserProfile.user_id == existing.id)
            )
            if profile_exists is None:
                db.add(
                    UserProfile(
                        user_id=existing.id,
                        full_name=full_name,
                        telegram=telegram,
                        avatar_url=f"https://picsum.photos/seed/avatar_{email.split('@')[0]}/256/256",
                    )
                )

            if institute and course:
                education_path_exists = await db.scalar(
                    select(EducationPath.user_id).where(
                        EducationPath.user_id == existing.id
                    )
                )
                if education_path_exists is None:
                    db.add(
                        EducationPath(
                            user_id=existing.id,
                            institute=institute,
                            course=course,
                            education_level="Бакалавриат",
                        )
                    )

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


def should_seed_live_notification_fixture(
    *, seed_target: str, admin_preexisted: bool
) -> bool:
    """Allow notification fixture preparation only on the first owned-stand seed."""
    return seed_target != ADMIN_SMOKE_PROJECT and not admin_preexisted


async def seed_live_notification_delivery_fixture(db) -> Group:
    """Prepare the isolated schedule group and explicit topic rows for known seeds.

    This is called only by ``main`` after the owned-stand seed target has been
    verified and the admin was confirmed absent. It never changes an existing
    topic preference and never discovers accounts by a broad email pattern.
    """
    matching_groups = list(
        (
            await db.scalars(
                select(Group).where(Group.name == LIVE_NOTIFICATION_DELIVERY_GROUP_NAME)
            )
        ).all()
    )
    if len(matching_groups) > 1:
        raise RuntimeError(
            "the dedicated notification delivery group name is ambiguous"
        )
    if matching_groups:
        group = matching_groups[0]
    else:
        group = Group(name=LIVE_NOTIFICATION_DELIVERY_GROUP_NAME)
        db.add(group)
        await db.flush()

    active_members = await db.scalar(
        select(func.count(User.id)).where(
            User.group_id == group.id,
            User.is_active.is_(True),
        )
    )
    schedules = await db.scalar(
        select(func.count(Schedule.id)).where(Schedule.group_id == group.id)
    )
    if int(active_members or 0) != 0 or int(schedules or 0) != 0:
        raise RuntimeError("the dedicated notification delivery group must be empty")

    users = list(
        (
            await db.scalars(
                select(User).where(
                    User.email.in_(LIVE_NOTIFICATION_DELIVERY_ROSTER_EMAILS)
                )
            )
        ).all()
    )
    users_by_email = {user.email: user for user in users}
    missing_emails = set(LIVE_NOTIFICATION_DELIVERY_ROSTER_EMAILS) - set(users_by_email)
    if missing_emails:
        raise RuntimeError(
            "the expected synthetic notification delivery roster is incomplete"
        )

    existing_preferences = {
        preference.user_id: preference
        for preference in (
            await db.scalars(
                select(UserPushTopic).where(
                    UserPushTopic.user_id.in_([user.id for user in users])
                )
            )
        ).all()
    }
    created_preferences = 0
    for user in users:
        if user.id in existing_preferences:
            continue
        db.add(
            UserPushTopic(
                user_id=user.id,
                topics=list(LIVE_NOTIFICATION_DELIVERY_TOPICS),
            )
        )
        created_preferences += 1

    await db.flush()
    print(
        "  ✓ Live notification fixture: dedicated empty schedule group and "
        f"{created_preferences} missing saved topic preference(s) prepared"
    )
    return group


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
        resource_id = f"{resource_type}-{idx + 100}"
        context = {"message": ctx_msg, "demo_seed": True}
        existing = await db.scalar(
            select(DataAccessLog.id).where(
                DataAccessLog.resource_type == resource_type,
                DataAccessLog.resource_id == resource_id,
                DataAccessLog.action == action,
                DataAccessLog.context["demo_seed"].as_boolean().is_(True),
            )
        )
        if existing is not None:
            continue

        try:
            await service.create_log(
                db,
                actor_user_id=actor.id,
                subject_user_id=subject.id if subject else None,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                context=context,
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
    seed_target = require_owned_live_stand_target()
    reconcile_stand_password = seed_target != ADMIN_SMOKE_PROJECT
    admin_password = _required_test_password()
    print("Initialising database connection…")
    init_database()

    async with async_session() as db:
        try:
            admin_preexisted = (
                await db.scalar(select(User.id).where(User.email == ADMIN_EMAIL))
            ) is not None
            seed_notification_fixture = should_seed_live_notification_fixture(
                seed_target=seed_target,
                admin_preexisted=admin_preexisted,
            )

            print("\n[1/6] Admin user")
            try:
                admin = await find_or_create_admin(
                    db,
                    admin_password=admin_password,
                    reconcile_stand_password=reconcile_stand_password,
                )
            finally:
                del admin_password

            print("\n[2/6] Extra groups")
            groups = await seed_extra_groups(db)

            print("\n[3/6] Extra users")
            others = await seed_extra_users(db, groups)

            if seed_notification_fixture:
                print("\n[4/6] Fresh owned-stand notification fixture")
                await seed_live_notification_delivery_fixture(db)

            print("\n[5/6] Audit logs")
            await seed_audit_logs(db, admin, others)

            print("\n[6/6] Dead-letter notification jobs")
            await seed_dead_letter_jobs(db)

            await db.commit()
            print("\n" + "=" * 60)
            print("Admin seed data committed successfully.")
            print("=" * 60)
            print(f"\n  Admin account:  {ADMIN_EMAIL}")
            print("  Student demo account: seeded")
            print(
                f"  Other users:    {len(EXTRA_USERS)} created (mix of student/teacher)"
            )
            print(f"  Audit entries:  {len(AUDIT_ACTIONS)} signed logs")
            print(
                f"  Dead-letter:    {len(DEAD_LETTER_JOBS)} jobs (mix of pending/retrying/failed)"
            )
            print("\n  Open: http://localhost:5173/admin/audit (or your dev URL)")
        except IntegrityError:
            await db.rollback()
            raise RuntimeError(
                "admin seed transaction failed and was rolled back"
            ) from None


if __name__ == "__main__":
    asyncio.run(main())
