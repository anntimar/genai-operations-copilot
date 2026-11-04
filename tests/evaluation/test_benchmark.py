from app.evaluation.run import evaluate
from scripts.seed import seed


def test_mock_benchmark(client):
    seed(client)
    summary = evaluate(client)["summary"]
    assert summary["cases"] >= 30
    assert summary["hit_rate_at_5"] >= 0.9
    assert summary["expected_answer_rate"] >= 0.9
    assert summary["missing_passed"]
    assert summary["injection_passed"]
