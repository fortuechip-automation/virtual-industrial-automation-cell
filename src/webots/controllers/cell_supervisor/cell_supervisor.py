"""
Conveyor cell supervisor — Webots MVP

Runs the virtual conveyor cell:
  - Moves the part (DEF PART) along the X axis based on conveyor state
  - Detects sensor positions at entry / station / exit X thresholds
  - Moves the pusher (DEF PUSHER) along the Z axis on command
  - Implements a standalone state machine so the cell self-runs when started
  - Exposes a TCP server on port 9000 for gateway integration

TCP interface (newline-delimited JSON):
  Supervisor → clients: state broadcast every ~100 ms
  Clients → supervisor: command objects, e.g. {"start": true} or {"reset": true}

When the gateway bridge is built (step 2), it connects here and replaces the
random-value loop in opcua_test_server.py with live physics data from this server.
The internal _update_state() method can then be bypassed by sending explicit
actuator commands from the gateway instead.
"""

import json
import socket
import threading
import time

from controller import Supervisor

TIMESTEP = 32  # ms

# Conveyor geometry — X axis (metres)
PART_START_X = -0.8
ENTRY_X = -0.6
STATION_X = 0.0
EXIT_X = 0.6
PART_END_X = 0.85
PART_Y = 0.075
PART_Z = 0.0

CONVEYOR_SPEED = 0.15  # m/s

# Pusher geometry — Z axis (metres)
PUSHER_RETRACTED_Z = -0.15
PUSHER_EXTENDED_Z = 0.05
PUSHER_SPEED = 0.08  # m/s
PUSHER_Y = 0.05

# Sensor detection half-width (metres each side of threshold)
SENSOR_RADIUS = 0.065

# Fault timeouts
CONVEYOR_TIMEOUT = 20.0  # seconds
PUSHER_TIMEOUT = 5.0

# TCP
TCP_HOST = "0.0.0.0"
TCP_PORT = 9000


