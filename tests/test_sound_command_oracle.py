"""#16 negative controls must reject silence, extra or wrongly routed SFX."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/probes'))
from sound_command_oracle import inspect_commands, compare_commands


class SoundCommandOracleTests(unittest.TestCase):
    def setUp(self):
        self.raw = ('# Boot frames: 338, measure frames: 600\n'
                    'rst_f=350 A=26 caller=57B2 bank=01 scene=02 sp=DFF3\n')
        self.engine = ('event\tframe\tcommand\tactive\tpc\tsvbk\n'
                       'read\t350\t26\t00\t45B6\tF9\n'
                       'accept\t350\t26\t00\t45C7\tF9\n')
        self.metrics = dict(transitions=2, command_pulses=1, clear_pulses=1,
                            chained_commands=0, unpaired_commands=0,
                            max_nonzero_run=1, command_values={0x26:1},
                            dma_unreadable_samples=0)

    def inspect(self, raw=None, engine=None, metrics=None):
        return inspect_commands(self.raw if raw is None else raw,
                                self.engine if engine is None else engine,
                                self.metrics if metrics is None else metrics, 600, True)

    def test_native_read_accept_pair_passes(self):
        result = self.inspect()
        self.assertEqual(result['engine_counts']['accept:26'], 1)

    def test_frame_sample_count_is_not_a_native_command_count(self):
        self.raw += 'rst_f=360 A=26 caller=57B2 bank=01 scene=02 sp=DFF3\n'
        self.engine += self.engine.split('\n',1)[1].replace('350', '360')
        a = self.inspect()
        b = self.inspect(metrics=dict(self.metrics,transitions=4,command_pulses=2,
                                      clear_pulses=2,command_values={0x26:2}))
        self.assertEqual(compare_commands(a,b)['status'], 'pass')

    def test_inconsistent_sampled_counts_fail(self):
        with self.assertRaises(ValueError):
            self.inspect(metrics=dict(self.metrics,transitions=100))

    def test_no_gameplay_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(raw='transitions=-1\n')

    def test_no_engine_output_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(engine='event\tframe\tcommand\tactive\tpc\tsvbk\n')

    def test_extra_consumed_command_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(engine=self.engine + self.engine.split('\n',1)[1])

    def test_unknown_command_and_wrong_caller_bank_scene_fail(self):
        for old,new in [('A=26','A=FF'),('caller=57B2','caller=1234'),
                        ('bank=01','bank=0D'),('scene=02','scene=0C')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.inspect(raw=self.raw.replace(old,new))

    def test_unknown_sampled_command_fails_even_with_low_count(self):
        with self.assertRaises(ValueError):
            self.inspect(metrics=dict(self.metrics,command_values={0xFF:1}))

    def test_missing_or_malformed_telemetry_fails(self):
        for key in self.metrics:
            metrics = dict(self.metrics)
            del metrics[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.inspect(metrics=metrics)

    def test_wrong_engine_bank_pc_value_or_order_fails(self):
        for old,new in [('F9','FA'),('45B6','1234'),('\t26\t','\t25\t'),
                        ('read\t350','read\t351')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.inspect(engine=self.engine.replace(old,new))

    def test_delayed_consumption_fails(self):
        with self.assertRaises(ValueError):
            self.inspect(engine=self.engine.replace('350','354'))

    def test_wrong_priority_decision_fails(self):
        with self.assertRaises(ValueError):
            self.inspect(engine=self.engine.replace('accept','reject').replace('45C7','45C2'))

    def test_extra_sound_count_fails_existing_tolerance(self):
        base = dict(engine_counts={'read:26':34,'accept:26':33,'reject:26':1})
        candidate = deepcopy(base)
        candidate['engine_counts']['accept:26'] = 70
        self.assertEqual(compare_commands(base,candidate)['status'], 'fail')

    def test_silent_candidate_fails(self):
        base = dict(engine_counts={'read:26':34,'accept:26':33,'reject:26':1})
        self.assertEqual(compare_commands(base,dict(engine_counts={}))['status'], 'fail')

    def test_new_command_class_fails(self):
        base = dict(engine_counts={'read:26':34,'accept:26':33,'reject:26':1})
        candidate = deepcopy(base)
        candidate['engine_counts']['accept:0E'] = 1
        self.assertEqual(compare_commands(base,candidate)['status'], 'fail')

    def test_invalid_tolerance_fails(self):
        for value in (0.5,float('nan'),float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_commands({}, {}, value)


if __name__ == '__main__':
    unittest.main()
