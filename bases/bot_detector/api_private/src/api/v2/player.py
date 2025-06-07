from fastapi import APIRouter, Depends, Query

from src.app.repositories.player import PlayerRepo
from src.core.fastapi.dependencies.session import get_session

router = APIRouter()


@router.get("/player")
async def get_player(
    player_id: str = None,
    player_name: str = None,
    label_id: int = None,
    greater_than: bool = False,
    limit: int = Query(default=1_000, ge=0, le=100_000),
    session=Depends(get_session),
):
    # TODO: make use of abstract base class
    repo = PlayerRepo(session=session)

    data = await repo.select(
        player_id=player_id,
        player_name=player_name,
        greater_than=greater_than,
        label_id=label_id,
        limit=limit,
    )
    return data
