from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/diagnostics/build_stage4_delay_trim_r344.py"
SPEC = importlib.util.spec_from_file_location("build_stage4_delay_trim_r344", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
r344 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r344)


def test_r344_changes_only_stage4_call_operand_and_checksums() -> None:
    source = r344.BASE.read_bytes()
    candidate, receipt = r344.build(source)
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    call_operand = r344.bank_offset(r344.OVERLAY_BANK, r344.CALL_SOURCE_ADDR) + 1
    assert changed - r344.CHECKSUM_OFFSETS == {call_operand}
    assert receipt["isolation"]["stage1_functional_bytes_changed"] == 0


def test_r344_delay_target_executes_four_nops_and_same_ret() -> None:
    source = r344.BASE.read_bytes()
    candidate, receipt = r344.build(source)
    call = r344.bank_offset(r344.OVERLAY_BANK, r344.CALL_SOURCE_ADDR)
    delay = r344.bank_offset(r344.OVERLAY_BANK, r344.DELAY_SOURCE_ADDR)
    assert candidate[call:call + 3] == bytes.fromhex("CD 0F DB")
    assert candidate[delay + 2:delay + 7] == bytes.fromhex("00 00 00 00 C9")
    assert receipt["timing"]["saved_t_cycles_per_hit"] == 8


def test_r344_rejects_a_non_exact_base() -> None:
    source = bytearray(r344.BASE.read_bytes())
    source[0x200] ^= 1
    try:
        r344.build(bytes(source))
    except AssertionError as error:
        assert "wrong exact r343 base" in str(error)
    else:
        raise AssertionError("r344 accepted a non-exact base")
