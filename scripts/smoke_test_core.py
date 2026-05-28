#!/usr/bin/env python3
"""
Smoke / tests profonds du cœur produit K-Voice.

Usage:
  cd k-voice-backend
  pip install pytest  # si besoin
  python -m pytest tests/ -v
  python scripts/smoke_test_core.py
  API_URL=http://localhost:8000 SMOKE_EMAIL=... SMOKE_PASSWORD=... python scripts/smoke_test_core.py --live
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_pytest() -> int:
    print("\n=== Tests unitaires (pytest) ===\n")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=ROOT,
    )
    return r.returncode


def live_api_checks(base_url: str, email: str, password: str) -> list[tuple[str, bool, str]]:
    import urllib.error
    import urllib.request

    results: list[tuple[str, bool, str]] = []

    def get(path: str) -> dict:
        req = urllib.request.Request(f"{base_url.rstrip('/')}{path}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def post_json(path: str, body: dict, token: str | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = {"detail": raw}
            return e.code, detail

    # Health
    try:
        h = get("/health")
        ok = h.get("status") == "ok"
        results.append(("GET /health", ok, str(h)))
    except Exception as e:
        results.append(("GET /health", False, str(e)))

    # Limits (retention)
    try:
        lim = get("/config/limits")
        ok = "max_upload_size_mb" in lim and "audio_retention_days" in lim
        results.append(("GET /config/limits", ok, json.dumps(lim, ensure_ascii=False)))
    except Exception as e:
        results.append(("GET /config/limits", False, str(e)))

    # Auth
    token = None
    try:
        code, data = post_json("/auth/login", {"email": email, "password": password})
        ok = code == 200 and bool(data.get("access_token"))
        token = data.get("access_token")
        results.append(("POST /auth/login", ok, f"status={code}"))
    except Exception as e:
        results.append(("POST /auth/login", False, str(e)))

    if token:
        try:
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/sermons",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            ok = isinstance(data, list)
            results.append(("GET /sermons (auth)", ok, f"count={len(data)}"))
        except Exception as e:
            results.append(("GET /sermons (auth)", False, str(e)))

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Appels HTTP vers API_URL")
    parser.add_argument("--skip-unit", action="store_true")
    args = parser.parse_args()

    exit_code = 0

    if not args.skip_unit:
        try:
            import pytest  # noqa: F401
        except ImportError:
            print("pytest non installé — pip install pytest")
            exit_code = 1
        else:
            exit_code = run_pytest()

    if args.live:
        base = os.environ.get("API_URL", "http://localhost:8000")
        email = os.environ.get("SMOKE_EMAIL", "admin@gmail.com")
        password = os.environ.get("SMOKE_PASSWORD", "admin")
        print(f"\n=== Tests live API ({base}) ===\n")
        for name, ok, detail in live_api_checks(base, email, password):
            mark = "OK" if ok else "FAIL"
            print(f"[{mark}] {name}")
            if not ok or os.environ.get("SMOKE_VERBOSE"):
                print(f"       {detail[:500]}")
            if not ok:
                exit_code = 1

    # Import sanity (modules cœur)
    print("\n=== Import modules cœur ===\n")
    sys.path.insert(0, str(ROOT))
    modules = [
        "app.services.nlp_service",
        "app.services.ai_service",
        "app.services.audio_retention",
        "app.routers.ai",
        "app.routers.sermons",
    ]
    for mod in modules:
        try:
            __import__(mod)
            print(f"[OK] import {mod}")
        except Exception as e:
            print(f"[FAIL] import {mod}: {e}")
            exit_code = 1

    print("\n=== Fin smoke test ===\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
