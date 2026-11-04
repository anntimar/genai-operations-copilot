import json
import os
from pathlib import Path
from statistics import mean, quantiles

import httpx


def evaluate(client):
    cases = json.loads(
        Path(__file__).with_name("cases.json").read_text(encoding="utf-8")
    )
    rows = []
    for case in cases:
        result = (
            client.post(
                "/chat/ask",
                json={
                    "question": case["question"],
                    "k": 5,
                    "category": case.get("category"),
                },
            )
            .raise_for_status()
            .json()
        )
        refs = set(case["refs"])
        retrieved = {item["name"] for item in result["retrieved"]}
        citations = result["citations"]
        supported = bool(citations) and all(
            item["quote"] in item["excerpt"] for item in citations
        )
        correct = supported and any(
            item["name"] in refs
            and case.get("expected", "").lower() in item["quote"].lower()
            for item in citations
        )
        abstained = result["status"] == "insufficient_evidence" and not citations
        rows.append(
            {
                "question": case["question"],
                "kind": case["kind"],
                "cited": bool(citations),
                "grounded": supported,
                "unsupported_answer": result["status"] == "answered" and not correct,
                "recall": len(refs & retrieved) / len(refs) if refs else None,
                "hit": bool(refs & retrieved),
                "correct": correct,
                "passed": correct
                if refs
                else abstained
                and (
                    case["kind"] != "injection" or "security.blocked" in result["trace"]
                ),
                "latency_ms": result["latency_ms"],
                **result["usage"],
            }
        )
    answerable = [row for row in rows if row["kind"] == "answer"]
    answered = [row for row in rows if row["cited"] or row["unsupported_answer"]]
    return {
        "summary": {
            "cases": len(rows),
            "answerable": len(answerable),
            "hit_rate_at_5": mean(row["hit"] for row in answerable),
            "recall_at_5": mean(row["recall"] for row in answerable),
            "citation_rate_answerable": mean(row["cited"] for row in answerable),
            "literal_grounding_rate_answered": mean(row["grounded"] for row in answered)
            if answered
            else None,
            "expected_answer_rate": mean(row["correct"] for row in answerable),
            "unsupported_answer_rate": mean(row["unsupported_answer"] for row in rows),
            "missing_passed": all(
                row["passed"] for row in rows if row["kind"] == "missing"
            ),
            "injection_passed": all(
                row["passed"] for row in rows if row["kind"] == "injection"
            ),
            "mean_latency_ms": round(mean(row["latency_ms"] for row in rows), 2),
            "p95_latency_ms": round(
                quantiles(
                    [row["latency_ms"] for row in rows], n=100, method="inclusive"
                )[94],
                2,
            ),
            "estimated_usd": sum(row["estimated_usd"] for row in rows),
        },
        "cases": rows,
    }


if __name__ == "__main__":
    with httpx.Client(
        base_url=os.getenv("API_URL", "http://localhost:8000"), timeout=45
    ) as client:
        print(json.dumps(evaluate(client), indent=2, ensure_ascii=True))
