from app.models.notifications import Notification


def test_notification_repository_factory_and_properties(db_session):
    from app.repositories.notification_repository import get_notification_repository

    repo = get_notification_repository(db_session)
    assert repo.model == Notification
    assert repo.db == db_session
