"""Room construction must be independent of capture-based qualification."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import r534_stage1_room_source as room


class RoomSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tmp/r534-source-prefix-current502/intermediate-r287.gb"
        if not fixture.is_file():
            raise unittest.SkipTest("exact source-prefix fixture is unavailable")
        cls.source = fixture.read_bytes()
        cls.r292, cls.r292_receipt = cls.source, None
        for pin in room.ancestry.PRE_BRANCH[:4]:
            args = [cls.r292] + ([cls.r292_receipt] if cls.r292_receipt is not None else [])
            cls.r292, metadata = importlib.import_module(pin.module).build(*args)
            cls.r292_receipt = room.serialize_receipt(metadata)
        cls.r303, _ = room.scene.construct(cls.r292)
        cls.r305, _ = room.unified.construct(cls.r303)
        cls.r310, _ = room.precompile.construct(cls.r305)
        cls.r307, _ = room.mirror.construct(cls.r305)
        cls.r311, _ = room.final_scene.construct(cls.r310, reference=cls.r305)
        cls.r312, _ = room.epoch.construct(cls.r311)
        cls.r313, _ = room.selfheal.construct(cls.r312)

    def test_no_capture_audits_or_observation_claims(self):
        with patch.object(room.wall, "validate_wall_contract", side_effect=AssertionError("capture audit")), \
             patch.object(room.wall, "build", side_effect=AssertionError("historical build")), \
             patch.object(room.semantic, "build", side_effect=AssertionError("historical build")), \
             patch.object(room.scene.r302, "validate_r300_identity", side_effect=AssertionError("historical build")), \
             patch.object(room.unified, "validate_preimages", side_effect=AssertionError("historical rejection audit")), \
             patch.object(room.unified, "exhaustive_contract", side_effect=AssertionError("historical tag observation")), \
             patch.object(room.unified, "build", side_effect=AssertionError("historical build")), \
             patch.object(room.precompile, "exhaustive_contract", side_effect=AssertionError("capture audit")), \
             patch.object(room.precompile, "validate_preimages", side_effect=AssertionError("historical resolver observation")), \
             patch.object(room.precompile, "build", side_effect=AssertionError("historical build")), \
             patch.object(room.mirror, "build", side_effect=AssertionError("historical branch build")), \
             patch.object(room.final_scene, "build", side_effect=AssertionError("historical composition")), \
             patch.object(room.final_scene, "validate_preimages", side_effect=AssertionError("live audit")), \
             patch.object(room.final_scene, "reviewed_release_caveats", side_effect=AssertionError("capture audit")), \
             patch.object(room.epoch, "validate_preimages", side_effect=AssertionError("rejection audit")), \
             patch.object(room.selfheal, "validate_preimages", side_effect=AssertionError("historical runtime audit")), \
             patch.object(room.selfheal, "timing_contract", side_effect=AssertionError("historical route density")), \
             patch.object(room.publication, "validate_preimages", side_effect=AssertionError("rejection audit")), \
             patch.object(room.epoch, "CAPTURED_STALE_DAD7", b""), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")):
            result, receipt = room.construct(self.source)
            self.assertEqual((result, receipt), room.construct(self.source))
        self.assertEqual(room.digest(result), room.OUTPUT_SHA256)
        self.assertEqual(len(receipt["steps"]), 11)
        for key in ("promotable", "historical_evidence_consumed", "room_capture_population_checked", "fresh_live_qualification"):
            self.assertIs(receipt[key], False)
        for revision in room.SOURCE_CONTRACT_SHA256:
            component = receipt["components"][revision]
            self.assertEqual(component["status"], "construction-only")
            self.assertNotIn("base_receipt_sha256", component)
        encoded = json.dumps(receipt)
        self.assertNotIn("room01_target_cells", encoded)
        self.assertNotIn("room01_target_counts", encoded)
        self.assertNotIn("room01_target_positions", encoded)
        self.assertNotIn("live_rejection_receipt_sha256", encoded)
        self.assertNotIn("build_receipt_sha256", encoded)
        self.assertNotIn("r303_observed_bad_tag", encoded)
        self.assertNotIn("r309_live_observation", encoded)
        self.assertNotIn("room01_corpus", encoded)
        self.assertNotIn("live_checks_all_pass", encoded)
        self.assertNotIn("live_expected_plane_promotions", encoded)
        self.assertNotIn("live_unexpected_attr_mismatches", encoded)
        self.assertNotIn("live_receipt_sha256", encoded)
        for claim in ("captured_DAD7_sha256", "captured_gateway", "known_capture_full_installer_differences",
                      "all_other_DA00_DAFF_DB80_DBFC_installer_bytes", "observed_rejected_route_density",
                      "steady_average_t_per_frame", "first_repair_average_t_per_frame",
                      "r313_postrepair_semantic_attr_mismatch_frames"):
            self.assertNotIn(claim, encoded)

    def test_historical_builders_still_require_receipts_and_valid_capture(self):
        for builder in (room.wall, room.semantic, room.scene):
            with self.subTest(builder=builder.__name__):
                with self.assertRaisesRegex(AssertionError, "receipt identity changed"):
                    builder.build(self.r292, b"", room01_capture=b"")
                with self.assertRaisesRegex(AssertionError, "packed capture width changed"):
                    builder.build(self.r292, self.r292_receipt, room01_capture=b"")
                with self.assertRaisesRegex(AssertionError, "reviewed room-01 wall companions"):
                    builder.build(self.r292, self.r292_receipt, room01_capture=bytes(576))

    def test_repair_audits_still_require_authentic_evidence(self):
        r303_pin = room.ancestry.PRE_BRANCH[4]
        r305_pin = room.ancestry.PRE_BRANCH[5]
        with self.assertRaisesRegex(AssertionError, "r303 build receipt identity"):
            room.unified.build(self.r303, b"", rejected_receipt_bytes=b"")
        with self.assertRaisesRegex(AssertionError, "rejected r303 live receipt identity"):
            room.unified.validate_preimages(self.r303, b"")
        with self.assertRaisesRegex(AssertionError, "r305 build receipt identity"):
            room.precompile.build(self.r305, b"", room01_capture=b"")
        for capture in (b"", bytes(576)):
            with self.subTest(capture_length=len(capture)), self.assertRaisesRegex(AssertionError, "target corpus changed"):
                room.precompile.exhaustive_contract(self.r305, capture)
        capture = (ROOT / room.ancestry.HISTORICAL_INPUTS["room01_capture"][0]).read_bytes()
        rejected = (ROOT / room.ancestry.HISTORICAL_INPUTS["r303_rejected"][0]).read_bytes()
        r303, metadata = room.scene.build(self.r292, self.r292_receipt, room01_capture=capture)
        encoded = room.serialize_receipt(metadata)
        self.assertEqual(room.digest(encoded), r303_pin.receipt)
        r305, metadata = room.unified.build(r303, encoded, rejected_receipt_bytes=rejected)
        encoded = room.serialize_receipt(metadata)
        self.assertEqual(room.digest(encoded), r305_pin.receipt)
        with self.assertRaisesRegex(AssertionError, "target corpus changed"):
            room.precompile.build(r305, encoded, room01_capture=b"")
        result, metadata = room.precompile.build(r305, encoded, room01_capture=capture)
        self.assertEqual(room.digest(result), room.ancestry.R310.rom)
        self.assertEqual(room.digest(room.serialize_receipt(metadata)), room.ancestry.R310.receipt)

    def test_wrong_bases_variants_and_rom_pins_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exact r287"):
            room.construct(self.source[:-1])
        for builder in (room.wall, room.semantic, room.scene):
            with self.subTest(builder=builder.__name__), self.assertRaises(AssertionError):
                builder.construct(self.r292[:-1])
        with self.assertRaisesRegex(AssertionError, "unknown diagnostic variant"):
            room.wall.construct(self.r292, variant="skip-checks")
        for builder, source in ((room.unified, self.r303), (room.precompile, self.r305)):
            with self.subTest(builder=builder.__name__), self.assertRaises(AssertionError):
                builder.construct(source[:-1])
        for index, pin in enumerate(room.ancestry.PRE_BRANCH[:4]):
            altered = list(room.ancestry.PRE_BRANCH)
            altered[index] = replace(pin, rom="0" * 64)
            with self.subTest(step=index), patch.object(room.ancestry, "PRE_BRANCH", tuple(altered)):
                with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                    room.construct(self.source)

    def test_source_contract_and_static_receipt_pins_fail_closed(self):
        for revision in room.SOURCE_CONTRACT_SHA256:
            changed = {**room.SOURCE_CONTRACT_SHA256, revision: "0" * 64}
            with self.subTest(revision=revision), patch.object(room, "SOURCE_CONTRACT_SHA256", changed):
                with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                    room.construct(self.source)
        with patch.object(room, "SOURCE_CONTRACT_SHA256", {}):
            with self.assertRaisesRegex(ValueError, "pin inventory differs"):
                room.construct(self.source)
        pin = room.ancestry.PRE_BRANCH[0]
        with patch.object(room.ancestry, "PRE_BRANCH", (replace(pin, receipt="0" * 64), *room.ancestry.PRE_BRANCH[1:])):
            with self.assertRaisesRegex(ValueError, "static receipt differs"):
                room.construct(self.source)
        with patch.object(room.wall, "wall_source_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                room.construct(self.source)

    def test_source_preimages_and_semantic_contracts_fail_closed(self):
        with patch.object(room.wall, "WALL_HELPER", room.wall.WALL_HELPER[:-1]):
            with self.assertRaisesRegex(AssertionError, "wall helper width"):
                room.wall.construct(self.r292)
        with patch.object(room.wall, "OLD_RST0", bytes(len(room.wall.OLD_RST0))):
            with self.assertRaisesRegex(AssertionError, "RST0 room hook preimage"):
                room.wall.construct(self.r292)
        with patch.object(room.wall, "wall_values", return_value={}):
            with self.assertRaisesRegex(AssertionError, "room 01 does not publish"):
                room.wall.construct(self.r292)
        with patch.object(room.scene, "OLD_ART_REGION", bytes(len(room.scene.OLD_ART_REGION))):
            with self.assertRaisesRegex(AssertionError, "art region changed"):
                room.scene.construct(self.r292)

    def test_repair_source_models_and_pins_fail_closed(self):
        with patch.object(room.unified, "OLD_WALL_HELPER", bytes(len(room.unified.OLD_WALL_HELPER))):
            with self.assertRaisesRegex(AssertionError, "wall helper preimage changed"):
                room.unified.construct(self.r303)
        with patch.object(room.precompile, "effective_room", return_value=0):
            with self.assertRaisesRegex(AssertionError, "native effective-room model changed"):
                room.precompile.construct(self.r305)
        for builder, source in ((room.unified, self.r303), (room.precompile, self.r305)):
            with self.subTest(builder=builder.__name__), patch.object(builder, "EXPECTED_CANDIDATE_SHA256", "0" * 64):
                with self.assertRaisesRegex(AssertionError, "candidate identity drift"):
                    builder.construct(source)
        for revision, builder in (("r305", room.unified), ("r310", room.precompile)):
            original = builder.construct
            def changed(source, original=original):
                result, metadata = original(source)
                return result[:-1], metadata
            with self.subTest(revision=revision), patch.object(builder, "construct", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "generated ROM differs"):
                    room.construct(self.source)

    def test_mirror_and_composition_fail_closed(self):
        with self.assertRaisesRegex(AssertionError, "wrong exact r305 base"):
            room.mirror.construct(self.r305[:-1])
        with self.assertRaisesRegex(AssertionError, "wrong exact r310 base"):
            room.final_scene.construct(self.r310[:-1], reference=self.r305)
        with self.assertRaisesRegex(AssertionError, "wrong exact r305 base"):
            room.final_scene.construct(self.r310, reference=self.r305[:-1])
        with self.assertRaises(TypeError):
            room.final_scene.construct(self.r310)
        with patch.object(room.mirror, "construct", return_value=(self.r307[:-1], {})):
            with self.assertRaisesRegex(AssertionError, "r307 candidate identity changed"):
                room.final_scene.construct(self.r310, reference=self.r305)
        with patch.object(room.final_scene, "PRECOMPILE_DI_ADDR", 0):
            with self.assertRaisesRegex(AssertionError, "precompile DI ownership changed"):
                room.final_scene.construct(self.r310, reference=self.r305)
        with patch.object(room.final_scene, "EXPECTED_CANDIDATE_SHA256", "0" * 64):
            with self.assertRaisesRegex(AssertionError, "r311 candidate identity drift"):
                room.final_scene.construct(self.r310, reference=self.r305)
        with patch.object(room.mirror, "installer_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                room.construct(self.source)

    def test_composition_historical_audit_remains_mandatory(self):
        with self.assertRaisesRegex(AssertionError, "r305 build receipt identity changed"):
            room.mirror.build(self.r305, b"")
        capture = (ROOT / room.ancestry.HISTORICAL_INPUTS["room01_capture"][0]).read_bytes()
        rejected = (ROOT / room.ancestry.HISTORICAL_INPUTS["r303_rejected"][0]).read_bytes()
        live = (ROOT / room.ancestry.HISTORICAL_INPUTS["r310_live"][0]).read_bytes()
        _, r303_meta = room.scene.build(self.r292, self.r292_receipt, room01_capture=capture)
        _, r305_meta = room.unified.build(self.r303, room.serialize_receipt(r303_meta), rejected_receipt_bytes=rejected)
        r305_receipt = room.serialize_receipt(r305_meta)
        _, r310_meta = room.precompile.build(self.r305, r305_receipt, room01_capture=capture)
        _, r307_meta = room.mirror.build(self.r305, r305_receipt)
        args = [self.r310, room.serialize_receipt(r310_meta), self.r307, room.serialize_receipt(r307_meta), live]
        for index, message in ((1, "r310 build receipt identity"), (2, "r307 candidate identity"),
                               (3, "r307 receipt identity"), (4, "r310 corrected live receipt identity")):
            altered = list(args)
            altered[index] = b""
            with self.subTest(index=index), self.assertRaisesRegex(AssertionError, message):
                room.final_scene.build(*altered, room01_capture=capture, reference=self.r305)
        with self.assertRaisesRegex(AssertionError, "room01 contextual BG6 corpus changed"):
            room.final_scene.build(*args, room01_capture=b"", reference=self.r305)
        candidate, metadata = room.final_scene.build(*args, room01_capture=capture, reference=self.r305)
        self.assertEqual(room.digest(candidate), room.ancestry.R311.rom)
        self.assertEqual(room.digest(room.serialize_receipt(metadata)), room.ancestry.R311.receipt)

    def test_epoch_selfheal_and_publication_source_guards(self):
        cases = ((room.epoch, self.r311), (room.selfheal, self.r312), (room.publication, self.r313))
        for builder, source in cases:
            with self.subTest(builder=builder.__name__), self.assertRaisesRegex(AssertionError, "requires exact"):
                builder.construct(source[:-1])
            with self.subTest(builder=builder.__name__), patch.object(builder, "EXPECTED_CANDIDATE_SHA256", "0" * 64):
                with self.assertRaisesRegex(AssertionError, "candidate identity drift"):
                    builder.construct(source)
        with patch.object(room.epoch, "OLD_GATE", bytes(len(room.epoch.OLD_GATE))):
            with self.assertRaisesRegex(AssertionError, "runtime epoch gate changed"):
                room.epoch.construct(self.r311)
        with patch.object(room.selfheal, "OLD_RST18", bytes(len(room.selfheal.OLD_RST18))):
            with self.assertRaisesRegex(AssertionError, "fixed RST18 route changed"):
                room.selfheal.construct(self.r312)
        with patch.object(room.publication, "MAIN_PUBLISHER", bytes(len(room.publication.MAIN_PUBLISHER))):
            with self.assertRaisesRegex(AssertionError, "primary .* publisher changed"):
                room.publication.construct(self.r313)
        with patch.object(room.selfheal, "source_timing_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                room.construct(self.source)
        with patch.object(room.publication, "transaction_contract", return_value={}):
            with self.assertRaisesRegex(ValueError, "contract receipt differs"):
                room.construct(self.source)

    def test_late_room_historical_audits_retain_exact_receipts(self):
        for builder, source, pin, evidence in (
            (room.epoch, self.r311, room.ancestry.R312, room.epoch.REJECTED_LIVE_RECEIPT.read_bytes()),
            (room.selfheal, self.r312, room.ancestry.R313, None),
            (room.publication, self.r313, room.ancestry.R314, room.publication.REJECTED_LIVE_RECEIPT.read_bytes()),
        ):
            base_receipt = builder.BASE_RECEIPT.read_bytes()
            extra = [] if evidence is None else [evidence]
            with self.subTest(builder=builder.__name__), self.assertRaisesRegex(AssertionError, "build receipt identity changed"):
                builder.build(source, b"", *extra)
            if evidence is not None:
                with self.subTest(builder=builder.__name__), self.assertRaisesRegex(AssertionError, "identity changed"):
                    builder.build(source, base_receipt, b"")
            result, metadata = builder.build(source, base_receipt, *extra)
            self.assertEqual(room.digest(result), pin.rom)
            self.assertEqual(room.digest(room.serialize_receipt(metadata)), pin.receipt)
        with patch.object(room.epoch, "CAPTURED_STALE_DAD7", b"invalid"):
            with self.assertRaisesRegex(AssertionError, "captured stale DAD7 gateway changed"):
                room.selfheal.build(self.r312, room.selfheal.BASE_RECEIPT.read_bytes())

    def test_factory_to_r314_double_build_with_no_historical_input_access(self):
        program = r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
factory=(root/'tmp/r534-palette-source-current503/build-1/factory.gb').read_bytes()
sys.path[:0]=[str(root/'scripts/diagnostics'),str(root/'scripts'),sys.argv[2]]
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        raw=args[0].decode() if isinstance(args[0],bytes) else args[0]
        path=(root/raw).resolve()
        if path.is_relative_to(root/'tmp') or path.suffix.lower() in ('.gb','.gbc','.ss0','.ss1'):
            raise AssertionError(f'undeclared artifact read: {path}')
sys.addaudithook(audit)
import build_r534_source_prefix as prefix
import r534_stage1_room_source as room
first=None
for _ in range(2):
    r287, prefix_receipt=prefix.build(factory)
    result,receipt=room.construct(r287)
    item=(result,prefix_receipt,receipt)
    if first is not None: assert item==first
    first=item
    assert room.digest(result)==room.OUTPUT_SHA256
print(json.dumps({'candidate_sha256':room.digest(first[0]),'historical_inputs_read':0}))
'''
        run = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT),
                              str(Path(yaml.__file__).resolve().parent.parent)],
                             cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["historical_inputs_read"], 0)


if __name__ == "__main__":
    unittest.main()
