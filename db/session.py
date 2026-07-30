from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.engine import engine

_factory = async_sessionmaker(engine, expire_on_commit=False)


def new_session() -> AsyncSession:
    return _factory()
