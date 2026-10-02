"""Rebuild r314 from retained r287 and authentic historical evidence.

These old observations are immutable inputs to the historical builders, not
fresh qualification of any candidate. All ROM and static-receipt intermediates,
including the separate r307 branch, are generated in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib

from r534_lineage_prefix import digest, serialize_receipt

BASE_SHA256 = "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
OUTPUT_SHA256 = "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303"
OUTPUT_RECEIPT_SHA256 = "730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1"

# Paths document the existing evidence; build() never opens these defaults.
HISTORICAL_INPUTS = {
    "r303_rejected": (
        "tmp/stage1-fast-scene0b-gates-r303/live-scene0b-dcbb40/receipt.json",
        "5ffb3c24a0f3ae150970081df4cd581136e3dc399221312722f31e41d816dd6c",
    ),
    "room01_capture": (
        "tmp/stage1-report-hook/r290-natural-north/candidate/c1a0.bin",
        "d1fba90404eea5047dabf7d1c41203f9231e7b780b7f664e6e7c9e4110d2a706",
    ),
    "r310_live": (
        "tmp/stage1-precompile-effective-room-r310/publication-owned-oracle-r2/receipt.json",
        "b7b93403fa901d8a5b7652740197bcd3302377356ef3d1f0c7f3493d33b62fd4",
    ),
    "r311_rejected": (
        "tmp/stage1-final-scene0b-r311/live-scene0b-r1/receipt.json",
        "c1960e14637ce4e5d2dcd554411a1112c9d396ca5b3e158a04395352d6bba8c9",
    ),
    "r313_rejected": (
        "tmp/stage1-scene0b-runtime-selfheal-r313/live-scene0b-hardening-diagnostic-r7/receipt.json",
        "158f31790ae4495894b26b80d7863deac36ccf8efbe28feb51f24e4acb3ccf08",
    ),
}


@dataclass(frozen=True)
class BuildPin:
    module: str
    rom: str
    receipt: str


PRE_BRANCH = (
    BuildPin("build_stage1_cold_art_gold_r288",
             "a18660d3ed0f883810d0ed542e63598f0a48a09280eb5f91e48aa621d70eb331",
             "ee7898612ade81fc290c3a707cc4a1a2109e0356f36bc1cad5f2c371a3abc550"),
    BuildPin("build_stage1_menu_sentinel_r289",
             "559e9aa7a81985dd8639ce70d830b9799faebb4f9e27ceec55e2ce0fb086d905",
             "3be4f457268a6ec043110734f05ab9418b9ee7cce2f3fefa06b40e5c1f84e7c6"),
    BuildPin("build_stage1_live_menu_selector_r290",
             "48582bed3b9c9746588de9d2de695927788b7b07a511b817da0cb36932d87736",
             "232ea8935182e2647632e921e7086a76c16d7578be3c32d6058cb58727f91447"),
    BuildPin("build_stage1_exact_background_r292",
             "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1",
             "fa5f837e0b5809d05dc1acafaa799613ff472720c0e8fda7e5b9406597125bd0"),
    BuildPin("build_stage1_fast_scene0b_gates_r303",
             "1137bcd557c7ea08f3e57c1f9b4a69fcec41c080ae817fbb139563509c4b08fe",
             "f59f2651a84d1f23394f1bdb1743841e1aeade8ea9dd7d984b368e0109bd4175"),
    BuildPin("build_stage1_unified_scene0b_r305",
             "9c83a6937a1b71f2b4d0a6628fa3022d8f46f89e46c7aafa23a61a8d9166ce13",
             "71a3a477a2be2fad9f0f83e24b9bdf6cacd940c7d772a546658bbaca1166c450"),
)
BRANCH = BuildPin("build_stage1_bank16_installer_mirror_r307",
                  "77722cf7abfff564de72caf0cdd06dbb774bf0614c071933247178817b3bea84",
                  "a36bc024705b9df3388b83e008f6add576a590db35a92e36110d2935a8b50bc5")
R310 = BuildPin("build_stage1_precompile_effective_room_r310",
                "84bf45826c1acd2ae36a971c61aaf05c0ba761b723cd87e568607f9ffac6f36c",
                "ddc5edeb0113edc78b913a3187a201fb86f0f31b3271915621fd5eb6c4d970df")
R311 = BuildPin("build_stage1_final_scene0b_r311",
                "be8e78761470b811111e74d47c1cbb9923e34d136c420ccb76314a6be22ab84d",
                "5db65ed067ed1bda36e933c466e77f88aba51a6212b8baa7c96938f800587130")
R312 = BuildPin("build_stage1_runtime_epoch_r312",
                "dca72f535850d4445fc8f27d032628e63b1a9b7dee0f8012fbfee9b69c4a1951",
                "3c677ced990956892c876d310207c4549f27016721ebf025db39990f3408f380")
R313 = BuildPin("build_stage1_scene0b_runtime_selfheal_r313",
                "07e12b47c1561822c7dbe2c9f7d739c418ad6fcbb1822d2fa06726c705ec82e8",
                "c4086dc2d7186d8e6b9c88829d130034b64fee83783a9314944023f44138ba96")
R314 = BuildPin("build_stage1_scene0b_publication_commit_r314",
                OUTPUT_SHA256, OUTPUT_RECEIPT_SHA256)


def build(source: bytes, evidence: dict[str, bytes]
          ) -> tuple[bytes, bytes, list[dict], list[dict]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("ancestry requires exact retained r287")
    if set(evidence) != set(HISTORICAL_INPUTS):
        raise ValueError("ancestry requires exactly the five historical evidence inputs")
    for name, (_, expected) in HISTORICAL_INPUTS.items():
        if digest(evidence[name]) != expected:
            raise ValueError(f"{name}: historical evidence identity differs")

    def run(pin, previous, receipt=None, extras=(), evidence_names=(), options=None):
        args = [previous] + ([receipt] if receipt is not None else []) + list(extras)
        result, metadata = importlib.import_module(pin.module).build(*args, **(options or {}))
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: generated ROM differs")
        encoded = serialize_receipt(metadata)
        if metadata.get("candidate_sha256") != pin.rom or digest(encoded) != pin.receipt:
            raise ValueError(f"{pin.module}: generated static receipt differs")
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        record = {
            "name": pin.module, "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "input_receipt_sha256": digest(receipt) if receipt is not None else None,
            "generated_receipt_sha256": digest(encoded),
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)
            }),
            "historical_evidence_sha256": {name: digest(evidence[name]) for name in evidence_names},
            "fresh_live_qualification": False,
        }
        return result, encoded, record

    result, receipt, records = source, None, []
    for pin in PRE_BRANCH:
        capture_step = pin.module == "build_stage1_fast_scene0b_gates_r303"
        rejected_step = pin.module == "build_stage1_unified_scene0b_r305"
        result, receipt, record = run(
            pin, result, receipt,
            evidence_names=("room01_capture",) if capture_step else (("r303_rejected",) if rejected_step else ()),
            options=({"room01_capture": evidence["room01_capture"]} if capture_step else
                     ({"rejected_receipt_bytes": evidence["r303_rejected"]} if rejected_step else None)),
        )
        records.append(record)
    r305_checkpoint = result
    side, side_receipt, side_record = run(BRANCH, result, receipt)
    result, receipt, record = run(R310, result, receipt,
                                   evidence_names=("room01_capture",),
                                   options={"room01_capture": evidence["room01_capture"]})
    records.append(record)
    result, receipt, record = run(
        R311, result, receipt, (side, side_receipt, evidence["r310_live"]),
        ("r310_live", "room01_capture"),
        {"room01_capture": evidence["room01_capture"], "reference": r305_checkpoint},
    )
    record["generated_component"] = {
        "candidate_sha256": digest(side), "build_receipt_sha256": digest(side_receipt),
    }
    record["generated_reference_sha256"] = digest(r305_checkpoint)
    records.append(record)
    for pin, name in ((R312, "r311_rejected"), (R313, None), (R314, "r313_rejected")):
        extras = (evidence[name],) if name else ()
        result, receipt, record = run(pin, result, receipt, extras, (name,) if name else ())
        records.append(record)
    return result, receipt, records, [side_record]
