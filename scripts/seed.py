from datetime import date
from pathlib import Path

import httpx


def seed(client):
    existing = {
        (item["category"], item["name"])
        for item in client.get("/documents").raise_for_status().json()
    }
    for path in sorted(Path("sample_documents").glob("*/*")):
        category = path.parent.name
        if (category, path.name) in existing:
            continue
        response = client.post(
            "/documents/upload",
            files={"file": (path.name, path.read_bytes())},
            data={"category": category, "effective_date": date(2025, 1, 1).isoformat()},
        )
        if path.name == "quarentena.txt" and response.status_code == 422:
            continue
        response.raise_for_status()
        print(response.json()["name"])


if __name__ == "__main__":
    import os

    with httpx.Client(
        base_url=os.getenv("API_URL", "http://localhost:8000"), timeout=45
    ) as client:
        seed(client)
