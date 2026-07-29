#!/usr/bin/env python3
"""Compatibility entry point for the real serial mGBA GAME START gate.

The former implementation was PyBoy-only, ignored its ROM argument, and
forced a canned path. Keep the old filename for local callers, but delegate to
the hash-bound natural-route verifier.
"""

from verify_game_start_routes import main


if __name__ == "__main__":
    raise SystemExit(main())
