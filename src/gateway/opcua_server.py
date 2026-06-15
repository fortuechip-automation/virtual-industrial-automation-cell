"""
Industrial Cell Gateway — OPC UA Server

Reads live physics data from the Webots supervisor (TCP, port 9000) and
publishes it as OPC UA tags so Ignition can display real simulation values.

Replaces the random-value loop in opcua_test_server.py.

Architecture:
  Webots supervisor (192.168.1.182:9000)
        |  newline-delimited JSON, ~100 ms
        v
  WebotsBridge (background thread)
        |  shared state dict
        v
  OPC UA Server (0.0.0.0:4840)
        |
        v
  Ignition SCADA

Tags added vs. test server:
  - StationSensor (new — not in the original test server)
"""

import asyncio
import json
import socket
import threading
import time

from asyncua import Server

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #

WEBOTS_HOST = "192.168.1.182"
WEBOTS_PORT = 9000
RECONNECT_DELAY = 5  # seconds between reconnect attempts
OPC_ENDPOINT = "opc.tcp://0.0.0.0:4840/industrial-cell/server/"
NAMESPACE_URI = "http://industrial-cell.local/opcua"


# ------------------------------------------------------------------ #
# Webots TCP bridge                                                    #
# ------------------------------------------------------------------ #

class WebotsBridge:
    """Maintains a persistent TCP connection to the Webots supervisor.

    Runs in a background thread. The latest state is always available
    via get_state(); callers never block waiting for a socket read.
    """

    def __init__(self):
        self._state: dict = {}
        self._lock = threading.Lock()
        self._connected = False
        t = threading.Thread(target=self._reader_loop, daemon=True)
        t.start()

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    @property
    def connected(self) -> bool:
        return self._connected

    def _reader_loop(self):
        while True:
            try:
                with socket.create_connection(
                    (WEBOTS_HOST, WEBOTS_PORT), timeout=5
                ) as sock:
                    self._connected = True
                    print(f"[Bridge] Connected to Webots at {WEBOTS_HOST}:{WEBOTS_PORT}")
                    sock.settimeout(2.0)
                    buf = ""
                    while True:
                        chunk = sock.recv(4096).decode(errors="replace")
                        if not chunk:
                            raise ConnectionResetError("Webots closed the connection")
                        buf += chunk
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            line = line.strip()
                            if line:
                                try:
                                    data = json.loads(line)
                                    with self._lock:
                                        self._state = data
                                except json.JSONDecodeError:
                                    pass
            except Exception as exc:
                self._connected = False
                print(f"[Bridge] Webots disconnected ({exc}), retrying in {RECONNECT_DELAY}s")
                time.sleep(RECONNECT_DELAY)


# ------------------------------------------------------------------ #
# OPC UA server                                                        #
# ------------------------------------------------------------------ #

async def main():
    bridge = WebotsBridge()

    server = Server()
    await server.init()
    server.set_endpoint(OPC_ENDPOINT)
    server.set_server_name("Industrial Automation Cell Gateway")

    idx = await server.register_namespace(NAMESPACE_URI)
    objects = server.nodes.objects
    cell = await objects.add_object(idx, "Cell_01")

    # Tags — matches opcua_test_server.py plus StationSensor
    machine_state  = await cell.add_variable(idx, "MachineState",  "UNKNOWN")
    conveyor_run   = await cell.add_variable(idx, "ConveyorRunning", False)
    conveyor_speed = await cell.add_variable(idx, "ConveyorSpeed",   0.0)
    entry_sensor   = await cell.add_variable(idx, "EntrySensor",   False)
    station_sensor = await cell.add_variable(idx, "StationSensor", False)
    exit_sensor    = await cell.add_variable(idx, "ExitSensor",    False)
    part_count     = await cell.add_variable(idx, "PartCount",     0)
    fault_active   = await cell.add_variable(idx, "FaultActive",   False)

    for node in (machine_state, conveyor_run, conveyor_speed,
                 entry_sensor, station_sensor, exit_sensor,
                 part_count, fault_active):
        await node.set_writable()

    print("OPC UA server starting")
    print(f"Endpoint : {OPC_ENDPOINT}")
    print(f"Namespace: {NAMESPACE_URI}")
    print("Browse   : Objects > Cell_01")
    print(f"Webots   : {WEBOTS_HOST}:{WEBOTS_PORT} (connecting…)")

    async with server:
        while True:
            state = bridge.get_state()

            if not state:
                # Webots not yet connected — write safe defaults
                await machine_state.write_value("DISCONNECTED")
                await asyncio.sleep(0.5)
                continue

            await machine_state.write_value(
                str(state.get("machine_state", "UNKNOWN")))
            await conveyor_run.write_value(
                bool(state.get("conveyor_running", False)))
            await conveyor_speed.write_value(
                float(state.get("conveyor_speed", 0.0)))
            await entry_sensor.write_value(
                bool(state.get("entry_sensor", False)))
            await station_sensor.write_value(
                bool(state.get("station_sensor", False)))
            await exit_sensor.write_value(
                bool(state.get("exit_sensor", False)))
            await part_count.write_value(
                int(state.get("part_count", 0)))
            await fault_active.write_value(
                bool(state.get("fault_active", False)))

            await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
