import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from github import Github
from github.Repository import Repository

from signals import (
    CodeActivitySignal,
    CollaborationSignal,
    CommitRecord,
    ProviderOutput,
    ReliabilitySignal,
    RevertedCommit,
)

BUG_LABELS = {"bug", "fix", "hotfix", "bugfix"}
FEATURE_LABELS = {"feature", "enhancement", "feat"}
TEST_PATTERNS = ("test_", "_test.", ".test.", "/test/", "/tests/", "spec/", "_spec.")
DOC_PATTERNS = ("docs/", "doc/", "README", ".md", "CHANGELOG", "wiki/")


class GitHubProvider:
    name = "github"

    def __init__(self, token: str, repos: list[str]) -> None:
        self._gh = Github(token)
        self._repos = repos

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        raw_commits: list[_RawCommit] = []
        raw_prs: list[_RawPR] = []
        raw_reviews: list[_RawReview] = []

        for repo_name in self._repos:
            repo = self._gh.get_repo(repo_name)
            _fetch_commits(repo, since, until, raw_commits)
            _fetch_pull_requests(repo, since, until, raw_prs, raw_reviews)

        return ProviderOutput(
            code_activity=_build_code_activity(raw_commits, raw_prs),
            collaboration=_build_collaboration(raw_reviews, raw_prs),
            reliability=_build_reliability(raw_commits),
        )


# ── internal raw types ────────────────────────────────────────────────────────

@dataclass
class _RawCommit:
    sha: str
    author_email: str
    author_name: str
    timestamp: datetime
    message: str
    files: list[str]
    is_revert: bool
    reverts_sha: str | None


@dataclass
class _RawPR:
    number: int
    author_email: str
    author_name: str
    merged_at: datetime
    labels: list[str]
    files: list[str]


@dataclass
class _RawReview:
    pr_number: int
    reviewer_email: str
    reviewer_name: str
    pr_author_email: str
    state: str


# ── fetchers ──────────────────────────────────────────────────────────────────

def _fetch_commits(repo: Repository, since: datetime, until: datetime, out: list[_RawCommit]) -> None:
    for c in repo.get_commits(since=since, until=until):
        author_email = ""
        author_name = ""
        if c.commit.author:
            author_email = c.commit.author.email or ""
            author_name = c.commit.author.name or ""

        message = c.commit.message or ""
        is_revert = message.lower().startswith("revert")
        reverts_sha = _parse_reverted_sha(message) if is_revert else None
        files = [f.filename for f in c.files] if c.files else []

        out.append(_RawCommit(
            sha=c.sha,
            author_email=author_email,
            author_name=author_name,
            timestamp=c.commit.author.date.replace(tzinfo=timezone.utc) if c.commit.author else since,
            message=message,
            files=files,
            is_revert=is_revert,
            reverts_sha=reverts_sha,
        ))


def _fetch_pull_requests(
    repo: Repository,
    since: datetime,
    until: datetime,
    prs: list[_RawPR],
    reviews: list[_RawReview],
) -> None:
    for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
        if pr.merged_at is None:
            continue
        merged = pr.merged_at.replace(tzinfo=timezone.utc)
        if merged < since:
            break
        if merged > until:
            continue

        author_email = pr.user.email or pr.user.login if pr.user else ""
        author_name = pr.user.name or pr.user.login if pr.user else ""
        labels = [label.name for label in pr.labels]
        files = [f.filename for f in pr.get_files()]

        prs.append(_RawPR(
            number=pr.number,
            author_email=author_email,
            author_name=author_name,
            merged_at=merged,
            labels=labels,
            files=files,
        ))

        for review in pr.get_reviews():
            reviewer = review.user
            if reviewer is None or reviewer.login == (pr.user.login if pr.user else ""):
                continue
            reviews.append(_RawReview(
                pr_number=pr.number,
                reviewer_email=reviewer.email or reviewer.login,
                reviewer_name=reviewer.name or reviewer.login,
                pr_author_email=author_email,
                state=review.state,
            ))


