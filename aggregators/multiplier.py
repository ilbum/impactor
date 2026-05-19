from dataclasses import dataclass

from collectors.github import GitHubData

DOC_PATTERNS = ("docs/", "doc/", "README", ".md", "CHANGELOG", "wiki/")


@dataclass
class MultiplierStats:
    prs_reviewed: int = 0
    review_comments: int = 0
    approvals_given: int = 0
    documentation_prs: int = 0


def aggregate(github_data: GitHubData, author_email: str) -> MultiplierStats:
    stats = MultiplierStats()

    for review in github_data.reviews:
        if review.reviewer_email != author_email:
            continue
        if review.pr_author_email == author_email:
            continue  # self-review, skip

        stats.prs_reviewed += 1
        if review.state == "APPROVED":
            stats.approvals_given += 1

    # Count distinct PRs reviewed for comment count proxy
    reviewed_prs = {
        r.pr_number
        for r in github_data.reviews
        if r.reviewer_email == author_email and r.pr_author_email != author_email
    }
    # Use review count as a proxy for comments (one entry per review submission)
    stats.review_comments = len([
        r for r in github_data.reviews
        if r.reviewer_email == author_email and r.pr_author_email != author_email
    ])

    for pr in github_data.pull_requests:
        if pr.author_email != author_email:
            continue
        if any(_is_doc_file(f) for f in pr.files):
            stats.documentation_prs += 1

    return stats


def _is_doc_file(path: str) -> bool:
    return any(pattern in path for pattern in DOC_PATTERNS)
