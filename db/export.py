import csv
import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead
from db.repository import get_leads

logger = logging.getLogger(__name__)


def _lead_to_dict(lead: Lead) -> dict:
    return {
        "place_id": lead.place_id,
        "name": lead.name,
        "full_address": lead.full_address,
        "city": lead.city,
        "state": lead.state,
        "postal_code": lead.postal_code,
        "country": lead.country,
        "phone": lead.phone,
        "website": lead.website,
        "email": lead.email,
        "rating": lead.rating,
        "review_count": lead.review_count,
        "category": lead.category,
        "all_categories": json.loads(lead.all_categories) if lead.all_categories else [],
        "latitude": lead.latitude,
        "longitude": lead.longitude,
        "google_maps_url": lead.google_maps_url,
        "hours": json.loads(lead.hours) if lead.hours else {},
        "attributes": json.loads(lead.attributes) if lead.attributes else {},
        "images": json.loads(lead.images) if lead.images else {},
        "facebook": lead.facebook,
        "instagram": lead.instagram,
        "twitter": lead.twitter,
        "linkedin": lead.linkedin,
        "youtube": lead.youtube,
        "tiktok": lead.tiktok,
        "source_query": lead.source_query,
        "scraped_at": lead.scraped_at.isoformat() if lead.scraped_at else None,
    }


async def export_jsonl(session: AsyncSession, path: Path, **filters) -> int:
    leads = await get_leads(session, **filters)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(_lead_to_dict(lead), ensure_ascii=False) + "\n")
    logger.info("Exported %d leads → %s", len(leads), path)
    return len(leads)


async def export_csv(session: AsyncSession, path: Path, **filters) -> int:
    leads = await get_leads(session, **filters)
    if not leads:
        logger.warning("No leads to export.")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_lead_to_dict(lead) for lead in leads]
    # Flatten nested dicts to JSON strings for CSV compatibility
    flat_rows = []
    for row in rows:
        flat = {}
        for k, v in row.items():
            flat[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        flat_rows.append(flat)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=flat_rows[0].keys())
        writer.writeheader()
        writer.writerows(flat_rows)
    logger.info("Exported %d leads → %s", len(leads), path)
    return len(leads)
