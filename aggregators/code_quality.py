from dataclasses import dataclass

from collectors.github import GitHubData

BUG_LABELS = {"bug", "fix", "hotfix", "bugfix"}
FEATURE_LABELS = {"feature", "enhancement", "feat"}
TEST_PATTERNS = ("test_", "_test.", ".test.", "/test/", "/tests/", "spec/", "_spec.")


@dataclass
class CodeQualityStats:
    commit_count: int = 0
    prs_merged: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    bug_fix_prs: int = 0
    feature_prs: int = 0
    test_prs: int = 0


def aggregate(github_data: GitHubData, author_email: str) -> CodeQualityStats:
    stats = CodeQualityStats()

    for commit in github_data.commits:
        if commit.author_email != author_email:
            continue
        stats.commit_count += 1

    for pr in github_data.pull_requests:
        if pr.author_email != author_email:
            continue
        stats.prs_merged += 1

        label_set = {l.lower() for l in pr.labels}
        if label_set & BUG_LABELS:
            stats.bug_fix_prs += 1
        if label_set & FEATURE_LABELS:
            stats.feature_prs += 1
        if any(_is_test_file(f) for f in pr.files):
            stats.test_prs += 1

    return stats


def _is_test_file(path: str) -> bool:
    return any(pattern in path for pattern in TEST_PATTERNS)
