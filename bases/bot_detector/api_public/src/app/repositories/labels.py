import logging

from bot_detector.database.api_public.models import Label as dbLabel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.sql.expression import Select

logger = logging.getLogger(__name__)


class LabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_labels(self) -> list[dbLabel]:
        sql_select: Select = select(dbLabel)
        sql_select = sql_select.order_by(dbLabel.id.asc())

        async with self.session:
            result: AsyncResult = await self.session.execute(sql_select)
            labels = result.scalars().all()

        return labels

    async def get_label_by_id(self, label_id: int) -> dbLabel | None:
        sql_select: Select = select(dbLabel).where(dbLabel.id == label_id)
        sql_select = sql_select.order_by(dbLabel.id.asc())

        async with self.session:
            result: AsyncResult = await self.session.execute(sql_select)
            label = result.scalar_one_or_none()

        return label
