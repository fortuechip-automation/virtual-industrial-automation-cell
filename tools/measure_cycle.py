#!/usr/bin/env python3
"""Measure the cell's cycle time in SIMULATED time.

    python3 tools/measure_cycle.py [cycles] [webots_host]

Why not a stopwatch: Webots runs at roughly 0.96x real time, and drops further
under rendering load, so a wall-clock measurement of a simulated machine is
measuring the host's spare capacity as much as the machine.

The supervisor publishes its tag set to any TCP client on port 9000, and it does
so on a simulation-time schedule (`publish_accumulator_ms += self.timestep_ms`).
So counting messages measures the simulation clock directly and is immune to the
drift. The ratio of sim time to wall time is reported as a by-product.

SUBTLETY: `_publish_state` resets its accumulator to 0 rather than subtracting
the period, so a publish costs a whole number of ticks - ceil(100/16)*16 = 112 ms
of simulated time, not the nominal 100. Using 100 here understates sim time by
12% and produces a real-time ratio that looks alarming and is simply wrong.

A cycle boundary is the carton being re-homed, which `_home_carton()` does on the
pusher's rising edge - i.e. one part completed and removed.

Read-only: this connects as an observer and writes nothing.
"""

from __future__ import annotations

import json
import math
import socket
import sys
import time

WEBOTS_HOST_DEFAULT = "192.168.1.182"
WEBOTS_TCP_PORT = 9000

BASIC_TIMESTEP_MS = 16  # webots/worlds/industrial_cell_mvp.wbt
PUBLISH_PERIOD_NOMINAL_MS = 100  # PUBLISH_PERIOD_MS in the supervisor
# The accumulator resets to 0, so the real interval rounds up to whole ticks.
PUBLISH_PERIOD_MS = math.ceil(PUBLISH_PERIOD_NOMINAL_MS / BASIC_TIMESTEP_MS) * BASIC_TIMESTEP_MS

HOME_JUMP_M = 0.5  # carton_x leaping back toward its home of 1.05
WALL_TIMEOUT_S = 300
RECV_TIMEOUT_S = 15


def main() -> int:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    host = sys.argv[2] if len(sys.argv) > 2 else WEBOTS_HOST_DEFAULT

    try:
        sock = socket.create_connection((host, WEBOTS_TCP_PORT), timeout=RECV_TIMEOUT_S)
    except OSError as exc:
        print(f"cannot connect to {host}:{WEBOTS_TCP_PORT}: {exc}")
        return 1
    print(f"connected to {host}:{WEBOTS_TCP_PORT}, {PUBLISH_PERIOD_MS} ms of sim time per message\n")

    buf = b""
    messages = 0
    prev_x: float | None = None
    marks: list[int] = []
    started = time.time()

    while len(marks) < cycles + 1:
        if time.time() - started > WALL_TIMEOUT_S:
            print(f"\n-- wall-clock timeout after {WALL_TIMEOUT_S}s --")
            break
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            print("no data - is the simulation paused?")
            break
        if not chunk:
            print("publisher closed the connection")
            break
        buf += chunk

        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                tags = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages += 1
            if messages == 1:
                print(
                    f"mode={tags.get('control_mode')} "
                    f"running={tags.get('conveyor_running')} "
                    f"fault={tags.get('fault_active')}\n"
                )
            x = tags.get("carton_x")
            if prev_x is not None and x is not None and (x - prev_x) > HOME_JUMP_M:
                marks.append(messages)
                if len(marks) > 1:
                    gap = (marks[-1] - marks[-2]) * PUBLISH_PERIOD_MS / 1000.0
                    print(f"cycle {len(marks) - 1}: {gap:.2f} s sim")
            prev_x = x

    sock.close()

    wall_s = time.time() - started
    sim_s = messages * PUBLISH_PERIOD_MS / 1000.0
    print(f"\nmessages={messages}  sim={sim_s:.1f}s  wall={wall_s:.1f}s  ratio={sim_s / wall_s:.3f}x")

    if len(marks) < 2:
        print(f"\nonly {len(marks)} cycle boundary/boundaries seen - nothing to measure.")
        print("if the cell is idle, start it with start_cell.py")
        return 1

    gaps = [(b - a) * PUBLISH_PERIOD_MS / 1000.0 for a, b in zip(marks, marks[1:])]
    mean = sum(gaps) / len(gaps)
    resolution = PUBLISH_PERIOD_MS / 1000.0
    print(
        f"\ncycle time: n={len(gaps)}  mean={mean:.2f}s sim  "
        f"min={min(gaps):.2f}s  max={max(gaps):.2f}s  (resolution +/-{resolution:.3f}s)"
    )
    if max(gaps) - min(gaps) <= resolution * 1.01:
        print("spread is within one sample - the cycle is timer-dominated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
