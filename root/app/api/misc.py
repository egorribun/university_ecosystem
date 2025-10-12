from fastapi import APIRouter

router = APIRouter(tags=["misc"])


@router.get("/activity/{id}")
async def get_activity(id: int):
    return {"id": id, "activity": "Demo activity"}


__all__ = ["router"]
