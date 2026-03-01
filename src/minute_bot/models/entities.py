"""Entity and relationship models for the memory graph."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Types of entities in the memory graph."""

    # People
    PERSON = "person"
    SPEAKER = "speaker"
    ASSIGNEE = "assignee"
    OWNER = "owner"
    REVIEWER = "reviewer"
    STAKEHOLDER = "stakeholder"
    # Artifacts
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    SPREADSHEET = "spreadsheet"
    TICKET = "ticket"
    CODE_REPO = "code_repository"
    URL = "url"
    DATASET = "dataset"
    TOOL = "tool"


class RelationType(str, Enum):
    """Types of relationships in the memory graph."""

    SAID_BY = "said_by"
    ASSIGNED_TO = "assigned_to"
    REFERS_TO = "refers_to"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    RESOLVES = "resolves"
    OVERRIDES = "overrides"
    FOLLOWS_FROM = "follows_from"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    HAPPENS_AT = "happens_at"
    PART_OF = "part_of"
    DISCUSSED_IN = "discussed_in"


class Entity(BaseModel):
    """An entity node in the memory graph."""

    entity_id: str
    entity_type: EntityType
    name: str
    attributes: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Relationship(BaseModel):
    """A relationship edge in the memory graph."""

    relationship_id: str
    relation_type: RelationType
    source_id: str
    target_id: str
    attributes: dict = {}
    timestamp: Optional[float] = None
