"""MFA adoption counts enrolled active accounts rather than all active users."""

from unittest.mock import patch

import pytest

from app.services import business_gauges


@pytest.mark.asyncio
async def test_mfa_adoption_excludes_unenrolled_and_inactive_accounts(
    db_session, user_factory
):
    with (
        patch.object(business_gauges, "set_active_users"),
        patch.object(business_gauges, "set_mfa_adoption") as exported,
    ):
        before = await business_gauges.refresh_business_gauges(db=db_session)
        await user_factory(mfa_default_method="totp", is_active=True)
        await user_factory(mfa_default_method="email_otp", is_active=True)
        await user_factory(mfa_default_method=None, is_active=True)
        await user_factory(mfa_default_method="totp", is_active=False)
        exported.reset_mock()

        after = await business_gauges.refresh_business_gauges(db=db_session)

    assert after["mfa"] == before["mfa"] + 2
    exported.assert_called_once_with(before["mfa"] + 2)
    assert after["daily"] == before["daily"]
    assert after["weekly"] == before["weekly"]
