from datetime import datetime

from bot_detector.database import Base
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class ApiUserTableStruct(Base):
    __tablename__ = "apiUser"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False
    )
    username: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ratelimit: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApiPermissionTableStruct(Base):
    __tablename__ = "apiPermissions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False
    )
    permission: Mapped[str] = mapped_column(Text)


class ApiUserPermTableStruct(Base):
    __tablename__ = "apiUserPerms"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("apiUser.id"))
    permission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("apiPermissions.id")
    )


class ApiUsageTableStruct(Base):
    __tablename__ = "apiUsage"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, init=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("apiUser.id"))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    route: Mapped[str | None] = mapped_column(Text, default=None)
