from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OutcomeMetric:
    name: str
    source: str
    service_tag: str | None
    delta: float | None
    is_improvement: bool
    direction: str  # "up" | "down"


@dataclass
class CommitRecord:
    sha: str
    author_email: str
    author_name: str
    files: list[str]


@dataclass
class CodeActivitySignal:
    author_email: str
    author_name: str
    commit_count: int
    prs_merged: int
    bug_fix_prs: int
    feature_prs: int
    test_prs: int
    commits: list[CommitRecord]


@dataclass
class CollaborationSignal:
    author_email: str
    author_name: str
    prs_reviewed: int
    approvals_given: int
    documentation_prs: int


@dataclass
class RevertedCommit:
    sha: str
    message: str
    timestamp: datetime


@dataclass
class Incident:
    id: str
    title: str
    timestamp: datetime
    source: str


@dataclass
class ReliabilitySignal:
    author_email: str
    author_name: str
    reverted_commits: list[RevertedCommit] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)


@dataclass
class ProviderOutput:
    outcome_metrics: list[OutcomeMetric] = field(default_factory=list)
    code_activity: list[CodeActivitySignal] = field(default_factory=list)
    collaboration: list[CollaborationSignal] = field(default_factory=list)
    reliability: list[ReliabilitySignal] = field(default_factory=list)
