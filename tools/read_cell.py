#!/usr/bin/env python3
"""Report what the cell is doing, straight from the PLC. Read-only.

    python3 tools/read_cell.py [samples] [plc_host]

Answers "why isn't it moving?" without opening XAE.

Reads the %MB window (12288+), which carries the state code, fault code, status
bits and part count - far more informative than the actuator word alone. A single
sample of the actuator word is misleading, because ConveyorRun is legitimately
false during the pusher phases and while waiting for a part; only the state code
distinguishes "faulted" from "mid-cycle" from "waiting".

Samples over a few seconds, since one instant of a cycling machine tells you
little.
"""

from __future__ import annotations

import sys
import time
from collections import Counter

from modbus_tcp import PLC_HOST_DEFAULT, ModbusError, read_holding

MB_WINDOW = 12288  # IG window -> %MB memory: status, state, fault, part count
REG_ACTUATORS = 32768  # GVL.mb_Output_Registers[0] - the actuator path in use
REG_COMMANDS = 32769  # GVL.mb_Output_Registers[1] - the command path in use
SENSOR_WINDOW = 33024  # GVL.mb_Input_Registers[0..] - Webots writes sensors here

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
FAULTS = {0: "none", 1: "stopped by operator", 2: "entry-to-station timeout"}
STATUS_BITS = {0: "Running", 1: "FaultActive", 2: "CycleActive"}
COMMAND_BITS = {0: "StartRequest", 1: "StopRequest", 2: "ResetRequest", 3: "AutoMode"}


def main() -> int:
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    host = sys.argv[2] if len(sys.argv) > 2 else PLC_HOST_DEFAULT

    seen: Counter[int] = Counter()
    first = last = None
    try:
        for i in range(samples):
            mb = read_holding(host, MB_WINDOW, 7)
            seen[mb[4]] += 1
            if first is None:
                first = mb
            last = mb
            if i < samples - 1:
                time.sleep(0.25)
        sensors = read_holding(host, SENSOR_WINDOW, 4)
        # MAIN ORs two command paths; only the symbol window is actually used,
        # so mwCommands (%MB4) reads 0 even while the cell is commanded.
        actuators, commands = read_holding(host, REG_ACTUATORS, 2)
    except (OSError, ModbusError) as exc:
        print(f"cannot read {host}: {exc}")
        print("if the connection was refused, check the TF6250 licence - the")
        print("trial expires periodically and needs re-activating.")
        return 1

    assert first is not None and last is not None
    status, state, fault, parts = last[3], last[4], last[5], last[6]

    print(f"state      {state} {STATES.get(state, '?')}")
    print(f"fault      {fault} ({FAULTS.get(fault, 'unknown')})")
    print(f"status     {status} " + "  ".join(
        f"{n}={bool(status & (1 << b))}" for b, n in STATUS_BITS.items()))
    print(f"commands   {commands} " + "  ".join(
        f"{n}={bool(commands & (1 << b))}" for b, n in COMMAND_BITS.items())
          + f"   [reg {REG_COMMANDS}]")
    print(f"actuators  {actuators} ConveyorRun={bool(actuators & 1)}  "
          f"PusherExtend={bool(actuators & 2)}   [reg {REG_ACTUATORS}]")
    print(f"parts      {parts}" + (
        f"  (+{parts - first[6]} during this {samples * 0.25:.0f}s sample)"
        if parts != first[6] else "  (unchanged during the sample)"))
    print(f"sensors    entry={bool(sensors[0])} station={bool(sensors[1])} "
          f"exit={bool(sensors[2])}")

    print("\nstates seen during the sample:")
    for code, count in sorted(seen.items()):
        print(f"  {code:3d} {STATES.get(code, '?'):<18} {count}x")

    print()
    if state == 900:
        print(f"FAULTED ({FAULTS.get(fault, fault)}). Clear it with:")
        print("  python3 tools/start_cell.py reset && python3 tools/start_cell.py start")
    elif commands == 0:
        print("command word is 0 - not commanded to run. This is IDLE-by-instruction,")
        print("not a fault. Start it with: python3 tools/start_cell.py start")
    elif len(seen) == 1 and state == 10:
        print("stuck in WAIT_FOR_PART - commanded, not faulted, but no part is")
        print("arriving at the entry photo-eye. Check the carton's position in")
        print("Webots, and that the simulation is not paused.")
    elif len(seen) == 1:
        print(f"state has not changed during the sample - sitting in {STATES.get(state)}.")
    else:
        print(f"cycling normally through {len(seen)} states.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
