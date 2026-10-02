"""Pinned r314/r343 -> r442 prefix for the r534 lineage audit.

Intermediate receipt-consuming steps receive freshly serialized build records.
The r314 entry additionally requires its explicitly supplied initial receipt.
These are static build records, not regenerated live evidence.
The historical bank24 ownership table independently pins the r372+ outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import json

BASE_SHA256 = "df359624edb86adfdc88d78e81b4a9d7c8e251956fb29512e2a0402b6c604d48"
OUTPUT_SHA256 = "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46"
EARLY_BASE_SHA256 = "010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303"
EARLY_RECEIPT_SHA256 = "730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1"
ORIGINAL_SHA256 = "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"


@dataclass(frozen=True)
class Step:
    module: str
    output_sha256: str
    receipt_sha256: str | None = None
    options: tuple[tuple[str, object], ...] = ()
    reference_sha256: str | None = None
    needs_original_rom: bool = False


EARLY_STEPS = (
    Step("build_stage1_selector_latch_cold_init_r317",
         "77e491aa7e34711a245f0586c2434461fc6c8d3e5fad1bca0b3b27fbcfb43da0",
         receipt_sha256=EARLY_RECEIPT_SHA256),
    Step("build_stage1_row_gate_abi_speed_r318",
         "909d7ee16bbf5080fd9992567bbe784e6df3234a08f9bde07ff7a10b2f729abb",
         receipt_sha256="e72a095a207fdc1bb86e30b7361ea046484c8acfbb75064faedaca039646706c"),
    Step("build_stage1_effective_row_context_r319",
         "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db",
         receipt_sha256="57e853011f4ba03252be78a60eefc385cc60bc71a97fc0c5b0d92ea4bc8e8cfd"),
    Step("build_stage1_atomic_presentation_commit_r320",
         "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7",
         receipt_sha256="ccf15f3f8d927f8d512329a1428190263e84b1f05c570a7d14fa9e9cd03b0d00"),
    Step("build_stage1_scene0b_admission_art_repair_r336",
         "484cd678bd6724f7ab9c128a985a0a50db1c523ad406103a8f57bd84784f4611",
         receipt_sha256="9ed345f166f16eae4d94fc69d06ddef51fdbdf195dad4ca50b106aa110c2018b"),
    Step("build_stage1_hazard_terminal_caps_r341",
         "30ba055bc4cdd7468994d8dbe017a9c73ec82d09184f792e690ffd22a95e73cf",
         receipt_sha256="070fe7f4380f5169d569d49d7067851f8dc4f3dbf8818af254204ea49561cbf9"),
    Step("build_stage1_hazard_terminal_resume_r342",
         "84bf020e4a9006e0ce9a3e79fec6687a281620108d5337ab8fddb99d0093dd1f",
         receipt_sha256="f80f4e4e7801560c10129a6920523ff9d1143ed0f19132c0465e45e260783cf4"),
    Step("build_stage1_hazard_terminal_silhouette_r343", BASE_SHA256,
         receipt_sha256="4b4368769c23ae30ec6b4b63143d774cbab629f516dfa5333c13b516ffae9900",
         needs_original_rom=True),
)


STEPS = (
    Step("build_stage4_delay_trim_r344",
         "3b35f1c938b4fefc1c6f6c02408494f4a6663be50f564b4476b502399c1f714e"),
    Step("build_stage1_pocket_map_authority_r345",
         "d7d388e354dc3649f81a5a62f61266f67ed454a2b2d8ac10e817102d82745a4a"),
    Step("build_stage1_hram_target_vblank_r353",
         "45502bf1914f9d8b365978296e2186ce122fe513e400ca4996dbaa744e5f0f67",
         receipt_sha256="b1c74bdef48ca07003ac1867de2cc9314168d5d03a4b14da3c56728c4c161056"),
    Step("build_stage1_postcommit_hram_target_r354",
         "3759f8ad10e6841f7705d13ee76f4b45478460b1bf782acb8507b4f70414e71f",
         receipt_sha256="b3e1f754c2a653a38327373374ff9a88725dfb659b056bc2c6ab0d7ed52adae5"),
    Step("build_stage1_vblank_palette_map_atomic_r356",
         "31a090fd4609ec1d42813abd13b312dbaba8723886a96e3857ee79ec4228852b",
         receipt_sha256="0cc07e1a3fe2b56f7f348fc254e4b361b7d7bbed1d63e547eb6c46cdf699d3d0"),
    Step("build_stage1_fast_final_window_selector_r363",
         "9a85f55b87f3450cd279556a17ed6bb6865298dc73b327fdbba70fdf0bc4a030",
         receipt_sha256="43809ef880fd9b5039aa0971e4b010830eb564cb65f0a491a12e04a299201dba"),
    Step("build_stage1_menu_close_atomic_hide_r364",
         "3b9f67ea25e65d40cc383e7af319b35bded7083143f3a1efbf2c69c42b48beb2",
         receipt_sha256="4078b328bfc9723759c3183b6b592fb9c57c76480931b5d3f8d9678dab3d2f09"),
    Step("build_stage1_sara_priority_clear_r365",
         "4243fa84946bc0325ff46b510103c1e1c4213f0879e40b5aff77d026bf69ea88",
         receipt_sha256="3c783ad861af9e91da0c01ca40af2e7a33f55271625c72b0e27c34136991896d"),
    Step("build_obj_priority_fast_r368",
         "5356bb026cba4d063b1324f1d9b9d9ef9be85dcdb7debe4a03ce7ef300a74111"),
    Step("build_stage1_timer_safe_stack_r371",
         "6368f89cb8712ea9915f81e97684a900808195a38d3ed0575a22a0cc8067a365"),
    Step("build_menu_vblank_reveal_r372",
         "201fe703ea060e666db00c8e9ba9daa515a854f50445aa1c3e2abc1bfe6f461d"),
    Step("build_interrupt_checked_vblank_r373",
         "21b03a23a447f6990c72bcb5723c3733d1e45153ce97c0939b80707ba44d0a21"),
    Step("build_deferred_commit_guard_r374",
         "85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922"),
    Step("build_inline_hazard_scanner_r379",
         "084c62ae02b34c09bec94d56d9eb122f9ad0315f4f580f6dc4aba8c2179345e0"),
    Step("build_combined_scanner_copy_r380",
         "64fece44776ac75d9822b264decd08736d63e67a259b76c625ebe8721a4939f1",
         reference_sha256="85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922"),
    Step("build_native_priority_collision_r381",
         "df46f77f2b6485558f1801f76e1fd72dc90226c96f7faccc987c322538dfbd88"),
    Step("build_latched_publication_r383",
         "0ee7d3947260967c1b36e7b9795bd109797a49ac4392ded8186a82c66b818930"),
    Step("build_idempotent_latched_publication_r384",
         "4b2316c9724e40102bdfc38e24ad0fc089b5df2746a84043d7d3b61fb92d3e89"),
    Step("build_exact_source_dirty_r385",
         "9712f93bd83cadc601e85d71e6358264748e03997c1893335e959bf2eb97ad4e"),
    Step("build_conditional_lut_invalidation_r386",
         "06e98bdbe412c7dd709370086eadd20431f9bc6322f7b0dff2ada950c52e82a6"),
    Step("build_inline_source_reuse_r387",
         "653d4c25f13d0fd1154528be76dd89cb5f84418d721c9c26631d01b19fa8ef32"),
    Step("build_inline_source_control_r388",
         "9302fee5fa1533c9996b3a154b3639610e11886aa86ed839c60866f6e6246438"),
    Step("build_source_row_reset_r389",
         "230c28f9615d2e2a08530782517aa4f353a7625a9e3b849605d7bf705c57a814"),
    Step("build_corrected_source_reuse_r390",
         "dbf34a3714721e790711432472cf28617dee30479e4e38bf4c27e116f5a13938"),
    Step("build_source_timer_mask_r391",
         "4c0d927985893cd31480301376c465f97ea84157299cb783689cbe82d774dd13"),
    Step("build_cold_art_vblank_guard_r392",
         "c8f21f0ed47b40b1372e1e2a73d6f526590e5dc4d1b2b2d00b9c1e916e59c5ff",
         options=(("variant", "defer"), ("window", 4), ("early", True))),
    Step("build_source_reload_r395",
         "6a9df65b934be690099c638fd00280abe6d015ac18a6b63b775eed03bba8a6e7"),
    Step("build_first_dirty_isolated_r398",
         "486146829f79674437e05dcf4537aec7a68a051247e21b650743c89cfd850fd2"),
    Step("build_five_tile_groups_r402",
         "728ae2a750b35c8e373f76d15909883ca97298c86c00cfb4bacfe4b1e1fa69bb"),
    Step("build_six_line_dma_r403",
         "ed51cfd5297bb5f35a610943df6b87e2664b361aeb87099138d23d29a9bc3909"),
    Step("build_relative_commit_consume_r404",
         "607dd53618c59e94dfb4b20cbac149549ca48ef7840cd39cdcb16ea60800f177"),
    Step("build_six_tile_groups_r405",
         "79e83ac5f63fe51d2c68fe3f3f3c7e2123c5607018ee381e76b48e18129a053b"),
    Step("build_stage1_pointer_r407",
         "1438d4d852d802921baa3f5c1e4d51aaa0dd6e000013d295b3d96371d0224c0a"),
    Step("build_metatile_increment_r412",
         "c558d9559dbdcc15c3ad8eb6a100eddfd4546529e2e4faaaf029f064e9edce36"),
    Step("build_stationary_copy_r415",
         "3c3fa4dd1fb1848cad3d6a66435dc0cda1474b60569f70228da5951a5d80057d"),
    Step("build_native_increment_r416",
         "13f34a8f8898fe4fd41c8e3eef695504d28b58c5fd0660e7fbb3afacde430586"),
    Step("build_private_stationary_copy_r417",
         "864d9993378dc07f676fb0413b04674b3f687e523d7de94cfa48a81ce34efcf8"),
    Step("build_room_writer_wait_r420",
         "366ebf308b63c489576c3ff0f34d2bbfcd8838ab25537eed834db467d1733dc9"),
    Step("build_native_metatile_increment_r421",
         "b67fd8f4bdd20991c4dda6d524b5d1c94790f19a81971ffdd0552b7b24053132"),
    Step("build_stage5_private_pointer_r424",
         "a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b"),
    Step("build_remove_entry_color_seed_r431",
         "838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042"),
    Step("build_aligned_tile_dma_r432",
         "a5fd94d0ea4287a92ed9139e882e32b6f74536a071844697b659c8c2ecb1f164"),
    Step("build_tail_coordinate_wait_r433",
         "5aee56bf413f96c4b9d86e4091a6098c43b5f2c47f943f50df57369fcef73ba3"),
    Step("build_combined_dma_compile_r434",
         "e9d7f4417e4835b1dc9bf1fd68eb9651cee5d06bd6819e7a640ab853eb3117b1",
         reference_sha256="a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b"),
    Step("build_stage5_dead_pointer_moves_r435",
         "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c"),
    Step("build_single_recovery_art_r436",
         "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3"),
    Step("build_compiled_tooth_bank_r438",
         "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796"),
    Step("build_room03_animation_envelope_r440",
         "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623"),
    Step("build_stage2_seven_rows_r441",
         "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702"),
    Step("build_stage1_subscene_tracking_r442",
         "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serialize_receipt(receipt: dict) -> bytes:
    # Match the original builders' serialization, including the terminal LF.
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()


def build(source: bytes, *, base_receipt: bytes | None = None,
          original_rom: bytes | None = None) -> tuple[bytes, list[dict]]:
    source_sha = digest(source)
    if source_sha == EARLY_BASE_SHA256:
        if base_receipt is None or digest(base_receipt) != EARLY_RECEIPT_SHA256:
            raise ValueError("r314 requires its exact retained static build receipt")
        if original_rom is None or digest(original_rom) != ORIGINAL_SHA256:
            raise ValueError("r314 requires the exact original cartridge for terminal art")
        sequence, receipt = EARLY_STEPS + STEPS, base_receipt
    elif source_sha == BASE_SHA256:
        if base_receipt is not None or original_rom is not None:
            raise ValueError("r343 replay does not consume extra input artifacts")
        sequence, receipt = STEPS, None
    else:
        raise ValueError("requires exact retained r314 or r343 input")
    result = source
    records = []
    reference_hashes = {step.reference_sha256 for step in sequence
                        if step.reference_sha256 is not None}
    checkpoints = {}
    for step in sequence:
        previous = result
        args = [previous]
        if step.receipt_sha256 is not None:
            if receipt is None or digest(receipt) != step.receipt_sha256:
                raise ValueError(f"{step.module}: generated input receipt hash differs")
            args.append(receipt)
        options = dict(step.options)
        if step.needs_original_rom:
            options["stock"] = original_rom
        if step.reference_sha256 is not None:
            reference = checkpoints.get(step.reference_sha256)
            if reference is None or digest(reference) != step.reference_sha256:
                raise ValueError(f"{step.module}: missing or changed generated reference")
            options["reference"] = reference
        output = importlib.import_module(step.module).build(*args, **options)
        metadata = None
        if isinstance(output, tuple):
            result, metadata = output
        else:
            result = output
        if not isinstance(result, bytes) or len(result) != len(source):
            raise ValueError(f"{step.module}: output type or size changed")
        if digest(result) != step.output_sha256:
            raise ValueError(f"{step.module}: output hash differs from pinned lineage")
        if step.output_sha256 in reference_hashes:
            checkpoints[step.output_sha256] = result
        receipt = None
        if isinstance(metadata, dict):
            if metadata.get("candidate_sha256") != digest(result):
                raise ValueError(f"{step.module}: receipt candidate hash differs")
            # These builders expose STATIC_PASS_LIVE_GATES_REQUIRED, never
            # live success. Preserve all fields in their exact serialization.
            receipt = serialize_receipt(metadata)
        changed = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        records.append({
            "name": step.module,
            "base_sha256": digest(previous),
            "candidate_sha256": digest(result),
            "changed_bytes": len(changed),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in changed if i not in (0x14D, 0x14E, 0x14F)
            }),
            "input_receipt_sha256": step.receipt_sha256,
            "generated_receipt_sha256": digest(receipt) if receipt is not None else None,
            "options": dict(step.options),
            "generated_reference_sha256": step.reference_sha256,
            "original_rom_sha256": ORIGINAL_SHA256 if step.needs_original_rom else None,
        })
    if digest(result) != OUTPUT_SHA256:
        raise ValueError("prefix did not reproduce exact r442")
    return result, records
