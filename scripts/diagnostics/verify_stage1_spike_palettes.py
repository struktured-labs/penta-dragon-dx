#!/usr/bin/env python3
"""Prove the YAML-owned Stage 1 rotating-spike art and palettes are live."""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage_card_palette_handoff import (  # noqa: E402
    VBLANK_ATOMIC_COMMIT,
    VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT,
    VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT,
    VBLANK_ATOMIC_WINDOW_FAST_COMMIT,
    VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT,
    VBLANK_ATOMIC_WINDOW_FINAL_COMMIT,
    VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT,
    VBLANK_ATOMIC_WINDOW_COMMIT,
    VBLANK_COMMIT_OFFSET,
)


PRIMARY_PUBLISHER_ADDR = 0x12E0
PRIMARY_PUBLISHER_END = 0x1303
LEGACY_PRIMARY = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 C9"
)
R320_PRIMARY = bytes.fromhex(
    "F3 F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 FA 0B DC B7 3E 83 28 02 "
    "CB DF E0 40 FB C9"
)
R346_PRIMARY = bytes.fromhex(
    "F3 00 F0 40 87 30 06 F0 44 FE 90 38 FA "
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "F0 40 EE 08 E0 40 FB C9"
)
R347_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 F0 40 EE 08 E0 40 "
    "18 05 3E 01 EA 5C DF FB C9"
)
R348_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 F0 40 EE 08 E0 40 "
    "18 05 F0 53 EA 5C DF FB C9"
)
R349_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 F0 40 EE 08 E0 40 "
    "18 05 F0 40 EA 5C DF FB C9"
)
R350_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 F0 40 EE 08 E0 40 "
    "18 05 3E 01 EA 5D DF FB C9"
)
R345_MAP_DONE = bytes.fromhex(
    "7C E0 53 F0 01 1F 38 07 CD F1 DB 00 FB C9 00"
)
R351_MAP_DONE = bytes.fromhex(
    "7C E0 53 12 F0 01 1F 38 06 CD F1 DB FB C9 00"
)
R354_MAP_DONE = bytes.fromhex(
    "7C E0 C4 F0 01 1F 38 07 CD F1 DB 00 FB C9 00"
)
R354_VBLANK_COMMIT = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F AF EA 5C DF "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 "
    "F0 C4 B7 28 10 E6 04 07 47 AF E0 C4 "
    "F0 40 E6 F7 B0 E0 40 18 06 F0 40 EE 08 E0 40 "
    "C3 1D 6F"
)
from build_latched_publication_r383 import (  # exact experimental publication ABI
    SHIM as R383_SHIM, GUARD as R383_GUARD,
    commit_bytes as r383_commit_bytes,
)
from build_idempotent_latched_publication_r384 import PACK as R384_PACK, PACK_OFFSET as R384_PACK_OFFSET

PUBLICATION_VARIANTS = {
    "r445c-title-v6-baeeb893": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "baeeb893cf5cd47192273b18eaf9d1bc7902f9ab55da2b3306d2e32db00fcebe",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r449f-title-v6-15ab73c3": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r456d-attract-white-69896bb1": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r527-ending-handoff-13beaa1b": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r528-palette-atomic-e8da7fde": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r529-palette-atomic-5c49fa5d": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r530-palette-atomic-46b498d8": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r531-palette-atomic-9d44e9d1": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r532-palette-atomic-055a2754": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r533-story-neutral-guard-4fc5028a": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage4-cache-key-727ee496": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-scoped-menu-title-951e770e": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "951e770e4a631f52056d881d7e6577b3d669c9a0566c0310a7299df6a91147d5",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-entry-scoped-menu-title-2db9f03c": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "2db9f03cd772e75367a219a73610007c2446655cfb7a27873ddaae3a62c816cd",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-cold-menu-title-69ff940a": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r536-penta-seam-vram-b93ebc46": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r536-stage1-only-card-black-ffb6a829": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-stage-card-black-fe14b0e3": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-stage1-only-card-black-b691c96c": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r535-title-tile-retire-681b4668": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage1-native-gold-72395c46": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "72395c46b865b11d5cf78880a41ae0248cf6e890e0069731439dc544f676a431",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage1-native-gold-2279fb35": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "2279fb35c57826870b70c1831786ee37336d2a3cd45d8f448a011699a781411a",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage1-native-gold-18d911a3": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "18d911a318083aa876517b922856ba705002973a9ba2915b2d30fe608ad508ad",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage1-native-gold-59c62cfc": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "59c62cfc0c5fd129b943b0fd25f277a49a5f6b57d13f6d918ad819cd30ba3e0b",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-stage1-native-gold-703c7c1c": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "703c7c1ce7e75b8f997cbba529271d86294f8829f0cfbae272cb795e326ae48d",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-reserved-gold-620d8a31": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "620d8a31bd1a68bb816a413abc6451e24eb1ea668efb59e80875c7e469e2c694",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-reserved-gold-mirror-1b2def34": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "1b2def345b2656c010ea9711c829bd99500572a25b5d2b35f37124712b862c32",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r534-reserved-gold-mirror-c67cea34": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "c67cea343c448d35319f5381d0d15674fa1a2744515de3ff45ad20fda06296fa",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r456c-attract-white-8234bd84": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r456a-attract-white-44dbde77": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "44dbde77f2422b37c040647c981e779aeffe843c90b5bf9bc237af06fbd95466",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r455-arena-storage-6e5e7a61": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r449f-prehelper-title-v6-d82f563d": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r451c-lut-reload-repatch-b331c5e0": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r443e3-title-v5-6b375a80": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "6b375a8080df3c982f63a92ea0a679241d8c77cf370776d38bd5b4be8c101e35",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r443e3-reload-dealias-299431cd": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "299431cd27123ec84830d38d021505b4180ceec628a87e20db13affb12c58fa3",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r443d-deferred-dma-7b3de7ac": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "7b3de7acf60614b958658b9f7f7139bb7b855dd23bc5f41c6c42d7322cead620",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r443e-reload-dealias-df0a2c73": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "df0a2c73b426a5a92a49b3050087f952c8ebb4ccc76b452acd707aac3f522392",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r442-title-v4-dbd75344": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "dbd753449146c64ccd3d97e9dfee5d20adcdbf61ae523ee92bfbb835a1a08028",
        "extras": tuple((13 * 0x4000 + address - 0x4000, bytes.fromhex("E0 40"))
                        for address in (0x7457, 0x7462)),
    },
    "r442-subscene-tracking-ea53ebb1": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
    },
    "r441-stage2-seven-rows-44ac932a": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
    },
    "r440-animation-envelope-dcb4f553": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623",
    },
    "r439-warning-source-tracking-24bbce66": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "24bbce66e2cd0d7c94e032488c18ff1f3946269b61199ffa4ee5d0c1cda1a137",
    },
    "r438-compiled-tooth-bank-4913e494": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796",
    },
    "r437-restore-room03-scanner-06146c7f": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "06146c7f7f77099c25458843d585abab125439183692c184dff1b2c878a649fd",
    },
    "r429-scanner-increments-d832cb65": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "d832cb6569f54101d6be6565667f369ca715e8e698574113a70dbcbbba432ada",
    },
    "r428-moving-publish-wait-61df7aef": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "61df7aef783e62013c54b2a05539a56d5e1e31da229565d0aea1f35ea497505f",
    },
    "r427-coordinate-wait-d509f950": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "d509f95087a493f0af84d0f06304db2487af4d5932169d7e0fd2f9db4f0ab63e",
    },
    "r426-stage1-bulk-context-f6d9550d": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "f6d9550d04ff34b32f299b817ab9cb9da5f84c90577cd11f35ad6a0d239a0b58",
    },
    "r425-stage1-bulk-compile-ee8b32b3": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "ee8b32b33a00fdae20bd299c82a1ea8bbab789e64c3086d1c5ba34012d2a79cb",
    },
    "r424-stage5-private-pointer-a36469fe": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b",
    },
    "r430-respawn-entry-colors-9f65073b": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "9f65073be9326d73b93f9f4279e554791d45279115d450e743b9bc2fa3660567",
    },
    "r431-remove-entry-seed-838110ba": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042",
    },
    "r432-aligned-tile-dma-a5fd94d0": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "a5fd94d0ea4287a92ed9139e882e32b6f74536a071844697b659c8c2ecb1f164",
    },
    "r436-single-recovery-art-37b4e9c8": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3",
    },
    "r435-stage5-dead-moves-6b5d6a65": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c",
    },
    "r434-combined-dma-compile-e9d7f441": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "e9d7f4417e4835b1dc9bf1fd68eb9651cee5d06bd6819e7a640ab853eb3117b1",
    },
    "r433-tail-coordinate-wait-5aee56bf": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "5aee56bf413f96c4b9d86e4091a6098c43b5f2c47f943f50df57369fcef73ba3",
    },
    "r423-native-pointer-increment-4ba37fda": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "4ba37fdacf6e467dcae8d3eed72d76044f832d4620939a149cf9d61f60ff8567",
    },
    "r422-static-copy-rows-6f28b86d": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "6f28b86d2af4828004c6c1d3b0e97dec0bd9f2c656c42fb49cc940eeed4d3be5",
    },
    "r420-room-writer-wait-366ebf30": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9",
    },
    "r419-stage7-room-wait-033476bd": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "033476bdd35dd754c1b3dad5d92c672dff83dca48d7bf5537880414311a79941",
    },
    "r418-skip-equal-tail-801981b6": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "801981b6a5e613bcb924e6e732984ba789a2da448da27e9a36341be0478b9769",
    },
    "r417-private-stationary-864d9993": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8",
    },
    "r416-native-increment-13f34a8f": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "13f34a8f8898fe4fd41c8e3eef695504d28b58c5fd0660e7fbb3afacde430586",
    },
    "r415-stationary-copy-3c3fa4dd": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "3c3fa4dd1fb1848cad3d6a66435dc0cda1474b60569f70228da5951a5d80057d",
    },
    "r414-native-equal-a377d079": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "a377d07919b573632a2605ae79f898a64f0ec017ba555725ca0dd3521fb5afbf",
    },
    "r413-native-cached-4e7587f2": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "4e7587f2744a97387184fd21c8be47abbd946bada997c3af26c3a0d30a34f698",
    },
    "r412-metatile-increment-c558d955": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "c558d9559dbdcc15c3ad8eb6a100eddfd4546529e2e4faaaf029f064e9edce36",
    },
    "r411-cached-only-edfade4e": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "edfade4e4715641b1a5fd008c152049cb7ea02850f25f4b2c79eb43c5f9c7b6f",
    },
    "r410-bulk-attributes-27be530d": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "27be530d5f245bcb34efe3cffd65b5a7718aa656174255c791e110c58b7fbfde",
    },
    "r409-precompile-abi-bb2468cc": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "bb2468ccaafc65c713b169eed9288aeee70e11769b085174ffa30a686721adf5",
    },
    "r408-precompile-eb88d017": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "eb88d01724e3a53076f5262878bbc7786e672b03845d3b2058fd481cb12ba6ce",
    },
    "r407-stage1-pointer-1438d4d8": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a",
    },
    "r406-metatile-pointer-267395bb": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "267395bbd9d75bf1b1c01cbbf47ddc5be8dcc91c2cf79d42a0bc1b9800da7626",
    },
    "r405-six-tiles-79e83ac5": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "79e83ac5f63fe51d2c68fe3f3f3c7e2123c5607018ee381e76b48e18129a053b",
    },
    # Identity enables observation only; r404 still requires every live gate.
    "r404-relative-consume-607dd536": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "607dd53618c59e94dfb4b20cbac149549ca48ef7840cd39cdcb16ea60800f177",
    },
    "r400-room1-deferred-df6fffb1": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "df6fffb16fcb1ada3213c50359213f0c65effe8345f74c4401360b86509bdf90",
    },
    "r397b-deferred-pipeline-7f1dcd6e": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "7f1dcd6e9479e41e0dfa338b0414f0052f88b55bfc268b7aa1f86a0c17d60109",
    },
    # Experimental identity only, not a qualification result. The deferred
    # pipeline still commits LCDC at the same instruction, but its multi-site
    # state machine differs from r384. Bind the entire reviewed ROM so no
    # partial/changed pipeline is admitted by an overly broad byte pattern.
    "r397-deferred-pipeline-1aeb2e66": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "rom_sha256": "1aeb2e66cdbdadd47d604d72b1abe8e1cc15497b8bbccf870f0b0633cdbb5831",
    },
    "r363-vblank-palette-map-window-fast-final-latched-r384": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (VBLANK_COMMIT_OFFSET, r383_commit_bytes(
                bytes.fromhex("C3 64 74 00") + VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT[4:])),
            (0x37464, R383_GUARD), (0x118B, R383_SHIM),
            (R384_PACK_OFFSET, R384_PACK),
        ),
    },
    "r363-vblank-palette-map-window-fast-final-backpressure-r382": {
        "bytes": R347_PRIMARY[:-7] + bytes.fromhex("C3 8B 11 00 00 FB C9"),
        "pc": 0x7457,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET,
             bytes.fromhex("C3 64 74 00") + VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT[4:]),
            (0x37464, bytes.fromhex(
                "F0 44 E6 FC FE 90 C2 1D 6F FA 5C DF B7 C3 00 74")),
            (0x118B, bytes.fromhex(
                "3E 01 EA 5C DF F5 FB F0 FF 0F 30 06 FA 5C DF B7 20 FA F1 C9")),
        ),
    },
    "r363-vblank-palette-map-window-fast-final-guard-r374": {
        "bytes": R347_PRIMARY, "pc": 0x7457,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET,
             bytes.fromhex("C3 64 74 00") + VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT[4:]),
            (0x37464, bytes.fromhex(
                "F0 44 E6 FC FE 90 C2 1D 6F FA 5C DF B7 C3 00 74")),
        ),
    },
    "legacy-v1": {"bytes": LEGACY_PRIMARY, "pc": 0x12EC},
    "r320-v1": {"bytes": R320_PRIMARY, "pc": 0x12FF},
    "r346-vblank-v1": {"bytes": R346_PRIMARY, "pc": 0x12FF},
    "r347-deferred-vblank-v1": {
        "bytes": R347_PRIMARY, "pc": 0x741F,
        "extra": (0x42ED, R345_MAP_DONE),
    },
    "r348-absolute-vblank-v1": {"bytes": R348_PRIMARY, "pc": 0x741F},
    "r349-requested-peer-vblank-v1": {"bytes": R349_PRIMARY, "pc": 0x7425},
    "r350-completed-map-vblank-v1": {"bytes": R350_PRIMARY, "pc": 0x7427},
    "r351-completed-source-end-vblank-v1": {
        "bytes": R347_PRIMARY, "pc": 0x7427,
        "extra": (0x42ED, R351_MAP_DONE),
    },
    "r354-postcommit-hram-vblank-v1": {
        "bytes": R347_PRIMARY, "pc": 0x742C,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, R354_VBLANK_COMMIT),
        ),
    },
    "r356-vblank-palette-map-atomic-v2": {
        "bytes": R347_PRIMARY, "pc": 0x7452,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_COMMIT),
        ),
    },
    "r357-vblank-palette-map-window-atomic-v3": {
        "bytes": R347_PRIMARY, "pc": 0x7459,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_WINDOW_COMMIT),
        ),
    },
    "r358-vblank-palette-map-stage1-window-atomic-v4": {
        "bytes": R347_PRIMARY, "pc": 0x7460,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT),
        ),
    },
    "r359-vblank-palette-map-stage1-only-window-atomic-v5": {
        "bytes": R347_PRIMARY, "pc": 0x7465,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT),
        ),
    },
    "r360-vblank-palette-map-window-fast-atomic-v6": {
        "bytes": R347_PRIMARY, "pc": 0x7456,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_WINDOW_FAST_COMMIT),
        ),
    },
    "r361-vblank-palette-map-window-robust-atomic-v7": {
        "bytes": R347_PRIMARY, "pc": 0x7456,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT),
        ),
    },
    "r362-vblank-palette-map-window-final-atomic-v8": {
        "bytes": R347_PRIMARY, "pc": 0x7457,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_WINDOW_FINAL_COMMIT),
        ),
    },
    "r363-vblank-palette-map-window-fast-final-atomic-v9": {
        "bytes": R347_PRIMARY, "pc": 0x7457,
        "extras": (
            (0x42ED, R354_MAP_DONE),
            (19 * 0x4000 + 0x6C51 - 0x4000, bytes.fromhex("00 00")),
            (VBLANK_COMMIT_OFFSET, VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT),
        ),
    },
}

