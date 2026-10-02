"""Regenerate repaired r264 from r210 via the exact X-flip/Stage-2 lineage."""
from __future__ import annotations

import importlib
import json

from r534_lineage_ancestry import BuildPin
from r534_lineage_prefix import digest

BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
OUTPUT_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
STEPS = (
    BuildPin("build_oam_xflip_fast_r231",
             "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c",
             "813076831def50fd02fa15c1f9acb4907ce896b08f963605ea6712c326c2aafe"),
    BuildPin("build_stage2_runtime_sparse_r255",
             "ee26f49e1e6780571a802000bd2a7f8eb4326fcc1c8515a92829cb2bb52f9eb7",
             "e30a0a2ba71437fcf6ab3935130791b9205cbca711bed310f80b1392cf56c16f"),
    BuildPin("build_stage2_runtime_sparse_r256",
             "3ca7c592935133a3a153e412b9c9b25421d3c8fbd2c4542283e43a8af909d6f5",
             "a730b4b1fd02e31d4f69b9029c9219ade5751ab0269177ec8e7a9f3fcec3deaf"),
    BuildPin("build_stage2_runtime_unrolled_r257",
             "a92f5783c68cfe1954189277e723af1611185aee829a3497cf006abddfd073a4",
             "e7a4c567512611a884d6fb36968ce5b2046c40405b21e6606390cc6eecea2652"),
    BuildPin("build_stage2_runtime_unrolled_abi_r258",
             "b27af6124eb21c3dc387a78c4ff126e451d07c1dd1507ec8d32330070bf9d3c9",
             "fe8761edbfae3c02ad41997135566c50cf5df0690885c87911da0131123f9849"),
    BuildPin("build_stage2_runtime_hdma6_r260",
             "799b288c6adf2939672685121127c7f60fc0ff2eb00e3f1eb27f8b7d12d7bff7",
             "77ed81575493e7bb7eed2b7e5f4a5ea55b45ec1dc84782c4eac389b1d1784acb"),
    BuildPin("build_stage2_isolated_entry_r263",
             "ce860a51b1f3daa783c08244ff02d2dbf957aa19cd04d23a7c04be2c8392e8bd",
             "8ea5b1663ebb92f7c2da129e252f774d2934d99cd5afcf3e1a68ed3a35546d00"),
    BuildPin("build_stage1_menu_hidden_repair_r264", OUTPUT_SHA256,
             "71c4961aa8fd0298f3f5112738f4911bd297f5109e836136476839617e443846"),
)


def build(source: bytes) -> tuple[bytes, list[dict]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("Stage-2 ancestry requires exact retained r210")
    result, records = source, []
    for pin in STEPS:
        builder = importlib.import_module(pin.module)
        previous = result
        compose = builder.build if pin.module == "build_oam_xflip_fast_r231" else builder.install
        result, metadata = compose(previous)
        if not isinstance(result, bytes) or len(result) != len(source) or digest(result) != pin.rom:
            raise ValueError(f"{pin.module}: generated ROM differs")
        encoded = (json.dumps(metadata, indent=2) + "\n").encode()
        if (metadata.get("base_sha256") != digest(previous)
                or metadata.get("candidate_sha256") != pin.rom or digest(encoded) != pin.receipt):
            raise ValueError(f"{pin.module}: generated static receipt differs")
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        records.append({
            "name": pin.module, "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "generated_receipt_sha256": digest(encoded),
            "generated_receipt_kind": "static-build",
            "fresh_live_qualification": False,
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)}),
        })
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("Stage-2 ancestry did not reproduce exact repaired r264")
    return result, records
