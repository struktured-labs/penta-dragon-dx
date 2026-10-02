#!/usr/bin/env python3

from __future__ import annotations

import copy
import unittest

import verify_stage7_state_patrol as verify


def row(
    ordinal: int, loop: int, frame: int, consumed: int, planned: int,
    half_cycles: int, room: int, x: int, y: int = verify.EXPECTED_SETTLED_Y,
) -> dict[str, int]:
    return {
        "ordinal": ordinal, "loop": loop, "frame": frame,
        "consumed": consumed, "planned": planned,
        "half_cycles": half_cycles, "room": room, "x": x, "y": y,
    }


class Stage7StatePatrol(unittest.TestCase):
    def test_row_validation_and_mutation_controls(self):
        rows = [
            row(1, 1, 0, 0, 0x10, 0, 5, 96),
            row(2, 2, 4, 0x10, 0x20, 1, 3, 152),
            row(3, 3, 8, 0x20, 0x10, 2, 7, 92),
        ]
        verify.validate_rows(rows, 3, "valid")
        self.assertTrue(all(verify.mutation_controls().values()))
        self.assertTrue(all(verify.metric_policy_controls().values()))
        for field, value in (("x", 96), ("room", 3), ("half_cycles", 4)):
            damaged = copy.deepcopy(rows)
            damaged[-1][field] = value
            with self.assertRaises(ValueError):
                verify.validate_rows(damaged, 3, "damaged")

    @staticmethod
    def metric_traces(dx_scale: int = 10, dx_settle: int = 5):
        traces = {}
        for family, scale, settle in (
            ("original", 10, 5), ("dx", dx_scale, dx_settle)
        ):
            events = []
            for half_cycle in range(1, 31):
                events.append({
                    "half_cycles": half_cycle,
                    "room": 3 if half_cycle % 2 else 7,
                    "x": 152 if half_cycle % 2 else 92,
                    "y": (1652 if half_cycle < settle
                          else verify.EXPECTED_SETTLED_Y),
                    "frame": half_cycle * scale,
                    "loop": half_cycle * 17,
                })
            for replay in ("a", "b"):
                traces[f"{family}_{replay}"] = {"endpoint_events": events}
        return traces

    def test_settled_metric_accepts_strict_parity(self):
        traces = self.metric_traces()
        result = verify.settled_metric(traces, 0.02, 8, 20)
        self.assertTrue(result["strict_target_met"])
        self.assertEqual(result["measurement_start_half_cycle"], 5)
        self.assertEqual(result["measured_half_cycles"], 25)
        self.assertEqual(result["contact_affected_half_cycles"], [])

    def test_settled_metric_rejects_slow_and_late_settle(self):
        slow = verify.settled_metric(
            self.metric_traces(dx_scale=12), 0.02, 8, 20
        )
        self.assertFalse(slow["strict_target_met"])
        with self.assertRaises(ValueError):
            verify.settled_metric(
                self.metric_traces(dx_settle=10), 0.02, 8, 20
            )

    def test_contact_leg_is_reported_but_does_not_bias_free_motion(self):
        traces = self.metric_traces()
        # Add one persistent 15-loop/100-frame stop to both original replays.
        # Only the transition into the stopped span has an oversized delta.
        for replay in ("a", "b"):
            events = traces[f"original_{replay}"]["endpoint_events"]
            for event in events[14:]:
                event["loop"] += 15
                event["frame"] += 100
        result = verify.settled_metric(traces, 0.02, 8, 20)
        self.assertTrue(result["strict_target_met"])
        self.assertEqual(result["contact_affected_half_cycles"], [15])
        self.assertNotEqual(
            result["whole_route_throughput_ratio_by_replay"]["a"], 1.0
        )

    def test_filter_cannot_hide_general_candidate_slowdown(self):
        traces = self.metric_traces()
        for replay in ("a", "b"):
            events = traces[f"dx_{replay}"]["endpoint_events"]
            for event in events:
                event["loop"] = event["half_cycles"] * 21
        with self.assertRaises(ValueError):
            verify.settled_metric(traces, 0.02, 8, 20)


if __name__ == "__main__":
    unittest.main()
