from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from config.settings import DATABASE_URL

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False)
