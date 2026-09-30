import pytest
from sqlalchemy import select

import app.models as models
from scripts.seed_admin_data import AUDIT_ACTIONS, seed_audit_logs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_seed_audit_logs_is_idempotent(db_session, user_factory, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_SECRET", "test-audit-signing-key")
    admin = await user_factory(role="admin")
    other = await user_factory(role="student")

    async def demo_seed_logs():
        result = await db_session.scalars(select(models.DataAccessLog))
        return [
            row
            for row in result.all()
            if row.context and row.context.get("demo_seed") is True
        ]

    await seed_audit_logs(db_session, admin, [other])
    first_run_logs = await demo_seed_logs()
    assert len(first_run_logs) == len(AUDIT_ACTIONS)
    await db_session.commit()

    await seed_audit_logs(db_session, admin, [other])
    second_run_logs = await demo_seed_logs()

    assert len(second_run_logs) == len(first_run_logs)


async def test_admin_seed_fails_closed_before_database_initialization_without_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import seed_admin_data

    monkeypatch.setattr(
        seed_admin_data,
        "require_owned_live_stand_target",
        lambda: "ue-live-testproject",
    )

    def database_must_not_start() -> None:
        pytest.fail(
            "admin seeding must reject a missing password before database initialization"
        )

    monkeypatch.setattr(seed_admin_data, "init_database", database_must_not_start)
    monkeypatch.delenv("TEST_PASSWORD", raising=False)
    try:
        with pytest.raises(RuntimeError, match="TEST_PASSWORD"):
            await seed_admin_data.main()
    finally:
        capsys.readouterr()

    monkeypatch.setenv("TEST_PASSWORD", " \t ")
    try:
        with pytest.raises(RuntimeError, match="TEST_PASSWORD"):
            await seed_admin_data.main()
    finally:
        capsys.readouterr()


@pytest.mark.parametrize(
    ("seed_target", "should_reconcile"),
    (("ue-live-0123456789abcdef", True), ("ci-admin-smoke", False)),
)
async def test_admin_seed_scopes_password_reconciliation_to_live_stands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    seed_target: str,
    should_reconcile: bool,
) -> None:
    import secrets

    from scripts import seed_admin_data

    monkeypatch.setattr(
        seed_admin_data,
        "require_owned_live_stand_target",
        lambda: seed_target,
    )

    runtime_password = secrets.token_urlsafe(32)
    monkeypatch.setenv("TEST_PASSWORD", runtime_password)

    def no_op_init_database() -> None:
        return None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    observed_passwords: list[tuple[str, bool]] = []

    async def capture_admin_password(
        db, *, admin_password: str, reconcile_stand_password: bool
    ):
        observed_passwords.append((admin_password, reconcile_stand_password))
        return object()

    async def no_op_seed(db, *args):
        return []

    monkeypatch.setattr(seed_admin_data, "init_database", no_op_init_database)
    monkeypatch.setattr(seed_admin_data, "async_session", FakeSession)
    monkeypatch.setattr(seed_admin_data, "find_or_create_admin", capture_admin_password)
    monkeypatch.setattr(seed_admin_data, "seed_extra_groups", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_extra_users", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_audit_logs", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_dead_letter_jobs", no_op_seed)

    try:
        await seed_admin_data.main()
    finally:
        output = capsys.readouterr()

    if len(observed_passwords) != 1 or not secrets.compare_digest(
        observed_passwords[0][0], runtime_password
    ):
        pytest.fail(
            "admin seeder did not pass the transient password to the admin creator"
        )
    if observed_passwords[0][1] is not should_reconcile:
        pytest.fail("password reconciliation escaped its owned live stand scope")

    if runtime_password in output.out or runtime_password in output.err:
        pytest.fail("admin seeder wrote the transient password to captured output")


async def test_reseeding_existing_admin_preserves_the_password_hash(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    import secrets

    from app.auth.security import verify_password_sync
    from scripts import seed_admin_data

    previous_password = secrets.token_urlsafe(32) + "!Aa0"
    current_password = secrets.token_urlsafe(32) + "!Aa0"
    previous_hash = seed_admin_data.get_password_hash_sync(previous_password)
    existing = await user_factory(
        email=seed_admin_data.ADMIN_EMAIL,
        role="admin",
        hashed_password=previous_hash,
    )
    profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    assert profile is not None
    await db_session.delete(profile)
    await db_session.flush()

    result = await seed_admin_data.find_or_create_admin(
        db_session, admin_password=current_password
    )
    await db_session.commit()
    await db_session.refresh(existing)
    output = capsys.readouterr()

    if result.id != existing.id:
        pytest.fail("admin reseeding must leave the matching account in place")
    if existing.hashed_password != previous_hash:
        pytest.fail("admin reseeding must preserve an existing password hash")
    if not verify_password_sync(previous_password, existing.hashed_password):
        pytest.fail("admin reseeding must preserve the existing account password")
    if verify_password_sync(current_password, existing.hashed_password):
        pytest.fail(
            "admin reseeding must not apply a new password to an existing account"
        )

    if current_password in output.out or current_password in output.err:
        pytest.fail("admin reseeding must not log the current password")
    restored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    assert restored_profile is not None
    assert restored_profile.full_name == "Платформенный администратор"


async def test_live_stand_seed_reconciles_its_persisted_admin_password(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    import secrets

    from app.auth.security import verify_password_sync
    from scripts import seed_admin_data

    previous_password = secrets.token_urlsafe(32) + "!Aa0"
    stand_password = secrets.token_urlsafe(32) + "!Bb1"
    previous_hash = seed_admin_data.get_password_hash_sync(previous_password)
    existing = await user_factory(
        email=seed_admin_data.ADMIN_EMAIL,
        role="admin",
        hashed_password=previous_hash,
    )

    result = await seed_admin_data.find_or_create_admin(
        db_session,
        admin_password=stand_password,
        reconcile_stand_password=True,
    )
    await db_session.commit()
    await db_session.refresh(existing)
    output = capsys.readouterr()

    assert result.id == existing.id
    assert existing.hashed_password != previous_hash
    assert verify_password_sync(stand_password, existing.hashed_password)
    assert not verify_password_sync(previous_password, existing.hashed_password)
    assert stand_password not in output.out
    assert stand_password not in output.err


async def test_reseeding_existing_extra_user_repairs_missing_demo_relations(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import seed_admin_data

    email, _password, full_name, role, telegram, institute, course, group_name = (
        seed_admin_data.EXTRA_USERS[0]
    )
    groups = await seed_admin_data.seed_extra_groups(db_session)
    existing = await user_factory(
        email=email,
        role=role,
        hashed_password="kept-hash",  # pragma: allowlist secret
    )
    profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    assert profile is not None
    await db_session.delete(profile)
    education_path = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == existing.id)
    )
    if education_path is not None:
        await db_session.delete(education_path)
    await db_session.flush()

    users = await seed_admin_data.seed_extra_users(db_session, groups)
    await db_session.flush()
    restored_profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    education_path = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == existing.id)
    )
    output = capsys.readouterr()

    assert any(user.id == existing.id for user in users)
    assert existing.hashed_password == "kept-hash"  # pragma: allowlist secret
    assert existing.role == role
    assert existing.group_id == groups[group_name].id
    assert restored_profile is not None
    assert restored_profile.full_name == full_name
    assert restored_profile.telegram == telegram
    assert education_path is not None
    assert education_path.institute == institute
    assert education_path.course == course
    assert email not in output.err