# ── signal builders ───────────────────────────────────────────────────────────

def _build_code_activity(raw_commits: list[_RawCommit], raw_prs: list[_RawPR]) -> list[CodeActivitySignal]:
    by_author: dict[str, dict] = defaultdict(lambda: {
        "name": "", "commits": [], "prs": 0, "bugs": 0, "features": 0, "tests": 0,
    })

    for c in raw_commits:
        if not c.author_email:
            continue
        a = by_author[c.author_email]
        a["name"] = c.author_name
        a["commits"].append(CommitRecord(sha=c.sha, author_email=c.author_email, author_name=c.author_name, files=c.files))

    for pr in raw_prs:
        if not pr.author_email:
            continue
        a = by_author[pr.author_email]
        a["name"] = a["name"] or pr.author_name
        a["prs"] += 1
        label_set = {l.lower() for l in pr.labels}
        if label_set & BUG_LABELS:
            a["bugs"] += 1
        if label_set & FEATURE_LABELS:
            a["features"] += 1
        if any(_is_test_file(f) for f in pr.files):
            a["tests"] += 1

    return [
        CodeActivitySignal(
            author_email=email,
            author_name=d["name"],
            commit_count=len(d["commits"]),
            prs_merged=d["prs"],
            bug_fix_prs=d["bugs"],
            feature_prs=d["features"],
            test_prs=d["tests"],
            commits=d["commits"],
        )
        for email, d in by_author.items()
    ]


def _build_collaboration(raw_reviews: list[_RawReview], raw_prs: list[_RawPR]) -> list[CollaborationSignal]:
    by_author: dict[str, dict] = defaultdict(lambda: {
        "name": "", "reviewed": 0, "approved": 0, "doc_prs": 0,
    })

    for r in raw_reviews:
        if r.reviewer_email == r.pr_author_email:
            continue
        a = by_author[r.reviewer_email]
        a["name"] = r.reviewer_name
        a["reviewed"] += 1
        if r.state == "APPROVED":
            a["approved"] += 1

    for pr in raw_prs:
        if not pr.author_email:
            continue
        if any(_is_doc_file(f) for f in pr.files):
            by_author[pr.author_email]["doc_prs"] += 1
            by_author[pr.author_email]["name"] = by_author[pr.author_email]["name"] or pr.author_name

    return [
        CollaborationSignal(
            author_email=email,
            author_name=d["name"],
            prs_reviewed=d["reviewed"],
            approvals_given=d["approved"],
            documentation_prs=d["doc_prs"],
        )
        for email, d in by_author.items()
        if d["reviewed"] > 0 or d["doc_prs"] > 0
    ]


def _build_reliability(raw_commits: list[_RawCommit]) -> list[ReliabilitySignal]:
    by_sha: dict[str, _RawCommit] = {c.sha: c for c in raw_commits}
    by_short: dict[str, _RawCommit] = {c.sha[:7]: c for c in raw_commits}

    by_author: dict[str, dict] = defaultdict(lambda: {"name": "", "reverts": []})

    for commit in raw_commits:
        if not commit.is_revert or commit.reverts_sha is None:
            continue
        original = by_sha.get(commit.reverts_sha) or by_short.get(commit.reverts_sha[:7])
        if original is None:
            continue
        a = by_author[original.author_email]
        a["name"] = original.author_name
        a["reverts"].append(RevertedCommit(
            sha=original.sha,
            message=original.message.splitlines()[0],
            timestamp=original.timestamp,
        ))

    return [
        ReliabilitySignal(
            author_email=email,
            author_name=d["name"],
            reverted_commits=d["reverts"],
        )
        for email, d in by_author.items()
    ]


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_reverted_sha(message: str) -> str | None:
    match = re.search(r"This reverts commit ([0-9a-f]{7,40})", message)
    return match.group(1) if match else None


def _is_test_file(path: str) -> bool:
    return any(p in path for p in TEST_PATTERNS)


def _is_doc_file(path: str) -> bool:
    return any(p in path for p in DOC_PATTERNS)
