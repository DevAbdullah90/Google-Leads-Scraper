"""
Pydantic models for all scraped business data.

Every field is Optional to ensure the scraper never crashes on missing data.
Use `extra="allow"` so unexpected fields are preserved rather than rejected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Address(BaseModel):
    model_config = ConfigDict(extra="allow")

    full_address: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="allow")

    latitude: Optional[float] = None
    longitude: Optional[float] = None


class Contact(BaseModel):
    model_config = ConfigDict(extra="allow")

    phone: Optional[str] = None
    phone_international: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None


class SocialMedia(BaseModel):
    model_config = ConfigDict(extra="allow")

    facebook: Optional[str] = None
    instagram: Optional[str] = None
    twitter: Optional[str] = None
    linkedin: Optional[str] = None
    youtube: Optional[str] = None
    tiktok: Optional[str] = None


class BusinessInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: Optional[str] = None
    all_categories: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    price_level: Optional[str] = None
    years_in_business: Optional[str] = None


class RatingDistribution(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    five_star: Optional[int] = Field(None, alias="5_star")
    four_star: Optional[int] = Field(None, alias="4_star")
    three_star: Optional[int] = Field(None, alias="3_star")
    two_star: Optional[int] = Field(None, alias="2_star")
    one_star: Optional[int] = Field(None, alias="1_star")


class Ratings(BaseModel):
    model_config = ConfigDict(extra="allow")

    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    rating_distribution: RatingDistribution = Field(default_factory=RatingDistribution)


class HoursByDay(BaseModel):
    model_config = ConfigDict(extra="allow")

    monday: Optional[str] = None
    tuesday: Optional[str] = None
    wednesday: Optional[str] = None
    thursday: Optional[str] = None
    friday: Optional[str] = None
    saturday: Optional[str] = None
    sunday: Optional[str] = None


class Hours(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_open_now: Optional[bool] = None
    current_status: Optional[str] = None
    hours_by_day: HoursByDay = Field(default_factory=HoursByDay)
    special_hours: List[str] = Field(default_factory=list)


class Attributes(BaseModel):
    model_config = ConfigDict(extra="allow")

    amenities: List[str] = Field(default_factory=list)
    accessibility: List[str] = Field(default_factory=list)
    payments_accepted: List[str] = Field(default_factory=list)
    service_options: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    crowd: List[str] = Field(default_factory=list)
    planning: List[str] = Field(default_factory=list)


class Images(BaseModel):
    model_config = ConfigDict(extra="allow")

    main_image_url: Optional[str] = None
    all_image_urls: List[str] = Field(default_factory=list)


class Review(BaseModel):
    model_config = ConfigDict(extra="allow")

    author: Optional[str] = None
    rating: Optional[float] = None
    text: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    scraped_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    data_freshness: Optional[str] = None
    verification_status: Optional[str] = None
    scraper_version: str = "1.0.0"
    query: Optional[str] = None
    has_warnings: bool = False
    warnings: List[str] = Field(default_factory=list)


class Business(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    business_name: str
    place_id: str = ""
    google_maps_url: str = ""
    address: Address = Field(default_factory=Address)
    coordinates: Coordinates = Field(default_factory=Coordinates)
    contact: Contact = Field(default_factory=Contact)
    social_media: SocialMedia = Field(default_factory=SocialMedia)
    business_info: BusinessInfo = Field(default_factory=BusinessInfo)
    ratings: Ratings = Field(default_factory=Ratings)
    hours: Hours = Field(default_factory=Hours)
    attributes: Attributes = Field(default_factory=Attributes)
    images: Images = Field(default_factory=Images)
    reviews_sample: List[Review] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict with snake_case keys."""
        return self.model_dump(mode="json")