async def test_reseeding_extra_user_rejects_role_collision_before_mutating_account(
    db_session, user_factory
) -> None:
    from scripts import seed_admin_data

    email, _password, _name, _expected_role, _telegram, _institute, _course, _group = (
        seed_admin_data.EXTRA_USERS[0]
    )
    groups = await seed_admin_data.seed_extra_groups(db_session)
    existing = await user_factory(
        email=email,
        role=models.UserRole.TEACHER,
        group_id=None,
        hashed_password="preserved-hash",  # pragma: allowlist secret
        full_name="Existing account name",
    )
    original_hash = existing.hashed_password

    with pytest.raises(ValueError, match="role"):
        await seed_admin_data.seed_extra_users(db_session, groups)

    await db_session.refresh(existing)
    profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    education_path = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == existing.id)
    )

    assert existing.role == models.UserRole.TEACHER
    assert existing.group_id is None
    assert existing.hashed_password == original_hash
    assert profile is not None
    assert profile.full_name == "Existing account name"
    assert education_path is None


async def test_reseeding_existing_extra_user_preserves_existing_custom_data(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import seed_admin_data

    email, _password, _full_name, role, _telegram, _institute, _course, _group_name = (
        seed_admin_data.EXTRA_USERS[0]
    )
    groups = await seed_admin_data.seed_extra_groups(db_session)
    existing = await user_factory(
        email=email,
        role=role,
        hashed_password="kept-hash",  # pragma: allowlist secret
    )
    existing.group_id = groups["ЭК-401"].id

    profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == existing.id)
    )
    assert profile is not None
    profile.full_name = "Custom existing name"
    profile.telegram = "@custom_handle"
    profile.avatar_url = "https://example.test/custom-avatar.png"

    education_path = await db_session.scalar(
        select(models.EducationPath).where(models.EducationPath.user_id == existing.id)
    )
    if education_path is None:
        education_path = models.EducationPath(
            user_id=existing.id,
            institute="Custom institute",
            course="Custom course",
            education_level="Магистратура",
        )
        db_session.add(education_path)
    else:
        education_path.institute = "Custom institute"
        education_path.course = "Custom course"
        education_path.education_level = "Магистратура"
    await db_session.flush()

    users = await seed_admin_data.seed_extra_users(db_session, groups)
    await db_session.flush()
    await db_session.refresh(existing)
    await db_session.refresh(profile)
    await db_session.refresh(education_path)
    capsys.readouterr()

    assert any(user.id == existing.id for user in users)
    assert existing.hashed_password == "kept-hash"  # pragma: allowlist secret
    assert existing.role == role
    assert existing.group_id == groups["ЭК-401"].id
    assert profile.full_name == "Custom existing name"
    assert profile.telegram == "@custom_handle"
    assert profile.avatar_url == "https://example.test/custom-avatar.png"
    assert education_path.institute == "Custom institute"
    assert education_path.course == "Custom course"
    assert education_path.education_level == "Магистратура"


async def test_reseeding_does_not_promote_an_existing_non_admin_account(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    import secrets

    from scripts import seed_admin_data

    existing = await user_factory(
        email=seed_admin_data.ADMIN_EMAIL,
        role="student",
    )

    try:
        with pytest.raises(ValueError, match="role"):
            await seed_admin_data.find_or_create_admin(
                db_session, admin_password=secrets.token_urlsafe(32) + "!Aa0"
            )
    finally:
        capsys.readouterr()

    await db_session.refresh(existing)
    assert str(existing.role.value) == "student"
