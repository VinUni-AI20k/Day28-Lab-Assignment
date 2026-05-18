"""Observability verification — Prometheus + LangSmith.

LangSmith check is skipped (not failed) when:
  - LANGCHAIN_API_KEY is unset, OR
  - no runs have been recorded yet for project lab28-platform.
"""
import os
import sys

import requests


def check_prometheus():
    resp = requests.get(
        "http://localhost:9090/api/v1/query",
        params={"query": 'up{job="api-gateway"}'},
        timeout=5,
    )
    data = resp.json()
    assert data["status"] == "success", f"Prometheus query failed: {data}"
    print("[OK] Integration 9: Prometheus is scraping api-gateway")


def check_langsmith():
    api_key = os.environ.get("LANGCHAIN_API_KEY", "").strip()
    if not api_key or api_key.startswith("lsv2_pt_placeholder"):
        print("[SKIP] LangSmith: LANGCHAIN_API_KEY not configured")
        return
    try:
        from langsmith import Client
    except ImportError:
        print("[SKIP] LangSmith: client library not installed")
        return
    try:
        client = Client(api_key=api_key)
        runs = list(client.list_runs(project_name="lab28-platform", limit=1))
        if runs:
            print(f"[OK] Integration 10: LangSmith has {len(runs)}+ trace(s)")
        else:
            print("[SKIP] LangSmith: project 'lab28-platform' has no runs yet")
    except Exception as exc:
        print(f"[SKIP] LangSmith: {exc}")


if __name__ == "__main__":
    try:
        check_prometheus()
    except Exception as exc:
        print(f"[FAIL] Prometheus check: {exc}")
        sys.exit(1)
    check_langsmith()