from build_v301_gdma import (  # noqa: E402
    _bg_table,
    create_inline_tile_copy_postcomputed_attrs,
    create_inline_tile_copy_stage1_precomputed_attrs,
)
from build_v302_title_fix import (  # noqa: E402
    ARENA_SANITIZER_DISPATCH_ADDR,
    ATTRACT_OBJ_COLORIZER_ADDR,
    BANK13,
    BANK14,
    BANK7,
    BG_SWEEP_COUNT_ADDR,
    COLORIZE_ADDR,
    COLD_STAGE1_SWEEP_ARM_ADDR,
    COLD_STAGE1_SWEEP_ARM_TAIL_ADDR,
    INLINE_ATTR_DECISION_HELPER_ADDR,
    LAVA_ATTR_DECIDER_ADDR,
    MENU_CLOSE_NATIVE_REPAIR_ADDR,
    OAM_PALETTE_RESOLVER_ADDR,
    OAM_WRAM_COPY_ADDR,
    OAM_WRAM_COPY_TAIL_ADDR,
    OAM_WRAM_BASE,
    PALETTE_COPY_CRAM8_ADDR,
    PALETTE_LOADER_ADDR,
    PALETTE_LOADER_EXT_ADDR,
    STAGE1_ATOMIC_GROUP_WIDTH,
    STAGE1_ATOMIC_SETUP_ADDR,
    STAGE1_ATOMIC_WRAP_ADDR,
    STAGE1_POSTCOPY_GUARD_WRAM_ADDR,
    STAGE1_ATTR_ROW_INIT_ADDR,
    STAGE1_ATTR_ROW_INIT_TAIL_ADDR,
    STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR,
    STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR,
    STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR,
    STAGE1_HAZARD_BANK1_LOADER_ADDR,
    STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR,
    STAGE1_HAZARD_BANK1_REFRESH_COUNT,
    STAGE1_HAZARD_BANK1_TILE_COUNT,
    STAGE1_HAZARD_BANK0_MAP_ADDR,
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_HAZARD_BG7_SOURCE_ADDR,
    STAGE1_HAZARD_ROW_COMPILER_ADDR,
    STAGE1_HAZARD_ROW_HELPER_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR,
    STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR,
    STAGE1_HAZARD_ROOM_DISPATCH_ADDR,
    STAGE1_HAZARD_SCANNER_FRONT_ADDR,
    STAGE1_HAZARD_SCANNER_MIDDLE_ADDR,
    STAGE1_HAZARD_SCANNER_SEAM_ADDR,
    STAGE1_HAZARD_SCANNER_TAIL_ADDR,
    STAGE1_HAZARD_START4_EDGE_ADDR,
    STAGE1_HAZARD_START4_HELPER_ADDR,
    STAGE1_HAZARD_TRANSITION_REPAIR_ADDR,
    STAGE1_HAZARD_BANKED_ENTRY_ADDR,
    STAGE1_SOURCE_GENERATION_RST,
    STAGE1_ENTRY_PATCH_BODY_ADDR,
    STAGE1_ENTRY_PATCH_FINISH_ADDR,
    STAGE1_ENTRY_PATCH_GATE_ADDR,
    STAGE1_ENTRY_PATCH_LOWER_ADDR,
    STAGE1_ENTRY_PATCH_TAIL_ADDR,
    WINDOW_ATTR_CLEAR_HELPER_ADDR,
    WRAPPER_ADDR,
    build_cold_stage1_sweep_arm,
    build_later_stage_bg0_arm,
    build_menu_close_native_repair,
    build_oam_wram_copy,
    build_oam_wram_copy_tail,
    build_phased_palette_loader,
    build_stage1_attr_runtime,
    build_stage1_postcopy_scene_guard,
    build_stage1_attr_row_helper,
    build_stage1_attr_row_initializer,
    build_stage1_atomic_attr_stack_vector,
    build_stage1_atomic_wrap,
    build_stage1_entry_attr_patch,
    build_stage1_entry_patch_gate,
    build_stage1_hazard_bank1_copy_routines,
    build_stage1_hazard_bank1_bank14_loader,
    build_stage1_hazard_bank1_loader,
    build_stage1_hazard_bank1_neutral_art,
    build_stage1_hazard_dispatcher,
    build_stage1_hazard_dynamic_scanner,
    build_stage1_hazard_row_helper,
    build_stage1_hazard_row0_transition_repair,
    build_stage1_hazard_room_dispatcher,
    build_stage1_hazard_room12_wall_repair,
    build_stage1_hazard_start4_edge_helpers,
    build_stage1_hazard_transition_repair,
    build_stage1_hazard_banked_entries,
)
from normalize_mgba_state_pc import (  # noqa: E402
    GB_STATE_ROM_CRC,
    GB_STATE_SIZE,
    GB_STATE_TITLE,
    GB_STATE_TITLE_SIZE,
    normalize,
    png_chunks,
    retarget_rom_identity,
    write_png,
)
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_terminal_variants,
    compile_stage1_hazard_variants,
    decode_tile,
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
)
from prototype_ted_expanded_bank import (  # noqa: E402
    STAGE1_WRAM_SCENE_GUARD,
    STAGE1_WRAM_SCENE_GUARD_SOURCE_B,
    STAGE1_WRAM_SCENE_GUARD_SOURCE_C,
)
from stage1_hazard_semantic_row import (  # noqa: E402
    CALLER_RETURNS as SEMANTIC_CALLER_RETURNS,
    HELPER_BANK as SEMANTIC_HELPER_BANK,
    HELPER_ENTRY as SEMANTIC_HELPER_ENTRY,
    LUT_ADDR as SEMANTIC_LUT_ADDR,
    PRIVATE_CONTINUATION as SEMANTIC_PRIVATE_CONTINUATION,
    PRIVATE_RETURN as SEMANTIC_PRIVATE_RETURN,
    RETURN_BRIDGE as SEMANTIC_RETURN_BRIDGE,
    STAGE1_PRIVATE_BANK as SEMANTIC_PRIVATE_BANK,
    build_helper as build_semantic_helper,
    build_lut as build_semantic_lut,
)
from build_stage1_room01_semantic_row_r300 import (  # noqa: E402
    ROOM01_HELPER_ADDR as SEMANTIC_ROOM01_HELPER_ADDR,
    ROOM01_LUT_ADDR as SEMANTIC_ROOM01_LUT_ADDR,
    build_room01_helper as build_semantic_room01_helper,
    build_room01_lut as build_semantic_room01_lut,
)
from build_stage1_effective_row_context_r319 import (  # noqa: E402
    NEW_TRAMPOLINE as SEMANTIC_CONTEXT_TRAMPOLINE,
    OLD_TRAMPOLINE as SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE,
)
from stage1_room01_wall_oracle import (  # noqa: E402
    load_reviewed_wall_contract,
    reviewed_room01_tile_attr_map,
)
from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    BG_TABLE_OFFSET,
    serialized_state,
)


DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
STATE_DIR = ROOT / "save_states_for_claude"
PROBE = Path(__file__).with_name("probe_stage1_spike_palettes.lua")
ROOM01_WALL_FIXTURE = (
    Path(__file__).with_name("fixtures") / "stage1_room01_wall_oracle.json"
)
ROOM01_WALL_FIXTURE_SHA256 = (
    "ec55b653db69d183021a88bf08a3b5b223b1c412c6a7fb1f92b46de0d6c2f894"
)
LIVE_STATE = "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
CEILING_LIVE_STATE = "level1_sara_w_spike_hazard.ss0"
PIXEL_SETTLE_FRAME = 120
STATE_NAMES = (
    "level1_sara_w_spike_hazard.ss0",
    "level1_sara_w_thrusting_spike_hazard.ss0",
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    "v2.26_level1_sara_w_gargoyle_mini_boss.ss0",
)
if SEMANTIC_CONTEXT_TRAMPOLINE != bytes.fromhex(
    "F0 E5 3D C2 00 43 C3 00 45"
):
    raise RuntimeError("effective-room semantic trampoline identity changed")
if SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE != bytes.fromhex(
    "F0 BD 3D C2 00 43 C3 00 45"
):
    raise RuntimeError("legacy row-context trampoline identity changed")


def semantic_expansion_is_exact(rom: bytes) -> bool:
    from build_spike_death_trial import (
        CANDIDATE_SHA as SPIKE_DEATH_SHA,
        authenticated_parent as spike_death_parent,
    )
    if hashlib.sha256(rom).hexdigest() == SPIKE_DEATH_SHA:
        return semantic_expansion_is_exact(spike_death_parent(rom))
    from build_gameover_row_guard import CANDIDATE_SHA, authenticated_parent
    if hashlib.sha256(rom).hexdigest() == CANDIDATE_SHA:
        return semantic_expansion_is_exact(authenticated_parent(rom))
    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    helper = build_semantic_helper()
    lut = build_semantic_lut(table)
    room01_helper = build_semantic_room01_helper(helper)
    room01_lut = build_semantic_room01_lut(lut)
    # r440 adds a bounded room03 span normalizer. Authenticate the complete
    # candidate and cave, retaining every old body/LUT/bridge comparison.
    if hashlib.sha256(rom).hexdigest() in {
        "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074",
        "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b",
        "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9",
        "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
        "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
        "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
        "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
        "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
        "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
        "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
        "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
        "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
        "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        "951e770e4a631f52056d881d7e6577b3d669c9a0566c0310a7299df6a91147d5",
        "2db9f03cd772e75367a219a73610007c2446655cfb7a27873ddaae3a62c816cd",
        "69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197",
        "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
        "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
        "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
        "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
        "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
        "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
        "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
        "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
        "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623",
        "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
        "1b2def345b2656c010ea9711c829bd99500572a25b5d2b35f37124712b862c32",
        "c67cea343c448d35319f5381d0d15674fa1a2744515de3ff45ad20fda06296fa",
    }:
        import build_room03_animation_envelope_r440 as envelope
        code = envelope.helper()
        if rom[envelope.CAVE:envelope.CAVE + len(code)] != code:
            return False
        helper = bytes.fromhex("C3 80 43 00") + helper[4:]
    bank_base = SEMANTIC_HELPER_BANK * 0x4000
    helper_off = bank_base + SEMANTIC_HELPER_ENTRY - 0x4000
    lut_off = bank_base + SEMANTIC_LUT_ADDR - 0x4000
    room01_helper_off = (
        bank_base + SEMANTIC_ROOM01_HELPER_ADDR - 0x4000
    )
    room01_lut_off = bank_base + SEMANTIC_ROOM01_LUT_ADDR - 0x4000
    call_bridges = all(
        rom[
            bank_base + address - 0x4000:
            bank_base + address - 0x4000 + len(SEMANTIC_CONTEXT_TRAMPOLINE)
        ] == SEMANTIC_CONTEXT_TRAMPOLINE
        for address in SEMANTIC_CALLER_RETURNS
    )
    return_bridge_off = bank_base + SEMANTIC_RETURN_BRIDGE - 0x4000
    private_return_off = (
        SEMANTIC_PRIVATE_BANK * 0x4000
        + SEMANTIC_PRIVATE_RETURN - 0x4000
    )
    return (
        rom[helper_off:helper_off + len(helper)] == helper
        and rom[
            room01_helper_off:room01_helper_off + len(room01_helper)
        ] == room01_helper
        and call_bridges
        and rom[return_bridge_off:return_bridge_off + 5] == bytes([
            0x3E, SEMANTIC_PRIVATE_BANK, 0xCD, 0x61, 0x00,
        ])
        and rom[private_return_off:private_return_off + 3] == bytes([
            0xC3, SEMANTIC_PRIVATE_CONTINUATION & 0xFF,
            SEMANTIC_PRIVATE_CONTINUATION >> 8,
        ])
        and rom[lut_off:lut_off + 0x100] == lut
        and rom[room01_lut_off:room01_lut_off + 0x100] == room01_lut
    )


_SEMANTIC_WRITE_OFFSETS = tuple(
    index for index, opcode in enumerate(build_semantic_helper())
    if opcode == 0x22
)
if _SEMANTIC_WRITE_OFFSETS != (0x2E, 0x30, 0x4D, 0x59):
    raise RuntimeError(
        "expanded semantic helper write instruction boundaries changed"
    )
SEMANTIC_WRITE_SITES = tuple(
    helper + offset
    for helper in (SEMANTIC_HELPER_ENTRY, SEMANTIC_ROOM01_HELPER_ADDR)
    for offset in _SEMANTIC_WRITE_OFFSETS
)
HAZARD = load_stage1_hazard_config()
SPIKE_TILES = HAZARD.family_tiles
SPIKE_TOOTH_TILES = HAZARD.tooth_tiles
SPIKE_FIRE_TILES = HAZARD.ring_tiles | HAZARD.body_tiles
SPIKE_CONNECTOR_TILES = HAZARD.connector_tiles
SPIKE_TERMINAL_TILES = HAZARD.terminal_tiles
SPIKE_FREE_TIP_TILES = frozenset(HAZARD.terminal_row_spans)
SPIKE_WALL_TERMINAL_TILES = SPIKE_TERMINAL_TILES - SPIKE_FREE_TIP_TILES
SPIKE_SUPPORT_TILES = HAZARD.support_tiles
SPIKE_TOOTH_PALETTE = HAZARD.tooth_palette
SPIKE_FIRE_PALETTE = HAZARD.body_palette
SPIKE_CONNECTOR_PALETTE = HAZARD.connector_palette
SPIKE_SUPPORT_PALETTE = HAZARD.support_palette
PATTERNED_FLOOR_TILES = frozenset(
    (*range(0x2A, 0x2F), *range(0x3A, 0x3E))
)
ROOM_OFFSET = 0x4400 + 0x1A0
ROOM_SIZE = 24 * 24
EXPECTED_TABLE = _bg_table()
EXPECTED_ATTR_TABLE = bytes(EXPECTED_TABLE)
EXPECTED_HISTOGRAM = dict(sorted(Counter(EXPECTED_ATTR_TABLE).items()))
if hashlib.sha256(ROOM01_WALL_FIXTURE.read_bytes()).hexdigest() != (
    ROOM01_WALL_FIXTURE_SHA256
):
    raise RuntimeError("reviewed room-$01 wall fixture identity changed")
REVIEWED_ROOM_LOCAL_ATTRS = reviewed_room01_tile_attr_map(
    load_reviewed_wall_contract(ROOM01_WALL_FIXTURE)
)
REVIEWED_ROOM_LOCAL_ATTR_SPEC = ",".join(
    f"{room:02X}:{tile:02X}:{attr:02X}"
    for (room, tile), attr in sorted(REVIEWED_ROOM_LOCAL_ATTRS.items())
)
REVIEWED_ROOM_LOCAL_DIVERGENCES = {
    (room, tile): attr
    for (room, tile), attr in REVIEWED_ROOM_LOCAL_ATTRS.items()
    if EXPECTED_ATTR_TABLE[tile] != attr
}
if REVIEWED_ROOM_LOCAL_DIVERGENCES != {
    (0x01, 0x24): 0x06,
    (0x01, 0x27): 0x06,
    (0x01, 0x30): 0x06,
    (0x01, 0x33): 0x06,
}:
    raise RuntimeError(
        "reviewed room-$01 wall policy no longer has the four expected "
        "immutable-LUT divergences"
    )
APPROVED_ART_TILES = HAZARD.art_tiles - {0x60, 0x61, 0x70, 0x71}
APPROVED_ART_SHA256 = (
    "60e07e5b6aff881bb5f628c4df48e3c256e81475afd0b1c6ad0f29b4f0a2d053"
)
# Captured natural animation corpus. Room $02's ceiling cylinder is shifted
# four packed cells from room $12, so each room owns one four-phase tooth
# sample. DC0E contributes the physical-map bit to the runtime key.
CAPTURED_PHASE_TILES = {
    0x02: (0x01, 0x74, 0x66, 0x64),
    0x12: (0x67, 0x75, 0x02, 0x65),
}
CYLINDER_BODY = bytes.fromhex(
    "60 61 6E 6E 6C 6D 6E 6E 6C 6D 6E 62"
)
CYLINDER_LOWER = bytes.fromhex(
    "70 71 7E 7D 7C 7E 7E 7D 7C 7E 7E 72"
)
SERIALIZED_VRAM_OFFSET = 0x400
SERIALIZED_LCDC_OFFSET = 0x340


def refresh_hazard_vram(state: Path, rom: bytes) -> dict[str, object]:
    """Replace stale fixture pixels in both VRAM banks with candidate art."""
    chunks = png_chunks(state.read_bytes())
    indices = [
        index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"
    ]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")
    signed_tiles = not raw[SERIALIZED_LCDC_OFFSET] & 0x10
    changed = 0
    refreshed = bytearray()
    for tile in sorted(HAZARD.family_tiles):
        source = rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        tile_offset = (0x1000 if signed_tiles else 0) + tile * 16
        start = SERIALIZED_VRAM_OFFSET + tile_offset
        before = raw[start:start + 16]
        changed += sum(left != right for left, right in zip(before, source))
        raw[start:start + 16] = source
        refreshed.extend(source)
    bank1_art = bytearray()
    neutral_art = build_stage1_hazard_bank1_neutral_art(rom)
    for tile_index, tile in enumerate((0x01, 0x02, 0x03, 0x04)):
        source = neutral_art[tile_index * 16:(tile_index + 1) * 16]
        start = SERIALIZED_VRAM_OFFSET + 0x2000 + 0x1000 + tile * 16
        before = raw[start:start + 16]
        changed += sum(left != right for left, right in zip(before, source))
        raw[start:start + 16] = source
        bank1_art.extend(source)
    for tile in sorted(SPIKE_TOOTH_TILES):
        source = rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        start = SERIALIZED_VRAM_OFFSET + 0x2000 + 0x1000 + tile * 16
        before = raw[start:start + 16]
        changed += sum(left != right for left, right in zip(before, source))
        raw[start:start + 16] = source
        bank1_art.extend(source)
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(state, chunks)
    return {
        "tile_addressing": "signed" if signed_tiles else "unsigned",
        "tiles": len(HAZARD.family_tiles),
        "changed_bytes": changed,
        "sha256": hashlib.sha256(refreshed).hexdigest(),
        "bank1_sha256": hashlib.sha256(bank1_art).hexdigest(),
    }


def cgb_rgb(word: int) -> tuple[int, int, int]:
    return tuple(
        round(((word >> shift) & 0x1F) * 255 / 31)
        for shift in (0, 5, 10)
    )


def rgb_palette(raw: bytes) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        cgb_rgb(raw[index] | (raw[index + 1] << 8))
        for index in range(0, 8, 2)
    )


# The live oracle revisits each captured frame for several independent pixel
# predicates.  Keep one decoded RGB copy per path so the evidence computation
# remains byte-identical without repeatedly reopening the same PNG.
_RGB_IMAGE_CACHE: dict[str, Image.Image] = {}


def load_rgb_image(path: Path) -> Image.Image:
    key = str(path)
    cached = _RGB_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    with Image.open(path) as source:
        image = source.convert("RGB").copy()
    _RGB_IMAGE_CACHE[key] = image
    return image


def rendered_tile(
    tile: bytes,
    palette: tuple[tuple[int, int, int], ...],
) -> bytes:
    return bytes(channel for pixel in decode_tile(tile) for channel in palette[pixel])


def rendered_hazard_cells(
    path: Path,
    scx: int,
    scy: int,
    patterns: dict[int, dict[bytes, tuple[int, ...]]],
) -> dict[str, object]:
    """Decode aligned native pixels back to candidate hazard tile/palette."""
    image = load_rgb_image(path)
    wrong_teeth = []
    gold_teeth = []
    wrong_terminal_caps = []
    fire_terminal_caps = []
    for y in range((-scy) & 7, image.height - 7, 8):
        for x in range((-scx) & 7, image.width - 7, 8):
            block = image.crop((x, y, x + 8, y + 8)).tobytes()
            wrong = set(patterns[0].get(block, ())) & SPIKE_TOOTH_TILES
            gold = set(patterns[SPIKE_TOOTH_PALETTE].get(block, ())) & SPIKE_TOOTH_TILES
            # A no-accent black/white block can be byte-identical under two
            # palettes. It is not evidence of gray palette-0 tooth pixels.
            wrong -= gold
            if wrong:
                wrong_teeth.append({
                    "x": x, "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(wrong)],
                })
            if gold:
                gold_teeth.append({
                    "x": x, "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(gold)],
                })
            gray_caps = (
                set(patterns[SPIKE_SUPPORT_PALETTE].get(block, ()))
                & SPIKE_TERMINAL_TILES
            )
            fire_caps = (
                set(patterns[SPIKE_FIRE_PALETTE].get(block, ()))
                & SPIKE_TERMINAL_TILES
            )
            gray_caps -= fire_caps
            if gray_caps:
                wrong_terminal_caps.append({
                    "x": x,
                    "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(gray_caps)],
                })
            if fire_caps:
                fire_terminal_caps.append({
                    "x": x,
                    "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(fire_caps)],
                })
    return {
        "path": str(path),
        "scx": scx,
        "scy": scy,
        "wrong_palette0_teeth": wrong_teeth,
        "gold_teeth": gold_teeth,
        "wrong_gray_terminal_caps": wrong_terminal_caps,
        "fire_terminal_caps": fire_terminal_caps,
    }


def oam_rectangles_by_frame(
    trace: str, *, default_height: int = 8,
) -> dict[int, list[dict[str, int]]]:
    """Decode probe OAM receipts into screen-space coverage rectangles."""
    result: dict[int, list[dict[str, int]]] = {}
    for entry in filter(None, trace.split(";")):
        match = re.match(r"f(\d+):(?:h(8|16)|[0-9A-F]{2}):(.*)", entry)
        if not match:
            continue
        frame = int(match.group(1))
        height = int(match.group(2) or default_height)
        rectangles = []
        for slot, x, y, tile, flags in re.findall(
            r"(\d+)/(\d+)/(\d+)/([0-9A-F]{2})/([0-9A-F]{2})",
            match.group(3),
        ):
            left = int(x) - 8
            top = int(y) - 16
            rectangles.append({
                "slot": int(slot),
                "left": left,
                "top": top,
                "right": left + 8,
                "bottom": top + height,
                "tile": int(tile, 16),
                "flags": int(flags, 16),
            })
        result[frame] = rectangles
    return result


