#!/usr/bin/env python3
"""Serve a Penta visual audit with durable, candidate-bound review state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MARKER = ".penta-visual-audit-owned"
SCHEMA = "penta-dragon-dx-visual-audit-v1"
EXPORT_SCHEMA = "penta-visual-human-review-v1"
STATE_SCHEMA = "penta-visual-human-review-state-v1"
VERDICTS = {"unreviewed", "good", "issue", "recapture", "intentional"}
MAX_REQUEST_BYTES = 2 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(value: object) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def evidence_digest(item: dict[str, Any]) -> str:
    """Mirror the builder's final per-item visual/semantic fingerprint."""
    payload = {
        "status": item.get("status"),
        "subtitle": item.get("subtitle", ""),
        "images": [
            {
                key: image.get(key)
                for key in ("sha256", "caption", "side", "pair_key")
                if image.get(key) is not None
            }
            for image in item.get("images", [])
        ],
        "palettes": item.get("palettes", []),
        "machine_notes": item.get("machine_notes", []),
    }
    import hashlib
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def allowed_state_path(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    if not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError("review state must live under repo tmp/ or /mnt/data/tmp/")
    return resolved


class ReviewStore:
    """Thread-safe, atomic review checkpoint with one rolling backup."""

    def __init__(
        self, site: Path, state_path: Path, *, adopt_legacy_evidence: bool = False,
    ):
        manifest = json.loads((site / "manifest.json").read_text())
        self.candidate = str(manifest.get("candidate", {}).get("sha256", ""))
        if len(self.candidate) != 64:
            raise ValueError("site manifest has no valid candidate SHA-256")
        self.evidence = {
            str(item["audit_id"]): (
                str(item.get("evidence_sha256", "")) or evidence_digest(item)
            )
            for category in manifest.get("categories", [])
            for item in category.get("items", [])
        }
        self.audit_ids = set(self.evidence)
        if not self.audit_ids:
            raise ValueError("site manifest has no audit IDs")
        if any(len(value) != 64 for value in self.evidence.values()):
            raise ValueError("site manifest has missing/invalid item evidence hashes")
        self.evidence_manifest = str(manifest.get("audit_evidence_sha256", ""))
        if len(self.evidence_manifest) != 64:
            import hashlib
            self.evidence_manifest = hashlib.sha256(
                json.dumps(
                    self.evidence, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        self.adopt_legacy_evidence = adopt_legacy_evidence
        self.path = allowed_state_path(state_path)
        self.backup_path = self.path.with_name(self.path.name + ".bak")
        self.lock = threading.Lock()
        self.state = self._empty()
        if self.path.is_file():
            try:
                raw_state = json.loads(self.path.read_text())
                self.state = self._normalize(
                    raw_state, adopt_legacy_evidence=adopt_legacy_evidence,
                )
            except (OSError, ValueError, json.JSONDecodeError):
                if not self.backup_path.is_file():
                    raise
                self.state = self._normalize(
                    json.loads(self.backup_path.read_text()),
                    adopt_legacy_evidence=adopt_legacy_evidence,
                )
                self._write(make_backup=False)
            else:
                if self.state != raw_state:
                    self._write()

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": STATE_SCHEMA,
            "candidate_sha256": self.candidate,
            "audit_evidence_sha256": self.evidence_manifest,
            "updated_at": "",
            "revision": 0,
            "cursor": None,
            "reviews": {},
        }

    def _normalize(
        self, payload: object, *, adopt_legacy_evidence: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("review payload must be a JSON object")
        schema = payload.get("schema")
        if schema not in (STATE_SCHEMA, EXPORT_SCHEMA):
            raise ValueError(f"unsupported review schema: {schema!r}")
        if payload.get("candidate_sha256") != self.candidate:
            raise ValueError("review belongs to a different candidate ROM")
        raw_reviews = payload.get("reviews")
        if not isinstance(raw_reviews, dict):
            raise ValueError("review payload has no review map")
        reviews: dict[str, dict[str, Any]] = {}
        for audit_id, row in raw_reviews.items():
            if audit_id not in self.audit_ids or not isinstance(row, dict):
                continue
            verdict = str(row.get("verdict", "unreviewed"))
            if verdict not in VERDICTS:
                verdict = "unreviewed"
            expected_evidence = self.evidence[audit_id]
            supplied_evidence = str(row.get("evidence_sha256", ""))
            normalized: dict[str, Any] = {
                "verdict": verdict,
                "notes": str(row.get("notes", ""))[:8000],
                "updated_at": str(row.get("updated_at", "")),
                "evidence_sha256": expected_evidence,
            }
            stale = (
                verdict != "unreviewed"
                and (
                    (not supplied_evidence and not adopt_legacy_evidence)
                    or (
                        bool(supplied_evidence)
                        and supplied_evidence != expected_evidence
                    )
                )
            )
            if stale:
                normalized.update({
                    "verdict": "unreviewed",
                    "needs_revalidation": True,
                    "previous_verdict": verdict,
                    "previous_evidence_sha256": supplied_evidence or "legacy-unbound",
                })
            elif row.get("needs_revalidation") and verdict == "unreviewed":
                normalized.update({
                    "needs_revalidation": True,
                    "previous_verdict": str(
                        row.get("previous_verdict", "unreviewed")
                    ),
                    "previous_evidence_sha256": str(
                        row.get("previous_evidence_sha256", "")
                    ),
                })
            reviews[audit_id] = normalized
        cursor = payload.get("cursor")
        if cursor not in self.audit_ids:
            cursor = None
        return {
            "schema": STATE_SCHEMA,
            "candidate_sha256": self.candidate,
            "audit_evidence_sha256": self.evidence_manifest,
            "updated_at": str(payload.get("updated_at", payload.get("exported_at", ""))),
            "revision": max(0, int(payload.get("revision", 0))),
            "cursor": cursor,
            "reviews": reviews,
        }

    def _write(self, *, make_backup: bool = True) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if make_backup and self.path.is_file():
            shutil.copyfile(self.path, self.backup_path)
        temporary = self.path.with_name("." + self.path.name + ".new")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, self.path)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def merge(self, payload: object) -> dict[str, Any]:
        incoming = self._normalize(payload)
        with self.lock:
            merged = dict(self.state["reviews"])
            for audit_id, row in incoming["reviews"].items():
                current = merged.get(audit_id)
                if current is None or timestamp(row["updated_at"]) >= timestamp(current["updated_at"]):
                    merged[audit_id] = row
            self.state["reviews"] = merged
            if incoming["cursor"] in self.audit_ids:
                self.state["cursor"] = incoming["cursor"]
            self.state["updated_at"] = utc_now()
            self.state["revision"] = int(self.state["revision"]) + 1
            self._write()
            return json.loads(json.dumps(self.state))

    def import_file(self, path: Path) -> dict[str, Any]:
        return self.merge(json.loads(path.read_text()))


class AuditHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, review_store: ReviewStore, **kwargs: Any):
        self.review_store = review_store
        super().__init__(*args, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, status: int, payload: object) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.split("?", 1)[0] == "/api/review":
            self._json(200, self.review_store.snapshot())
            return
        super().do_GET()

    def _save_review(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("review request has an invalid size")
            payload = json.loads(self.rfile.read(length))
            self._json(200, self.review_store.merge(payload))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._json(400, {"status": "error", "message": str(exc)})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.split("?", 1)[0] == "/api/review":
            self._save_review()
            return
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
        self.do_POST()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "site",
        nargs="?",
        type=Path,
        default=ROOT / "tmp" / "visual-audit-site",
    )
    parser.add_argument(
        "--adopt-legacy-evidence",
        action="store_true",
        help=(
            "one-time migration: bind review rows lacking evidence hashes to "
            "this exact site; never use after replacing site evidence"
        ),
    )
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="normalize/write the checkpoint, print its status, and exit",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--review-state",
        type=Path,
        help="durable JSON checkpoint (default: candidate-bound repo tmp path)",
    )
    parser.add_argument(
        "--import-review",
        type=Path,
        action="append",
        default=[],
        help="merge a candidate-matching exported review before serving",
    )
    args = parser.parse_args()
    site = args.site.resolve()
    if not (site / "index.html").is_file():
        parser.error(f"site has no index.html: {site}")
    marker = site / MARKER
    if not marker.is_file() or marker.read_text().strip() != SCHEMA:
        parser.error(f"site is not an owned {SCHEMA} build: {site}")
    manifest = json.loads((site / "manifest.json").read_text())
    candidate = str(manifest.get("candidate", {}).get("sha256", ""))
    state_path = args.review_state or (
        ROOT / "tmp" / "visual-audit-review-state" / f"{candidate}.json"
    )
    try:
        store = ReviewStore(
            site, state_path,
            adopt_legacy_evidence=args.adopt_legacy_evidence,
        )
        for review in args.import_review:
            store.import_file(review.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.migrate_only:
        snapshot = store.snapshot()
        print(
            f"Migrated review state: {store.path} "
            f"({len(snapshot['reviews'])} saved items)"
        )
        return 0
    handler = partial(AuditHandler, directory=str(site), review_store=store)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    snapshot = store.snapshot()
    print(f"Visual audit: http://{args.host}:{server.server_port}/", flush=True)
    print(
        f"Review state: {store.path} ({len(snapshot['reviews'])} saved items)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
