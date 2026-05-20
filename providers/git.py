import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from signals import (
    CodeActivitySignal,
    CommitRecord,
    ProviderOutput,
    ReliabilitySignal,
    RevertedCommit,
)

BUG_KEYWORDS = frozenset({"fix", "bug", "hotfix", "bugfix"})
FEATURE_KEYWORDS = frozenset({"feat", "feature"})
TEST_PATTERNS = ("test_", "_test.", ".test.", "/test/", "/tests/", "spec/", "_spec.")

_REVERT_SHA_RE = re.compile(r"this reverts commit ([0-9a-f]{7,40})", re.IGNORECASE)
_MERGE_RE = re.compile(r"^merge (pull request|branch)\b", re.IGNORECASE)


class GitProvider:
    name = "git"

    def __init__(self, paths: list[str]) -> None:
        self._paths = paths

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        raw: list[_RawCommit] = []
        for path in self._paths:
            raw.extend(_fetch_commits(path, since, until))
        return ProviderOutput(
            code_activity=_build_code_activity(raw),
            reliability=_build_reliability(raw),
        )


# ── internal raw type ─────────────────────────────────────────────────────────

@dataclass
class _RawCommit:
    sha: str
    author_email: str
    author_name: str
    timestamp: datetime
    subject: str
    files: list[str]
    is_merge: bool
    is_revert: bool
    reverts_sha: str | None


# ── git log parsing ───────────────────────────────────────────────────────────

def _fetch_commits(path: str, since: datetime, until: datetime) -> list[_RawCommit]:
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
    until_iso = until.strftime("%Y-%m-%dT%H:%M:%S")

    # Pass 1: per-commit metadata including body (for revert SHA extraction)
    meta_raw = _git(
        path, "log",
        "--format=%H%x1f%ae%x1f%an%x1f%at%x1f%s%x1f%b%x1e",
        f"--since={since_iso}", f"--until={until_iso}",
    )

    # Pass 2: sha + changed file names
    files_raw = _git(
        path, "log",
        "--format=%H%x1e", "--name-only",
        f"--since={since_iso}", f"--until={until_iso}",
    )

    # Build sha → files mapping
    files_by_sha: dict[str, list[str]] = {}
    for chunk in files_raw.split("\x1e"):
        lines = [l.strip() for l in chunk.strip().splitlines() if l.strip()]
        if lines:
            files_by_sha[lines[0]] = lines[1:]

    # Parse metadata records
    commits: list[_RawCommit] = []
    for record in meta_raw.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f", 5)
        if len(parts) < 5:
            continue
        sha, email, name, ts_str, subject = parts[0], parts[1], parts[2], parts[3], parts[4]
        body = parts[5] if len(parts) > 5 else ""

        try:
            timestamp = datetime.fromtimestamp(int(ts_str.strip()), tz=timezone.utc)
        except ValueError:
            continue

        is_revert = subject.lower().startswith("revert")
        reverts_sha: str | None = None
        if is_revert:
            m = _REVERT_SHA_RE.search(subject + " " + body)
            reverts_sha = m.group(1) if m else None

        commits.append(_RawCommit(
            sha=sha.strip(),
            author_email=email.strip(),
            author_name=name.strip(),
            timestamp=timestamp,
            subject=subject.strip(),
            files=files_by_sha.get(sha.strip(), []),
            is_merge=bool(_MERGE_RE.match(subject)),
            is_revert=is_revert,
            reverts_sha=reverts_sha,
        ))

    return commits


def _git(path: str, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {path!r}: {result.stderr.strip()}")
    return result.stdout


# ── signal builders ───────────────────────────────────────────────────────────

def _build_code_activity(raw: list[_RawCommit]) -> list[CodeActivitySignal]:
    by_author: dict[str, dict] = defaultdict(lambda: {
        "name": "", "commits": [], "prs": 0, "bugs": 0, "features": 0, "tests": 0,
    })

    for c in raw:
        if not c.author_email:
            continue
        a = by_author[c.author_email]
        a["name"] = c.author_name

        if c.is_merge:
            a["prs"] += 1
        else:
            a["commits"].append(CommitRecord(
                sha=c.sha, author_email=c.author_email,
                author_name=c.author_name, files=c.files,
            ))

        subj = c.subject.lower()
        if any(kw in subj for kw in BUG_KEYWORDS):
            a["bugs"] += 1
        elif any(kw in subj for kw in FEATURE_KEYWORDS):
            a["features"] += 1

        if any(_is_test_file(f) for f in c.files):
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


def _build_reliability(raw: list[_RawCommit]) -> list[ReliabilitySignal]:
    by_sha: dict[str, _RawCommit] = {c.sha: c for c in raw}
    by_short: dict[str, _RawCommit] = {c.sha[:7]: c for c in raw}

    by_author: dict[str, dict] = defaultdict(lambda: {"name": "", "reverts": []})

    for commit in raw:
        if not commit.is_revert or commit.reverts_sha is None:
            continue
        original = by_sha.get(commit.reverts_sha) or by_short.get(commit.reverts_sha[:7])
        if original is None:
            continue
        a = by_author[original.author_email]
        a["name"] = original.author_name
        a["reverts"].append(RevertedCommit(
            sha=original.sha,
            message=original.subject,
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


def _is_test_file(path: str) -> bool:
    return any(p in path for p in TEST_PATTERNS)