class ConveyorSupervisor:
    def __init__(self):
        self.robot = Supervisor()

        part_node = self.robot.getFromDef("PART")
        pusher_node = self.robot.getFromDef("PUSHER")
        if part_node is None:
            raise RuntimeError("DEF PART not found — check conveyor_cell.wbt")
        if pusher_node is None:
            raise RuntimeError("DEF PUSHER not found — check conveyor_cell.wbt")

        self._part_tf = part_node.getField("translation")
        self._pusher_tf = pusher_node.getField("translation")

        # Physics state
        self.part_x = PART_START_X
        self.pusher_z = PUSHER_RETRACTED_Z

        # Machine state
        self.machine_state = "IDLE"
        self.conveyor_running = False
        self.pusher_extending = False
        self.pusher_retracting = False
        self.part_count = 0
        self.fault_active = False
        self.fault_message = ""
        self._state_timer = 0.0

        # Pending commands from TCP clients
        self._cmd_lock = threading.Lock()
        self._pending = {"start": False, "stop": False, "reset": False}

        # TCP clients (set of open sockets)
        self._clients = set()
        self._clients_lock = threading.Lock()

        t = threading.Thread(target=self._tcp_server, daemon=True)
        t.start()

    # ------------------------------------------------------------------ #
    # Derived sensor values                                                #
    # ------------------------------------------------------------------ #

    @property
    def entry_sensor(self):
        return abs(self.part_x - ENTRY_X) <= SENSOR_RADIUS

    @property
    def station_sensor(self):
        return abs(self.part_x - STATION_X) <= SENSOR_RADIUS

    @property
    def exit_sensor(self):
        return abs(self.part_x - EXIT_X) <= SENSOR_RADIUS

    @property
    def pusher_extended(self):
        return self.pusher_z >= PUSHER_EXTENDED_Z - 0.004

    @property
    def pusher_retracted(self):
        return self.pusher_z <= PUSHER_RETRACTED_Z + 0.004

    # ------------------------------------------------------------------ #
    # State machine                                                        #
    # ------------------------------------------------------------------ #

    def _update_state(self, dt):
        with self._cmd_lock:
            start = self._pending.pop("start", False)
            stop = self._pending.pop("stop", False)
            reset = self._pending.pop("reset", False)

        if reset:
            self._do_reset()
            return

        if stop and self.machine_state not in ("IDLE", "FAULT"):
            self._stop_all()
            return

        self._state_timer += dt

        if self.fault_active:
            self.machine_state = "FAULT"
            self.conveyor_running = False
            return

        if self.machine_state == "IDLE":
            if start:
                self.machine_state = "CONVEYOR_RUNNING"
                self.conveyor_running = True
                self._state_timer = 0.0
                print("[STATE] IDLE → CONVEYOR_RUNNING")

        elif self.machine_state == "CONVEYOR_RUNNING":
            self.conveyor_running = True
            if self.station_sensor:
                self.conveyor_running = False
                self.machine_state = "PART_AT_STATION"
                self._state_timer = 0.0
                print("[STATE] CONVEYOR_RUNNING → PART_AT_STATION")
            elif self._state_timer > CONVEYOR_TIMEOUT:
                self._fault("Conveyor timeout: part did not reach station")

        elif self.machine_state == "PART_AT_STATION":
            # Brief dwell before pusher extends
            if self._state_timer >= 0.5:
                self.machine_state = "PUSHER_EXTENDING"
                self.pusher_extending = True
                self._state_timer = 0.0
                print("[STATE] PART_AT_STATION → PUSHER_EXTENDING")

        elif self.machine_state == "PUSHER_EXTENDING":
            if self.pusher_extended:
                self.pusher_extending = False
                self.machine_state = "PUSHER_RETRACTING"
                self.pusher_retracting = True
                self._state_timer = 0.0
                print("[STATE] PUSHER_EXTENDING → PUSHER_RETRACTING")
            elif self._state_timer > PUSHER_TIMEOUT:
                self._fault("Pusher extend timeout")

        elif self.machine_state == "PUSHER_RETRACTING":
            if self.pusher_retracted:
                self.pusher_retracting = False
                self.machine_state = "CONVEYOR_TO_EXIT"
                self.conveyor_running = True
                self._state_timer = 0.0
                print("[STATE] PUSHER_RETRACTING → CONVEYOR_TO_EXIT")
            elif self._state_timer > PUSHER_TIMEOUT:
                self._fault("Pusher retract timeout")

        elif self.machine_state == "CONVEYOR_TO_EXIT":
            self.conveyor_running = True
            if self.exit_sensor:
                self.conveyor_running = False
                self.part_count += 1
                self.machine_state = "COMPLETE"
                self._state_timer = 0.0
                print(f"[STATE] CONVEYOR_TO_EXIT → COMPLETE (count={self.part_count})")
            elif self._state_timer > CONVEYOR_TIMEOUT:
                self._fault("Conveyor timeout: part did not reach exit")

        elif self.machine_state == "COMPLETE":
            # 1 s dwell, then reset part and start next cycle automatically
            if self._state_timer >= 1.0:
                self._reset_part()
                self.machine_state = "CONVEYOR_RUNNING"
                self.conveyor_running = True
                self._state_timer = 0.0
                print("[STATE] COMPLETE → CONVEYOR_RUNNING (next cycle)")

    def _fault(self, message):
        self.fault_active = True
        self.fault_message = message
        self.conveyor_running = False
        self.pusher_extending = False
        self.pusher_retracting = False
        self.machine_state = "FAULT"
        print(f"[FAULT] {message}")

    def _stop_all(self):
        self.conveyor_running = False
        self.pusher_extending = False
        self.pusher_retracting = False
        self.machine_state = "IDLE"
        self._state_timer = 0.0
        print("[STATE] → IDLE (stopped)")

    def _do_reset(self):
        self.fault_active = False
        self.fault_message = ""
        self._stop_all()
        self._reset_part()
        print("[STATE] Reset complete")

    def _reset_part(self):
        self.part_x = PART_START_X
        self._part_tf.setSFVec3f([self.part_x, PART_Y, PART_Z])
        self.pusher_z = PUSHER_RETRACTED_Z
        self._pusher_tf.setSFVec3f([0.0, PUSHER_Y, self.pusher_z])

    # ------------------------------------------------------------------ #
    # Physics update                                                       #
    # ------------------------------------------------------------------ #

    def _update_physics(self, dt):
        if self.conveyor_running:
            self.part_x = min(self.part_x + CONVEYOR_SPEED * dt, PART_END_X)
            self._part_tf.setSFVec3f([self.part_x, PART_Y, PART_Z])

        if self.pusher_extending and not self.pusher_extended:
            self.pusher_z = min(self.pusher_z + PUSHER_SPEED * dt, PUSHER_EXTENDED_Z)
            self._pusher_tf.setSFVec3f([0.0, PUSHER_Y, self.pusher_z])

        elif self.pusher_retracting and not self.pusher_retracted:
            self.pusher_z = max(self.pusher_z - PUSHER_SPEED * dt, PUSHER_RETRACTED_Z)
            self._pusher_tf.setSFVec3f([0.0, PUSHER_Y, self.pusher_z])

    # ------------------------------------------------------------------ #
    # TCP server                                                           #
    # ------------------------------------------------------------------ #

    def _state_dict(self):
        return {
            "ts": time.time(),
            "machine_state": self.machine_state,
            "conveyor_running": self.conveyor_running,
            "conveyor_speed": round(CONVEYOR_SPEED if self.conveyor_running else 0.0, 3),
            "entry_sensor": self.entry_sensor,
            "station_sensor": self.station_sensor,
            "exit_sensor": self.exit_sensor,
            "pusher_position": round(self.pusher_z, 4),
            "pusher_extended": self.pusher_extended,
            "pusher_retracted": self.pusher_retracted,
            "part_position_x": round(self.part_x, 4),
            "part_count": self.part_count,
            "fault_active": self.fault_active,
            "fault_message": self.fault_message,
        }

    def _handle_client(self, conn, addr):
        print(f"[TCP] Client connected: {addr}")
        conn.settimeout(0.05)  # short recv wait so state is sent every ~0.15s
        buf = ""
        try:
            while True:
                try:
                    conn.sendall((json.dumps(self._state_dict()) + "\n").encode())
                except OSError:
                    break

                try:
                    chunk = conn.recv(4096).decode(errors="replace")
                    if not chunk:
                        break
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            try:
                                cmd = json.loads(line)
                                with self._cmd_lock:
                                    self._pending.update(cmd)
                            except json.JSONDecodeError:
                                pass
                except socket.timeout:
                    pass
                except OSError:
                    break

                time.sleep(0.1)
        finally:
            print(f"[TCP] Client disconnected: {addr}")
            with self._clients_lock:
                self._clients.discard(conn)
            conn.close()

    def _tcp_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((TCP_HOST, TCP_PORT))
            srv.listen(5)
            print(f"[TCP] Listening on {TCP_HOST}:{TCP_PORT}")
            while True:
                conn, addr = srv.accept()
                with self._clients_lock:
                    self._clients.add(conn)
                threading.Thread(
                    target=self._handle_client, args=(conn, addr), daemon=True
                ).start()

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    def run(self):
        print("[Supervisor] Conveyor cell starting")
        print(f"[Supervisor] TCP interface: port {TCP_PORT}")
        print("[Supervisor] Send {\"start\": true} to begin cycle")

        last_sim_time = self.robot.getTime()

        while self.robot.step(TIMESTEP) != -1:
            now = self.robot.getTime()
            dt = now - last_sim_time
            last_sim_time = now

            self._update_state(dt)
            self._update_physics(dt)


def main():
    sup = ConveyorSupervisor()
    sup.run()


if __name__ == "__main__":
    main()
