#!/usr/bin/env python3
"""Command the cell over Modbus by writing the command word.

    python3 tools/start_cell.py start [plc_host]   # StartRequest + AutoMode (9)
    python3 tools/start_cell.py stop  [plc_host]   # clear the word (0)
    python3 tools/start_cell.py reset [plc_host]   # ResetRequest (4)

This writes to the plant. The write is verified by reading the actuator word
back, so the tool reports what the PLC actually did rather than assuming the
command was honoured.
"""

from __future__ import annotations

import sys
import time

from modbus_tcp import (
    PLC_HOST_DEFAULT,
    REG_COMMANDS,
    ModbusError,
    read_holding,
    write_single,
)

WORDS = {"start": 9, "stop": 0, "reset": 4}

MB_WINDOW = 12288  # IG window -> %MB memory; index 4 is mwStateCode
STATES = {
    0: "IDLE",
    10: "WAIT_FOR_PART",
    20: "CONVEYOR_RUNNING",
    30: "PART_AT_STATION",
    40: "PUSHER_EXTENDING",
    50: "PUSHER_RETRACTING",
    60: "COMPLETE",
    900: "FAULT",
}
VERIFY_SECONDS = 3.0
VERIFY_INTERVAL = 0.25


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in WORDS:
        print(__doc__)
        return 2
    action = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else PLC_HOST_DEFAULT
    value = WORDS[action]

    # Verify against the state code sampled over a few seconds, not a single
    # read of the actuator bit: ConveyorRun is legitimately false during the
    # pusher phases, so one badly-timed sample looks like a refused command.
    try:
        echoed = write_single(host, REG_COMMANDS, value)
        print(f"wrote {echoed} to register {REG_COMMANDS} ({action})")
        seen = []
        deadline = time.time() + VERIFY_SECONDS
        while time.time() < deadline:
            seen.append(read_holding(host, MB_WINDOW, 5)[4])
            time.sleep(VERIFY_INTERVAL)
    except (OSError, ModbusError) as exc:
        print(f"failed talking to {host}: {exc}")
        return 1

    distinct = sorted(set(seen))
    print("states over {:.0f}s: {}".format(
        VERIFY_SECONDS, ", ".join(f"{s} {STATES.get(s, '?')}" for s in distinct)))

    if 900 in distinct:
        print("WARNING: the cell is FAULTED. Clear it with 'reset', then 'start'.")
        return 1
    if action == "start" and distinct == [0]:
        print("WARNING: commanded to start but the cell stayed in IDLE.")
        return 1
    if action == "stop" and distinct != [0]:
        print(f"note: still finishing a cycle (states {distinct}); it will stop at IDLE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
