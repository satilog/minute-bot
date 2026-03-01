"""Meeting event models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events extracted from meetings."""

    ACTION_ITEM = "action_item"
    DECISION = "decision"
    TASK_ASSIGNMENT = "task_assignment"
    TASK_REASSIGNMENT = "task_reassignment"
    TASK_CANCELLATION = "task_cancellation"
    QUESTION = "question"
    ANSWER = "answer"
    PROPOSAL = "proposal"
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    ISSUE = "issue"
    RESOLUTION = "resolution"
    STATUS_UPDATE = "status_update"
    DEADLINE = "deadline"
    PRIORITY_CHANGE = "priority_change"
    DEPENDENCY = "dependency"
    FOLLOW_UP = "follow_up"
    REFERENCE = "reference"
    COMMAND = "command"


class MeetingEvent(BaseModel):
    """An event extracted from meeting conversation."""

    event_id: str
    session_id: str
    event_type: EventType
    description: str
    speaker_id: Optional[str] = None
    entities: list = []  # List of Entity objects
    timestamp: float  # Meeting time in seconds
    source_text: str
    confidence: float = 1.0
    requires_action: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