def rectangles_intersect(
    left: int, top: int, right: int, bottom: int,
    rectangle: dict[str, int],
) -> bool:
    return (
        left < rectangle["right"] and right > rectangle["left"]
        and top < rectangle["bottom"] and bottom > rectangle["top"]
    )


def recurring_phase_raster_receipt(
    periodic_trace: list[dict[str, object]],
    periodic_map_signatures: dict[int, str],
    periodic_map_cells: dict[int, list[tuple[int, int, int]]],
    periodic_oam: dict[int, list[dict[str, int]]],
    *,
    screenshot_interval: int,
) -> dict[str, object]:
    """Compare exact recurring hazard phases at their rendered BG pixels."""
    disabled = {
        "enabled": False,
        "frames": 0,
        "phase_signatures": 0,
        "recurring_phase_signatures": 0,
        "comparisons": 0,
        "compared_pixels": 0,
        "mismatch_frames": 0,
        "first_mismatch": None,
    }
    if screenshot_interval != 1:
        return disabled

    references: dict[str, dict[str, object]] = {}
    signature_counts: dict[str, int] = {}
    mismatches: list[dict[str, object]] = []
    compared_pixels = 0
    comparisons = 0
    eligible_frames = 0

    def rectangle_covers(
        rectangle: dict[str, int], x: int, y: int
    ) -> bool:
        return (
            rectangle["left"] <= x < rectangle["right"]
            and rectangle["top"] <= y < rectangle["bottom"]
        )

    for item in periodic_trace:
        frame_number = int(item["frame"])
        if frame_number < PIXEL_SETTLE_FRAME:
            continue
        signature = periodic_map_signatures.get(frame_number)
        cells = periodic_map_cells.get(frame_number, [])
        path = Path(str(item["path"]))
        if signature is None or not cells or not path.is_file():
            continue
        pixels = list(load_rgb_image(path).getdata())
        scx, scy = int(item["scx"]), int(item["scy"])
        positions = set()
        for offset, _tile, _attr in cells:
            left = (((offset & 0x1F) * 8) - scx) & 0xFF
            top = (((offset >> 5) * 8) - scy) & 0xFF
            for y in range(top, top + 8):
                for x in range(left, left + 8):
                    if 0 <= x < 160 and 0 <= y < 144:
                        positions.add((x, y))
        if not positions:
            continue
        eligible_frames += 1
        signature_counts[signature] = signature_counts.get(signature, 0) + 1
        previous = references.get(signature)
        current = {
            "frame": frame_number,
            "pixels": pixels,
            "oam": periodic_oam.get(frame_number, []),
        }
        if previous is not None:
            comparisons += 1
            previous_pixels = previous["pixels"]
            previous_oam = previous["oam"]
            current_oam = current["oam"]
            comparable = [
                (x, y) for x, y in positions
                if not any(
                    rectangle_covers(rectangle, x, y)
                    for rectangle in [*previous_oam, *current_oam]
                )
            ]
            compared_pixels += len(comparable)
            changed = [
                (x, y) for x, y in comparable
                if previous_pixels[y * 160 + x] != pixels[y * 160 + x]
            ]
            if changed:
                mismatches.append({
                    "frame": frame_number,
                    "reference_frame": int(previous["frame"]),
                    "changed_pixels": len(changed),
                    "first_xy": list(changed[0]),
                    "path": str(path),
                })
        references[signature] = current
    recurring_signatures = sum(count > 1 for count in signature_counts.values())
    return {
        "enabled": (
            eligible_frames >= 120
            and recurring_signatures >= 4
            and comparisons > 0
            and compared_pixels > 0
        ),
        "frames": eligible_frames,
        "phase_signatures": len(signature_counts),
        "recurring_phase_signatures": recurring_signatures,
        "comparisons": comparisons,
        "compared_pixels": compared_pixels,
        "mismatch_frames": len(mismatches),
        "first_mismatch": mismatches[0] if mismatches else None,
    }


def room_source(path: Path) -> bytes:
    state = serialized_state(path)
    return state[ROOM_OFFSET:ROOM_OFFSET + ROOM_SIZE]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def state_rom_identity_matches(path: Path, rom: bytes) -> bool:
    """Return whether an mGBA state is already bound to this exact ROM."""
    chunks = [
        payload for kind, payload in png_chunks(path.read_bytes())
        if kind == b"gbAs"
    ]
    if len(chunks) != 1:
        return False
    try:
        raw = zlib.decompress(chunks[0])
    except zlib.error:
        return False
    if len(raw) != GB_STATE_SIZE:
        return False
    state_crc = int.from_bytes(
        raw[GB_STATE_ROM_CRC:GB_STATE_ROM_CRC + 4], "little"
    )
    return (
        state_crc == (zlib.crc32(rom) & 0xFFFFFFFF)
        and raw[GB_STATE_TITLE:GB_STATE_TITLE + GB_STATE_TITLE_SIZE]
        == rom[0x0134:0x0134 + GB_STATE_TITLE_SIZE]
    )


def parse_live_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def publication_boundary(rom: bytes) -> dict[str, int | str]:
    """Return the one reviewed physical-page LCDC publication site."""
    from build_spike_death_trial import (
        CANDIDATE_SHA as SPIKE_DEATH_SHA,
        authenticated_parent as spike_death_parent,
    )
    if hashlib.sha256(rom).hexdigest() == SPIKE_DEATH_SHA:
        return publication_boundary(spike_death_parent(rom))
    from build_gameover_row_guard import CANDIDATE_SHA, authenticated_parent
    if hashlib.sha256(rom).hexdigest() == CANDIDATE_SHA:
        # Publisher bytes are untouched; authenticate the complete delta first.
        return publication_boundary(authenticated_parent(rom))
    body = rom[PRIMARY_PUBLISHER_ADDR:PRIMARY_PUBLISHER_END]
    def extras_match(contract: dict[str, object]) -> bool:
        expected_rom = contract.get("rom_sha256")
        if expected_rom is not None and hashlib.sha256(rom).hexdigest() != expected_rom:
            return False
        extras = contract.get("extras")
        if extras is None and "extra" in contract:
            extras = (contract["extra"],)
        if extras is None:
            return True
        return all(
            rom[int(offset):int(offset) + len(expected)] == expected
            for offset, expected in extras
        )

    matches = [
        (name, contract)
        for name, contract in PUBLICATION_VARIANTS.items()
        if body == contract["bytes"]
        and extras_match(contract)
    ]
    if not matches:
        raise RuntimeError("candidate has no reviewed Stage-1 LCDC publisher")
    if len(matches) != 1:
        raise RuntimeError("candidate has ambiguous Stage-1 LCDC publishers")
    name, contract = matches[0]
    return {"variant": name, "pc": int(contract["pc"])}


def semantic_attr_write_receipt(values: dict[str, str]) -> dict[str, object]:
    """Validate unbounded, bank-exact semantic-helper write counters.

    The human-readable trace is intentionally bounded.  It can fill while
    only one physical BG page is hidden, so neither coverage nor the verdict
    may be inferred from its contents.  These counters cover every primary or
    room-$01 clone write-instruction hit and fail closed if any hit is lost,
    bank-ambiguous, outside the two BG maps, or directed at the visible map.
    """
    trace = values["hazard_attr_write_trace"]
    events = tuple(filter(None, trace.split(";")))
    total = int(values["semantic_attr_write_hits"])
    hidden = int(values["hidden_semantic_attr_write_hits"])
    visible = int(values["active_hazard_attr_write_hits"])
    invalid = int(values["semantic_attr_write_invalid_destination_hits"])
    bank_mismatches = int(values["semantic_attr_write_bank_mismatch_hits"])
    installed_sites = int(values["semantic_attr_write_installed_sites"])
    trace_dropped = int(values["hazard_attr_write_trace_dropped"])
    base_hits = {
        "9800": int(values["semantic_attr_write_9800_hits"]),
        "9C00": int(values["semantic_attr_write_9c00_hits"]),
    }
    traced_hidden = sum(event.endswith(":hidden") for event in events)
    traced_visible = sum(event.endswith(":VISIBLE") for event in events)
    traced_invalid = sum(event.endswith(":INVALID") for event in events)
    bases = sorted(base for base, hits in base_hits.items() if hits > 0)
    partition_exact = (
        total > 0
        and hidden + visible + invalid == total
        and sum(base_hits.values()) + invalid == total
        and len(events) + trace_dropped == total
        and traced_hidden <= hidden
        and traced_visible <= visible
        and traced_invalid <= invalid
    )
    clean = (
        partition_exact
        and installed_sites == len(SEMANTIC_WRITE_SITES)
        and bank_mismatches == 0
        and invalid == 0
        and hidden == total
        and visible == 0
        and bases == ["9800", "9C00"]
    )
    return {
        "trace": trace,
        "trace_events": len(events),
        "trace_dropped": trace_dropped,
        "hits": total,
        "hidden_hits": hidden,
        "visible_hits": visible,
        "invalid_destination_hits": invalid,
        "bank_mismatch_hits": bank_mismatches,
        "installed_sites": installed_sites,
        "base_hits": base_hits,
        "bases": bases,
        "partition_exact": partition_exact,
        "clean": clean,
    }


def run_probe_process(command, *, cwd, env, stream, timeout, done_path,
                      report_path, screenshot_path):
    """Reap only our child after a fresh, fully written probe handshake.

    Qt can remain alive after Lua calls quit. The sentinel is written after
    closing the report and saving the terminal screenshot. It is completion
    evidence only: callers still validate every semantic and raster assertion.
    """
    done_path.unlink(missing_ok=True)
    deadline = time.monotonic() + timeout
    terminal_cleanup = False
    timed_out = False
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                          stderr=subprocess.STDOUT) as child:
        try:
            while child.poll() is None:
                if (done_path.is_file()
                        and done_path.read_text().strip() == "probe_finished=1"
                        and report_path.is_file()
                        and "probe_finished=1" in report_path.read_text().splitlines()
                        and screenshot_path.is_file()):
                    # Confirm the PNG is complete before terminating Qt.
                    with Image.open(screenshot_path) as screenshot:
                        screenshot.verify()
                    terminal_cleanup = True
                    child.terminate()
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    child.kill()
                    break
                try:
                    child.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
        finally:
            # Also cover exceptions/interruptions without stranding our child.
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return subprocess.CompletedProcess(command, 124 if timed_out else child.returncode), timed_out, terminal_cleanup


