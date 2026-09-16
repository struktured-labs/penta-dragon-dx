#!/usr/bin/env python3
"""expected_bank31(): deterministic bank31 image for the r-series head = FF plus the ORDERED written diffs of the
scene-0B builder chain. Each step replays the checked-in builder on its own recorded base (BASE_SHA256 / BASE, receipt via
BASE_RECEIPT, rejected-run artifacts where needed); base and output are pinned to full sha256 constants and the build FAILS
on drift. No candidate is inspected while assembling; the CLI compare happens only at the end. Local historical artifacts are required; no emulator.
"""
import contextlib, glob, hashlib, inspect, io, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
BS = 0x4000; BANK = 31
CHAIN = [
    ("build_stage1_live_menu_selector_r290", "559e9aa7a81985dd8639ce70d830b9799faebb4f9e27ceec55e2ce0fb086d905", "48582bed3b9c9746588de9d2de695927788b7b07a511b817da0cb36932d87736"),
    ("build_stage1_room01_semantic_row_r300", "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1", "abc06464cb331fb93da5b7a573374775896306b3aefdbe7908280dea70edf3d7"),
    ("build_stage1_unified_scene0b_r305", "1137bcd557c7ea08f3e57c1f9b4a69fcec41c080ae817fbb139563509c4b08fe", "9c83a6937a1b71f2b4d0a6628fa3022d8f46f89e46c7aafa23a61a8d9166ce13"),
    ("build_stage1_scene0b_runtime_selfheal_r313", "dca72f535850d4445fc8f27d032628e63b1a9b7dee0f8012fbfee9b69c4a1951", "07e12b47c1561822c7dbe2c9f7d739c418ad6fcbb1822d2fa06726c705ec82e8"),
    ("build_stage1_scene0b_publication_commit_r314", "07e12b47c1561822c7dbe2c9f7d739c418ad6fcbb1822d2fa06726c705ec82e8", "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303"),
    ("build_stage1_selector_latch_relocation_r316", "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303", "1373479e5a63c1adfa958ae1e278d99d32032b1d3d08386fc3a4d7641496dc2e"),
    ("build_stage1_selector_latch_cold_init_r317", "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303", "77e491aa7e34711a245f0586c2434461fc6c8d3e5fad1bca0b3b27fbcfb43da0"),
    ("build_stage1_effective_row_context_r319", "909d7ee16bbf5080fd9992567bbe784e6df3234a08f9bde07ff7a10b2f729abb", "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db"),
    ("build_stage1_atomic_presentation_commit_r320", "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db", "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7"),
    ("build_stage1_scene0b_admission_art_repair_r336", "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7", "484cd678bd6724f7ab9c128a985a0a50db1c523ad406103a8f57bd84784f4611"),
    ("build_stage1_hazard_terminal_resume_r342", "30ba055bc4cdd7468994d8dbe017a9c73ec82d09184f792e690ffd22a95e73cf", "84bf020e4a9006e0ce9a3e79fec6687a281620108d5337ab8fddb99d0093dd1f"),
    ("build_stage1_hazard_terminal_silhouette_r343", "84bf020e4a9006e0ce9a3e79fec6687a281620108d5337ab8fddb99d0093dd1f", "df359624edb86adfdc88d78e81b4a9d7c8e251956fb29512e2a0402b6c604d48"),
    ("build_stage1_menu_close_atomic_hide_r364", "9a85f55b87f3450cd279556a17ed6bb6865298dc73b327fdbba70fdf0bc4a030", "3b9f67ea25e65d40cc383e7af319b35bded7083143f3a1efbf2c69c42b48beb2"),
]
EXTRA_NAMES = ("REJECTED_LIVE_RECEIPT", "REJECTED_CHR_DUMP", "REJECTED_PLANE_DUMP", "REJECTED_PLANE_METADATA")
class Drift(AssertionError): pass
def _candidate_index():
    idx = {}
    for p in glob.glob(str(ROOT / "tmp/*/candidate.gb")) + glob.glob(str(ROOT / "tmp/title-nightfall-port/*/candidate.gb")):
        try: idx.setdefault(hashlib.sha256(Path(p).read_bytes()).hexdigest(), p)
        except OSError: pass
    return idx
def _resolve_base(mod, pinned, idx):
    bsha = getattr(mod, "BASE_SHA256", None) or getattr(mod, "BASE_SHA", None)
    if isinstance(bsha, str) and bsha != pinned: raise Drift(f"{mod.__name__}: BASE_SHA256 changed to {bsha[:8]}")
    if isinstance(bsha, str) and bsha in idx: return Path(idx[bsha]).read_bytes()
    bpath = getattr(mod, "BASE", None)
    if bpath and Path(bpath).exists(): return Path(bpath).read_bytes()
    raise Drift(f"{mod.__name__}: base {pinned[:8]} not available")
def expected_bank31(verbose=False):
    image = bytearray([0xFF]) * BS; idx = _candidate_index(); log = []
    for name, base_sha, out_sha in CHAIN:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): mod = __import__(name)
        base = _resolve_base(mod, base_sha, idx)
        if hashlib.sha256(base).hexdigest() != base_sha: raise Drift(f"{name}: base sha mismatch")
        brp = getattr(mod, "BASE_RECEIPT", None); rb = Path(brp).read_bytes() if brp and Path(brp).exists() else None
        extras = [Path(getattr(mod, n)).read_bytes() for n in EXTRA_NAMES if getattr(mod, n, None) and Path(getattr(mod, n)).exists()]
        nreq = len([p for p in inspect.signature(mod.build).parameters.values() if p.default is inspect._empty])
        args = [base] + ([rb] if nreq >= 2 else []) + extras[:max(0, nreq - 2)]
        if len(args) != nreq: raise Drift(f"{name}: build() arity changed")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): out = mod.build(*args)
        out = bytes(out[0] if isinstance(out, tuple) else out)
        if hashlib.sha256(out).hexdigest() != out_sha: raise Drift(f"{name}: output sha {hashlib.sha256(out).hexdigest()[:8]} != pinned {out_sha[:8]}")
        ob = out[BANK*BS:(BANK+1)*BS]; bb = base[BANK*BS:(BANK+1)*BS]; wrote = 0
        for i in range(BS):
            if ob[i] != bb[i]: image[i] = ob[i]; wrote += 1
        log.append((name, wrote))
    if verbose:
        for name, wrote in log: print(f"  {name}: wrote {wrote} bank31 bytes")
    return bytes(image)
if __name__ == "__main__":
    img = expected_bank31(verbose=True); print("expected_bank31 sha256", hashlib.sha256(img).hexdigest())
    if len(sys.argv) > 1:
        cand = Path(sys.argv[1]).read_bytes()[BANK*BS:(BANK+1)*BS]; diff = [i for i in range(BS) if cand[i] != img[i]]
        print("candidate bank31 matches:", not diff, "| residual", len(diff), [f"{0x4000+i:04X}" for i in diff[:16]]); sys.exit(0 if not diff else 1)
