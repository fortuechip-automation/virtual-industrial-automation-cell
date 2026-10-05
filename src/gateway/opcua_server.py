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
import os
import socket
import struct
import threading
import time

from asyncua import Server

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #

# Each setting can be overridden by an environment variable of the same
# name; the defaults below match the lab layout.
WEBOTS_HOST = os.environ.get("WEBOTS_HOST", "192.168.1.182")
WEBOTS_PORT = int(os.environ.get("WEBOTS_PORT", "9000"))
RECONNECT_DELAY = int(os.environ.get("RECONNECT_DELAY", "5"))  # seconds between reconnect attempts
OPC_ENDPOINT = os.environ.get(
    "OPC_ENDPOINT", "opc.tcp://0.0.0.0:4840/industrial-cell/server/"
)
NAMESPACE_URI = "http://industrial-cell.local/opcua"

# The PLC owns the state machine, the fault code and the part count; Webots
# does not know them in PLC mode, so they are read from the PLC over Modbus.
PLC_HOST = os.environ.get("PLC_HOST", "192.168.1.181")
PLC_PORT = int(os.environ.get("PLC_PORT", "502"))
PLC_POLL_INTERVAL = float(os.environ.get("PLC_POLL_INTERVAL", "0.5"))  # seconds
PLC_UNIT_ID = 1  # TF6250 answers on unit 1
PLC_MB_WINDOW = 12288  # 12288+n -> %MB(2n): status, state, fault, part count

PLC_STATES = {
    0: "IDLE",
    10: "WAIT_FOR_PART",
    20: "CONVEYOR_RUNNING",
    30: "PART_AT_STATION",
    40: "PUSHER_EXTENDING",
    50: "PUSHER_RETRACTING",
    60: "COMPLETE",
    900: "FAULT",
}
PLC_FAULTS = {
    0: "none",
    1: "stopped by operator",
    2: "entry-to-station timeout",
    3: "part reached exit",
    99: "invalid state",
}


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
# PLC Modbus bridge                                                    #
# ------------------------------------------------------------------ #

class PlcBridge:
    """Polls the PLC's status registers over Modbus TCP. Read-only.

    Same shape as WebotsBridge: a background thread keeps the latest
    values, and get_state() returns {} while the PLC is unreachable.
    """

    def __init__(self):
        self._state: dict = {}
        self._lock = threading.Lock()
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    @staticmethod
    def _recv_exact(sock, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionResetError("PLC closed the connection")
            buf += chunk
        return buf

    def _read_holding(self, sock, start: int, count: int) -> list:
        pdu = struct.pack(">BHH", 0x03, start, count)
        sock.sendall(struct.pack(">HHHB", 1, 0, len(pdu) + 1, PLC_UNIT_ID) + pdu)
        _, _, length, _, func = struct.unpack(">HHHBB", self._recv_exact(sock, 8))
        body = self._recv_exact(sock, length - 2)
        if func & 0x80:
            raise RuntimeError(f"modbus exception code {body[0]}")
        return list(struct.unpack(">" + "H" * (body[0] // 2), body[1:1 + body[0]]))

    def _poll_loop(self):
        while True:
            try:
                with socket.create_connection((PLC_HOST, PLC_PORT), timeout=5) as sock:
                    print(f"[PLC] Connected to PLC at {PLC_HOST}:{PLC_PORT}")
                    while True:
                        mb = self._read_holding(sock, PLC_MB_WINDOW, 7)
                        with self._lock:
                            self._state = {
                                "state_code": mb[4],
                                "fault_code": mb[5],
                                "part_count": mb[6],
                            }
                        time.sleep(PLC_POLL_INTERVAL)
            except Exception as exc:
                with self._lock:
                    self._state = {}
                print(f"[PLC] PLC unreachable ({exc}), retrying in {RECONNECT_DELAY}s")
                time.sleep(RECONNECT_DELAY)


# ------------------------------------------------------------------ #
# OPC UA server                                                        #
# ------------------------------------------------------------------ #

async def main():
    bridge = WebotsBridge()
    plc = PlcBridge()

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

    # PLC tags — added after the Webots tags so the existing NodeIds, which
    # clients such as Ignition are bound to, do not move.
    plc_connected  = await cell.add_variable(idx, "PlcConnected",  False)
    plc_state      = await cell.add_variable(idx, "PlcState",      "UNKNOWN")
    plc_state_code = await cell.add_variable(idx, "PlcStateCode",  0)
    fault_code     = await cell.add_variable(idx, "FaultCode",     0)
    fault_text     = await cell.add_variable(idx, "FaultText",     "unknown")

    for node in (machine_state, conveyor_run, conveyor_speed,
                 entry_sensor, station_sensor, exit_sensor,
                 part_count, fault_active):
        await node.set_writable()

    print("OPC UA server starting")
    print(f"Endpoint : {OPC_ENDPOINT}")
    print(f"Namespace: {NAMESPACE_URI}")
    print("Browse   : Objects > Cell_01")
    print(f"Webots   : {WEBOTS_HOST}:{WEBOTS_PORT} (connecting…)")
    print(f"PLC      : {PLC_HOST}:{PLC_PORT} (connecting…)")

    async with server:
        while True:
            state = bridge.get_state()
            plc_data = plc.get_state()

            # PLC-owned values. Without the PLC, the part count and fault
            # flag fall back to whatever Webots reports.
            await plc_connected.write_value(bool(plc_data))
            if plc_data:
                code = plc_data["state_code"]
                fault = plc_data["fault_code"]
                await plc_state.write_value(PLC_STATES.get(code, f"UNKNOWN_{code}"))
                await plc_state_code.write_value(code)
                await fault_code.write_value(fault)
                await fault_text.write_value(PLC_FAULTS.get(fault, f"code {fault}"))
                await part_count.write_value(plc_data["part_count"])
                await fault_active.write_value(fault != 0)
            else:
                await plc_state.write_value("DISCONNECTED")
                await part_count.write_value(int(state.get("part_count", 0)))
                await fault_active.write_value(
                    bool(state.get("fault_active", False)))

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

            await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