def live_receipt(
    rom: Path,
    state: Path,
    mgba: Path,
    output: Path,
    timeout: float,
    *,
    prefix_name: str = "stage1-spike-live",
    reinitialize: bool = True,
    settle: int = 180,
    input_mask: int = 0,
    post_menu_input_mask: int = -1,
    screenshot_interval: int = 0,
    expected_room: int = 0x03,
    expected_phase_layout: int = 0x12,
    phase_offset: int = -1,
    normalization_writes: tuple[tuple[int, int], ...] = (),
    normalization_bank: int | None = 1,
    expect_scroll: bool = False,
    force_miniboss_frame: int = -1,
    menu_open: bool = False,
    menu_open_frame: int = 160,
    menu_close_frame: int = -1,
    menu_use_frame: int = -1,
    low_health_frame: int = -1,
    menu_anchor_room: int = -1,
    menu_anchor_delay: int = 20,
    trace_routes: bool = True,
    trace_writers: bool = False,
    preserve_machine_state: bool = False,
    preserve_rom_owned_state: bool = False,
    broad_visible_oracle: bool = False,
    mutation_base_rom: Path | None = None,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / prefix_name
    report_path = Path(str(prefix) + ".txt")
    screenshot_path = Path(str(prefix) + ".png")
    log_path = output / "mgba.log"
    for path in (report_path, screenshot_path, log_path):
        path.unlink(missing_ok=True)
    for path in output.glob(prefix.name + "-*.png"):
        path.unlink()
    rom_bytes = rom.read_bytes()
    observer_rom = rom_bytes
    mutation_control = None
    if mutation_base_rom is not None:
        from hazard_mutations_r442 import authenticate
        observer_rom = mutation_base_rom.read_bytes()
        mutation_control = authenticate(observer_rom, rom_bytes)
    expected_publication = publication_boundary(observer_rom)
    # Cross-ROM fixtures serialize the live DA00 helper page.  Retargeting
    # only the ROM CRC is therefore insufficient when a candidate changes the
    # Stage-1 atomic-setup ABI: the new fixed-bank caller would execute the old
    # savestate's DA13 body.  Refresh that exact 14-byte runtime from its
    # candidate-owned bank-13 source before the first instruction executes.
    atomic_source = (
        BANK13 + OAM_PALETTE_RESOLVER_ADDR - 0x4000
        + STAGE1_ATOMIC_SETUP_ADDR - OAM_WRAM_BASE
    )
    atomic_setup = rom_bytes[atomic_source:atomic_source + 14]
    if len(atomic_setup) != 14 or atomic_setup[-1] != 0xC9:
        raise RuntimeError("candidate Stage-1 atomic-setup source is invalid")
    normalized = output / "stage1-spike-current.ss0"
    if preserve_rom_owned_state:
        if normalization_writes or reinitialize or not preserve_machine_state:
            raise ValueError(
                "ROM-owned state preservation forbids normalization writes "
                "and runtime reinitialization"
            )
        shutil.copy2(state, normalized)
        state_chunks = [
            payload for kind, payload in png_chunks(normalized.read_bytes())
            if kind == b"gbAs"
        ]
        if len(state_chunks) != 1:
            raise ValueError("ROM-owned state must contain one gbAs payload")
        try:
            state_raw = zlib.decompress(state_chunks[0])
        except zlib.error as error:
            raise ValueError("ROM-owned state has malformed gbAs data") from error
        if len(state_raw) != GB_STATE_SIZE:
            raise ValueError("ROM-owned state has the wrong serialized size")
        expected_crc = zlib.crc32(rom_bytes) & 0xFFFFFFFF
        state_crc = int.from_bytes(
            state_raw[GB_STATE_ROM_CRC:GB_STATE_ROM_CRC + 4], "little"
        )
        state_title = state_raw[
            GB_STATE_TITLE:GB_STATE_TITLE + GB_STATE_TITLE_SIZE
        ]
        rom_title = rom_bytes[0x0134:0x0134 + GB_STATE_TITLE_SIZE]
        if state_crc != expected_crc or state_title != rom_title:
            raise ValueError(
                "ROM-owned state identity does not exactly match the candidate"
            )
        vram_refresh = {
            "mode": "rom-owned-state-preserved",
            "tiles": 0,
            "changed_bytes": 0,
            "source_state_sha256": digest(state),
            "preserved_state_sha256": digest(normalized),
        }
    else:
        state_writes = [
            *normalization_writes,
            *(
                (STAGE1_ATOMIC_SETUP_ADDR + index, byte)
                for index, byte in enumerate(atomic_setup)
            ),
            (STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR, 0),
        ]
        if preserve_machine_state:
            normalize(
                state, normalized, 0x016C, state_writes, rom,
                preserve_machine=True,
            )
        else:
            normalize(
                state, normalized, 0x016C, state_writes, rom,
                bank=normalization_bank,
            )
        vram_refresh = refresh_hazard_vram(normalized, rom_bytes)
    # Command-line state loading is deliberately stricter than Lua's runtime
    # loader.  Legacy cross-ROM fixtures require the exact $80->$C0 identity
    # conversion; candidate-native fixtures already carry the exact title and
    # CRC and must not be retargeted a second time.
    if (
        not preserve_rom_owned_state
        and not state_rom_identity_matches(normalized, rom_bytes)
    ):
        retarget_rom_identity(normalized, normalized, rom)

    exact_semantic_expansion = semantic_expansion_is_exact(observer_rom)
    expected_bg5 = rom_bytes[
        BG_PALETTE_OFFSET + SPIKE_FIRE_PALETTE * 8:
        BG_PALETTE_OFFSET + (SPIKE_FIRE_PALETTE + 1) * 8
    ]
    expected_bg7 = rom_bytes[
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000):
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000) + 8
    ]
    rendered_palettes = {
        palette: rgb_palette(
            expected_bg7 if palette == SPIKE_TOOTH_PALETTE else
            rom_bytes[
                BG_PALETTE_OFFSET + palette * 8:
                BG_PALETTE_OFFSET + (palette + 1) * 8
            ]
        )
        for palette in (0, SPIKE_FIRE_PALETTE, SPIKE_SUPPORT_PALETTE,
                        SPIKE_TOOTH_PALETTE)
    }
    mutable_patterns: dict[int, dict[bytes, list[int]]] = {
        palette: {} for palette in rendered_palettes
    }
    for palette, colors in rendered_palettes.items():
        for tile in sorted(HAZARD.family_tiles):
            source = rom_bytes[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            pattern = rendered_tile(source, colors)
            mutable_patterns[palette].setdefault(pattern, []).append(tile)
    rendered_patterns = {
        palette: {
            pattern: tuple(tiles) for pattern, tiles in patterns.items()
        }
        for palette, patterns in mutable_patterns.items()
    }
    expected_bg5_words = [
        expected_bg5[index] | (expected_bg5[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    expected_bg7_words = [
        expected_bg7[index] | (expected_bg7[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    # Keep the live oracle on the same canonical neutral-art compiler used by
    # the ROM builder.  The former inline ``(low | high, low & high)`` formula
    # encoded the retired [0,1,1,3] remap and falsely rejected the exact
    # [0,1,3,3] shadow/background fix for tiles $03/$04.
    bank1_art = bytearray(build_stage1_hazard_bank1_neutral_art(rom_bytes))
    for tile in (
        0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
        0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    ):
        source = rom_bytes[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        bank1_art.extend(source)

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "TMPDIR": str((ROOT / "tmp").resolve()),
        "STAGE1_SPIKE_OUT": str(prefix),
        "STAGE1_SPIKE_WATCHDOG": str(prefix) + "-watchdog.txt",
        "PENTA_STATE_FILE": str(normalized.resolve()),
        "PENTA_STATE_PRELOADED": "1",
        "STAGE1_SPIKE_SETTLE": str(settle),
        "STAGE1_SPIKE_REINIT": "1" if reinitialize else "0",
        "STAGE1_SPIKE_REFRESH_CODE": "0" if preserve_rom_owned_state else "1",
        "STAGE1_SPIKE_KEYS": str(input_mask),
        "STAGE1_SPIKE_POST_MENU_KEYS": str(post_menu_input_mask),
        "STAGE1_SPIKE_SCREENSHOT_INTERVAL": str(screenshot_interval),
        "STAGE1_SPIKE_PHASE_OFFSET": str(phase_offset),
        "STAGE1_SPIKE_FORCE_MINIBOSS_FRAME": str(force_miniboss_frame),
        "STAGE1_SPIKE_MENU_OPEN": "1" if menu_open else "0",
        "STAGE1_SPIKE_MENU_OPEN_FRAME": str(menu_open_frame),
        "STAGE1_SPIKE_MENU_CLOSE_FRAME": str(menu_close_frame),
        "STAGE1_SPIKE_MENU_USE_FRAME": str(menu_use_frame),
        "STAGE1_SPIKE_LOW_HEALTH_FRAME": str(low_health_frame),
        "STAGE1_SPIKE_MENU_ANCHOR_ROOM": str(menu_anchor_room),
        "STAGE1_SPIKE_MENU_ANCHOR_DELAY": str(menu_anchor_delay),
        "STAGE1_SPIKE_TRACE_ROUTES": "1" if trace_routes else "0",
        "STAGE1_SPIKE_TRACE_WRITERS": "1" if trace_writers else "0",
        "STAGE1_SPIKE_EXPECTED_LOAD_COUNT": str(
            STAGE1_HAZARD_BANK1_REFRESH_COUNT
        ),
        "STAGE1_SPIKE_EXPECTED_BG5": ",".join(
            f"{word:04X}" for word in expected_bg5_words
        ),
        "STAGE1_SPIKE_EXPECTED_BG7": ",".join(
            f"{word:04X}" for word in expected_bg7_words
        ),
        "STAGE1_SPIKE_EXPECTED_BANK1_ART": bank1_art.hex(),
        "STAGE1_SPIKE_EXPECTED_ATTR_TABLE": EXPECTED_ATTR_TABLE.hex(),
        "STAGE1_SPIKE_EXPECTED_ROOM": str(expected_room),
        "STAGE1_SPIKE_EXPECTED_PUBLICATION_VARIANT": str(
            expected_publication["variant"]
        ),
        "STAGE1_SPIKE_EXPECTED_PUBLICATION_PC": f"{int(expected_publication['pc']):04X}",
        "STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTRS": (
            REVIEWED_ROOM_LOCAL_ATTR_SPEC
        ),
        "STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTR_COUNT": str(
            len(REVIEWED_ROOM_LOCAL_ATTRS)
        ),
        "STAGE1_SPIKE_BROAD_VISIBLE_ORACLE": (
            "1" if broad_visible_oracle else "0"
        ),
        "STAGE1_SPIKE_CODE_BANK": str(
            rom_bytes[STAGE1_HAZARD_PURE_MAP_ADDR + 1]
        ),
        "STAGE1_SPIKE_SEMANTIC_HELPER_BANK": str(SEMANTIC_HELPER_BANK),
        "STAGE1_SPIKE_SEMANTIC_WRITE_SITES": ",".join(
            f"{address:04X}" for address in SEMANTIC_WRITE_SITES
        ),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command: list[str] = []
    if "mgba-qt" in mgba.name:
        command.extend([str(mgba), "--fastforward"])
    else:
        command.append(str(mgba))
    command.extend([
        "-t", str(normalized.resolve()),
        "--script", str(PROBE), str(rom),
    ])
    process_started = time.monotonic()
    with log_path.open("w") as stream:
        completed, timed_out, terminal_cleanup = run_probe_process(
            command, cwd=ROOT, env=environment, stream=stream, timeout=timeout,
            done_path=Path(str(prefix) + ".done"), report_path=report_path,
            screenshot_path=screenshot_path,
        )
    process_seconds = time.monotonic() - process_started
    print(f"{prefix.name}: capture/reap {process_seconds:.2f}s; "
          f"terminal_cleanup={terminal_cleanup}; analyzing raster evidence", flush=True)
    log_text = log_path.read_text(errors="replace")
    qt_teardown_abort = (
        completed.returncode == 134
        and report_path.is_file()
        and screenshot_path.is_file()
        and "pure virtual method called" in log_text
        and "Aborted (core dumped)" in log_text
    )
    qt_teardown_segfault = (
        completed.returncode == 139
        and report_path.is_file()
        and screenshot_path.is_file()
        and log_text.strip() == "Segmentation fault (core dumped)"
    )
    complete_marker = (
        report_path.is_file()
        and "probe_finished=1" in report_path.read_text(errors="replace").splitlines()
    )
    if (
        (
            completed.returncode != 0
            and not terminal_cleanup
            and not qt_teardown_abort
            and not qt_teardown_segfault
            and not timed_out
        )
        or (timed_out and not complete_marker)
        or not report_path.is_file()
        or not screenshot_path.is_file()
    ):
        raise RuntimeError(
            f"live spike probe status={completed.returncode}; see {log_path}"
        )
    values = parse_live_report(report_path)
    if values.get("probe_finished") != "1":
        raise RuntimeError("spike probe report lacks terminal completion marker")
    if values.get("map_owner_publication_variant") != expected_publication["variant"]:
        raise RuntimeError("spike probe publisher variant receipt disagrees with ROM")
    if values.get("map_owner_publication_pc") != f"{expected_publication['pc']:04X}":
        raise RuntimeError("spike probe publisher boundary receipt disagrees with ROM")
    found9800, matched9800 = (
        int(value) for value in values["map9800"].split(",")
    )
    found9c00, matched9c00 = (
        int(value) for value in values["map9c00"].split(",")
    )
    lcdc = int(values["lcdc"], 16)
    active_base = "9c00" if lcdc & 0x08 else "9800"
    active_found, active_matched = (
        (found9c00, matched9c00)
        if active_base == "9c00"
        else (found9800, matched9800)
    )
    actual_bg5 = [int(value, 16) for value in values["bg5"].split(",")]
    actual_bg7 = [int(value, 16) for value in values["bg7"].split(",")]
    tooth_found, tooth_matched = (
        int(value) for value in values["tooth"].split(",")
    )
    tooth_bank1 = int(values["tooth_bank1"])
    static_rows_found, static_rows_matched = (
        int(value) for value in values["static_tooth_rows"].split(",")
    )
    active_static_rows_found, active_static_rows_matched = (
        int(value)
        for value in values["active_static_tooth_rows"].split(",")
    )
    # Low two bits count art uploads; high bits cache the first two stable-map
    # stamps after the immutable art is ready.
    bank1_load_index = int(values["bank1_load_index"], 16) & 0x03
    bank1_art_mismatches = int(values["bank1_art_mismatches"])
    fire_found, fire_matched = (
        int(value) for value in values["fire"].split(",")
    )
    terminal_found, terminal_matched = (
        int(value) for value in values["terminal"].split(",")
    )
    support_found, support_matched = (
        int(value) for value in values["support"].split(",")
    )
    transient_mismatch_frames = int(values["transient_mismatch_frames"])
    inactive_preparation_mismatch_frames = int(
        values["inactive_preparation_mismatch_frames"]
    )
    map_flip_events = int(values.get("map_flip_events", "0"))
    unsafe_map_flip_events = int(values.get("unsafe_map_flip_events", "0"))
    primary_ff97_02_events = int(values.get("primary_ff97_02_events", "0"))
    map_flip_trace = values.get("map_flip_trace", "")
    map_owner_seed_events = int(values.get("map_owner_seed_events", "0"))
    map_owner_publications = int(values.get("map_owner_publications", "0"))
    map_owner_reused_flips = int(values.get("map_owner_reused_flips", "0"))
    map_owner_superseded_arms = int(
        values.get("map_owner_superseded_arms", "0")
    )
    map_owner_invalid_publications = int(
        values.get("map_owner_invalid_publications", "0")
    )
    map_owner_missing_flip_events = int(
        values.get("map_owner_missing_flip_events", "0")
    )
    map_owner_missing_visible_frames = int(
        values.get("map_owner_missing_visible_frames", "0")
    )
    map_owner_live_room_divergence_frames = int(
        values.get("map_owner_live_room_divergence_frames", "0")
    )
    map_owner_pending = int(values.get("map_owner_pending", "0"))
    map_owner_trace = values.get("map_owner_trace", "")
    map_owner_bases = sorted(set(re.findall(
        r":b(9800|9C00):r[0-9A-F]{2}:e\d+:(?:seed|published)",
        map_owner_trace,
    )))
    exact_readable_map_flip_receipts = {
        base: sum(
            trace_base == base
            and stat_mode != "3"
            and tile_mismatches == "0"
            and attr_mismatches == "0"
            and status == "ok"
            for (
                trace_base, stat_mode, tile_mismatches,
                attr_mismatches, status,
            ) in re.findall(
                r":b(9800|9C00):h[0-9A-F]{2}:s([0-3]):"
                r"ly[0-9A-F]{2}:x[0-9A-F]{2}:"
                r"t(\d+):a(\d+):(ok|bad)",
                map_flip_trace,
            )
        )
        for base in ("9800", "9C00")
    }
    miniboss_first_frame = int(values["miniboss_first_frame"])
    palette_mismatch_frames = int(values["palette_mismatch_frames"])
    menu_open_frames = int(values["menu_open_frames"])
    menu_anchor_room = int(values.get("menu_anchor_room", "-1"))
    menu_anchor_frame = int(values.get("menu_anchor_frame", "-1"))
    effective_menu_open_frame = int(
        values.get("effective_menu_open_frame", str(menu_open_frame))
    )
    effective_menu_close_frame = int(
        values.get("effective_menu_close_frame", str(menu_close_frame))
    )
    effective_menu_use_frame = int(
        values.get("effective_menu_use_frame", str(menu_use_frame))
    )
    effective_low_health_frame = int(
        values.get("effective_low_health_frame", str(low_health_frame))
    )
    menu_use_input_frames = int(values.get("menu_use_input_frames", "0"))
    menu_map_alias_frames = int(values.get("menu_map_alias_frames", "0"))
    menu_hud_change_frame = int(values.get("menu_hud_change_frame", "-1"))
    menu_hp_change_frame = int(values.get("menu_hp_change_frame", "-1"))
    menu_a_handler_hits = int(values.get("menu_a_handler_hits", "0"))
    menu_item_dispatch_hits = int(
        values.get("menu_item_dispatch_hits", "0")
    )
    menu_closed_frame = int(values.get("menu_closed_frame", "-1"))
    post_menu_closed_frames = int(
        values.get("post_menu_closed_frames", "0")
    )
    post_menu_input_frames = int(
        values.get("post_menu_input_frames", "0")
    )
    menu_close_repair_hits = int(values.get("menu_close_repair_hits", "0"))
    menu_close_native_tail_hits = int(
        values.get("menu_close_native_tail_hits", "0")
    )
    floor_mismatch_frames = int(values["floor_mismatch_frames"])
    endpoint_mismatch_frames = int(
        values.get("endpoint_mismatch_frames", "0")
    )
    visible_attr_mismatch_frames = int(
        values.get("visible_attr_mismatch_frames", "0")
    )
    post_menu_transient_mismatch_frames = int(
        values.get("post_menu_transient_mismatch_frames", "0")
    )
    post_menu_palette_mismatch_frames = int(
        values.get("post_menu_palette_mismatch_frames", "0")
    )
    post_menu_floor_mismatch_frames = int(
        values.get("post_menu_floor_mismatch_frames", "0")
    )
    post_menu_endpoint_mismatch_frames = int(
        values.get("post_menu_endpoint_mismatch_frames", "0")
    )
    post_menu_visible_attr_mismatch_frames = int(
        values.get("post_menu_visible_attr_mismatch_frames", "0")
    )
    low_health_forced_frames = int(
        values.get("low_health_forced_frames", "0")
    )
    low_health_scene_frames = int(
        values.get("low_health_scene_frames", "0")
    )
    floor_lut_mismatch_frames = int(values["floor_lut_mismatch_frames"])
    atomic_floor_lut_mismatch_hits = int(
        values["atomic_floor_lut_mismatch_hits"]
    )
    active_hazard_attr_write_hits = int(
        values.get("active_hazard_attr_write_hits", "0")
    )
    post_menu_active_hazard_attr_write_hits = int(
        values.get("post_menu_active_hazard_attr_write_hits", "0")
    )
    atomic_path_hits = int(values["atomic_path_hits"])
    hazard_trampoline_hits = int(values.get("hazard_trampoline_hits", "0"))
    hazard_helper_hits = int(values.get("hazard_helper_hits", "0"))
    semantic_writes = semantic_attr_write_receipt(values)
    semantic_attr_write_trace = str(semantic_writes["trace"])
    semantic_attr_write_hits = int(semantic_writes["hits"])
    hidden_semantic_attr_write_hits = int(semantic_writes["hidden_hits"])
    visible_semantic_attr_write_hits = int(semantic_writes["visible_hits"])
    semantic_attr_write_bases = list(semantic_writes["bases"])
    post_miniboss_helper_hits = int(values["post_miniboss_hazard_helper_hits"])
    post_miniboss_row_hits = int(values["post_miniboss_hazard_row_hits"])
    invalid_hazard_row_writes = int(values["invalid_hazard_row_writes"])
    published_rows = set(re.findall(
        r":rowsem:hl([0-9A-F]{4}):c(?:09|0A|0B)",
        values["hazard_event_trace"],
    ))
    if expected_phase_layout not in CAPTURED_PHASE_TILES:
        raise ValueError(
            f"unknown Stage-1 hazard layout ${expected_phase_layout:02X}"
        )
    row_shift = 4 if expected_phase_layout == 0x02 else 0
    reviewed_rows = {
        f"{base + offset:04X}"
        for base in (0x9800, 0x9C00)
        for offset in (0x40 + row_shift, 0xA0 + row_shift)
    }
    rendered_phases: list[dict[str, object]] = []
    for entry in filter(None, values.get("rendered_phase_trace", "").split(";")):
        frame_text, tile_attr, image_path = entry.split(":", 2)
        tile_text, attr_text = tile_attr.split("/", 1)
        rendered_phases.append({
            "frame": int(frame_text.removeprefix("f")),
            "tile": int(tile_text, 16),
            "attr": int(attr_text),
            "path": image_path,
        })
    expected_rendered_phases = set(
        CAPTURED_PHASE_TILES[expected_phase_layout]
    )
    captured_rendered_phases = {
        int(item["tile"]) for item in rendered_phases
    }
    active_reviewed_map_receipts: dict[str, bool] = {}
    phase_floor_cells_reviewed = 0
    phase_floor_attr_mismatch_cells = 0
    phase_images = [
        load_rgb_image(Path(str(item["path"])))
        for item in rendered_phases
        if Path(str(item["path"])).is_file()
    ]
    phase_montage_path = Path(str(prefix) + "-phase-montage.png")
    if phase_images:
        cell_width, cell_height, label_height = 160, 144, 12
        montage = Image.new(
            "RGB", (cell_width * 2, (cell_height + label_height) * 2), "black"
        )
        draw = ImageDraw.Draw(montage)
        for index, (item, phase_image) in enumerate(
            zip(rendered_phases[:4], phase_images[:4])
        ):
            left = (index % 2) * cell_width
            top = (index // 2) * (cell_height + label_height)
            montage.paste(phase_image, (left, top))
            draw.text(
                (left + 2, top + cell_height),
                f"phase {int(item['tile']):02X} frame {int(item['frame'])}",
                fill="white",
            )
        montage.save(phase_montage_path)
    lower_field_metrics = []
    for phase_image in phase_images:
        lower = phase_image.crop((0, 64, 160, 144))
        colors = list(lower.getdata())
        upper = phase_image.crop((0, 0, 160, 64))
        upper_colors = list(upper.getdata())
        lower_field_metrics.append({
            "red": colors.count((255, 0, 0)),
            "yellow": colors.count((255, 255, 0)),
            "upper_red": upper_colors.count((255, 0, 0)),
            "upper_yellow": upper_colors.count((255, 255, 0)),
        })
    periodic_paths = sorted(prefix.parent.glob(prefix.name + "-frame*.png"))
    settled_periodic_paths = [
        path for path in periodic_paths
        if int(path.stem.rsplit("frame", 1)[-1]) >= PIXEL_SETTLE_FRAME
    ]
    phase_scroll = {}
    phase_terminal_cells: dict[int, list[dict[str, int]]] = {}
    for entry in filter(
        None, values.get("rendered_phase_map_trace", "").split(";")
    ):
        map_match = re.match(
            r"f(\d+):[0-9A-F]{2}:([0-9A-F]{4}):"
            r"([0-9A-F]{2}):([0-9A-F]{2}):(.*)",
            entry,
        )
        if map_match:
            frame_number = int(map_match.group(1))
            base = int(map_match.group(2), 16)
            scx = int(map_match.group(3), 16)
            scy = int(map_match.group(4), 16)
            phase_scroll[frame_number] = (scx, scy)
            cells = {
                int(offset, 16): (int(tile, 16), int(attr, 16))
                for offset, tile, attr in re.findall(
                    r"([0-9A-F]{3})/([0-9A-F]{2})/([0-9A-F]{2})",
                    map_match.group(5),
                )
            }
            terminals = []
            for offset, (tile, attr) in cells.items():
                if (tile not in SPIKE_TERMINAL_TILES
                        or attr & 0x07 != SPIKE_FIRE_PALETTE):
                    continue
                x = ((offset & 0x1F) * 8 - scx) & 0xFF
                y = ((offset >> 5) * 8 - scy) & 0xFF
                if x >= 0xF8:
                    x -= 0x100
                if y >= 0xF8:
                    y -= 0x100
                if x < 160 and x + 8 > 0 and y < 144 and y + 8 > 0:
                    terminals.append({"x": x, "y": y, "tile": tile})
            phase_terminal_cells[frame_number] = terminals
            for tile, attr in cells.values():
                if tile in {0x01, 0x02, 0x03, 0x04}:
                    phase_floor_cells_reviewed += 1
                    if attr != 0x00:
                        phase_floor_attr_mismatch_cells += 1
            reviewed_offsets = {
                row + column
                for row in (0x40 + row_shift, 0xA0 + row_shift)
                for column in range(9)
            }
            # Teeth use BG7 plus bank-1 artwork. Retracted floor cells must
            # return fully to BG0/bank 0; permitting BG7 here certified the
            # yellow trails reported on hardware.
            exact = True
            for offset in reviewed_offsets:
                tile_attr = cells.get(offset)
                if tile_attr is None:
                    exact = False
                    break
                tile, attr = tile_attr
                if tile in SPIKE_TOOTH_TILES:
                    exact = exact and attr == 0x0F
                elif tile in {0x01, 0x02, 0x03, 0x04}:
                    exact = exact and attr == 0x00
                else:
                    exact = False
                if not exact:
                    break
            key = f"{base:04X}"
            active_reviewed_map_receipts[key] = (
                active_reviewed_map_receipts.get(key, True) and exact
            )
    periodic_trace = []
    for entry in filter(
        None, values.get("periodic_render_trace", "").split(";")
    ):
        match = re.match(
            r"f(\d+):([0-9A-F]{2}):([0-9A-F]{2}):"
            r"([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):(.*)",
            entry,
        )
        if match:
            periodic_trace.append({
                "frame": int(match.group(1)),
                "scx": int(match.group(2), 16),
                "scy": int(match.group(3), 16),
                "scene": int(match.group(4), 16),
                "room": int(match.group(5), 16),
                "miniboss": int(match.group(6), 16),
                "path": match.group(7),
            })
    periodic_oam = oam_rectangles_by_frame(
        values.get("periodic_render_oam_trace", "")
    )
    periodic_map_signatures: dict[int, str] = {}
    periodic_map_cells: dict[int, list[tuple[int, int, int]]] = {}
    for entry in filter(
        None, values.get("periodic_render_map_trace", "").split(";")
    ):
        match = re.match(
            r"f(\d+):[0-9A-F]{4}:([0-9A-F]{2}):([0-9A-F]{2}):(.*)",
            entry,
        )
        if match:
            frame_number = int(match.group(1))
            # Physical $9800/$9C00 pages alternate by design.  The rendered
            # phase identity is scroll plus exact tile/attribute semantics,
            # independent of which byte-identical physical page owns it.
            periodic_map_signatures[frame_number] = (
                f"{match.group(2)}:{match.group(3)}:{match.group(4)}"
            )
            periodic_map_cells[frame_number] = [
                (int(offset, 16), int(tile, 16), int(attr, 16))
                for offset, tile, attr in re.findall(
                    r"([0-9A-F]{3})/([0-9A-F]{2})/([0-9A-F]{2})",
                    match.group(4),
                )
            ]
    phase_oam = oam_rectangles_by_frame(
        values.get("rendered_phase_oam_trace", "")
    )
    phase_pixel_receipts = []
    for item in rendered_phases:
        frame_number = int(item["frame"])
        path = Path(str(item["path"]))
        if path.is_file() and frame_number in phase_scroll:
            scx, scy = phase_scroll[frame_number]
            decoded = rendered_hazard_cells(
                path, scx, scy, rendered_patterns
            )
            decoded["frame"] = frame_number
            visible = {
                (int(cell["x"]), int(cell["y"]))
                for cell in decoded["fire_terminal_caps"]
            }
            expected = phase_terminal_cells.get(frame_number, [])
            missing = [
                cell for cell in expected
                if (int(cell["x"]), int(cell["y"])) not in visible
            ]
            occluded = [
                cell for cell in missing
                if any(
                    rectangles_intersect(
                        int(cell["x"]), int(cell["y"]),
                        int(cell["x"]) + 8, int(cell["y"]) + 8,
                        rectangle,
                    )
                    for rectangle in phase_oam.get(frame_number, [])
                )
            ]
            decoded["expected_terminal_caps"] = expected
            decoded["occluded_terminal_caps"] = occluded
            decoded["unexplained_missing_terminal_caps"] = [
                cell for cell in missing if cell not in occluded
            ]
            phase_pixel_receipts.append(decoded)
    periodic_pixel_receipts = []
    for item in periodic_trace:
        path = Path(str(item["path"]))
        if path.is_file():
            decoded = rendered_hazard_cells(
                path, int(item["scx"]), int(item["scy"]),
                rendered_patterns,
            )
            decoded.update({
                "frame": item["frame"],
                "scene": f"{int(item['scene']):02X}",
                "room": f"{int(item['room']):02X}",
                "miniboss": f"{int(item['miniboss']):02X}",
            })
            periodic_pixel_receipts.append(decoded)
    pixel_receipts = phase_pixel_receipts + periodic_pixel_receipts
    settled_pixel_receipts = [
        item for item in pixel_receipts
        if int(item["frame"]) >= PIXEL_SETTLE_FRAME
    ]
    wrong_tooth_cells = sum(
        len(item["wrong_palette0_teeth"]) for item in settled_pixel_receipts
    )
    gold_tooth_cells = sum(
        len(item["gold_teeth"]) for item in pixel_receipts
    )
    wrong_terminal_cap_cells = sum(
        len(item["wrong_gray_terminal_caps"])
        for item in settled_pixel_receipts
    )
    # Completed-frame VRAM checks cannot prove that the raster drawn for a
    # recurring hazard phase is stable.  Compare every recurrence of the
    # exact same scroll + tile + attribute signature at the hazard cells.
    # Moving OBJ coverage is excluded from both sides so player/miniboss
    # sprites cannot either create a false mismatch or conceal one.
    recurring_phase_raster = recurring_phase_raster_receipt(
        periodic_trace,
        periodic_map_signatures,
        periodic_map_cells,
        periodic_oam,
        screenshot_interval=screenshot_interval,
    )
    periodic_metrics = []
    for path in periodic_paths:
        periodic = load_rgb_image(path)
        lower_colors = list(periodic.crop((0, 64, 160, 144)).getdata())
        periodic_metrics.append({
            "path": str(path),
            "red": lower_colors.count((255, 0, 0)),
            "yellow": lower_colors.count((255, 255, 0)),
        })

    # A completed-frame VRAM read cannot expose an HBlank-era palette smear:
    # hardware can display the bad scanline and still have the correct final
    # attributes by the frame callback.  For a stationary menu fixture, learn
    # saturated gameplay positions separately for each exact semantic hazard
    # phase, then compare menu/post-close frames only with the same phase.  A
    # union across the whole animation cycle would incorrectly allow a yellow
    # tooth trail merely because that position is valid in a different phase.
    temporal_raster = {
        "enabled": False,
        "baseline_frames": 0,
        "checked_frames": 0,
        "mismatch_frames": 0,
        "baseline_phase_signatures": 0,
        "baseline_observable_pixels": 0,
        "baseline_unobservable_pixels": 0,
        "unmatched_phase_frames": 0,
        "first_mismatch": None,
    }
    if menu_open and broad_visible_oracle and screenshot_interval > 0:
        def screenshot_frame(path: Path) -> int:
            return int(path.stem.rsplit("frame", 1)[-1])

        def saturated(color: tuple[int, int, int]) -> bool:
            return max(color) >= 200 and max(color) - min(color) >= 150

        def oam_covered(frame_number: int, pixel_index: int) -> bool:
            x, y = pixel_index % 160, pixel_index // 160
            return any(
                rectangle["left"] <= x < rectangle["right"]
                and rectangle["top"] <= y < rectangle["bottom"]
                for rectangle in periodic_oam.get(frame_number, [])
            )

        baseline_paths = [
            path for path in periodic_paths
            # The anchor is the moment the input schedule becomes eligible,
            # not the start of the visual baseline.  Starting there left only
            # four frames before SELECT was acknowledged and taught the
            # oracle one of four legitimate cylinder phases.  Learn every
            # settled pre-menu phase instead.
            if PIXEL_SETTLE_FRAME <= screenshot_frame(path)
            < effective_menu_open_frame
        ]
        checked_paths = [
            path for path in periodic_paths
            if screenshot_frame(path) >= effective_menu_open_frame
        ]
        allowed_positions_by_phase: dict[str, set[int]] = {}
        observable_positions_by_phase: dict[str, set[int]] = {}
        for path in baseline_paths:
            frame_number = screenshot_frame(path)
            signature = periodic_map_signatures.get(frame_number)
            if signature is None:
                continue
            pixels = list(load_rgb_image(path).crop((0, 0, 160, 64)).getdata())
            observable_positions_by_phase.setdefault(signature, set()).update(
                index for index in range(len(pixels))
                if not oam_covered(frame_number, index)
            )
            allowed_positions_by_phase.setdefault(signature, set()).update(
                index for index, color in enumerate(pixels)
                if saturated(color) and not oam_covered(frame_number, index)
            )
        mismatch_rows = []
        unmatched_phase_frames = 0
        for path in checked_paths:
            frame_number = screenshot_frame(path)
            signature = periodic_map_signatures.get(frame_number)
            allowed_positions = (
                allowed_positions_by_phase.get(signature)
                if signature is not None else None
            )
            observable_positions = (
                observable_positions_by_phase.get(signature)
                if signature is not None else None
            )
            if allowed_positions is None or observable_positions is None:
                unmatched_phase_frames += 1
                mismatch_rows.append({
                    "frame": frame_number,
                    "pixels": -1,
                    "first_xy": None,
                    "path": str(path),
                    "reason": "semantic hazard phase absent from baseline",
                })
                continue
            pixels = list(load_rgb_image(path).crop((0, 0, 160, 64)).getdata())
            unexpected = [
                index for index, color in enumerate(pixels)
                if index in observable_positions
                and saturated(color) and index not in allowed_positions
                and not oam_covered(frame_number, index)
            ]
            if unexpected:
                mismatch_rows.append({
                    "frame": frame_number,
                    "pixels": len(unexpected),
                    "first_xy": [unexpected[0] % 160, unexpected[0] // 160],
                    "path": str(path),
                })
        temporal_raster = {
            "enabled": len(baseline_paths) >= 32,
            "baseline_frames": len(baseline_paths),
            "checked_frames": len(checked_paths),
            "mismatch_frames": len(mismatch_rows),
            "baseline_phase_signatures": len(allowed_positions_by_phase),
            "baseline_observable_pixels": sum(
                len(positions)
                for positions in observable_positions_by_phase.values()
            ),
            "baseline_unobservable_pixels": sum(
                160 * 64 - len(positions)
                for positions in observable_positions_by_phase.values()
            ),
            "unmatched_phase_frames": unmatched_phase_frames,
            "first_mismatch": mismatch_rows[0] if mismatch_rows else None,
        }
    scroll_montage_path = Path(str(prefix) + "-scroll-montage.png")
    if settled_periodic_paths:
        count = min(16, len(settled_periodic_paths))
        indices = sorted({
            round(index * (len(settled_periodic_paths) - 1) / max(1, count - 1))
            for index in range(count)
        })
        cell_width, cell_height, label_height = 160, 144, 12
        montage = Image.new(
            "RGB", (cell_width * 4, (cell_height + label_height) * 4), "black"
        )
        draw = ImageDraw.Draw(montage)
        for slot, index in enumerate(indices):
            image = load_rgb_image(settled_periodic_paths[index])
            left = (slot % 4) * cell_width
            top = (slot // 4) * (cell_height + label_height)
            montage.paste(image, (left, top))
            draw.text(
                (left + 2, top + cell_height),
                settled_periodic_paths[index].stem.rsplit("-", 1)[-1],
                fill="white",
            )
        montage.save(scroll_montage_path)

    floor_checks = {
        "visible patterned floors never inherit a hazard palette": (
            floor_mismatch_frames == 0
        ),
        "every atomic floor compile reads Dungeon BG0": (
            atomic_floor_lut_mismatch_hits == 0
        ),
    }
    progress_trace = values["progress_trace"]
    expected_live_phase_observed = bool(re.search(
        rf":s(?:02|0A):r{expected_room:02X}:", progress_trace
    ))
    gargoyle_phase_observed = bool(re.search(
        r":s0A:r12:", progress_trace
    ))
    if expect_scroll:
        tile_copy_states = values["tile_copy_states"]
        atomic_source_trace = values["atomic_source_trace"]
        patterned_counts = [
            int(value) for value in re.findall(r":p(\d+):", atomic_source_trace)
        ]
        platform_counts = [
            int(left) + int(right)
            for left, right in re.findall(r":c(\d+):d(\d+):", atomic_source_trace)
        ]
        checks = {
            **floor_checks,
            "scroll receipt holds the exact north input": input_mask == 0x80,
            "north scroll reaches patterned-floor room $05": (
                bool(re.search(r":r05:", progress_trace))
            ),
            "north scroll exercises live Stage-1 scene $0A": (
                bool(re.search(r":s0A:", progress_trace))
            ),
            "regular and Gargoyle layouts both use atomic attributes": (
                "02/01:" in tile_copy_states
                and "0A/01:" in tile_copy_states
                and atomic_path_hits > 0
            ),
            "scroll corpus includes patterned and 4C/4D floor layouts": (
                bool(patterned_counts)
                and max(patterned_counts) >= 200
                and bool(platform_counts)
                and max(platform_counts) >= 100
            ),
            "Stage-1 hazard CRAM does not flicker during north scroll": (
                palette_mismatch_frames == 0
            ),
            "periodic rendered receipt covers the complete north scroll": (
                screenshot_interval > 0
                and len(periodic_paths) >= max(4, settle // screenshot_interval - 1)
                and scroll_montage_path.is_file()
            ),
            "rendered lower field never becomes a red/gold disco floor": (
                bool(periodic_metrics)
                and max(item["red"] for item in periodic_metrics) < 200
                and max(item["yellow"] for item in periodic_metrics) < 700
            ),
        }
    else:
        checks = {
            **floor_checks,
            "historical spike room remains a live Stage-1 phase": (
                expected_live_phase_observed
            ),
            "active map contains the rotating spike family": active_found >= 20,
            "every active-map spike tile uses its YAML material split": (
                active_matched == active_found
            ),
            "visible map contains complete BG7 teeth": (
                tooth_found >= 4 and tooth_matched == tooth_found
            ),
            "every visible tooth phase uses the gold hazard palette": (
                tooth_found > 0 and tooth_matched == tooth_found
            ),
            "both physical maps are observed active with exact tooth colors": (
                all(
                    exact_readable_map_flip_receipts[base] > 0
                    for base in ("9800", "9C00")
                )
            ),
            "all bank-1 neutral/tooth art finished and matches bank 0": (
                bank1_load_index == STAGE1_HAZARD_BANK1_REFRESH_COUNT
                and bank1_art_mismatches == 0
            ),
            "visible map contains BG5 rings and fire body": (
                fire_found >= 4 and fire_matched == fire_found
            ),
            "all four right-wall pole terminal cells use fire BG5": (
                terminal_found >= 4 and terminal_matched == terminal_found
            ),
            "visible support and shadow cells remain metallic BG6": (
                support_found >= 2 and support_matched == support_found
            ),
            "left/right endpoints match tooth/retracted semantics every frame": (
                endpoint_mismatch_frames == 0
            ),
            "every visible animation frame keeps tile and palette atomic": (
                transient_mismatch_frames == 0
            ),
            "hidden-map preparation never leaks through a physical-map flip": (
                transient_mismatch_frames == 0
                and unsafe_map_flip_events == 0
                and all(
                    exact_readable_map_flip_receipts[base] > 0
                    for base in ("9800", "9C00")
                )
            ),
            "live BG5 CRAM matches the candidate": (
                actual_bg5 == expected_bg5_words
            ),
            "live Stage-1 BG7 CRAM matches the YAML hazard row": (
                actual_bg7 == expected_bg7_words
            ),
            "Stage-1 hazard BG5/BG7 never flicker during the sampled interval": (
                palette_mismatch_frames == 0
            ),
            "every recurring semantic spike phase renders identical hazard pixels": (
                recurring_phase_raster["enabled"]
                and recurring_phase_raster["mismatch_frames"] == 0
            ),
            "a semantic hazard publication path is exercised": (
                hazard_trampoline_hits > 0
                and hazard_helper_hits > 0
                and semantic_attr_write_hits > 0
                and semantic_attr_write_bases == ["9800", "9C00"]
                and semantic_writes["partition_exact"] is True
            ),
            "selective row publisher is statically bounded and dynamically exact": (
                exact_semantic_expansion
                and invalid_hazard_row_writes == 0
                and active_hazard_attr_write_hits == 0
                and semantic_writes["clean"] is True
            ),
            "all four live cylinder phases have rendered-frame receipts": (
                captured_rendered_phases == expected_rendered_phases
                and len(phase_images) == 4
                and phase_montage_path.is_file()
            ),
            "normalized fixtures render current candidate hazard art": (
                (
                    preserve_rom_owned_state
                    and vram_refresh["mode"] == "rom-owned-state-preserved"
                    and bank1_load_index == STAGE1_HAZARD_BANK1_REFRESH_COUNT
                    and bank1_art_mismatches == 0
                )
                or vram_refresh["tiles"] == len(HAZARD.family_tiles)
            ),
            "rendered candidate pixels never expose gray palette-0 teeth": (
                bool(pixel_receipts) and wrong_tooth_cells == 0
            ),
            "every rendered phase visibly contains candidate BG7 gold teeth": (
                len(phase_pixel_receipts) == 4
                and all(item["gold_teeth"] for item in phase_pixel_receipts)
            ),
            "every rendered phase shows all four terminal caps in fire BG5": (
                len(phase_pixel_receipts) == 4
                and wrong_terminal_cap_cells == 0
                and all(
                    len(item["expected_terminal_caps"]) >= 4
                    and not item["unexplained_missing_terminal_caps"]
                    and (
                        len(item["fire_terminal_caps"])
                        + len(item["occluded_terminal_caps"])
                    ) >= 4
                    for item in phase_pixel_receipts
                )
            ),
            "rendered cylinder phases visibly contain red and gold material": (
                bool(lower_field_metrics)
                and all(
                    item["upper_red"] >= 100 and item["upper_yellow"] >= 100
                    for item in lower_field_metrics
                )
            ),
            "rendered lower field has no legacy red/gold palette wash": (
                phase_floor_cells_reviewed > 0
                and phase_floor_attr_mismatch_cells == 0
                and floor_mismatch_frames == 0
            ),
        }
        if not trace_routes:
            checks.pop("a semantic hazard publication path is exercised")
            checks.pop(
                "selective row publisher is statically bounded and dynamically exact"
            )
    if input_mask and not expect_scroll:
        checks.update({
            "held combat input naturally starts the Gargoyle": (
                miniboss_first_frame > 0
                and gargoyle_phase_observed
            ),
            "hazard row publisher remains active in the live miniboss scene": (
                post_miniboss_row_hits > 0
                and invalid_hazard_row_writes == 0
            ),
        })
        if screenshot_interval > 0:
            pre_miniboss_pixels = [
                item for item in periodic_pixel_receipts
                if int(item["frame"]) < miniboss_first_frame
            ]
            post_miniboss_pixels = [
                item for item in periodic_pixel_receipts
                if int(item["frame"]) > miniboss_first_frame
            ]
            checks.update({
                "rendered pixel trace brackets the live miniboss transition": (
                    bool(pre_miniboss_pixels) and bool(post_miniboss_pixels)
                    and any(item["gold_teeth"] for item in pre_miniboss_pixels)
                    and any(item["gold_teeth"] for item in post_miniboss_pixels)
                ),
                "post-miniboss raster keeps every decoded tooth on BG7": (
                    all(
                        not item["wrong_palette0_teeth"]
                        for item in post_miniboss_pixels
                    )
                ),
            })
    if menu_open:
        checks.update({
            "every native map flip is transfer-idle and complete": (
                map_flip_events > 0 and unsafe_map_flip_events == 0
            ),
            "primary map publications never require retired FF97 SCX skip": (
                map_flip_events > 0 and primary_ff97_02_events == 0
            ),
            "SELECT opens and holds the native item menu": (
                menu_open_frames >= 120
                and any("/" in item for item in values["menu_state_trace"].split(";"))
            ),
            "frozen item menu never recolors visible Stage-1 floor cells": (
                floor_mismatch_frames == 0
            ),
            "frozen item menu never exposes gray spike teeth": (
                transient_mismatch_frames == 0
                and wrong_tooth_cells == 0
            ),
            "item Window never aliases the visible gameplay BG map": (
                menu_map_alias_frames == 0
            ),
        })
        if menu_use_frame >= 0:
            checks.update({
                "item use input is accepted for six visible-menu frames": (
                    menu_use_input_frames == 6
                ),
                "seeded item crosses the real native item dispatcher": (
                    menu_a_handler_hits == 1
                    and menu_item_dispatch_hits == 1
                    and bool(
                        re.search(
                            r":g00:i(?!00)[0-9A-F]{2}",
                            values.get("menu_selected_item_trace", ""),
                        )
                    )
                ),
                "item-use redraw keeps Window and gameplay maps isolated": (
                    menu_map_alias_frames == 0
                ),
            })
        if menu_close_frame >= 0:
            post_close_pixels = [
                item for item in periodic_pixel_receipts
                if int(item["frame"]) >= menu_closed_frame
            ]
            checks.update({
            "SELECT closes the native item menu on schedule": (
                    menu_closed_frame >= effective_menu_close_frame
                    and post_menu_closed_frames >= 120
                ),
                "menu-close recovery uses the requested movement policy": (
                    input_mask == 0
                    and (
                        post_menu_input_mask <= 0
                        or (
                            post_menu_input_mask > 0
                            and post_menu_input_frames >= 120
                        )
                    )
                ),
                "menu close executes exactly one native hidden-map handoff": (
                    menu_close_repair_hits == 1
                    and menu_close_native_tail_hits == 1
                ),
                "stationary post-menu gameplay has no stale red floor attrs": (
                    post_menu_floor_mismatch_frames == 0
                ),
                "stationary post-menu gameplay keeps BG5/BG7 CRAM stable": (
                    post_menu_palette_mismatch_frames == 0
                ),
                "stationary post-menu hazard tiles and attrs stay atomic": (
                    post_menu_transient_mismatch_frames == 0
                ),
                "left/right spike endpoints stay gold after menu close": (
                    post_menu_endpoint_mismatch_frames == 0
                ),
                "post-menu raster has at least twenty rendered samples": (
                    len(post_close_pixels) >= 20
                ),
                "post-menu rendered frames contain no gray tooth pixels": (
                    bool(post_close_pixels)
                    and all(
                        not item["wrong_palette0_teeth"]
                        for item in post_close_pixels
                    )
                ),
                "semantic hazard attributes never write the visible BG map": (
                    active_hazard_attr_write_hits == 0
                ),
                "menu close never repaints hazards into the visible BG map": (
                    post_menu_active_hazard_attr_write_hits == 0
                ),
            })
    if low_health_frame >= 0:
        checks.update({
            "warning health is held after the menu/item sequence": (
                low_health_forced_frames >= 120
            ),
            "post-menu warning mode leaves floors, endpoints and hazards exact": (
                post_menu_floor_mismatch_frames == 0
                and post_menu_endpoint_mismatch_frames == 0
                and post_menu_transient_mismatch_frames == 0
                and post_menu_palette_mismatch_frames == 0
                and post_menu_visible_attr_mismatch_frames == 0
            ),
        })
    if menu_open and broad_visible_oracle:
        checks[
            "broad visible/map-flip oracle uses pinned room-local wall context"
        ] = (
            digest(ROOM01_WALL_FIXTURE) == ROOM01_WALL_FIXTURE_SHA256
            and len(REVIEWED_ROOM_LOCAL_ATTRS) == 8
            and set(REVIEWED_ROOM_LOCAL_DIVERGENCES) == {
                (0x01, 0x24),
                (0x01, 0x27),
                (0x01, 0x30),
                (0x01, 0x33),
            }
            # The semantic room is owned by the physical page that completed
            # a native copy+flip epoch.  A bare FFBD commit must not retag the
            # still-displayed outgoing page.
            and map_owner_seed_events == 1
            and map_owner_publications > 0
            and map_owner_invalid_publications == 0
            and map_owner_missing_flip_events == 0
            and map_owner_missing_visible_frames == 0
            and map_owner_bases == ["9800", "9C00"]
        )
        checks["frozen item menu keeps every visible BG attribute exact"] = (
            visible_attr_mismatch_frames == 0
        )
        if menu_close_frame >= 0:
            checks[
                "stationary post-menu gameplay keeps every visible BG attribute exact"
            ] = post_menu_visible_attr_mismatch_frames == 0
        checks[
            "phase-aligned rendered raster has no yellow spike trails"
        ] = (
            temporal_raster["enabled"] is True
            and temporal_raster["baseline_phase_signatures"] >= 4
            and temporal_raster["unmatched_phase_frames"] == 0
            and temporal_raster["mismatch_frames"] == 0
        )
    return {
        "state": str(state),
        "state_sha256": digest(state),
        "normalized_state": str(normalized),
        "normalized_vram_refresh": vram_refresh,
        "machine_state_preserved": preserve_machine_state,
        "mutation_control": mutation_control,
        "rom_owned_state_preserved": preserve_rom_owned_state,
        "broad_visible_oracle": broad_visible_oracle,
        "reviewed_room_local_attr_oracle": {
            "fixture": str(ROOM01_WALL_FIXTURE),
            "fixture_sha256": ROOM01_WALL_FIXTURE_SHA256,
            "policy": REVIEWED_ROOM_LOCAL_ATTR_SPEC,
            "entries": len(REVIEWED_ROOM_LOCAL_ATTRS),
            "immutable_lut_divergences": [
                f"{room:02X}:{tile:02X}:{attr:02X}"
                for (room, tile), attr in sorted(
                    REVIEWED_ROOM_LOCAL_DIVERGENCES.items()
                )
            ],
            "candidate_runtime_lut_used_as_oracle": False,
        },
        "report": str(report_path),
        "screenshot": str(screenshot_path),
        "emulator_returncode": completed.returncode,
        "emulator_process_seconds": process_seconds,
        "emulator_terminal_handshake_cleanup": terminal_cleanup,
        "qt_teardown_abort_after_complete_artifacts": qt_teardown_abort,
        "qt_teardown_segfault_after_complete_artifacts": (
            qt_teardown_segfault
        ),
        "active_map": active_base,
        "scene": values["scene"],
        "room": values["room"],
        "map9800": {"found": found9800, "matched": matched9800},
        "map9c00": {"found": found9c00, "matched": matched9c00},
        "tooth": {"found": tooth_found, "matched": tooth_matched},
        "tooth_bank1": tooth_bank1,
        "static_tooth_rows": {
            "found": static_rows_found,
            "matched": static_rows_matched,
        },
        "active_static_tooth_rows": {
            "found": active_static_rows_found,
            "matched": active_static_rows_matched,
        },
        "static_tooth_rows_mismatch_trace": (
            values["static_tooth_rows_mismatch_trace"]
        ),
        "active_reviewed_map_receipts": active_reviewed_map_receipts,
        "exact_readable_map_flip_receipts": exact_readable_map_flip_receipts,
        "compiler_unreadable_scene_frames": int(
            values["compiler_unreadable_scene_frames"]
        ),
        "bank1_load_index": f"{bank1_load_index:02X}",
        "bank1_art_mismatches": bank1_art_mismatches,
        "fire": {"found": fire_found, "matched": fire_matched},
        "terminal": {
            "found": terminal_found,
            "matched": terminal_matched,
        },
        "support": {"found": support_found, "matched": support_matched},
        "transient_mismatch_frames": transient_mismatch_frames,
        "transient_mismatch_trace": values["transient_mismatch_trace"],
        "first_transient_mismatch": values["first_transient_mismatch"],
        "inactive_preparation_mismatch_frames": (
            inactive_preparation_mismatch_frames
        ),
        "map_flip_events": map_flip_events,
        "unsafe_map_flip_events": unsafe_map_flip_events,
        "primary_ff97_02_events": primary_ff97_02_events,
        "map_flip_bases": sorted(set(re.findall(
            r":b(9800|9C00):", values.get("map_flip_trace", "")
        ))),
        "map_flip_trace": map_flip_trace,
        "physical_map_ownership": {
            "initial_room": f"{expected_room:02X}",
            "seed_events": map_owner_seed_events,
            "publications": map_owner_publications,
            "reused_flips": map_owner_reused_flips,
            "superseded_arms": map_owner_superseded_arms,
            "invalid_publications": map_owner_invalid_publications,
            "missing_flip_events": map_owner_missing_flip_events,
            "missing_visible_frames": map_owner_missing_visible_frames,
            "live_room_divergence_frames": (
                map_owner_live_room_divergence_frames
            ),
            "pending": map_owner_pending,
            "owned_bases": map_owner_bases,
            "trace": map_owner_trace,
            "room_source": "FFE5-at-42A7",
            "promotion_boundary": (
                f"bank0:{expected_publication['pc']:04X}-LCDC-write"
            ),
            "publication_variant": expected_publication["variant"],
            "live_ffbd_used_as_oracle": False,
        },
        "inactive_preparation_mismatch_trace": (
            values["inactive_preparation_mismatch_trace"]
        ),
        "miniboss_first_frame": miniboss_first_frame,
        "miniboss_trace": values["miniboss_trace"],
        "progress_trace": values["progress_trace"],
        "palette_mismatch_frames": palette_mismatch_frames,
        "first_palette_mismatch": values["first_palette_mismatch"],
        "menu_open_frames": menu_open_frames,
        "menu_anchor_room": menu_anchor_room,
        "menu_anchor_delay": menu_anchor_delay,
        "menu_anchor_frame": menu_anchor_frame,
        "effective_menu_open_frame": effective_menu_open_frame,
        "effective_menu_close_frame": effective_menu_close_frame,
        "effective_menu_use_frame": effective_menu_use_frame,
        "effective_low_health_frame": effective_low_health_frame,
        "menu_use_input_frames": menu_use_input_frames,
        "menu_map_alias_frames": menu_map_alias_frames,
        "first_menu_map_alias": values.get("first_menu_map_alias", ""),
        "menu_hud_before_use": values.get("menu_hud_before_use", ""),
        "menu_hud_change_frame": menu_hud_change_frame,
        "menu_hp_before_use": values.get("menu_hp_before_use", ""),
        "menu_hp_change_frame": menu_hp_change_frame,
        "menu_hp_after_use": values.get("menu_hp_after_use", ""),
        "menu_a_handler_hits": menu_a_handler_hits,
        "menu_item_dispatch_hits": menu_item_dispatch_hits,
        "menu_selected_item_trace": values.get(
            "menu_selected_item_trace", ""
        ),
        "menu_closed_frame": menu_closed_frame,
        "post_menu_closed_frames": post_menu_closed_frames,
        "post_menu_input_mask": post_menu_input_mask,
        "post_menu_input_frames": post_menu_input_frames,
        "menu_close_repair_hits": menu_close_repair_hits,
        "menu_close_native_tail_hits": menu_close_native_tail_hits,
        "menu_close_trace": values.get("menu_close_trace", ""),
        "menu_state_trace": values["menu_state_trace"],
        "input_trace": values.get("input_trace", ""),
        "floor_mismatch_frames": floor_mismatch_frames,
        "floor_mismatch_trace": values["floor_mismatch_trace"],
        "first_floor_mismatch": values["first_floor_mismatch"],
        "endpoint_mismatch_frames": endpoint_mismatch_frames,
        "visible_attr_mismatch_frames": visible_attr_mismatch_frames,
        "visible_attr_mismatch_trace": values.get(
            "visible_attr_mismatch_trace", ""
        ),
        "first_visible_attr_mismatch": values.get(
            "first_visible_attr_mismatch", ""
        ),
        "endpoint_mismatch_trace": values.get("endpoint_mismatch_trace", ""),
        "first_endpoint_mismatch": values.get("first_endpoint_mismatch", ""),
        "post_menu_transient_mismatch_frames": (
            post_menu_transient_mismatch_frames
        ),
        "post_menu_palette_mismatch_frames": (
            post_menu_palette_mismatch_frames
        ),
        "post_menu_floor_mismatch_frames": post_menu_floor_mismatch_frames,
        "post_menu_endpoint_mismatch_frames": (
            post_menu_endpoint_mismatch_frames
        ),
        "post_menu_visible_attr_mismatch_frames": (
            post_menu_visible_attr_mismatch_frames
        ),
        "temporal_raster": temporal_raster,
        "recurring_phase_raster": recurring_phase_raster,
        "low_health_forced_frames": low_health_forced_frames,
        "low_health_scene_frames": low_health_scene_frames,
        "floor_lut_trace": values["floor_lut_trace"],
        "floor_lut_mismatch_frames": floor_lut_mismatch_frames,
        "atomic_floor_lut_mismatch_hits": atomic_floor_lut_mismatch_hits,
        "active_hazard_attr_write_hits": active_hazard_attr_write_hits,
        "post_menu_active_hazard_attr_write_hits": (
            post_menu_active_hazard_attr_write_hits
        ),
        "hazard_attr_write_trace": values.get("hazard_attr_write_trace", ""),
        "visible_hazard_attr_write_trace": values.get(
            "visible_hazard_attr_write_trace", ""
        ),
        "atomic_path_hits": atomic_path_hits,
        "hazard_trampoline_hits": hazard_trampoline_hits,
        "hazard_helper_hits": hazard_helper_hits,
        "semantic_attr_write_hits": semantic_attr_write_hits,
        "hidden_semantic_attr_write_hits": hidden_semantic_attr_write_hits,
        "visible_semantic_attr_write_hits": visible_semantic_attr_write_hits,
        "semantic_attr_write_bases": semantic_attr_write_bases,
        "semantic_attr_write_counters": {
            key: value for key, value in semantic_writes.items()
            if key != "trace"
        },
        "atomic_source_trace": values["atomic_source_trace"],
        "tile_copy_states": values["tile_copy_states"],
        "post_miniboss_hazard_helper_hits": post_miniboss_helper_hits,
        "post_miniboss_hazard_row_hits": post_miniboss_row_hits,
        "trace_routes": trace_routes,
        "invalid_hazard_row_writes": invalid_hazard_row_writes,
        "published_rows": sorted(published_rows),
        "rendered_phases": rendered_phases,
        "phase_montage": str(phase_montage_path),
        "scroll_montage": str(scroll_montage_path),
        "lower_field_metrics": lower_field_metrics,
        "phase_floor_cells_reviewed": phase_floor_cells_reviewed,
        "phase_floor_attr_mismatch_cells": phase_floor_attr_mismatch_cells,
        "periodic_metrics": periodic_metrics,
        "phase_pixel_receipts": phase_pixel_receipts,
        "periodic_pixel_receipts": periodic_pixel_receipts,
        "rendered_wrong_palette0_tooth_cells": wrong_tooth_cells,
        "rendered_wrong_gray_terminal_cap_cells": wrong_terminal_cap_cells,
        "rendered_bg7_gold_tooth_cells": gold_tooth_cells,
        "bg5": [f"{word:04X}" for word in actual_bg5],
        "bg7": [f"{word:04X}" for word in actual_bg7],
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=STATE_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument(
        "--runtime-only",
        action="store_true",
        help=(
            "diagnostically run live fixtures even when an older candidate "
            "does not match the current source-byte contract"
        ),
    )
    parser.add_argument(
        "--live-state",
        default=LIVE_STATE,
        help=(
            "checked-in state used by both live spike passes; accepts a "
            "path relative to --states"
        ),
    )
    parser.add_argument(
        "--ceiling-state",
        default=CEILING_LIVE_STATE,
        help=(
            "checked-in room-$02 ceiling-cylinder state; accepts a path "
            "relative to --states"
        ),
    )
    parser.add_argument(
        "--live-settle",
        type=int,
        default=180,
        help="frames sampled after current-ROM runtime reinitialization",
    )
    parser.add_argument(
        "--natural-settle",
        type=int,
        default=420,
        help="frames sampled from the untouched checked-in state",
    )
    parser.add_argument(
        "--ceiling-settle",
        type=int,
        default=180,
        help="frames sampled from the current-ROM ceiling-cylinder fixture",
    )
    parser.add_argument(
        "--miniboss-settle",
        type=int,
        default=600,
        help="frames sampled from the active-Gargoyle spike-room fixture",
    )
    parser.add_argument(
        "--scroll-settle",
        type=int,
        default=600,
        help="frames sampled while holding north through the patterned floor",
    )
    parser.add_argument(
        "--scroll-screenshot-interval",
        type=int,
        default=15,
        help="native-frame interval for the deterministic north-scroll receipt",
    )
    parser.add_argument(
        "--keys",
        type=lambda value: int(value, 0),
        default=0,
        help=(
            "controller bit mask held during floor/miniboss passes; the "
            "ceiling animation fixture remains stationary"
        ),
    )
    parser.add_argument(
        "--screenshot-interval",
        type=int,
        default=0,
        help="capture a native frame at this interval (0 disables periodic captures)",
    )
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    rom = rom_path.read_bytes()
    if len(rom) < 0x40000 or len(rom) % 0x4000:
        print(
            f"FAIL: ROM size is {len(rom)}; expected at least 262144 "
            "and a whole number of 16 KiB banks"
        )
        return 1
    # Expanded Ted candidates deliberately mirror the production image into
    # private banks.  Uniqueness assertions below describe the live 256 KiB
    # production address space, not byte patterns in isolated payload banks.
    production_rom = rom[:0x40000]

    rooms = {
        name: room_source((args.states / name).resolve())
        for name in STATE_NAMES
    }
    observed_family = {
        tile
        for room in rooms.values()
        for tile in room
        if 0x60 <= tile <= 0x7F
    }
    cylinder_room = rooms[STATE_NAMES[0]]
    rows = [
        cylinder_room[offset:offset + 24]
        for offset in range(0, ROOM_SIZE, 24)
    ]
    body_rows = [index for index, row in enumerate(rows) if CYLINDER_BODY in row]
    paired_rows = [
        row
        for row in body_rows
        if row + 1 < len(rows) and CYLINDER_LOWER in rows[row + 1]
    ]

    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    exact_semantic_expansion = semantic_expansion_is_exact(rom)
    histogram = dict(sorted(Counter(table).items()))
    stock = STOCK_ROM.read_bytes()
    variants = compile_stage1_hazard_variants(stock, HAZARD)
    terminal_variants = compile_stage1_hazard_terminal_variants(stock, HAZARD)
    candidate_variants = {
        tile: rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        for tile in HAZARD.art_tiles
    }
    candidate_terminal_variants = {
        tile: rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        for tile in SPIKE_FREE_TIP_TILES
    }
    changed_bytes = sum(
        before != after
        for tile in sorted(HAZARD.art_tiles)
        for before, after in zip(
            stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ],
            candidate_variants[tile],
        )
    )
    detached_tooth_accent_pixels = 0
    for tile in sorted(HAZARD.tooth_tiles):
        source_pixels = decode_tile(stock[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ])
        candidate_pixels = decode_tile(candidate_variants[tile])
        rows = HAZARD.tooth_row_spans[tile]
        for index, (source_pixel, candidate_pixel) in enumerate(
            zip(source_pixels, candidate_pixels)
        ):
            x, y = index & 7, index >> 3
            span = rows.get(y)
            inside = bool(span and span[0] <= x < span[1])
            if (
                not inside
                and candidate_pixel != HAZARD.environment_remap[source_pixel]
            ):
                detached_tooth_accent_pixels += 1
    detached_terminal_accent_pixels = 0
    for tile in sorted(SPIKE_FREE_TIP_TILES):
        candidate_pixels = decode_tile(candidate_terminal_variants[tile])
        rows = HAZARD.terminal_row_spans[tile]
        for y, span in rows.items():
            for x in range(span[0]):
                if candidate_pixels[y * 8 + x] != 0:
                    detached_terminal_accent_pixels += 1
    hazard_slot, hazard_palette = load_stage1_hazard_palette(PALETTE_YAML)
    hazard_palette_off = (
        BANK13 + STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000
    )
    loader, loader_ext, copy_cram8, _later_stage_selector = (
        build_phased_palette_loader()
    )
    later_stage_bg0_arm = build_later_stage_bg0_arm()
    loader_off = BANK13 + PALETTE_LOADER_ADDR - 0x4000
    loader_ext_off = BANK13 + PALETTE_LOADER_EXT_ADDR - 0x4000
    copy_cram8_off = BANK13 + PALETTE_COPY_CRAM8_ADDR - 0x4000
    atomic_wrap = build_stage1_atomic_wrap()
    atomic_attr_stack_vector = build_stage1_atomic_attr_stack_vector()
    scanner_front, scanner_middle, scanner_tail, scanner_seam = (
        build_stage1_hazard_dynamic_scanner()
    )
    transition_repair = build_stage1_hazard_transition_repair()
    room12_wall_repair = build_stage1_hazard_room12_wall_repair()
    gap_front, gap_middle, gap_tail = (
        build_stage1_hazard_row0_transition_repair()
    )
    start4_helper, start4_edge = build_stage1_hazard_start4_edge_helpers()
    scanner_blobs = (
        (STAGE1_HAZARD_SCANNER_FRONT_ADDR, scanner_front),
        (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR, scanner_middle),
        (STAGE1_HAZARD_SCANNER_TAIL_ADDR, scanner_tail),
        (STAGE1_HAZARD_SCANNER_SEAM_ADDR, scanner_seam),
        (STAGE1_HAZARD_TRANSITION_REPAIR_ADDR, transition_repair),
        (STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR, room12_wall_repair),
        (STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR, gap_front),
        (STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR, gap_middle),
        (STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR, gap_tail),
        (STAGE1_HAZARD_START4_HELPER_ADDR, start4_helper),
        (STAGE1_HAZARD_START4_EDGE_ADDR, start4_edge),
    )
    production_inline = create_inline_tile_copy_stage1_precomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        external_post_copy_helper_addr=STAGE1_HAZARD_PURE_MAP_ADDR,
        external_attr_stack_helper_rst=STAGE1_SOURCE_GENERATION_RST,
        atomic_group_width=STAGE1_ATOMIC_GROUP_WIDTH,
    )
    postcomputed_inline = create_inline_tile_copy_postcomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        STAGE1_POSTCOPY_GUARD_WRAM_ADDR,
        STAGE1_SOURCE_GENERATION_RST,
    )
    cached_postcomputed_inline = create_inline_tile_copy_postcomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        STAGE1_HAZARD_PURE_MAP_ADDR,
        STAGE1_SOURCE_GENERATION_RST,
    )
    wram_scene_postcomputed_inline = create_inline_tile_copy_postcomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        STAGE1_WRAM_SCENE_GUARD,
        STAGE1_SOURCE_GENERATION_RST,
    )
    buffered_postcomputed_active = (
        rom[0x42A7:0x42A7 + len(postcomputed_inline)]
        == postcomputed_inline
    )
    cached_postcomputed_active = (
        rom[0x42A7:0x42A7 + len(cached_postcomputed_inline)]
        == cached_postcomputed_inline
    )
    wram_scene_postcomputed_active = (
        rom[0x42A7:0x42A7 + len(wram_scene_postcomputed_inline)]
        == wram_scene_postcomputed_inline
    )
    postcomputed_active = (
        buffered_postcomputed_active
        or cached_postcomputed_active
        or wram_scene_postcomputed_active
    )
    active_postcomputed_inline = (
        postcomputed_inline
        if buffered_postcomputed_active
        else wram_scene_postcomputed_inline
        if wram_scene_postcomputed_active
        else cached_postcomputed_inline
    )
    runtime_gate = build_stage1_attr_runtime(
        always_stage1=buffered_postcomputed_active
    )
    postcopy_guard = build_stage1_postcopy_scene_guard()
    production_inline_active = (
        rom[0x42A7:0x42A7 + len(production_inline)]
        == production_inline
    )
    oam_wram_copy = build_oam_wram_copy(
        always_stage1=buffered_postcomputed_active
    )
    oam_wram_tail13, _oam_wram_tail14 = build_oam_wram_copy_tail(
        postcomputed_attrs=postcomputed_active,
    )
    row_init_front, row_init_tail = build_stage1_attr_row_initializer()
    generated_row_helper = build_stage1_attr_row_helper()
    arena_sanitizer_marker = bytes(
        [STAGE1_SOURCE_GENERATION_RST]
        + [0x13] * STAGE1_ATOMIC_GROUP_WIDTH
        + [0x1B, 0x1A, 0x4F, 0x0A, 0xF5] * STAGE1_ATOMIC_GROUP_WIDTH
    )
    oam_wram_copy_off = BANK13 + OAM_WRAM_COPY_ADDR - 0x4000
    oam_wram_tail13_off = BANK13 + OAM_WRAM_COPY_TAIL_ADDR - 0x4000
    # Expanded candidates may keep native bank 14 byte-exact and relocate the
    # complete Stage-1 executable image. The fixed pure-map trampoline is the
    # single source of truth for the selected code bank.
    assert rom[STAGE1_HAZARD_PURE_MAP_ADDR] == 0x3E
    stage1_code_bank_number = rom[STAGE1_HAZARD_PURE_MAP_ADDR + 1]
    assert stage1_code_bank_number in (0x0E, 0x13)
    stage1_code_base = stage1_code_bank_number * 0x4000
    bank1_art_loader_mutable = bytearray(build_stage1_hazard_bank1_loader())
    mapper_sequence = bytes.fromhex("3E 0E C3 61 00")
    mapper_offset = bank1_art_loader_mutable.find(mapper_sequence)
    assert mapper_offset >= 0
    assert bank1_art_loader_mutable.find(
        mapper_sequence, mapper_offset + 1
    ) < 0
    bank1_art_loader_mutable[mapper_offset + 1] = stage1_code_bank_number
    bank1_art_loader = bytes(bank1_art_loader_mutable)
    bank1_art_bank14_loader = build_stage1_hazard_bank1_bank14_loader()
    bank14_copy, bank7_copy, bank7_copy_middle, bank7_copy_tail = (
        build_stage1_hazard_bank1_copy_routines()
    )
    bank1_neutral_art = build_stage1_hazard_bank1_neutral_art(rom)
    dungeon_palette = rom[BG_PALETTE_OFFSET:BG_PALETTE_OFFSET + 8]
    dungeon_colors = rgb_palette(dungeon_palette)
    hazard_colors = rgb_palette(hazard_palette)
    semantic_background_pixels = 0
    semantic_background_mismatch_pixels = 0
    for tile in sorted(HAZARD.tooth_tiles):
        candidate_pixels = decode_tile(candidate_variants[tile])
        baseline_tile = HAZARD.semantic_base_tiles[tile]
        baseline_pixels = decode_tile(stock[
            HAZARD.source_offset + baseline_tile * 16:
            HAZARD.source_offset + (baseline_tile + 1) * 16
        ])
        spans = HAZARD.tooth_row_spans[tile]
        for index, (candidate_pixel, baseline_pixel) in enumerate(zip(
            candidate_pixels, baseline_pixels, strict=True,
        )):
            x, y = index & 7, index >> 3
            span = spans.get(y)
            if span and span[0] <= x < span[1]:
                continue
            semantic_background_pixels += 1
            semantic_background_mismatch_pixels += (
                hazard_colors[candidate_pixel]
                != dungeon_colors[baseline_pixel]
            )
    neutral_background_mismatch_pixels = 0
    for index, tile in enumerate((0x01, 0x02, 0x03, 0x04)):
        candidate_pixels = decode_tile(
            bank1_neutral_art[index * 16:(index + 1) * 16]
        )
        baseline_pixels = decode_tile(stock[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ])
        neutral_background_mismatch_pixels += sum(
            hazard_colors[candidate_pixel] != dungeon_colors[baseline_pixel]
            for candidate_pixel, baseline_pixel in zip(
                candidate_pixels, baseline_pixels, strict=True,
            )
        )
    bank1_art_loader_off = (
        BANK13 + STAGE1_HAZARD_BANK1_LOADER_ADDR - 0x4000
    )
    bank1_art_bank14_loader_off = (
        stage1_code_base + STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR - 0x4000
    )
    entry_patch_gate = build_stage1_entry_patch_gate()
    (
        entry_patch_body,
        entry_patch_tail,
        entry_patch_finish,
        entry_patch_lower,
    ) = build_stage1_entry_attr_patch(table)
    entry_patch_blobs = (
        (STAGE1_ENTRY_PATCH_GATE_ADDR, entry_patch_gate),
        (STAGE1_ENTRY_PATCH_BODY_ADDR, entry_patch_body),
        (STAGE1_ENTRY_PATCH_LOWER_ADDR, entry_patch_lower),
        (STAGE1_ENTRY_PATCH_TAIL_ADDR, entry_patch_tail),
        (STAGE1_ENTRY_PATCH_FINISH_ADDR, entry_patch_finish),
    )
    exact_entry_patch = all(
        rom[
            BANK13 + address - 0x4000:
            BANK13 + address - 0x4000 + len(payload)
        ] == payload
        and production_rom.count(payload) == 1
        for address, payload in entry_patch_blobs
    )
    cold_sweep_arm, cold_sweep_arm_tail = build_cold_stage1_sweep_arm()
    cold_sweep_arm_blobs = (
        (COLD_STAGE1_SWEEP_ARM_ADDR, cold_sweep_arm),
        (COLD_STAGE1_SWEEP_ARM_TAIL_ADDR, cold_sweep_arm_tail),
    )
    wrapper_entry_marker = bytes([
        # Receipt-locked stateful selector: run the complete gameplay BG/OAM
        # pass while a sweep is active, then retain the lightweight attract
        # OBJ path. Death containment exits before this selector is reached.
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xB7,
        0x28, 0x05,
        0xCD, COLORIZE_ADDR & 0xFF, COLORIZE_ADDR >> 8,
        0x18, 0x03,
        0xCD,
        ATTRACT_OBJ_COLORIZER_ADDR & 0xFF,
        ATTRACT_OBJ_COLORIZER_ADDR >> 8,
    ])
    hazard_row_helper, hazard_row_compiler = build_stage1_hazard_row_helper()
    embedded_hazard_helper = bytearray(hazard_row_helper)
    neutral_relative = (
        STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR
        - STAGE1_HAZARD_ROW_HELPER_ADDR
    )
    bank14_copy_relative = (
        STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR
        - STAGE1_HAZARD_ROW_HELPER_ADDR
    )
    embedded_hazard_helper[
        neutral_relative:neutral_relative + len(bank1_neutral_art)
    ] = bank1_neutral_art
    embedded_hazard_helper[
        bank14_copy_relative:bank14_copy_relative + len(bank14_copy)
    ] = bank14_copy
    hazard_room_dispatcher = build_stage1_hazard_room_dispatcher()
    hazard_row_helper_off = (
        stage1_code_base + STAGE1_HAZARD_ROW_HELPER_ADDR - 0x4000
    )
    hazard_row_compiler_off = (
        stage1_code_base + STAGE1_HAZARD_ROW_COMPILER_ADDR - 0x4000
    )
    hazard_dispatcher = build_stage1_hazard_dispatcher()
    hazard_dispatcher_off = BANK13 + LAVA_ATTR_DECIDER_ADDR - 0x4000
    hazard_banked_entry13, hazard_banked_entry14 = (
        build_stage1_hazard_banked_entries()
    )
    private_entry_off = (
        stage1_code_base + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000
    )
    private_guard_off = stage1_code_base + 0x6CCA - 0x4000
    private_scanner_guard_active = (
        rom[private_entry_off:private_entry_off + 3]
        == bytes.fromhex("C3 CA 6C")
        and rom[private_guard_off:private_guard_off + 4]
        == bytes.fromhex("F0 BA B7 C0")
    )
    wram_scene_guard = bytes.fromhex(
        "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
    )
    wram_scene_guard_active = (
        wram_scene_postcomputed_active
        and rom[
            BANK13 + STAGE1_WRAM_SCENE_GUARD_SOURCE_B - 0x4000:
            BANK13 + STAGE1_WRAM_SCENE_GUARD_SOURCE_B - 0x4000 + 7
        ] == wram_scene_guard[:7]
        and rom[
            BANK13 + STAGE1_WRAM_SCENE_GUARD_SOURCE_C - 0x4000:
            BANK13 + STAGE1_WRAM_SCENE_GUARD_SOURCE_C - 0x4000 + 5
        ] == wram_scene_guard[7:]
    )
    phase_keys = {
        room: {
            map_bit: {
                (
                    (tile ^ map_bit)
                    ^ 0x02                  # ordinary Stage-1 D880
                    ^ room
                ) + 1 & 0xFF
                for tile in CAPTURED_PHASE_TILES[room]
            }
            for map_bit in (0x00, 0x80)
        }
        for room in (0x02, 0x12)
    }
    menu_close_native_repair = build_menu_close_native_repair()
    checks = {
        "tracked BG room fixtures cover every 60-7F animation tile": (
            observed_family == SPIKE_TILES
        ),
        "rotating cylinder body is serialized in the packed BG room": (
            bool(paired_rows)
        ),
        "all 24 production source-art variants match the YAML compiler": (
            candidate_variants == variants
        ),
        "the 20 audience-approved variants retain their exact artifact hash": (
            hashlib.sha256(b"".join(
                candidate_variants[tile]
                for tile in sorted(APPROVED_ART_TILES)
            )).hexdigest() == APPROVED_ART_SHA256
        ),
        "duplicate 61/71 body phases exactly match remapped 6E/7E": (
            candidate_variants[0x61] == candidate_variants[0x6E]
            and candidate_variants[0x71] == candidate_variants[0x7E]
        ),
        "production source-art delta is exactly 237 of 384 bytes": (
            changed_bytes == 237 and len(candidate_variants) == 24
        ),
        "tooth color is pixel-contained by every reviewed silhouette mask": (
            detached_tooth_accent_pixels == 0
        ),
        "tooth-cell environment pixels render as exact Dungeon baselines": (
            semantic_background_pixels > 0
            and semantic_background_mismatch_pixels == 0
        ),
        "bank-1 neutral 01-04 render as exact Dungeon baselines": (
            neutral_background_mismatch_pixels == 0
        ),
        "all 4 support and cast-shadow source tiles remain stock": all(
            rom[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ] == stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            for tile in SPIKE_SUPPORT_TILES
        ),
        "base tooth identities select scene-local BG7": all(
            table[tile] == SPIKE_TOOTH_PALETTE
            for tile in SPIKE_TOOTH_TILES
        ),
        "rings and continuous body select fire BG5": all(
            table[tile] == SPIKE_FIRE_PALETTE
            for tile in SPIKE_FIRE_TILES
        ),
        "wall-facing cylinder connector selects fire BG5": all(
            table[tile] == SPIKE_CONNECTOR_PALETTE
            for tile in SPIKE_CONNECTOR_TILES
        ),
        "right-wall pole terminal caps select fire BG5": all(
            table[tile] == HAZARD.terminal_palette
            for tile in SPIKE_TERMINAL_TILES
        ),
        "free-tip cells select fire BG5 instead of gray support BG6": all(
            table[tile] == HAZARD.terminal_palette
            and table[tile] != SPIKE_SUPPORT_PALETTE
            for tile in SPIKE_FREE_TIP_TILES
        ),
        "wall-contact cells select fire BG5 instead of gray support BG6": all(
            table[tile] == HAZARD.terminal_palette
            and table[tile] != SPIKE_SUPPORT_PALETTE
            for tile in SPIKE_WALL_TERMINAL_TILES
        ),
        "free-tip caps match the YAML diagonal silhouette compiler": (
            candidate_terminal_variants == terminal_variants
        ),
        "free-tip BG5 cells have no yellow-capable pixels outside outline": (
            detached_terminal_accent_pixels == 0
        ),
        "wall-contact terminal caps retain native source art": all(
            rom[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ] == stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            for tile in SPIKE_WALL_TERMINAL_TILES
        ),
        "unpainted support and shadow cells remain metallic BG6": all(
            table[tile] == SPIKE_SUPPORT_PALETTE
            for tile in SPIKE_SUPPORT_TILES
        ),
        "2A-3D patterned floor remains on stable Dungeon BG0": all(
            table[tile] == 0
            for tile in PATTERNED_FLOOR_TILES
        ),
        "complete Stage 1 base attribute table equals YAML": (
            table == EXPECTED_ATTR_TABLE
        ),
        "Stage 1 palette histogram is exact": histogram == EXPECTED_HISTOGRAM,
        "candidate embeds the YAML Stage-1 hazard palette row": (
            hazard_slot == SPIKE_TOOTH_PALETTE
            and rom[
                hazard_palette_off:hazard_palette_off + 8
            ] == hazard_palette
        ),
        "candidate embeds the cycle-neutral inline Stage-1 BG7 selector": (
            rom[loader_off:loader_off + len(loader)] == loader
            and rom[
                loader_ext_off:loader_ext_off + len(loader_ext)
            ] == loader_ext
        ),
        "candidate embeds the shared CRAM copier and later-stage BG0 arm": (
            rom[
                copy_cram8_off:copy_cram8_off + len(copy_cram8)
            ] == copy_cram8
            and rom[
                copy_cram8_off + len(copy_cram8):
                copy_cram8_off + len(copy_cram8) + len(later_stage_bg0_arm)
            ] == later_stage_bg0_arm
            and rom[
                copy_cram8_off + len(copy_cram8) + len(later_stage_bg0_arm):
                copy_cram8_off + 18
            ] == bytes(18 - len(copy_cram8) - len(later_stage_bg0_arm))
        ),
        "candidate embeds one scene-gated Stage 1 attr runtime and exact post-copy route": (
            runtime_gate.startswith(bytes.fromhex("FA80D8E6F7FE02"))
            and production_rom.count(runtime_gate) == 1
            and (
                (
                    buffered_postcomputed_active
                    and production_rom.count(postcopy_guard) == 1
                )
                or (
                    cached_postcomputed_active
                    and active_postcomputed_inline.count(bytes([
                        0xCD,
                        STAGE1_HAZARD_PURE_MAP_ADDR & 0xFF,
                        STAGE1_HAZARD_PURE_MAP_ADDR >> 8,
                    ])) == 2
                )
                or wram_scene_guard_active
            )
        ),
        "WRAM-local scene guard clears later-stage dirty latch and tail-enters Stage 1": (
            wram_scene_guard_active
            and active_postcomputed_inline.count(bytes([
                0xCD,
                STAGE1_WRAM_SCENE_GUARD & 0xFF,
                STAGE1_WRAM_SCENE_GUARD >> 8,
            ])) == 2
            and wram_scene_guard[-3:] == bytes([
                0xC3,
                STAGE1_HAZARD_PURE_MAP_ADDR & 0xFF,
                STAGE1_HAZARD_PURE_MAP_ADDR >> 8,
            ])
        ) if wram_scene_postcomputed_active else True,
        "candidate embeds one complete Stage-1 attribute publisher": (
            (
                production_inline_active
                and rom[0x0018:0x0020] == atomic_attr_stack_vector
            )
            or (
                postcomputed_active
                and len(generated_row_helper) == 121
                and generated_row_helper == bytes(
                    opcode
                    for _ in range(24)
                    for opcode in (0x1A, 0x13, 0x4F, 0x0A, 0x22)
                ) + bytes([0xC9])
                and rom[
                    BANK13 + STAGE1_ATTR_ROW_INIT_ADDR - 0x4000:
                    BANK13 + STAGE1_ATTR_ROW_INIT_ADDR - 0x4000
                    + len(row_init_front)
                ] == row_init_front
                and rom[
                    BANK13 + STAGE1_ATTR_ROW_INIT_TAIL_ADDR - 0x4000:
                    BANK13 + STAGE1_ATTR_ROW_INIT_TAIL_ADDR - 0x4000
                    + len(row_init_tail)
                ] == row_init_tail
            )
        ),
        "candidate embeds the exact source-row scanner and transition repairs": (
            all(
                rom[
                    stage1_code_base + address - 0x4000:
                    stage1_code_base + address - 0x4000 + len(payload)
                ] == payload
                for address, payload in scanner_blobs
            )
        ),
        "one-time WRAM initialization crosses banks and returns exactly": (
            rom[
                oam_wram_copy_off:oam_wram_copy_off + len(oam_wram_copy)
            ] == oam_wram_copy
            and oam_wram_copy[-3:] == bytes([
                0xC3,
                OAM_WRAM_COPY_TAIL_ADDR & 0xFF,
                OAM_WRAM_COPY_TAIL_ADDR >> 8,
            ])
            and rom[
                oam_wram_tail13_off:
                oam_wram_tail13_off + 12
            ] == oam_wram_tail13[:12]
        ),
        "captured hazard phase keys are room-aware, nonzero, and disjoint": (
            all(
                len(keys) == len(CAPTURED_PHASE_TILES[room])
                and 0 not in keys
                for room, maps in phase_keys.items()
                for keys in maps.values()
            )
            and all(
                maps[0x00].isdisjoint(maps[0x80])
                for maps in phase_keys.values()
            )
            and phase_keys[0x02][0x00].isdisjoint(
                phase_keys[0x12][0x00]
            )
            and phase_keys[0x02][0x80].isdisjoint(
                phase_keys[0x12][0x80]
            )
        ),
        "candidate embeds the immutable bank-1 tooth art loader": (
            not 0x7200 <= STAGE1_HAZARD_BANK1_LOADER_ADDR < 0x7B00
            and
            rom[
                bank1_art_loader_off:
                bank1_art_loader_off + len(bank1_art_loader)
            ] == bank1_art_loader
            and production_rom.count(bank1_art_loader) == 1
            and rom[
                bank1_art_bank14_loader_off:
                bank1_art_bank14_loader_off + len(bank1_art_bank14_loader)
            ] == bank1_art_bank14_loader
            and rom.count(bank1_art_bank14_loader) == 1
        ),
        "candidate embeds the YAML-asserted hidden Stage-1 entry patch": (
            exact_entry_patch
            and rom[
                BANK13 + WRAPPER_ADDR - 0x4000:
                BANK13 + 0x6F90 - 0x4000
            ].count(wrapper_entry_marker) == 1
            and rom[0x0824:0x0842].count(bytes([
                0xCD, WRAPPER_ADDR & 0xFF, WRAPPER_ADDR >> 8,
            ])) == 1
        ),
        "candidate arms the cold Stage-1 sweep only after art upload 3": (
            all(
                rom[
                    BANK13 + address - 0x4000:
                    BANK13 + address - 0x4000 + len(payload)
                ] == payload
                and production_rom.count(payload) == 1
                for address, payload in cold_sweep_arm_blobs
            )
            and cold_sweep_arm.startswith(bytes([
                0xFA,
                STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
                STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
                0xFE, STAGE1_HAZARD_BANK1_REFRESH_COUNT,
                0xC0,
            ]))
            and cold_sweep_arm_tail == bytes([
                0x7E, 0xFE, 0x7F, 0xC0, 0x36, 0x92, 0xC9,
            ])
            and bank7_copy_tail.startswith(bytes([
                0x01,
                COLD_STAGE1_SWEEP_ARM_ADDR & 0xFF,
                COLD_STAGE1_SWEEP_ARM_ADDR >> 8,
                0xC5,
            ]))
        ),
        "immutable copy routines and neutral art occupy verified ROM slots": (
            rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR - 0x4000
                + len(bank7_copy)
            ] == bank7_copy
            and rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR - 0x4000
                + len(bank7_copy_middle)
            ] == bank7_copy_middle
            and rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR - 0x4000
                + len(bank7_copy_tail)
            ] == bank7_copy_tail
            and rom[
                stage1_code_base
                + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000:
                stage1_code_base
                + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000
                + len(bank1_neutral_art)
            ] == bank1_neutral_art
            and rom[
                stage1_code_base
                + STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR - 0x4000:
                stage1_code_base
                + STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR - 0x4000
                + len(bank14_copy)
            ] == bank14_copy
        ),
        "native hazard source return is no longer phase-hooked": (
            rom[0x13E4] == 0xC9
        ),
        "both completed-copy paths call the post-copy stamper": (
            rom[
                STAGE1_ATOMIC_WRAP_ADDR:
                STAGE1_ATOMIC_WRAP_ADDR + len(atomic_wrap)
            ] == atomic_wrap
            and (
                bytes([
                    0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x02, 0xCC,
                    STAGE1_HAZARD_PURE_MAP_ADDR & 0xFF,
                    STAGE1_HAZARD_PURE_MAP_ADDR >> 8,
                    0xFB, 0xC9,
                ]) in production_inline
                or (
                    postcomputed_active
                    and active_postcomputed_inline.count(bytes([
                        0xCD,
                        (
                            STAGE1_POSTCOPY_GUARD_WRAM_ADDR
                            if buffered_postcomputed_active
                            else STAGE1_WRAM_SCENE_GUARD
                            if wram_scene_postcomputed_active
                            else STAGE1_HAZARD_PURE_MAP_ADDR
                        ) & 0xFF,
                        (
                            STAGE1_POSTCOPY_GUARD_WRAM_ADDR
                            if buffered_postcomputed_active
                            else STAGE1_WRAM_SCENE_GUARD
                            if wram_scene_postcomputed_active
                            else STAGE1_HAZARD_PURE_MAP_ADDR
                        ) >> 8,
                    ])) == 2
                    and bytes([
                        0xC3,
                        STAGE1_ATOMIC_WRAP_ADDR & 0xFF,
                        STAGE1_ATOMIC_WRAP_ADDR >> 8,
                    ]) in active_postcomputed_inline
                )
            )
        ),
        "native menu close tail preserves hidden-map publication order": (
            rom[
                MENU_CLOSE_NATIVE_REPAIR_ADDR:
                MENU_CLOSE_NATIVE_REPAIR_ADDR + len(menu_close_native_repair)
            ] == menu_close_native_repair
            and menu_close_native_repair == bytes.fromhex("AF E0 E4 C9")
        ),
        "candidate embeds the exact expanded semantic helper, mapper entry, and LUT": (
            exact_semantic_expansion
        ),
        "candidate embeds the bounded Stage-1 source-row publisher": (
            rom[
                hazard_row_helper_off:
                hazard_row_helper_off + len(hazard_row_helper)
            ] == embedded_hazard_helper
            and rom[
                hazard_row_compiler_off:
                hazard_row_compiler_off + len(hazard_row_compiler)
            ] == hazard_row_compiler
            and rom.count(hazard_row_compiler) == 1
        ),
        "candidate embeds the spike/Shield room dispatcher": (
            rom[
                stage1_code_base
                + STAGE1_HAZARD_ROOM_DISPATCH_ADDR - 0x4000:
                stage1_code_base
                + STAGE1_HAZARD_ROOM_DISPATCH_ADDR - 0x4000
                + len(hazard_room_dispatcher)
            ] == hazard_room_dispatcher
            and rom.count(hazard_room_dispatcher) == 1
        ),
        "candidate embeds the shared Stage-1/Stage-5 dispatcher": (
            rom[
                hazard_dispatcher_off:
                hazard_dispatcher_off + len(hazard_dispatcher)
            ] == hazard_dispatcher
        ),
        "candidate embeds exact same-address hazard bank selectors": (
            rom[
                BANK13 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000:
                BANK13 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000
                + len(hazard_banked_entry13)
            ] == hazard_banked_entry13
            and (
                rom[
                    private_entry_off:
                    private_entry_off + len(hazard_banked_entry14)
                ] == hazard_banked_entry14
                or private_scanner_guard_active
            )
        ),
    }
    receipt = {
        "rom": str(rom_path),
        "states": list(STATE_NAMES),
        "observed_animation_tiles": [
            f"{tile:02X}" for tile in sorted(observed_family)
        ],
        "cylinder_body_rows": paired_rows,
        "tooth_palette": SPIKE_TOOTH_PALETTE,
        "fire_palette": SPIKE_FIRE_PALETTE,
        "support_palette": SPIKE_SUPPORT_PALETTE,
        "connector_palette": SPIKE_CONNECTOR_PALETTE,
        "art_tiles": [f"{tile:02X}" for tile in sorted(HAZARD.art_tiles)],
        "art_changed_bytes": changed_bytes,
        "detached_tooth_accent_pixels": detached_tooth_accent_pixels,
        "detached_terminal_accent_pixels": (
            detached_terminal_accent_pixels
        ),
        "terminal_art_tiles": [
            f"{tile:02X}" for tile in sorted(SPIKE_FREE_TIP_TILES)
        ],
        "semantic_background_pixels": semantic_background_pixels,
        "semantic_background_mismatch_pixels": (
            semantic_background_mismatch_pixels
        ),
        "neutral_background_mismatch_pixels": (
            neutral_background_mismatch_pixels
        ),
        "hazard_palette_source": (
            f"bank13:{STAGE1_HAZARD_BG7_SOURCE_ADDR:04X}"
        ),
        "hazard_palette": hazard_palette.hex(),
        "stage1_code_bank": stage1_code_bank_number,
        "selector": f"inline bank13:{PALETTE_LOADER_EXT_ADDR:04X}",
        "private_scanner_guard_active": private_scanner_guard_active,
        "wram_scene_guard_active": wram_scene_guard_active,
        "cram8_copier": f"bank13:{PALETTE_COPY_CRAM8_ADDR:04X}",
        "table_histogram": {str(key): value for key, value in histogram.items()},
        "expected_table_histogram": {
            str(key): value for key, value in EXPECTED_HISTOGRAM.items()
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    static_passed = receipt["passed"]
    if args.runtime_only:
        receipt["static_contract_passed"] = static_passed
        receipt["runtime_only"] = True
        receipt["passed"] = True
    live = None
    natural_live = None
    ceiling_live = None
    miniboss_live = None
    floor_scroll = None
    if not args.static_only and receipt["passed"]:
        if not args.mgba.is_file():
            print(f"FAIL: guarded mGBA frontend not found: {args.mgba}")
            return 1
        live_state = Path(args.live_state)
        if not live_state.is_absolute():
            live_state = args.states / live_state
        live_state = live_state.resolve()
        if not live_state.is_file():
            print(f"FAIL: live spike state not found: {live_state}")
            return 1
        ceiling_state = Path(args.ceiling_state)
        if not ceiling_state.is_absolute():
            ceiling_state = args.states / ceiling_state
        ceiling_state = ceiling_state.resolve()
        if not ceiling_state.is_file():
            print(f"FAIL: ceiling spike state not found: {ceiling_state}")
            return 1
        if args.output:
            # The matrix runs this verifier twice with different input/settle
            # contracts.  Namespace every runtime corpus by its receipt stem
            # so a later gate cannot overwrite the evidence named by an
            # earlier JSON receipt.
            runtime_root = args.output.parent / args.output.stem
            live_output = runtime_root / "stage1-spike-live"
            live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                live_output,
                args.timeout,
                settle=args.live_settle,
                input_mask=args.keys,
                screenshot_interval=(args.screenshot_interval or 15),
            )
            natural_live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                runtime_root / "stage1-spike-natural",
                args.timeout,
                prefix_name="stage1-spike-natural",
                reinitialize=False,
                settle=args.natural_settle,
                input_mask=args.keys,
                screenshot_interval=args.screenshot_interval,
            )
            ceiling_live = live_receipt(
                rom_path,
                ceiling_state,
                args.mgba.resolve(),
                runtime_root / "stage1-spike-ceiling",
                args.timeout,
                prefix_name="stage1-spike-ceiling",
                settle=args.ceiling_settle,
                input_mask=0,
                screenshot_interval=args.screenshot_interval,
                expected_room=0x02,
                expected_phase_layout=0x02,
                normalization_writes=((0xD880, 0x02),),
                normalization_bank=1,
            )
            miniboss_live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                runtime_root / "stage1-spike-miniboss",
                args.timeout,
                prefix_name="stage1-spike-miniboss",
                settle=args.miniboss_settle,
                input_mask=0,
                screenshot_interval=(args.screenshot_interval or 15),
                expected_room=0x03,
                force_miniboss_frame=200,
                trace_routes=False,
            )
            floor_scroll = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                runtime_root / "stage1-floor-scroll",
                args.timeout,
                prefix_name="stage1-floor-scroll",
                reinitialize=False,
                settle=args.scroll_settle,
                input_mask=0x80,
                screenshot_interval=args.scroll_screenshot_interval,
                expect_scroll=True,
            )
        else:
            with tempfile.TemporaryDirectory(
                prefix="penta-spike-live-", dir=ROOT / "tmp",
            ) as name:
                live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    settle=args.live_settle,
                    input_mask=args.keys,
                    screenshot_interval=(args.screenshot_interval or 15),
                )
                natural_live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-natural",
                    reinitialize=False,
                    settle=args.natural_settle,
                    input_mask=args.keys,
                    screenshot_interval=args.screenshot_interval,
                )
                ceiling_live = live_receipt(
                    rom_path,
                    ceiling_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-ceiling",
                    settle=args.ceiling_settle,
                    input_mask=0,
                    screenshot_interval=args.screenshot_interval,
                    expected_room=0x02,
                    expected_phase_layout=0x02,
                    normalization_writes=((0xD880, 0x02),),
                    normalization_bank=1,
                )
                miniboss_live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-miniboss",
                    settle=args.miniboss_settle,
                    input_mask=0,
                    screenshot_interval=(args.screenshot_interval or 15),
                    expected_room=0x03,
                    force_miniboss_frame=200,
                    trace_routes=False,
                )
                floor_scroll = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-floor-scroll",
                    reinitialize=False,
                    settle=args.scroll_settle,
                    input_mask=0x80,
                    screenshot_interval=args.scroll_screenshot_interval,
                    expect_scroll=True,
                )
                live["normalized_state"] = "temporary"
                live["report"] = "temporary"
                live["screenshot"] = "temporary"
                natural_live["normalized_state"] = "temporary"
                natural_live["report"] = "temporary"
                natural_live["screenshot"] = "temporary"
                ceiling_live["normalized_state"] = "temporary"
                ceiling_live["report"] = "temporary"
                ceiling_live["screenshot"] = "temporary"
                miniboss_live["normalized_state"] = "temporary"
                miniboss_live["report"] = "temporary"
                miniboss_live["screenshot"] = "temporary"
                floor_scroll["normalized_state"] = "temporary"
                floor_scroll["report"] = "temporary"
                floor_scroll["screenshot"] = "temporary"
        receipt["live"] = live
        receipt["natural_live"] = natural_live
        receipt["ceiling_live"] = ceiling_live
        # This route deliberately toggles the exact three Gargoyle scene bytes
        # while a real cylinder is visible. It catches scene/palette overlays
        # without pretending that the source room itself is a boss room. The
        # north-scroll route separately reaches the real scene-$0A room-$05.
        miniboss_live["checks"].pop(
            "every visible tooth phase uses the immutable bank-1 cell", None
        )
        miniboss_live["checks"].pop(
            "both physical maps are observed active with exact tooth colors",
            None,
        )
        miniboss_live["checks"].pop(
            "all bank-1 neutral/tooth art finished and matches bank 0",
            None,
        )
        miniboss_live["checks"].update({
            "Gargoyle scene overlay is applied in hazard room $03 at frame 200": (
                miniboss_live["scene"] == "0A"
                and miniboss_live["room"] == "03"
                and miniboss_live["miniboss_first_frame"] == 200
            ),
            "Gargoyle scene overlay keeps post-scene stamps exact": (
                miniboss_live["scene"] == "0A"
                and miniboss_live["transient_mismatch_frames"] == 0
                and miniboss_live["palette_mismatch_frames"] == 0
                and miniboss_live["rendered_wrong_palette0_tooth_cells"] == 0
            ),
            "Gargoyle raster brackets scene $02 to $0A with gold teeth": (
                any(
                    int(item["frame"]) < 200
                    and item.get("scene") == "02"
                    and item["gold_teeth"]
                    for item in miniboss_live["periodic_pixel_receipts"]
                )
                and any(
                    int(item["frame"]) > 200
                    and item.get("scene") == "0A"
                    and item["gold_teeth"]
                    for item in miniboss_live["periodic_pixel_receipts"]
                )
            ),
            "Gargoyle overlay raster has no decoded gray teeth": (
                miniboss_live["rendered_wrong_palette0_tooth_cells"] == 0
            ),
        })
        miniboss_live["passed"] = all(miniboss_live["checks"].values())
        receipt["miniboss_live"] = miniboss_live
        receipt["floor_scroll"] = floor_scroll
        receipt["passed"] = (
            receipt["passed"]
            and live["passed"]
            and natural_live["passed"]
            and ceiling_live["passed"]
            and miniboss_live["passed"]
            and floor_scroll["passed"]
        )
        if args.runtime_only:
            receipt["runtime_passed"] = receipt["passed"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")

    # ``--runtime-only`` is the documented escape hatch for exercising the
    # live raster/oracle against a newer candidate whose static source-byte
    # contract has not yet been taught that revision.  Preserve those static
    # failures in ``static_contract_passed`` above, but do not turn a passing
    # runtime diagnostic into a command failure because of them.
    failed = (
        [] if args.runtime_only
        else [name for name, passed in checks.items() if not passed]
    )
    if live:
        failed.extend(
            name for name, passed in live["checks"].items() if not passed
        )
    if natural_live:
        failed.extend(
            "untouched state: " + name
            for name, passed in natural_live["checks"].items()
            if not passed
        )
    if ceiling_live:
        failed.extend(
            "ceiling fixture: " + name
            for name, passed in ceiling_live["checks"].items()
            if not passed
        )
    if miniboss_live:
        failed.extend(
            "miniboss fixture: " + name
            for name, passed in miniboss_live["checks"].items()
            if not passed
        )
    if floor_scroll:
        failed.extend(
            "north-scroll fixture: " + name
            for name, passed in floor_scroll["checks"].items()
            if not passed
        )
    if failed:
        print("FAIL: " + "; ".join(failed))
        return 1
    print(
        "PASS: tracked room sources prove BG-only 60-7F spike animation; "
        "24 YAML-compiled art variants use BG7 teeth + BG5 rings/body/wall "
        "connector + BG6 supports"
        + (
            "; current-ROM mGBA confirms the floor and ceiling cylinders, "
            "complete animation palettes, CRAM, and the north-scroll floor."
            if live else "."
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
