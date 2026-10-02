#!/usr/bin/env python3
"""Deterministic contract for disk review checkpoints and keyboard review UI."""

from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from serve_visual_audit import (  # noqa: E402
    AuditHandler,
    EXPORT_SCHEMA,
    MARKER,
    ReviewStore,
    SCHEMA,
    STATE_SCHEMA,
)


def request_json(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(
        url,
        data=body,
        method="GET" if body is None else "PUT",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read())


def main() -> int:
    scratch_root = ROOT / "tmp"
    scratch_root.mkdir(exist_ok=True)
    candidate = "a" * 64
    with TemporaryDirectory(prefix="review-workflow-", dir=scratch_root) as raw:
        work = Path(raw)
        site = work / "site"
        site.mkdir()
        (site / MARKER).write_text(SCHEMA + "\n")
        (site / "index.html").write_text("<!doctype html><title>fixture</title>")
        (site / "manifest.json").write_text(json.dumps({
            "candidate": {"sha256": candidate},
            "audit_evidence_sha256": "d" * 64,
            "categories": [{"items": [
                {"audit_id": "stages:one", "evidence_sha256": "b" * 64},
                {"audit_id": "bosses:two", "evidence_sha256": "c" * 64},
            ]}],
        }))
        state_path = work / "state" / "review.json"
        store = ReviewStore(site, state_path)
        handler = partial(AuditHandler, directory=str(site), review_store=store)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/api/review"
        try:
            empty = request_json(endpoint)
            assert empty["schema"] == STATE_SCHEMA
            assert empty["reviews"] == {}

            first = request_json(endpoint, {
                "schema": EXPORT_SCHEMA,
                "candidate_sha256": candidate,
                "exported_at": "2026-08-22T00:00:00Z",
                "reviews": {
                    "stages:one": {
                        "verdict": "good",
                        "notes": "first durable verdict",
                        "updated_at": "2026-08-22T00:00:00Z",
                        "evidence_sha256": "b" * 64,
                    }
                },
            })
            assert first["reviews"]["stages:one"]["verdict"] == "good"
            assert state_path.is_file()

            second = request_json(endpoint, {
                "schema": STATE_SCHEMA,
                "candidate_sha256": candidate,
                "revision": first["revision"],
                "cursor": "bosses:two",
                "reviews": {
                    "stages:one": {
                        "verdict": "issue",
                        "notes": "stale tab must not win",
                        "updated_at": "2026-08-21T00:00:00Z",
                        "evidence_sha256": "b" * 64,
                    },
                    "bosses:two": {
                        "verdict": "recapture",
                        "notes": "second durable verdict",
                        "updated_at": "2026-08-22T00:01:00Z",
                        "evidence_sha256": "c" * 64,
                    },
                },
            })
            assert second["cursor"] == "bosses:two"
            assert second["reviews"]["stages:one"]["verdict"] == "good"
            assert second["reviews"]["bosses:two"]["verdict"] == "recapture"
            assert store.backup_path.is_file()
            assert request_json(endpoint)["reviews"] == second["reviews"]

            stale = request_json(endpoint, {
                "schema": STATE_SCHEMA,
                "candidate_sha256": candidate,
                "reviews": {
                    "stages:one": {
                        "verdict": "issue",
                        "notes": "preserve me across changed frames",
                        "updated_at": "2026-08-22T00:02:00Z",
                        "evidence_sha256": "e" * 64,
                    }
                },
            })
            assert stale["reviews"]["stages:one"]["verdict"] == "unreviewed"
            assert stale["reviews"]["stages:one"]["previous_verdict"] == "issue"
            assert stale["reviews"]["stages:one"]["needs_revalidation"] is True
            assert stale["reviews"]["stages:one"]["notes"] == "preserve me across changed frames"

            try:
                request_json(endpoint, {
                    "schema": STATE_SCHEMA,
                    "candidate_sha256": "b" * 64,
                    "reviews": {},
                })
                raise AssertionError("candidate-mismatched review was accepted")
            except HTTPError as exc:
                assert exc.code == 400
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        # Corrupting the primary fixture proves a fresh server restores the
        # rolling backup rather than silently starting an empty review.
        state_path.write_text("{broken")
        recovered = ReviewStore(site, state_path).snapshot()
        assert recovered["reviews"]["stages:one"]["verdict"] == "good"

    source = (ROOT / "scripts/diagnostics/visual_audit_assets/site.js").read_text()
    page_builder = (ROOT / "scripts/diagnostics/build_visual_audit.py").read_text()
    for token in (
        'g: () => mark("good", "next")',
        'i: () => mark("issue", "notes")',
        'r: () => mark("recapture", "next")',
        'j: () => move(1)',
        'k: () => move(-1)',
        'control.addEventListener("change", () => mouseVerdict(control.dataset.id, control.value))',
        'if (verdict === "issue") focusNotes(id)',
        'else if (verdict !== "unreviewed") move(1)',
        'control.addEventListener("click", () => advanceFrom(control.dataset.id))',
        'event.key === "Enter" && event.ctrlKey',
        '["issue","I · Visual issue"]',
        'fetch("/api/review"',
        'navigator.sendBeacon?.("/api/review"',
        'function asArray(value) { return Array.isArray(value) ? value : []; }',
        'const requestedPreset = queryParameters.get("preset") || ""',
        'const reviewIds = activePreset',
        'compactImages(item.images, item)',
        'activate(target, {scroll: false, checkpoint: false})',
        'await loadServerState();',
    ):
        assert token in source, f"keyboard/durable UI token missing: {token}"
    assert source.index('activate(target, {scroll: false, checkpoint: false})') < source.index('await loadServerState();')
    for token in ("queue-resume", "save-state", "Keyboard review", "Ctrl+Enter", "preset-banner"):
        assert token in page_builder, f"queue HTML token missing: {token}"

    print(
        "[visual-audit-review] PASS atomic disk + backup recovery + stale-tab "
        "merge + candidate binding + keyboard queue contract"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
