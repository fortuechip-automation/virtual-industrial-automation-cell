"""Physics-first Webots controller for the industrial cell MVP.

The conveyor is a Webots Track driven by a LinearMotor. The carton is a
physical Solid; this controller does not force its position during normal
operation. Sensor tags come from Webots DistanceSensor devices.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any

from controller import Supervisor


CONTROL_MODE_ENV = "WEBOTS_CELL_MODE"
CONTROL_MODE_DEMO = "demo"
CONTROL_MODE_PLC = "plc"
VALID_CONTROL_MODES = {CONTROL_MODE_DEMO, CONTROL_MODE_PLC}
TCP_HOST = "0.0.0.0"
TCP_PORT = 9000
PUBLISH_PERIOD_MS = 100
PLC_HOST_ENV = "WEBOTS_PLC_HOST"
PLC_HOST_DEFAULT = "192.168.1.181"
PLC_POLL_PERIOD_MS = 100
MB_REG_ACTUATORS = 32768  # TF6250 map: GVL.mb_Output_Registers[0] = actuator word
MB_ACTUATOR_BIT_CONVEYOR_RUN = 0x0001  # bit 0 = ConveyorRun
MB_ACTUATOR_BIT_PUSHER_EXTEND = 0x0002  # bit 1 = PusherExtend
MB_REG_SENSOR_BASE = 33024  # TF6250 map: GVL.mb_Input_Registers[0..] (writable window)
BELT_SPEED_MPS = 0.24
PHOTOEYE_BLOCKED_THRESHOLD = 450.0
OUTFEED_RECYCLE_DELAY_MS = 1500
CARTON_HOME = [1.05, 0.0, 0.34]  # staged on the entry photo-eye beam
CARTON_HOME_ROTATION = [0.0, 0.0, 1.0, 0.0]


def configured_control_mode() -> str:
    mode = os.environ.get(CONTROL_MODE_ENV, CONTROL_MODE_DEMO).strip().lower()
    if mode in VALID_CONTROL_MODES:
        return mode
    print(
        f"[Webots] Unknown {CONTROL_MODE_ENV}={mode!r}; "
        f"falling back to {CONTROL_MODE_DEMO!r}",
        flush=True,
    )
    return CONTROL_MODE_DEMO


class TcpPublisher:
    def __init__(self, host: str, port: int) -> None:
        self.clients: list[socket.socket] = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(4)
        self.server.setblocking(False)
        print(f"[Webots] TCP publisher listening on {host}:{port}", flush=True)

    def publish(self, payload: dict[str, Any]) -> None:
        self._accept_pending()
        if not self.clients:
            return

        message = (json.dumps(payload) + "\n").encode("utf-8")
        alive: list[socket.socket] = []
        for client in self.clients:
            try:
                client.sendall(message)
                alive.append(client)
            except OSError:
                try:
                    client.close()
                except OSError:
                    pass
        self.clients = alive

    def _accept_pending(self) -> None:
        while True:
            try:
                client, addr = self.server.accept()
            except BlockingIOError:
                return
            client.setblocking(False)
            self.clients.append(client)
            print(f"[Webots] Gateway connected from {addr[0]}:{addr[1]}", flush=True)


class PlcIoClient:
    """Modbus TCP link to the TwinCAT PLC.

    Fail-safe by design: any read problem (no connection, Modbus exception,
    timeout) is reported as None, and the caller must treat None as STOP.
    """

    def __init__(self, host: str) -> None:
        # Imported here, not at module top, so demo mode still runs on a
        # machine without pymodbus installed.
        from pymodbus.client import ModbusTcpClient
        from pymodbus.exceptions import ModbusException

        self.modbus_exception = ModbusException
        self.host = host
        self.client = ModbusTcpClient(host, timeout=0.2, retries=1)
        # None = unknown, so the very first read always reports UP or DOWN.
        self.link_up: bool | None = None

    def read_actuators(self) -> int | None:
        try:
            response = self.client.read_holding_registers(
                MB_REG_ACTUATORS, count=1
            )
            if response.isError():
                self._report_link(False)
                return None
        except (OSError, self.modbus_exception):
            self._report_link(False)
            return None
        self._report_link(True)
        return response.registers[0]

    def write_sensors(self, values: list[int]) -> None:
        try:
            response = self.client.write_registers(MB_REG_SENSOR_BASE, values)
            if response.isError():
                self._report_link(False)
                return
        except (OSError, self.modbus_exception):
            self._report_link(False)
            return
        self._report_link(True)

    def _report_link(self, up: bool) -> None:
        if up == self.link_up:
            return
        self.link_up = up
        state = "UP" if up else "DOWN (fail-safe stop)"
        print(f"[Webots] PLC Modbus link to {self.host}: {state}", flush=True)


class IndustrialCellSupervisor:
    def __init__(self) -> None:
        self.robot = Supervisor()
        self.timestep_ms = int(self.robot.getBasicTimeStep())
        self.control_mode = configured_control_mode()
        self.demo_mode = self.control_mode == CONTROL_MODE_DEMO
        self.plc_mode = self.control_mode == CONTROL_MODE_PLC
        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep_ms)

        self.belt_motor = self.robot.getDevice("belt_motor")
        self.entry_sensor = self.robot.getDevice("pe_entry")
        self.station_sensor = self.robot.getDevice("pe_station")
        self.exit_sensor = self.robot.getDevice("pe_exit")
        for sensor in (self.entry_sensor, self.station_sensor, self.exit_sensor):
            sensor.enable(self.timestep_ms)

        self.carton = self.robot.getFromDef("CARTON")
        if self.carton is None:
            raise RuntimeError("World is missing required DEF CARTON node")

        self.carton_translation = self.carton.getField("translation")
        self.carton_rotation = self.carton.getField("rotation")
        self.publisher = TcpPublisher(TCP_HOST, TCP_PORT)

        self.running = self.demo_mode
        self.plc_conveyor_run_cmd = False
        self.pusher_extended_prev = False
        self.plc_conveyor_speed_cmd = BELT_SPEED_MPS
        self.fault_active = False
        self.fault_code = ""
        self.part_count = 0
        self.exit_latched = False
        self.belt_position = 0.0
        self.recycle_accumulator_ms = 0
        self.publish_accumulator_ms = 0
        self.plc_poll_accumulator_ms = 0
        self.last_snapshot: tuple[Any, ...] | None = None
        self.plc_io: PlcIoClient | None = None
        if self.plc_mode:
            plc_host = os.environ.get(PLC_HOST_ENV, PLC_HOST_DEFAULT)
            self.plc_io = PlcIoClient(plc_host)

        self.belt_motor.setPosition(self.belt_position)
        self._home_carton()
        print(f"[Webots] Physics conveyor ready in {self.control_mode.upper()} mode", flush=True)
        print("[Webots] Keys: S=start T=stop R=reset F=fault", flush=True)
        if self.plc_mode:
            print("[Webots] PLC mode waits for external I/O commands", flush=True)

    def run(self) -> None:
        while self.robot.step(self.timestep_ms) != -1:
            self._handle_keyboard()
            self._poll_plc()
            self._drive_belt()
            self._update_count()
            self._print_changes()
            self._publish_state()

    def _handle_keyboard(self) -> None:
        key = self.keyboard.getKey()
        while key != -1:
            char = chr(key).lower() if 0 <= key <= 255 else ""
            if char == "s":
                self.running = True
                self.fault_active = False
                self.fault_code = ""
            elif char == "t":
                self.running = False
            elif char == "r":
                self.reset_cell()
            elif char == "f":
                self.running = False
                self.fault_active = True
                self.fault_code = "MANUAL_FAULT"
            key = self.keyboard.getKey()

    def _poll_plc(self) -> None:
        if self.plc_io is None:
            return
        self.plc_poll_accumulator_ms += self.timestep_ms
        if self.plc_poll_accumulator_ms < PLC_POLL_PERIOD_MS:
            return
        self.plc_poll_accumulator_ms = 0
        self.plc_io.write_sensors(
            [
                int(self._blocked(self.entry_sensor)),
                int(self._blocked(self.station_sensor)),
                int(self._blocked(self.exit_sensor)),
            ]
        )
        actuators = self.plc_io.read_actuators()
        self.plc_conveyor_run_cmd = bool(
            actuators is not None and actuators & MB_ACTUATOR_BIT_CONVEYOR_RUN
        )
        pusher_extended = bool(
            actuators is not None and actuators & MB_ACTUATOR_BIT_PUSHER_EXTEND
        )
        if pusher_extended and not self.pusher_extended_prev:
            self._home_carton()
            print("[Webots] Pusher removed part; next carton staged at infeed", flush=True)
        self.pusher_extended_prev = pusher_extended

    def _drive_belt(self) -> None:
        dt_s = self.timestep_ms / 1000.0
        if self._conveyor_commanded():
            self.belt_position -= self._commanded_belt_speed() * dt_s
        self.belt_motor.setPosition(self.belt_position)

    def _update_count(self) -> None:
        exit_blocked = self._blocked(self.exit_sensor)
        if self.demo_mode and exit_blocked and not self.exit_latched:
            self.part_count += 1
            self.exit_latched = True
        elif not exit_blocked:
            self.exit_latched = False

        carton_x = self.carton_translation.getSFVec3f()[0]
        if self.demo_mode and self.running and not exit_blocked and carton_x < -1.48:
            self.recycle_accumulator_ms += self.timestep_ms
            if self.recycle_accumulator_ms >= OUTFEED_RECYCLE_DELAY_MS:
                self._home_carton()
                self.recycle_accumulator_ms = 0
                print("[Webots] Loaded next carton at infeed", flush=True)
        else:
            self.recycle_accumulator_ms = 0

    def _print_changes(self) -> None:
        entry = self._blocked(self.entry_sensor)
        station = self._blocked(self.station_sensor)
        exit_ = self._blocked(self.exit_sensor)
        snapshot = (
            entry,
            station,
            exit_,
            self.part_count,
            self._conveyor_commanded(),
            self.control_mode,
        )
        if snapshot == self.last_snapshot:
            return
        self.last_snapshot = snapshot
        print(
            "[I/O] "
            f"Mode={self.control_mode.upper()} "
            f"Run={self._conveyor_commanded()} "
            f"Entry={entry}({self.entry_sensor.getValue():.0f}) "
            f"Station={station}({self.station_sensor.getValue():.0f}) "
            f"Exit={exit_}({self.exit_sensor.getValue():.0f}) "
            f"Count={self.part_count}",
            flush=True,
        )

    def _publish_state(self) -> None:
        self.publish_accumulator_ms += self.timestep_ms
        if self.publish_accumulator_ms < PUBLISH_PERIOD_MS:
            return
        self.publish_accumulator_ms = 0
        self.publisher.publish(self.tags())

    def reset_cell(self) -> None:
        self.running = False
        self.fault_active = False
        self.fault_code = ""
        self.exit_latched = False
        self.recycle_accumulator_ms = 0
        self.part_count = 0
        self._home_carton()
        if self.demo_mode:
            print("[Webots] Reset complete; press S to run", flush=True)
        else:
            print("[Webots] Reset complete; waiting for PLC run command", flush=True)

    def _home_carton(self) -> None:
        self.carton_translation.setSFVec3f(CARTON_HOME)
        self.carton_rotation.setSFRotation(CARTON_HOME_ROTATION)
        self.carton.resetPhysics()

    def _conveyor_commanded(self) -> bool:
        if self.fault_active:
            return False
        if self.demo_mode:
            return self.running
        return self.plc_conveyor_run_cmd

    def _commanded_belt_speed(self) -> float:
        if self.demo_mode:
            return BELT_SPEED_MPS
        return self.plc_conveyor_speed_cmd

    def tags(self) -> dict[str, Any]:
        carton_position = self.carton_translation.getSFVec3f()
        conveyor_running = self._conveyor_commanded()
        return {
            "control_mode": self.control_mode,
            "machine_state": "RUNNING" if conveyor_running else "IDLE",
            "conveyor_running": conveyor_running,
            "conveyor_speed": self._commanded_belt_speed() if conveyor_running else 0.0,
            "entry_sensor": self._blocked(self.entry_sensor),
            "station_sensor": self._blocked(self.station_sensor),
            "exit_sensor": self._blocked(self.exit_sensor),
            "part_count": self.part_count,
            "fault_active": self.fault_active,
            "fault_code": self.fault_code,
            "carton_x": carton_position[0],
            "carton_y": carton_position[1],
            "carton_z": carton_position[2],
        }

    @staticmethod
    def _blocked(sensor: Any) -> bool:
        return sensor.getValue() > PHOTOEYE_BLOCKED_THRESHOLD


if __name__ == "__main__":
    IndustrialCellSupervisor().run()
