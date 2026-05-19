from dataclasses import dataclass, field
from datetime import datetime, timezone

from github import Github
from github.Repository import Repository


@dataclass
class Commit:
    sha: str
    author_email: str
    author_name: str
    timestamp: datetime
    message: str
    files: list[str]
    is_revert: bool = False
    reverts_sha: str | None = None


@dataclass
class PullRequest:
    number: int
    author_email: str
    author_name: str
    merged_at: datetime
    title: str
    labels: list[str]
    files: list[str]


@dataclass
class Review:
    pr_number: int
    reviewer_email: str
    reviewer_name: str
    pr_author_email: str
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED


@dataclass
class GitHubData:
    commits: list[Commit] = field(default_factory=list)
    pull_requests: list[PullRequest] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)


def collect(token: str, repos: list[str], since: datetime, until: datetime) -> GitHubData:
    gh = Github(token)
    data = GitHubData()

    for repo_name in repos:
        repo = gh.get_repo(repo_name)
        _collect_commits(repo, since, until, data)
        _collect_pull_requests(repo, since, until, data)

    return data


def _collect_commits(repo: Repository, since: datetime, until: datetime, data: GitHubData) -> None:
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

        data.commits.append(Commit(
            sha=c.sha,
            author_email=author_email,
            author_name=author_name,
            timestamp=c.commit.author.date.replace(tzinfo=timezone.utc) if c.commit.author else since,
            message=message,
            files=files,
            is_revert=is_revert,
            reverts_sha=reverts_sha,
        ))


def _collect_pull_requests(repo: Repository, since: datetime, until: datetime, data: GitHubData) -> None:
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

        data.pull_requests.append(PullRequest(
            number=pr.number,
            author_email=author_email,
            author_name=author_name,
            merged_at=merged,
            title=pr.title,
            labels=labels,
            files=files,
        ))

        for review in pr.get_reviews():
            reviewer = review.user
            if reviewer is None or reviewer.login == pr.user.login:
                continue
            data.reviews.append(Review(
                pr_number=pr.number,
                reviewer_email=reviewer.email or reviewer.login,
                reviewer_name=reviewer.name or reviewer.login,
                pr_author_email=author_email,
                state=review.state,
            ))


def _parse_reverted_sha(message: str) -> str | None:
    # GitHub revert messages include: 'This reverts commit <sha>.'
    import re
    match = re.search(r"This reverts commit ([0-9a-f]{7,40})", message)
    return match.group(1) if match else None
