import json
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Lead
from models.business import Business

logger = logging.getLogger(__name__)


def _flatten(business: Business, source_query: str | None = None) -> dict:
    b = business
    return {
        "place_id": b.place_id,
        "name": b.business_name,
        "full_address": b.address.full_address,
        "city": b.address.city,
        "state": b.address.state,
        "postal_code": b.address.postal_code,
        "country": b.address.country,
        "phone": b.contact.phone,
        "website": b.contact.website,
        "email": b.contact.email,
        "rating": b.ratings.average_rating,
        "review_count": b.ratings.total_reviews,
        "category": b.business_info.category,
        "all_categories": json.dumps(b.business_info.all_categories, ensure_ascii=False),
        "latitude": b.coordinates.latitude,
        "longitude": b.coordinates.longitude,
        "google_maps_url": b.google_maps_url or None,
        "hours": json.dumps(b.hours.model_dump(mode="json"), ensure_ascii=False),
        "attributes": json.dumps(b.attributes.model_dump(mode="json"), ensure_ascii=False),
        "images": json.dumps(b.images.model_dump(mode="json"), ensure_ascii=False),
        "facebook": b.social_media.facebook,
        "instagram": b.social_media.instagram,
        "twitter": b.social_media.twitter,
        "linkedin": b.social_media.linkedin,
        "youtube": b.social_media.youtube,
        "tiktok": b.social_media.tiktok,
        "source_query": source_query or b.metadata.query,
        "scraped_at": datetime.now(timezone.utc),
    }


async def upsert_lead(
    session: AsyncSession,
    business: Business,
    source_query: str | None = None,
) -> bool:
    if not business.place_id:
        logger.warning("Business %r has no place_id — skipping DB save", business.business_name)
        return False

    data = _flatten(business, source_query)
    stmt = sqlite_insert(Lead).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["place_id"],
        set_={k: v for k, v in data.items() if k != "place_id"},
    )
    try:
        await session.execute(stmt)
        await session.commit()

        # Warn on secondary duplicates (same phone/website, different place_id)
        await _warn_secondary_duplicates(session, business)
        return True
    except Exception as exc:
        logger.error("DB upsert failed for %r: %s", business.business_name, exc)
        await session.rollback()
        return False


async def _warn_secondary_duplicates(session: AsyncSession, business: Business) -> None:
    phone = business.contact.phone
    website = business.contact.website
    if not phone and not website:
        return

    filters = []
    if phone:
        filters.append(Lead.phone == phone)
    if website:
        filters.append(Lead.website == website)

    stmt = (
        select(Lead.place_id, Lead.name)
        .where(or_(*filters))
        .where(Lead.place_id != business.place_id)
        .limit(3)
    )
    result = await session.execute(stmt)
    rows = result.fetchall()
    for row in rows:
        logger.warning(
            "Secondary duplicate: %r (place_id=%s) shares phone/website with %r (place_id=%s)",
            business.business_name, business.place_id, row.name, row.place_id,
        )


async def get_leads(
    session: AsyncSession,
    *,
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    has_email: bool | None = None,
    has_phone: bool | None = None,
    source_query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead)
    if city:
        stmt = stmt.where(Lead.city.ilike(f"%{city}%"))
    if category:
        stmt = stmt.where(Lead.category.ilike(f"%{category}%"))
    if min_rating is not None:
        stmt = stmt.where(Lead.rating >= min_rating)
    if has_email is True:
        stmt = stmt.where(Lead.email.isnot(None), Lead.email != "")
    elif has_email is False:
        stmt = stmt.where(or_(Lead.email.is_(None), Lead.email == ""))
    if has_phone is True:
        stmt = stmt.where(Lead.phone.isnot(None), Lead.phone != "")
    elif has_phone is False:
        stmt = stmt.where(or_(Lead.phone.is_(None), Lead.phone == ""))
    if source_query:
        stmt = stmt.where(Lead.source_query == source_query)
    stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_urls_for_query(session: AsyncSession, query: str) -> set[str]:
    stmt = select(Lead.google_maps_url).where(
        Lead.source_query == query,
        Lead.google_maps_url.isnot(None),
        Lead.google_maps_url != "",
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.fetchall()}


async def get_place_ids_for_query(session: AsyncSession, query: str) -> set[str]:
    stmt = select(Lead.place_id).where(Lead.source_query == query)
    result = await session.execute(stmt)
    return {row[0] for row in result.fetchall()}


async def count_leads(session: AsyncSession) -> int:
    from sqlalchemy import func
    result = await session.execute(select(func.count()).select_from(Lead))
    return result.scalar_one()
