#!/usr/bin/env python3
"""expected_bank24(): deterministic bank24 image for the r-series head = FF plus the ORDERED written diffs of the
scene-0B builder chain. Each step replays the checked-in builder on its own recorded base (BASE_SHA256 / BASE, receipt via
BASE_RECEIPT, rejected-run artifacts where needed); base and output are pinned to full sha256 constants and the build FAILS
on drift. No candidate is inspected while assembling; the CLI compare happens only at the end. Local historical artifacts are required; no emulator.
"""
import contextlib, glob, hashlib, inspect, io, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
BS = 0x4000; BANK = 24
CHAIN = [
    ("build_menu_vblank_reveal_r372", "6368f89cb8712ea9915f81e97684a900808195a38d3ed0575a22a0cc8067a365", "201fe703ea060e666db00c8e9ba9daa515a854f50445aa1c3e2abc1bfe6f461d"),
    ("build_interrupt_checked_vblank_r373", "201fe703ea060e666db00c8e9ba9daa515a854f50445aa1c3e2abc1bfe6f461d", "21b03a23a447f6990c72bcb5723c3733d1e45153ce97c0939b80707ba44d0a21"),
    ("build_deferred_commit_guard_r374", "21b03a23a447f6990c72bcb5723c3733d1e45153ce97c0939b80707ba44d0a21", "85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922"),
    ("build_inline_hazard_scanner_r379", "85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922", "084c62ae02b34c09bec94d56d9eb122f9ad0315f4f580f6dc4aba8c2179345e0"),
    ("build_combined_scanner_copy_r380", "084c62ae02b34c09bec94d56d9eb122f9ad0315f4f580f6dc4aba8c2179345e0", "64fece44776ac75d9822b264decd08736d63e67a259b76c625ebe8721a4939f1"),
    ("build_native_priority_collision_r381", "64fece44776ac75d9822b264decd08736d63e67a259b76c625ebe8721a4939f1", "df46f77f2b6485558f1801f76e1fd72dc90226c96f7faccc987c322538dfbd88"),
    ("build_latched_publication_r383", "df46f77f2b6485558f1801f76e1fd72dc90226c96f7faccc987c322538dfbd88", "0ee7d3947260967c1b36e7b9795bd109797a49ac4392ded8186a82c66b818930"),
    ("build_idempotent_latched_publication_r384", "0ee7d3947260967c1b36e7b9795bd109797a49ac4392ded8186a82c66b818930", "4b2316c9724e40102bdfc38e24ad0fc089b5df2746a84043d7d3b61fb92d3e89"),
    ("build_exact_source_dirty_r385", "4b2316c9724e40102bdfc38e24ad0fc089b5df2746a84043d7d3b61fb92d3e89", "9712f93bd83cadc601e85d71e6358264748e03997c1893335e959bf2eb97ad4e"),
    ("build_conditional_lut_invalidation_r386", "9712f93bd83cadc601e85d71e6358264748e03997c1893335e959bf2eb97ad4e", "06e98bdbe412c7dd709370086eadd20431f9bc6322f7b0dff2ada950c52e82a6"),
    ("build_inline_source_reuse_r387", "06e98bdbe412c7dd709370086eadd20431f9bc6322f7b0dff2ada950c52e82a6", "653d4c25f13d0fd1154528be76dd89cb5f84418d721c9c26631d01b19fa8ef32"),
    ("build_inline_source_control_r388", "653d4c25f13d0fd1154528be76dd89cb5f84418d721c9c26631d01b19fa8ef32", "9302fee5fa1533c9996b3a154b3639610e11886aa86ed839c60866f6e6246438"),
    ("build_source_row_reset_r389", "9302fee5fa1533c9996b3a154b3639610e11886aa86ed839c60866f6e6246438", "230c28f9615d2e2a08530782517aa4f353a7625a9e3b849605d7bf705c57a814"),
    ("build_corrected_source_reuse_r390", "230c28f9615d2e2a08530782517aa4f353a7625a9e3b849605d7bf705c57a814", "dbf34a3714721e790711432472cf28617dee30479e4e38bf4c27e116f5a13938"),
    ("build_source_timer_mask_r391", "dbf34a3714721e790711432472cf28617dee30479e4e38bf4c27e116f5a13938", "4c0d927985893cd31480301376c465f97ea84157299cb783689cbe82d774dd13"),
    ("build_source_reload_r395", "c8f21f0ed47b40b1372e1e2a73d6f526590e5dc4d1b2b2d00b9c1e916e59c5ff", "6a9df65b934be690099c638fd00280abe6d015ac18a6b63b775eed03bba8a6e7"),
    ("build_first_dirty_isolated_r398", "6a9df65b934be690099c638fd00280abe6d015ac18a6b63b775eed03bba8a6e7", "486146829f79674437e05dcf4537aec7a68a051247e21b650743c89cfd850fd2"),
    ("build_five_tile_groups_r402", "486146829f79674437e05dcf4537aec7a68a051247e21b650743c89cfd850fd2", "728ae2a750b35c8e373f76d15909883ca97298c86c00cfb4bacfe4b1e1fa69bb"),
    ("build_six_line_dma_r403", "728ae2a750b35c8e373f76d15909883ca97298c86c00cfb4bacfe4b1e1fa69bb", "ed51cfd5297bb5f35a610943df6b87e2664b361aeb87099138d23d29a9bc3909"),
    ("build_relative_commit_consume_r404", "ed51cfd5297bb5f35a610943df6b87e2664b361aeb87099138d23d29a9bc3909", "607dd53618c59e94dfb4b20cbac149549ca48ef7840cd39cdcb16ea60800f177"),
    ("build_six_tile_groups_r405", "607dd53618c59e94dfb4b20cbac149549ca48ef7840cd39cdcb16ea60800f177", "79e83ac5f63fe51d2c68fe3f3f3c7e2123c5607018ee381e76b48e18129a053b"),
    ("build_stage1_pointer_r407", "79e83ac5f63fe51d2c68fe3f3f3c7e2123c5607018ee381e76b48e18129a053b", "1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a"),
    ("build_metatile_increment_r412", "1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a", "c558d9559dbdcc15c3ad8eb6a100eddfd4546529e2e4faaaf029f064e9edce36"),
    ("build_stationary_copy_r415", "c558d9559dbdcc15c3ad8eb6a100eddfd4546529e2e4faaaf029f064e9edce36", "3c3fa4dd1fb1848cad3d6a66435dc0cda1474b60569f70228da5951a5d80057d"),
    ("build_native_increment_r416", "3c3fa4dd1fb1848cad3d6a66435dc0cda1474b60569f70228da5951a5d80057d", "13f34a8f8898fe4fd41c8e3eef695504d28b58c5fd0660e7fbb3afacde430586"),
    ("build_private_stationary_copy_r417", "13f34a8f8898fe4fd41c8e3eef695504d28b58c5fd0660e7fbb3afacde430586", "864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8"),
    ("build_room_writer_wait_r420", "864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8", "366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9"),
    ("build_native_metatile_increment_r421", "366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9", "b67fd8f4bdd20991c4dda6d524b5d1c94790f19a81971ffdd0552b7b24053132"),
    ("build_stage5_private_pointer_r424", "b67fd8f4bdd20991c4dda6d524b5d1c94790f19a81971ffdd0552b7b24053132", "a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b"),
    ("build_remove_entry_color_seed_r431", "a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b", "838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042"),
    ("build_aligned_tile_dma_r432", "838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042", "a5fd94d0ea4287a92ed9139e882e32b6f74536a071844697b659c8c2ecb1f164"),
    ("build_tail_coordinate_wait_r433", "a5fd94d0ea4287a92ed9139e882e32b6f74536a071844697b659c8c2ecb1f164", "5aee56bf413f96c4b9d86e4091a6098c43b5f2c47f943f50df57369fcef73ba3"),
    ("build_combined_dma_compile_r434", "5aee56bf413f96c4b9d86e4091a6098c43b5f2c47f943f50df57369fcef73ba3", "e9d7f4417e4835b1dc9bf1fd68eb9651cee5d06bd6819e7a640ab853eb3117b1"),
    ("build_stage5_dead_pointer_moves_r435", "e9d7f4417e4835b1dc9bf1fd68eb9651cee5d06bd6819e7a640ab853eb3117b1", "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c"),
    ("build_single_recovery_art_r436", "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c", "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3"),
    ("build_compiled_tooth_bank_r438", "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3", "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796"),
    ("build_room03_animation_envelope_r440", "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796", "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623"),
    ("build_stage2_seven_rows_r441", "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623", "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702"),
    ("build_stage1_subscene_tracking_r442", "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702", "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46"),
    ("build_later_stage_deferred_dma_r443", "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46", "7b3de7acf60614b958658b9f7f7139bb7b855dd23bc5f41c6c42d7322cead620"),
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
def expected_bank24(verbose=False):
    image = bytearray([0xFF]) * BS; idx = _candidate_index(); log = []
    for name, base_sha, out_sha in CHAIN:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): mod = __import__(name)
        base = _resolve_base(mod, base_sha, idx)
        if hashlib.sha256(base).hexdigest() != base_sha: raise Drift(f"{name}: base sha mismatch")
        brp = getattr(mod, "BASE_RECEIPT", None); rb = Path(brp).read_bytes() if brp and Path(brp).exists() else None
        extras = [Path(getattr(mod, n)).read_bytes() for n in EXTRA_NAMES if getattr(mod, n, None) and Path(getattr(mod, n)).exists()]
        fn = mod.build if hasattr(mod, 'build') else mod.install
        nreq = len([p for p in inspect.signature(fn).parameters.values() if p.default is inspect._empty])
        args = [base] + ([rb] if nreq >= 2 else []) + extras[:max(0, nreq - 2)]
        if len(args) != nreq: raise Drift(f"{name}: build() arity changed")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): out = fn(*args)
        out = bytes(out[0] if isinstance(out, tuple) else out)
        if hashlib.sha256(out).hexdigest() != out_sha: raise Drift(f"{name}: output sha {hashlib.sha256(out).hexdigest()[:8]} != pinned {out_sha[:8]}")
        ob = out[BANK*BS:(BANK+1)*BS]; bb = base[BANK*BS:(BANK+1)*BS]; wrote = 0
        for i in range(BS):
            if ob[i] != bb[i]: image[i] = ob[i]; wrote += 1
        log.append((name, wrote))
    if verbose:
        for name, wrote in log: print(f"  {name}: wrote {wrote} bank24 bytes")
    return bytes(image)
if __name__ == "__main__":
    img = expected_bank24(verbose=True); print("expected_bank24 sha256", hashlib.sha256(img).hexdigest())
    if len(sys.argv) > 1:
        cand = Path(sys.argv[1]).read_bytes()[BANK*BS:(BANK+1)*BS]; diff = [i for i in range(BS) if cand[i] != img[i]]
        print("candidate bank24 matches:", not diff, "| residual", len(diff), [f"{0x4000+i:04X}" for i in diff[:16]]); sys.exit(0 if not diff else 1)
