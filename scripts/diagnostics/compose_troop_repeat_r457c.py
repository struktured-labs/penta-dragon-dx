"""Troop-only exact-repeat pacing repair.

The original 576-cell copier is skipped on semantic-cache exact repeats.
Wait for 120 visible-line mode-3 exits only in Troop, compensating that path
without reintroducing tile/attribute publication. LCD-off calls never wait.
Calibrated by independent 2800-frame native publication cadence captures.
"""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from compose_boss_sync_dma_r454 import off, update_checksums

BASE_SHA = '69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722'
WINDOWS = 120
ENTRY = 0x60B4
CAVE = 0x6157
RAW_CAVE = 0x617D


def wait_code():
    # Branches to XOR A;RET at +36. BC saved across the complete wait;
    # DE/HL/SP and IME unchanged. No memory writes except paired stack save.
    return bytes.fromhex(
        'FA80D8 FE11 201D F040 CB7F 2817 C5 0678 '
        'F041 E603 FE03 20F8 F041 E603 FE03 28F8 05 20ED C1 AF C9')


def patches():
    return (
        (0x60A3, b'\x12', b'\x13'),
        (ENTRY, bytes.fromhex('AFC97A7716021814'),
         bytes.fromhex('C35761C37D610000')),
        (CAVE, b'\xff' * 45,
         wait_code() + bytes.fromhex('7A771602C3D060')),
    )


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r456d base')
    result = bytearray(source)
    for address, before, after in patches():
        start = off(20, address)
        if len(before) != len(after) or source[start:start+len(before)] != before:
            raise ValueError(f'preimage mismatch at bank20:{address:04X}')
        result[start:start+len(after)] = after
    update_checksums(result)
    return bytes(result)
