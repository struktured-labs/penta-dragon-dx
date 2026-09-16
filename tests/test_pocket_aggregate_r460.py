from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import copy
import unittest
import json
import hashlib
from unittest.mock import patch
from verify_pocket_visual_receipts import runtime_lut_contract
import verify_pocket_visual_receipts as aggregate


class RuntimeLutEvidence(unittest.TestCase):
    def clean(self):
        return dict(runtime_lut_mismatch_frames=0, runtime_lut_mismatch_cells=0,
                    runtime_lut_mismatch_max=0, runtime_lut_mismatch_pairs={},
                    runtime_lut_dma_unreadable_frames=0,
                    first_runtime_lut_dma_unreadable='')

    def reviewed(self):
        p = self.clean()
        p.update(runtime_lut_mismatch_frames=2627, runtime_lut_mismatch_cells=10508,
                 runtime_lut_mismatch_max=4,
                 runtime_lut_mismatch_pairs={k:2627 for k in
                     ('24/6/0','27/6/0','30/6/0','33/6/0')})
        return p

    def test_exact_clean_and_reviewed(self):
        self.assertTrue(runtime_lut_contract(self.clean()))
        self.assertTrue(runtime_lut_contract(self.reviewed()))

    def test_missing_invalid_and_inconsistent_counters(self):
        for baseline in (self.clean(), self.reviewed()):
            for key in baseline:
                p = copy.deepcopy(baseline); del p[key]
                # Missing empty-detail defaults to empty; all numerical and
                # signature evidence is mandatory.
                if key != 'first_runtime_lut_dma_unreadable':
                    self.assertFalse(runtime_lut_contract(p), key)
            for key in ('runtime_lut_mismatch_frames','runtime_lut_mismatch_cells',
                        'runtime_lut_mismatch_max'):
                for value in (-1, None, True, 1.5, '0'):
                    p = copy.deepcopy(baseline); p[key] = value
                    self.assertFalse(runtime_lut_contract(p), (key,value))
        for key in ('runtime_lut_mismatch_cells','runtime_lut_mismatch_max'):
            p = self.reviewed(); p[key] += 1
            self.assertFalse(runtime_lut_contract(p), key)

    def test_unknown_missing_and_false_role_counts(self):
        p = self.reviewed(); p['runtime_lut_mismatch_pairs']['99/7/0'] = 1
        self.assertFalse(runtime_lut_contract(p))
        p = self.reviewed(); del p['runtime_lut_mismatch_pairs']['24/6/0']
        self.assertFalse(runtime_lut_contract(p))
        for value in (0,-1,True,None,'2627',2628):
            p = self.reviewed(); p['runtime_lut_mismatch_pairs']['24/6/0'] = value
            self.assertFalse(runtime_lut_contract(p))
        p = self.reviewed(); p['runtime_lut_dma_unreadable_frames'] = 1
        self.assertFalse(runtime_lut_contract(p))


class AggregateBinding(unittest.TestCase):
    def test_pickup_generator_requires_saved_state_stage1_witness(self):
        required = "saved state independently records active Stage 1"
        self.assertIn(required, aggregate.PICKUP_GENERATOR_CHECKS)
        receipt = {
            "schema": aggregate.PICKUP_GENERATOR_SCHEMA,
            "status": "pass",
            "passed": True,
            "rom_sha256": "a" * 64,
            "checks": {
                name: True for name in aggregate.PICKUP_GENERATOR_CHECKS
                if name != required
            },
        }
        failures = []
        with (
            patch.object(
                aggregate, "validate_bound_artifact", return_value=None
            ),
            patch.object(aggregate, "file_digest", return_value="b" * 64),
        ):
            aggregate.validate_pickup_generator(
                receipt, Path("receipt.json"), "a" * 64, failures
            )
        self.assertTrue(any(required in failure for failure in failures))

    def test_stronger_stage_card_name_is_mandatory(self):
        receipt = dict(schema=aggregate.STAGE_CARD_SCHEMA, status='pass',
                       observe_only=False, rom_sha256='a'*64,
                       checks={name:True for name in aggregate.STAGE_CARD_CHECKS})
        failures=[]
        aggregate.validate_stage_card_receipt(receipt,'a'*64,failures)
        self.assertEqual(failures,[])
        new='blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state'
        del receipt['checks'][new]
        receipt['checks']['blank-SRAM Stage-1 entry exposes no third cyan/partial state']=True
        failures=[]
        aggregate.validate_stage_card_receipt(receipt,'a'*64,failures)
        self.assertTrue(failures)

    def test_tilemap_identities_come_from_reviewed_source_models(self):
        with patch.object(aggregate,'reviewed_postcomputed_copier',return_value=b'copier') as copier, \
             patch.object(aggregate,'reviewed_stage1_lut',return_value=b'lut') as lut, \
             patch.object(aggregate,'publication_oracle_report_failures',return_value=[]) as validator:
            reports=[(Path(str(i)),{'copier_sha256':'forged','lut_sha256':'forged'}) for i in range(3)]
            aggregate.validate_tilemap_reports(reports,'a'*64,[],b'candidate')
            copier.assert_called_once_with(b'candidate');lut.assert_called_once_with(b'candidate')
            for call in validator.call_args_list:
                self.assertEqual(call.kwargs['expected_copier_sha256'],hashlib.sha256(b'copier').hexdigest())
                self.assertEqual(call.kwargs['expected_lut_sha256'],hashlib.sha256(b'lut').hexdigest())
                self.assertTrue(call.kwargs['require_atomic'])

    def test_menu_race_protocol_cannot_be_omitted_or_retired(self):
        # Keep every other invalid-field failure constant to isolate the
        # required new protocol evidence without relying on saved receipts.
        kwargs=dict(rom=Path('/unused'),rom_sha256='a'*64,attr_mode='canonical',attr_lut_sha256='b'*64)
        report=dict(forced_commit='1',forced_commit_consumed='1',
                    forced_commit_protocol=aggregate.COMMIT_PROTOCOL_NAME)
        baseline=aggregate.menu_window_report_failures(report,**kwargs)
        for value in ('', 'retired-dfc4-df5c', None):
            report['forced_commit_protocol']=value
            failures=aggregate.menu_window_report_failures(report,**kwargs)
            self.assertEqual(len(failures),len(baseline)+1)


if __name__ == '__main__': unittest.main()
