"""#67: a negative visual control must reproduce, not merely fail."""
import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import unittest
from verify_stage1_exact_destination_mutation import mutant_pair_is_exact


class MutationPairTests(unittest.TestCase):
    def setUp(self):
        self.receipt = {
            'schema': 'penta-low-health-hazard-determinism-v2',
            'statuses': [1, 1], 'passed': False,
            'exact_comparison': {'passed': True},
            'checks': {
                'both low-health hazard replays pass': False,
                'full unshifted state trace and rendered corpus are byte-exact': True,
                'complete native audio video state and input timeline are byte-exact': True,
            },
        }

    def test_expected_visual_failures_with_exact_output(self):
        self.assertTrue(mutant_pair_is_exact(self.receipt))

    def test_shifted_legacy_receipt_is_not_accepted(self):
        self.assertFalse(mutant_pair_is_exact({
            'schema': 'penta-low-health-hazard-determinism-v1',
            'alignment': {'passed': True}, 'statuses': [1, 1]}))

    def test_native_or_sample_difference_is_not_accepted(self):
        for key in list(self.receipt['checks'])[1:]:
            for value in (False, None):
                mutant = copy.deepcopy(self.receipt)
                mutant['checks'][key] = value
                self.assertFalse(mutant_pair_is_exact(mutant), key)
        self.receipt['exact_comparison']['passed'] = False
        self.assertFalse(mutant_pair_is_exact(self.receipt))

    def test_crash_or_single_child_success_is_not_expected_rejection(self):
        for statuses in ([1, 0], [0, 1], [-9, 1], [1], [0, 0]):
            self.receipt['statuses'] = statuses
            self.assertFalse(mutant_pair_is_exact(self.receipt), statuses)


if __name__ == '__main__':
    unittest.main()
