"""Closure tests for AuditRepository's model contract and factory."""

from app.repositories.audit_repository import AuditRepository, get_audit_repository


def test_audit_repository_contract_and_factory(db_session):
    repo = AuditRepository(db_session)

    assert repo.model.__name__ == "DataAccessLog"
    assert repo.dto_class.__name__ == "DataAccessLogDTO"

    factory_repo = get_audit_repository(db_session)
    assert isinstance(factory_repo, AuditRepository)
    assert factory_repo.db is db_session
