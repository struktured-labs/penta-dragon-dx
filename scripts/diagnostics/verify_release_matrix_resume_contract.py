#!/usr/bin/env python3
"""Prove that resuming an intact completed matrix cannot rewrite it.

The deterministic-suite receipt hashes the release-matrix manifest. A
historical completed ``--resume`` added a timestamp and invalidated that
receipt without changing any gate evidence. This control exercises the exact
predicate guarding the immutable completed-manifest path, with negative
controls for every identity and integrity field that matters.
"""

from __future__ import annotations

from copy import deepcopy
import json

from verify_release_candidate import Gate, complete_resume_is_immutable


GATES = [Gate("alpha", ("true",), 1), Gate("beta", ("true",), 1)]
SELECTED = {gate.name for gate in GATES}
SOURCE_HASH = "source-md5"
TESTED_HASH = "tested-md5"
SOURCE_FINGERPRINT = "suite-sha256"
SOURCE_INPUT_COUNT = 123


def completed_manifest() -> dict[str, object]:
    return {
        "status": "emulator-pass",
        "scope": "full",
        "selected_gates": ["alpha", "beta"],
        "failures": 0,
        "rom_md5": SOURCE_HASH,
        "source_rom_md5_after": SOURCE_HASH,
        "tested_rom_md5_after": TESTED_HASH,
        "rom_hashes_intact": True,
        "source_fingerprint": SOURCE_FINGERPRINT,
        "source_fingerprint_after": SOURCE_FINGERPRINT,
        "source_input_count": SOURCE_INPUT_COUNT,
        "source_inputs_intact": True,
        "results": [
            {"name": "alpha", "status": "passed", "returncode": 0},
            {"name": "beta", "status": "passed", "returncode": 0},
        ],
    }


def accepted(manifest: dict[str, object]) -> bool:
    return complete_resume_is_immutable(
        manifest,
        GATES,
        SELECTED,
        full_matrix=True,
        source_hash=SOURCE_HASH,
        tested_hash=TESTED_HASH,
        source_fingerprint=SOURCE_FINGERPRINT,
        source_input_count=SOURCE_INPUT_COUNT,
    )


def main() -> int:
    pristine = completed_manifest()
    encoded_before = json.dumps(pristine, sort_keys=True)
    controls: dict[str, bool] = {
        "intact_complete_manifest_accepted": accepted(pristine),
        "predicate_is_non_mutating": (
            json.dumps(pristine, sort_keys=True) == encoded_before
        ),
    }

    mutations = {
        "running_status_rejected": ("status", "running"),
        "selected_scope_rejected": ("scope", "selected"),
        "failure_count_rejected": ("failures", 1),
        "source_rom_change_rejected": ("source_rom_md5_after", "changed"),
        "tested_rom_change_rejected": ("tested_rom_md5_after", "changed"),
        "rom_integrity_false_rejected": ("rom_hashes_intact", False),
        "source_change_rejected": ("source_fingerprint_after", "changed"),
        "source_inventory_change_rejected": ("source_input_count", 124),
        "source_integrity_false_rejected": ("source_inputs_intact", False),
    }
    for name, (field, value) in mutations.items():
        candidate = deepcopy(pristine)
        candidate[field] = value
        controls[name] = not accepted(candidate)

    omitted = deepcopy(pristine)
    omitted["results"] = omitted["results"][:-1]
    controls["omitted_result_rejected"] = not accepted(omitted)

    reordered = deepcopy(pristine)
    reordered["results"] = list(reversed(reordered["results"]))
    controls["reordered_results_rejected"] = not accepted(reordered)

    failed = deepcopy(pristine)
    failed["results"][1]["status"] = "failed"
    failed["results"][1]["returncode"] = 1
    controls["failed_result_rejected"] = not accepted(failed)

    failures = [name for name, passed in controls.items() if not passed]
    if failures:
        print("FAIL: " + ", ".join(failures))
        return 1
    print(
        "PASS: completed matrix resume is immutable; "
        f"{len(controls) - 1} corruption controls rejected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
