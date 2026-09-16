#!/usr/bin/env python3
"""Install the receipt-qualified Stage-7 r265 transport into exact r264.

This is production-facing installation code, not an emulator verifier.  The
machine-code blobs are frozen because the live receipts qualify their exact
bytes.  Installation therefore fails closed unless the complete input ROM,
every target preimage, every bound receipt, every emitted component, and the
complete output ROM have their recorded SHA-256 identities.

Until the remaining release gates are complete, ``build_v302_title_fix.py``
exposes this installer only through an explicit diagnostic flag and requires a
scratch output.  The default production build does not import or execute it.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parents[1]
BANK_SIZE = 0x4000

R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
E048_SHA256 = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
R265_SHA256 = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"

RUNTIME_BANKS = (13, 16)
RUNTIME_BASE = 0xDA60
RUNTIME_REDIRECT_OPERAND = 0xDAB7
RUNTIME_TAIL = 0xDAE9
RUNTIME_SOURCE_A = 0x7BB2
RUNTIME_SOURCE_A_SIZE = 46
RUNTIME_SOURCE_B = 0x7C4D
RUNTIME_SOURCE_B_SIZE = 114
RUNTIME_SHA256 = "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"

PAYLOAD_BANK = 22
HELPER_ADDR = 0x6C80
DESCRIPTORS_ADDR = 0x7500
LUT_ADDR = 0x7600

WINDOW_BANK = 13
WINDOW_HELPER_ADDR = 0x6A40
WINDOW_HELPER_END = 0x6A57
WINDOW_CALLSITE = 0x6EB1
VBLANK_MAPPER = 0x0824

OLD_WINDOW_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 C0 AF EA 53 DF EA 57 DF 3C C9 "
    "00 00 00 00"
)
NEW_WINDOW_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 FE 02 28 03 FE 08 C0 AF EA 53 DF "
    "EA 57 DF 3C C9"
)
NEXT_WINDOW_HELPER = bytes.fromhex("0E 08 2A E0 69 0D 20 FA C9")
WINDOW_CALLSITE_CONTRACT = bytes.fromhex(
    "CD 40 6A 28 10 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)
VBLANK_MAPPER_CONTRACT = bytes.fromhex(
    "F0 99 F5 3E 0D E0 99 EA 00 21 CD 1D 6F F1 E0 99 EA 00 21 C9"
)


@dataclass(frozen=True)
class FrozenBlob:
    name: str
    size: int
    sha256: str
    compressed_base85: str

    def decode(self) -> bytes:
        payload = zlib.decompress(base64.b85decode(self.compressed_base85))
        require(len(payload) == self.size, f"{self.name} width changed")
        require(digest(payload) == self.sha256, f"{self.name} bytes changed")
        return payload


# These are the exact executable/data bytes qualified by b724... and
# transferred unchanged by 295ce....  Keeping them frozen prevents a harmless-
# looking assembler refactor from silently escaping the live evidence.
ROUTER_TAIL = FrozenBlob(
    "runtime_router_tail",
    22,
    "49d0342202b5b27ec248b1e689a424db4655716dfa1d60587aacaff36bc17969",
    "c-nh-@!;2A4LAOAXfS;|`T66=k9J~*-8lfU%ni{",
)
STAGE7_HELPER = FrozenBlob(
    "stage7_dual_plane_helper",
    1459,
    "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003",
    (
        "c-pm;ze~eF7(kO&LqHtTF2SjG3R$Ee=+FkOi;I;0T3m{gZfy!m2T}W1sG#6d"
        "aLbTI1cx+>H53Y3C|&$ISX_jZE+xX%yPPfJoC_iElKbvud)`G4iA_^?ACW*{A)"
        "a8%DH9aY6ysyEpdx5K>1QZ{p96PiI3~MkAE)R_iJ%*L>RgF9CA^fE{Fg<i^kV9"
        "xcC@dBp|Z+#q&rJE(PV%&_h!U@FBeh(u`ew|M;@$|XgrX6{s-xkfm3b<@7!hJ"
        "tTAxjGjR48I7K^n=OzQ^5d-HH1Lt$_P6IMYsC;wdc3<yXIthiwLq_XB)_|PbNI"
        "~9!f}fLR!Em>SVHA!{YH~<hgQ8o+pS}MIKP1N_Gvt`SD<Pq-LRN*Gn!&<4<W("
        "p*HAS4;W+s}VS1QD#hejD1{GKRXu6HG{HQqkpMv|HC`m2F$>fZi4OlOlxfcd89"
        "mo-uK%ZfqDib2YXLCT6jN{W%DXrODH(px%4Q<|v$Nok^Lv^H8l2*7V9"
    ),
)
TILE_DESCRIPTORS = FrozenBlob(
    "stage7_tile_descriptors",
    96,
    "2d71e8844827ec11da155fabec1b42d93ea8e039bd56df69f3ddb0e463912874",
    (
        "c-jTQ0RhA?2m`=?5+qCl5+(sDNSFj9Oah|@QU{gr68`QhfPj63(+~qB9W@u4"
        "fiodsip?X=l9-lcOU+N3N6s?EhT6K-w`r`@+^)4=?HzjlJYgr7"
    ),
)
STAGE7_LUT = FrozenBlob(
    "stage7_immutable_lut",
    256,
    "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a",
    "c-muNzyVlU83qGjVL|3GF`@HOX>@VI000wF04o",
)


@dataclass(frozen=True)
class Evidence:
    path: str
    sha256: str
    required_fields: tuple[tuple[str, Any], ...]


EVIDENCE = (
    Evidence(
        "tmp/stage7-dual-plane-hdma-r264/static-receipt.json",
        "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272",
        (
            ("schema", "penta-stage7-hidden-dual-plane-hdma-r264-static-v1"),
            ("status", "STATIC_PASS_LIVE_GATES_REQUIRED"),
            ("base_sha256", R264_SHA256),
            ("in_memory_candidate.sha256", E048_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/helper-equivalence-static-receipt.json",
        "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583",
        (
            ("schema", "penta-stage7-r265-helper-equivalence-static-v1"),
            ("status", "STATIC_PASS_REBIND_WRAPPERS_REQUIRED"),
            ("identities.e048_rom", E048_SHA256),
            ("identities.r265_rom", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json",
        "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7",
        (
            ("schema", "penta-stage7-menu-signature-invalidation-r265-static-v1"),
            ("status", "STATIC_PASS_LIVE_GATES_REQUIRED"),
            ("base_sha256", E048_SHA256),
            ("candidate_sha256", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/transferred-stage7-static-receipt.json",
        "3bf962c18274ba8c5efe1e1ee9673ba19401dbebfc970782efed5e9e96673661",
        (
            ("schema", "penta-stage7-hidden-dual-plane-hdma-r264-static-v1"),
            ("status", "STATIC_PASS_LIVE_GATES_REQUIRED"),
            ("in_memory_candidate.sha256", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/menu-fixed-r1/receipt.json",
        "17c2d8a5a6b2d1d36ce5cb9d931db03534b2dbf7cacf5fae06be4cf3dbfdb7e5",
        (
            ("schema", "penta-stage7-menu-signature-control-fix-live-v1"),
            ("status", "PASS"),
            ("rom_sha256", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/generic-menu-natural-receipt.json",
        "f32977eb72a3030b21015b089db00d93420dd1c7c58613b78a6a234b59415019",
        (
            ("schema", "penta-stage7-r265-generic-window-receipt-v2"),
            ("status", "PASS"),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/stage1-current-hazard-menu-r1/receipt.json",
        "1e56ed46137a8fb4f1da8a64e009e8208c0b63f51a1a45fbeccff8f6df521d55",
        (
            ("schema", "penta-stage1-current-hazard-menu-v1"),
            ("passed", True),
            ("rom_sha256", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/abi-r265-r2/receipt.json",
        "49561196551f825cb3f235b2081320ea59c133b7acb20e7cce0633f8a0859f90",
        (
            ("schema", "penta-stage7-dual-plane-abi-smoke-v1"),
            ("status", "PASS"),
            ("expected_candidate_sha256", R265_SHA256),
        ),
    ),
    Evidence(
        "tmp/stage7-menu-signature-invalidation-r265/execution-equivalence-short-abi-r1.json",
        "70e1a4f0dae2e928b7261cbe290dc723e9f0fad7602113d42c21b8b48bb0b6fc",
        (
            ("schema", "penta-stage7-r265-execution-equivalence-v1"),
            ("status", "PASS_SHORT_ABI_ONLY_MORE_LIVE_GATES_REQUIRED"),
            ("identities.r265_rom", R265_SHA256),
        ),
    ),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address <= 0x7FFF, "invalid bank address")
    return bank * BANK_SIZE + address - 0x4000


def runtime_source_address(index: int) -> int:
    if index < RUNTIME_SOURCE_A_SIZE:
        return RUNTIME_SOURCE_A + index
    return RUNTIME_SOURCE_B + index - RUNTIME_SOURCE_A_SIZE


def runtime_from_source(payload: bytes, bank: int) -> bytes:
    first = payload[
        bank_offset(bank, RUNTIME_SOURCE_A):
        bank_offset(bank, RUNTIME_SOURCE_A) + RUNTIME_SOURCE_A_SIZE
    ]
    second = payload[
        bank_offset(bank, RUNTIME_SOURCE_B):
        bank_offset(bank, RUNTIME_SOURCE_B) + RUNTIME_SOURCE_B_SIZE
    ]
    return first + second


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def dotted_get(document: dict[str, Any], key: str) -> Any:
    current: Any = document
    for component in key.split("."):
        require(isinstance(current, dict) and component in current,
                f"evidence field missing: {key}")
        current = current[component]
    return current


def verify_evidence(root: Path = ROOT) -> list[dict[str, Any]]:
    """Verify the exact static and current live receipts used by this port."""

    verified = []
    for contract in EVIDENCE:
        path = root / contract.path
        require(path.is_file(), f"bound evidence missing: {contract.path}")
        payload = path.read_bytes()
        actual_sha = digest(payload)
        require(actual_sha == contract.sha256,
                f"bound evidence changed: {contract.path}: {actual_sha}")
        document = json.loads(payload)
        for key, expected in contract.required_fields:
            actual = dotted_get(document, key)
            require(actual == expected,
                    f"bound evidence field changed: {contract.path}:{key}")
        verified.append({
            "path": contract.path,
            "sha256": actual_sha,
            "fields": {key: expected for key, expected in contract.required_fields},
        })
    return verified


def require_preimages(payload: bytes) -> dict[str, Any]:
    require(len(payload) == 0x80000, f"expected 512 KiB ROM, got {len(payload)}")
    actual_sha = digest(payload)
    require(actual_sha == R264_SHA256,
            f"Stage-7 r265 requires exact r264 {R264_SHA256}; got {actual_sha}")

    redirect_index = RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE
    tail_index = RUNTIME_TAIL - RUNTIME_BASE
    runtime_receipts = []
    for bank in RUNTIME_BANKS:
        runtime = runtime_from_source(payload, bank)
        require(digest(runtime) == RUNTIME_SHA256,
                f"bank{bank} DA60 runtime source changed")
        require(runtime[redirect_index] == 0xEB,
                f"bank{bank} DAB7 redirect operand changed")
        require(runtime[tail_index:tail_index + ROUTER_TAIL.size]
                == bytes(ROUTER_TAIL.size),
                f"bank{bank} DAE9 tail cave is not clear")
        runtime_receipts.append({
            "bank": bank,
            "source_sha256": digest(runtime),
            "redirect_preimage": "$EB",
            "tail_preimage_sha256": digest(bytes(ROUTER_TAIL.size)),
        })

    decoded = {
        HELPER_ADDR: STAGE7_HELPER.decode(),
        DESCRIPTORS_ADDR: TILE_DESCRIPTORS.decode(),
        LUT_ADDR: STAGE7_LUT.decode(),
    }
    payload_preimages = []
    for address, blob in decoded.items():
        offset = bank_offset(PAYLOAD_BANK, address)
        expected = bytes([0xFF]) * len(blob)
        require(payload[offset:offset + len(blob)] == expected,
                f"bank{PAYLOAD_BANK}:${address:04X} payload cave is not free")
        payload_preimages.append({
            "bank": PAYLOAD_BANK,
            "range": f"${address:04X}-${address + len(blob) - 1:04X}",
            "length": len(blob),
            "preimage_sha256": digest(expected),
        })

    helper_offset = bank_offset(WINDOW_BANK, WINDOW_HELPER_ADDR)
    require(len(OLD_WINDOW_HELPER) == len(NEW_WINDOW_HELPER)
            == WINDOW_HELPER_END - WINDOW_HELPER_ADDR,
            "Window helper width changed")
    require(payload[helper_offset:helper_offset + len(OLD_WINDOW_HELPER)]
            == OLD_WINDOW_HELPER, "Window helper preimage changed")
    require(payload[helper_offset + len(OLD_WINDOW_HELPER):
                    helper_offset + len(OLD_WINDOW_HELPER)
                    + len(NEXT_WINDOW_HELPER)] == NEXT_WINDOW_HELPER,
            "Window helper boundary changed")
    callsite_offset = bank_offset(WINDOW_BANK, WINDOW_CALLSITE)
    require(payload[callsite_offset:callsite_offset
                    + len(WINDOW_CALLSITE_CONTRACT)]
            == WINDOW_CALLSITE_CONTRACT, "Window callsite changed")
    require(payload[VBLANK_MAPPER:VBLANK_MAPPER
                    + len(VBLANK_MAPPER_CONTRACT)] == VBLANK_MAPPER_CONTRACT,
            "Window VBlank bank mapper changed")

    return {
        "complete_rom_sha256": actual_sha,
        "runtime_sources": runtime_receipts,
        "payload_caves": payload_preimages,
        "window_helper": {
            "bank": WINDOW_BANK,
            "range": "$6A40-$6A56",
            "preimage_sha256": digest(OLD_WINDOW_HELPER),
            "next_helper_sha256": digest(NEXT_WINDOW_HELPER),
            "callsite_sha256": digest(WINDOW_CALLSITE_CONTRACT),
            "vblank_mapper_sha256": digest(VBLANK_MAPPER_CONTRACT),
        },
    }


def input_mutation_controls(base: bytes) -> dict[str, bool]:
    """Prove representative mutations cannot cross the complete-ROM gate."""

    offsets = {
        "header_identity": 0x0134,
        "runtime_redirect": bank_offset(13, 0x7C76),
        "bank22_payload_cave": bank_offset(PAYLOAD_BANK, HELPER_ADDR),
        "window_signature_helper": bank_offset(WINDOW_BANK, WINDOW_HELPER_ADDR),
    }
    controls = {}
    for name, offset in offsets.items():
        mutant = bytearray(base)
        mutant[offset] ^= 1
        try:
            require_preimages(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"input mutation escaped: {name}")
    return controls


def install_stage7_r265(
    base: bytes,
    *,
    evidence_root: Path = ROOT,
    require_bound_evidence: bool = True,
) -> tuple[bytes, dict[str, Any]]:
    """Return the exact a4c... candidate and a non-promotable static receipt."""

    preimages = require_preimages(base)
    mutation_controls = input_mutation_controls(base)
    evidence = verify_evidence(evidence_root) if require_bound_evidence else []
    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}

    tail = ROUTER_TAIL.decode()
    redirect_source = runtime_source_address(
        RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE
    )
    tail_source = runtime_source_address(RUNTIME_TAIL - RUNTIME_BASE)
    for bank in RUNTIME_BANKS:
        redirect_offset = bank_offset(bank, redirect_source)
        tail_offset = bank_offset(bank, tail_source)
        rom[redirect_offset] = 0x31
        rom[tail_offset:tail_offset + len(tail)] = tail
        allowed.add(redirect_offset)
        allowed.update(range(tail_offset, tail_offset + len(tail)))

    components = []
    for address, frozen in (
        (HELPER_ADDR, STAGE7_HELPER),
        (DESCRIPTORS_ADDR, TILE_DESCRIPTORS),
        (LUT_ADDR, STAGE7_LUT),
    ):
        blob = frozen.decode()
        offset = bank_offset(PAYLOAD_BANK, address)
        rom[offset:offset + len(blob)] = blob
        allowed.update(range(offset, offset + len(blob)))
        components.append({
            "name": frozen.name,
            "bank": PAYLOAD_BANK,
            "range": f"${address:04X}-${address + len(blob) - 1:04X}",
            "length": len(blob),
            "sha256": frozen.sha256,
        })

    update_checksums(rom)
    e048 = bytes(rom)
    require(digest(e048) == E048_SHA256,
            f"Stage-7 transport rematerialization changed: {digest(e048)}")

    window_offset = bank_offset(WINDOW_BANK, WINDOW_HELPER_ADDR)
    rom[window_offset:window_offset + len(NEW_WINDOW_HELPER)] = NEW_WINDOW_HELPER
    allowed.update(range(window_offset, window_offset + len(NEW_WINDOW_HELPER)))
    update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    require(candidate_sha == R265_SHA256,
            f"r265 rematerialization changed: {candidate_sha}")

    changed = [
        index for index, (before, after) in enumerate(zip(base, candidate, strict=True))
        if before != after
    ]
    unexpected = sorted(set(changed) - allowed)
    require(not unexpected,
            f"installer changed unapproved offsets: {unexpected[:16]}")

    receipt = {
        "schema": "penta-stage7-r265-production-install-v1",
        "status": "STATIC_PASS_LIVE_RELEASE_GATES_REMAIN",
        "promotable": False,
        "emulator_run": False,
        "default_production_build_changed": False,
        "activation": "explicit --stage7-dual-plane-r265 flag only",
        "base_sha256": R264_SHA256,
        "transport_intermediate_sha256": E048_SHA256,
        "candidate_sha256": candidate_sha,
        "changed_byte_count_including_checksums": len(changed),
        "strict_preimages": preimages,
        "input_mutation_controls": mutation_controls,
        "components": components,
        "runtime_router_tail": {
            "banks": list(RUNTIME_BANKS),
            "length": len(tail),
            "sha256": ROUTER_TAIL.sha256,
        },
        "window_signature_invalidation": {
            "bank": WINDOW_BANK,
            "range": "$6A40-$6A56",
            "old_sha256": digest(OLD_WINDOW_HELPER),
            "new_sha256": digest(NEW_WINDOW_HELPER),
            "scene02_preserved": True,
            "scene08_added": True,
            "FFE4_zero_path_byte_and_cycle_exact": True,
        },
        "bound_evidence_required": require_bound_evidence,
        "bound_evidence": evidence,
        "remaining_release_scope": [
            "candidate-bound duplicate long Stage-7 visual patrol",
            "candidate-bound safe-boundary speed finalization",
            "Crystal Dragon containment completion",
            "full source-built release suite after upstream base lineage is restored",
        ],
        "decision": (
            "Exact r265 bytes are production-installable from exact aa4c r264, "
            "but the opt-in remains non-promotable until the remaining live "
            "release gates and source-base lineage gate pass."
        ),
    }
    return candidate, receipt


def checked_scratch(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            f"{label} must be below repo tmp/ or /mnt/data/tmp/")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    output = checked_scratch(args.output, label="candidate output")
    receipt_path = checked_scratch(args.receipt, label="receipt output")
    require(output != receipt_path, "candidate and receipt paths alias")
    candidate, receipt = install_stage7_r265(args.base.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt["candidate_path"] = str(output.relative_to(ROOT))
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": receipt["status"],
        "candidate": receipt["candidate_path"],
        "candidate_sha256": receipt["candidate_sha256"],
        "receipt": str(receipt_path.relative_to(ROOT)),
        "receipt_sha256": digest(receipt_path.read_bytes()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
