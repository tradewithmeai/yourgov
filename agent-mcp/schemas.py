"""Shared data schemas for the MyGov agent API client."""
from dataclasses import dataclass, field


@dataclass
class HealthResult:
    status: str
    db: bool
    version: str


@dataclass
class DivisionSummary:
    division_id: int
    title: str
    date: str
    aye_count: int
    no_count: int


@dataclass
class VoterSample:
    member_id: int
    name: str
    party: str
    constituency: str
    vote: str


@dataclass
class DivisionDetail:
    division_id: int
    title: str
    date: str
    aye_count: int
    no_count: int
    sample_voters: list = field(default_factory=list)
    caveat: str = ""


@dataclass
class ExplainResult:
    explanation: str
    cached: bool
    caveat: str
    fallback: bool = False


@dataclass
class MpSummary:
    member_id: int
    name: str
    party: str
    constituency: str
    votes_recorded: int
    questions_recorded: int
    recent_votes: list = field(default_factory=list)
