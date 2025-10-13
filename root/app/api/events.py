import logging
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.core.database import get_db
from app.models import models
from app.schemas import schemas
from app.services.notifications import notify_about_event
from app.utils.files import delete_static_file, save_attachment

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=schemas.EventOut)
async def create_event(
    data: schemas.EventCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    record = await crud.create_event(db, data, user_id=user.id)
    try:
        await notify_about_event(db, record)
    except Exception:
        logger.exception(
            "Failed to dispatch event notification", extra={"event_id": record.id}
        )
    return record


@router.get("", response_model=List[schemas.EventOut])
async def all_events(
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    search: str = Query("", alias="search"),
    type: str = Query("", alias="type"),
    location: str = Query("", alias="location"),
    is_active: bool = Query(True, alias="is_active"),
):
    return await crud.get_all_events(
        db,
        user_id=user.id,
        search=search,
        type=type,
        location=location,
        is_active=is_active,
    )


@router.post("/attendance", response_model=schemas.EventAttendanceOut)
async def attend(
    data: schemas.EventAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role in ("admin", "teacher"):
        raise HTTPException(
            status_code=403,
            detail="Регистрация на мероприятия недоступна для вашей роли",
        )
    return await crud.register_attendance(db, data, user_id=user.id)


@router.delete("/attendance", response_model=dict)
async def unregister_event(
    data: schemas.EventAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return await crud.unregister_attendance(db, data, user_id=user.id)


@router.get("/my", response_model=List[schemas.EventOut])
async def my_events(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    return await crud.get_my_events(db, user_id=user.id)


@router.post("/{id}/upload_file", response_model=schemas.EventFileOut)
async def upload_event_file(
    id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    event = await db.get(models.Event, id)
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_attachment(file, "event_files", f"event_{id}")
    ef = models.EventFile(event_id=id, file_url=url)
    db.add(ef)
    await db.commit()
    await db.refresh(ef)
    return ef


@router.get("/{id}/files", response_model=List[schemas.EventFileOut])
async def get_event_files(id: int, db: AsyncSession = Depends(get_db)):
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == id)
            )
        )
        .scalars()
        .all()
    )
    return files


@router.post("/upload_image")
async def upload_event_image(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_upload(file, "event_images", "event")
    return {"url": url}


@router.patch("/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: int,
    data: schemas.EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(q, field, value)
    await db.commit()
    await db.refresh(q)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    return out


@router.delete("/{event_id}", response_model=dict)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    file_urls = [
        row[0]
        for row in (
            await db.execute(
                select(models.EventFile.file_url).where(
                    models.EventFile.event_id == event_id
                )
            )
        ).all()
        if row[0]
    ]
    await db.execute(
        delete(models.EventFile).where(models.EventFile.event_id == event_id)
    )
    await db.delete(q)
    await db.commit()
    for url in file_urls:
        await delete_static_file(url)
    return {"ok": True}


@router.get("/{id}", response_model=schemas.EventOut)
async def get_event(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    attendance = (
        await db.execute(
            select(models.EventAttendance).where(
                and_(
                    models.EventAttendance.event_id == q.id,
                    models.EventAttendance.user_id == user.id,
                )
            )
        )
    ).scalar_one_or_none()
    if attendance and not attendance.qr_code:
        attendance.qr_code = str(uuid.uuid4())
        await db.commit()
        await db.refresh(attendance)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    out.is_registered = attendance is not None
    out.my_qr_code = attendance.qr_code if attendance else None
    return out


@router.delete("/file/{file_id}", response_model=dict)
async def delete_event_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ef = await db.get(models.EventFile, file_id)
    if not ef:
        raise HTTPException(status_code=404, detail="Файл не найден")
    event = await db.get(models.Event, ef.event_id)
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    file_url = ef.file_url
    await db.delete(ef)
    await db.commit()
    await delete_static_file(file_url)
    return {"ok": True}


__all__ = ["router"]
