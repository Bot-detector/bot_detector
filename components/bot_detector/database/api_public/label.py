from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Select

from bot_detector.database import Base
from sqlalchemy import Column, Integer, Text


class Label(Base):
    __tablename__ = "Labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(Text)


class LabelRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_labels(self) -> list[Label]:
        sql_select: Select = select(Label)
        sql_select = sql_select.order_by(Label.id.asc())

        async with self.session:
            result = await self.session.execute(sql_select)
            labels = result.scalars().all()

        return labels

    async def get_label_by_id(self, label_id: int) -> Label | None:
        sql_select: Select = select(Label).where(Label.id == label_id)
        sql_select = sql_select.order_by(Label.id.asc())

        async with self.session:
            result = await self.session.execute(sql_select)
            label = result.scalar_one_or_none()

        return label
