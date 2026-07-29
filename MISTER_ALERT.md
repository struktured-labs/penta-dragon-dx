# hardware_alert.md — MISTER FPGA IS ONLINE

As of July 13, 2026:
The physical MiSTer FPGA console at port 9900 is **ONLINE** and ready for active deployments.

## Directives:
1. **Reservation is mandatory:** Acquire the MiSTer reservation through the
   reservation service before status checks, shell access, deployment, input,
   reload, or screenshots. Never infer that "ONLINE" means unoccupied, and
   never bypass the reservation through direct SSH or `mister_shell`.
2. **Maximize Headless Testing first:** Run
   `scripts/diagnostics/verify_release_candidate.py` and require all 30
   emulator/local-tooling gates before reserving hardware.
3. **Execute Physical Deployments:** Once the build passes the complete matrix
   and a reservation is held, run **`/mister-deploy`** to verify the candidate
   on the Game Boy Color core. The repository's `scripts/mister.py` path also
   requires `MISTER_RESERVATION_ID` and a trusted
   `MISTER_RESERVATION_CHECKER`; it refuses all hardware access without them.
4. **Capture Hardware State:** Use `/mister-screenshot` to verify that there are zero pops, timing sags, or sub-frame sags on actual hardware display outputs.
