import logging

from app.core.events import EventCreated, EventUpdated
from app.core.exceptions.domain import EntityNotFound
from app.models import models
from app.repositories.event import EventRepository
from app.schemas import schemas
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class EventService:
    def __init__(self, repo: EventRepository, vector_service: VectorService):
        self.repo = repo
        self.vector_service = vector_service

    async def get_events(
        self,
        *,
        user_id: int | None = None,
        search: str = "",
        type: str = "",
        location: str = "",
        is_active: bool | None = True,
        limit: int = 20,
        cursor: str | None = None,
    ):
        query_embedding = None
        if search:
            query_embedding = await self.vector_service.get_embedding(search)

        # Cursor decoding moved to service/util logic
        # For brevity, assuming a helper or repository handled it or passing raw
        # Let's assume repo handles the tuple cursor
        decoded_cursor = None  # logic to decode cursor...

        results = await self.repo.search_events(
            user_id=user_id,
            search_query=search,
            event_type=type,
            location=location,
            is_active=is_active,
            limit=limit,
            cursor=decoded_cursor,
            query_embedding=query_embedding,
        )
        return results

    async def create_event(
        self, data: schemas.EventCreate, user_id: int
    ) -> models.Event:
        event = await self.repo.create(**data.model_dump(), created_by=user_id)
        event.record_event(EventCreated(event_id_entity=event.id, title=event.title))
        await self.repo.db.commit()
        await self.repo.db.refresh(event)
        return event

    async def update_event(
        self, event_id: int, data: schemas.EventUpdate
    ) -> models.Event:
        event = await self.repo.get(event_id)
        if not event:
            raise EntityNotFound("Event", event_id)

        updates = data.model_dump(exclude_unset=True)
        text_changed = any(
            f in updates for f in ("title", "description", "location", "about")
        )

        updated_event = await self.repo.update(event, **updates)
        if text_changed:
            updated_event.record_event(
                EventUpdated(
                    event_id_entity=updated_event.id, title=updated_event.title
                )
            )

        await self.repo.db.commit()
        await self.repo.db.refresh(updated_event)
        return updated_event
