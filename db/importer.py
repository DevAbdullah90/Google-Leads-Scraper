import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from db.repository import upsert_lead
from models.business import Business

logger = logging.getLogger(__name__)


async def import_jsonl(session: AsyncSession, path: Path) -> int:
    """Import business records from a legacy JSONL file into the DB."""
    if not path.exists():
        logger.error("File not found: %s", path)
        return 0

    saved = 0
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                business = Business.model_validate(data)
                if await upsert_lead(session, business):
                    saved += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.warning("Line %d in %s: %s", line_no, path.name, exc)

    logger.info("Import complete: %d saved, %d skipped — %s", saved, skipped, path.name)
    return saved
