from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    place_id = Column(Text, unique=True, nullable=False, index=True)
    name = Column(Text)
    full_address = Column(Text)
    city = Column(Text)
    state = Column(Text)
    postal_code = Column(Text)
    country = Column(Text)
    phone = Column(Text)
    website = Column(Text)
    email = Column(Text)
    rating = Column(Float)
    review_count = Column(Integer)
    category = Column(Text)
    all_categories = Column(Text)   # JSON array
    latitude = Column(Float)
    longitude = Column(Float)
    google_maps_url = Column(Text)
    hours = Column(Text)            # JSON object
    attributes = Column(Text)       # JSON object
    images = Column(Text)           # JSON object
    facebook = Column(Text)
    instagram = Column(Text)
    twitter = Column(Text)
    linkedin = Column(Text)
    youtube = Column(Text)
    tiktok = Column(Text)
    source_query = Column(Text, index=True)
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
