from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.database import get_session_factory
from storage.models import AdminOperation


@dataclass(slots=True)
class AdminOperationPayload:
    request_id: str
    admin_user: str
    operation: str
    resource_type: str = ""
    resource_id: str = ""


@dataclass(slots=True)
class AdminOperationQuery:
    limit: int = 20
    offset: int = 0
    operation: str | None = None
    resource_type: str | None = None


@dataclass(slots=True)
class AdminOperationPage:
    items: list[AdminOperation]
    total: int
    limit: int
    offset: int


class AdminOperationWriter:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def write(self, payload: AdminOperationPayload) -> AdminOperation:
        async with self._session_factory() as session:
            operation = AdminOperation(
                request_id=payload.request_id,
                admin_user=payload.admin_user,
                operation=payload.operation,
                resource_type=payload.resource_type,
                resource_id=payload.resource_id,
            )
            session.add(operation)
            await session.commit()
            await session.refresh(operation)
            return operation


class AdminOperationReader:
    def __init__(self, session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory or get_session_factory()

    async def list(self, query: AdminOperationQuery) -> AdminOperationPage:
        safe_limit = min(max(query.limit, 1), 100)
        safe_offset = max(query.offset, 0)
        stmt = select(AdminOperation)
        count_stmt = select(func.count(AdminOperation.id))
        filters = []
        if query.operation:
            filters.append(AdminOperation.operation == query.operation)
        if query.resource_type:
            filters.append(AdminOperation.resource_type == query.resource_type)
        for item in filters:
            stmt = stmt.where(item)
            count_stmt = count_stmt.where(item)
        stmt = stmt.order_by(AdminOperation.created_at.desc(), AdminOperation.id.desc()).limit(safe_limit).offset(safe_offset)
        async with self._session_factory() as session:
            total = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            return AdminOperationPage(
                items=list(result.scalars().all()),
                total=total or 0,
                limit=safe_limit,
                offset=safe_offset,
            )
