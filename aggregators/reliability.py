from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from collectors.github import Commit, GitHubData


@dataclass
class RevertedCommit:
    sha: str
    message: str
    timestamp: datetime


@dataclass
class ReliabilityStats:
    reverted_commits: list[RevertedCommit] = field(default_factory=list)


def aggregate(github_data: GitHubData, author_email: str) -> ReliabilityStats:
    stats = ReliabilityStats()

    # Build a SHA -> commit map for revert resolution
    commit_by_sha: dict[str, Commit] = {c.sha: c for c in github_data.commits}
    commit_by_short_sha: dict[str, Commit] = {c.sha[:7]: c for c in github_data.commits}

    for commit in github_data.commits:
        if not commit.is_revert or commit.reverts_sha is None:
            continue

        # Find the original commit
        original = (
            commit_by_sha.get(commit.reverts_sha)
            or commit_by_short_sha.get(commit.reverts_sha[:7])
        )
        if original is None:
            continue
        if original.author_email != author_email:
            continue

        stats.reverted_commits.append(RevertedCommit(
            sha=original.sha,
            message=original.message.splitlines()[0],
            timestamp=original.timestamp,
        ))

    return stats
