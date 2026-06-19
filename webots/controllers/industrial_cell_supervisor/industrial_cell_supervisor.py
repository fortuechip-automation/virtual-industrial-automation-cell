"""Physics-first Webots controller for the industrial cell MVP.

The conveyor is a Webots Track driven by a LinearMotor. The carton is a
physical Solid; this controller does not force its position during normal
operation. Sensor tags come from Webots DistanceSensor devices.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from controller import Supervisor


TCP_HOST = "0.0.0.0"
TCP_PORT = 9000
PUBLISH_PERIOD_MS = 100
BELT_SPEED_MPS = 0.24
PHOTOEYE_BLOCKED_THRESHOLD = 450.0
OUTFEED_RECYCLE_DELAY_MS = 1500
CARTON_HOME = [1.38, 0.0, 0.34]
CARTON_HOME_ROTATION = [0.0, 0.0, 1.0, 0.0]


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


class IndustrialCellSupervisor:
    def __init__(self) -> None:
        self.robot = Supervisor()
        self.timestep_ms = int(self.robot.getBasicTimeStep())
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

        self.running = True
        self.fault_active = False
        self.fault_code = ""
        self.part_count = 0
        self.exit_latched = False
        self.belt_position = 0.0
        self.recycle_accumulator_ms = 0
        self.publish_accumulator_ms = 0
        self.last_snapshot: tuple[bool, bool, bool, int, bool] | None = None

        self.belt_motor.setPosition(self.belt_position)
        self._home_carton()
        print("[Webots] Physics conveyor ready", flush=True)
        print("[Webots] Keys: S=start T=stop R=reset F=fault", flush=True)

    def run(self) -> None:
        while self.robot.step(self.timestep_ms) != -1:
            self._handle_keyboard()
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

    def _drive_belt(self) -> None:
        dt_s = self.timestep_ms / 1000.0
        if self.running and not self.fault_active:
            self.belt_position -= BELT_SPEED_MPS * dt_s
        self.belt_motor.setPosition(self.belt_position)

    def _update_count(self) -> None:
        exit_blocked = self._blocked(self.exit_sensor)
        if exit_blocked and not self.exit_latched:
            self.part_count += 1
            self.exit_latched = True
        elif not exit_blocked:
            self.exit_latched = False

        carton_x = self.carton_translation.getSFVec3f()[0]
        if self.running and not exit_blocked and carton_x < -1.48:
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
        snapshot = (entry, station, exit_, self.part_count, self.running)
        if snapshot == self.last_snapshot:
            return
        self.last_snapshot = snapshot
        print(
            "[I/O] "
            f"Run={self.running} "
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
        print("[Webots] Reset complete; press S to run", flush=True)

    def _home_carton(self) -> None:
        self.carton_translation.setSFVec3f(CARTON_HOME)
        self.carton_rotation.setSFRotation(CARTON_HOME_ROTATION)
        self.carton.resetPhysics()

    def tags(self) -> dict[str, Any]:
        carton_position = self.carton_translation.getSFVec3f()
        return {
            "machine_state": "RUNNING" if self.running else "IDLE",
            "conveyor_running": self.running and not self.fault_active,
            "conveyor_speed": BELT_SPEED_MPS if self.running and not self.fault_active else 0.0,
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
