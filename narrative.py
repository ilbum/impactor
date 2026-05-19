import json

import anthropic

from signals import CodeActivitySignal, CollaborationSignal, ReliabilitySignal

SYSTEM_PROMPT = """\
You are a thoughtful engineering manager writing a concise performance snapshot for a contributor.
You will receive structured signal data about their contributions during a review period.
Write in a direct, specific, and positive tone that reflects their actual impact.
Do not invent specifics not present in the data. Do not use filler phrases like "hard worker" or "team player".
"""


def generate(
    author_name: str,
    period_from: str,
    period_to: str,
    code: CodeActivitySignal | None,
    collab: CollaborationSignal | None,
    reliability: ReliabilitySignal | None,
    attribution: dict[str, float],
    api_key: str,
    model: str,
) -> tuple[str, list[str]]:
    signals: dict = {"contributor": author_name, "period": f"{period_from} to {period_to}"}

    if attribution:
        signals["attribution"] = {
            metric: f"{round(credit * 100)}% credited share"
            for metric, credit in attribution.items()
        }

    if code:
        signals["code_authorship"] = {
            "commits": code.commit_count,
            "prs_merged": code.prs_merged,
            "bug_fix_prs": code.bug_fix_prs,
            "feature_prs": code.feature_prs,
            "prs_touching_tests": code.test_prs,
        }

    if collab:
        signals["multiplier_effect"] = {
            "prs_reviewed": collab.prs_reviewed,
            "approvals_given": collab.approvals_given,
            "documentation_prs": collab.documentation_prs,
        }

    if reliability:
        signals["reliability_context"] = {
            "reverted_commits": len(reliability.reverted_commits),
            "incidents": len(reliability.incidents),
        }

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"Signal data:\n{json.dumps(signals, indent=2)}\n\n"
                    "Respond with JSON only, no markdown fences:\n"
                    '{"summary": "<2-3 sentence paragraph>", "highlights": ["<bullet 1>", "<bullet 2>", "<bullet 3>"]}'
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    parsed = json.loads(raw)
    return parsed["summary"], parsed["highlights"]
