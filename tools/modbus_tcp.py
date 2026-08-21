"""Minimal Modbus TCP client, dependency-free.

The Webots supervisor uses pymodbus, but these tools are meant to run from any
machine on the lab network — including one with nothing installed — so this
speaks the wire protocol over a raw socket instead.

Only two function codes are implemented: 0x03 (read holding registers) and
0x06 (write single register). That is all the cell's command path needs.
"""

from __future__ import annotations

import socket
import struct

PLC_HOST_DEFAULT = "192.168.1.181"
PLC_PORT = 502
PLC_UNIT_ID = 1  # TF6250 answers on unit 1

REG_ACTUATORS = 32768  # GVL.mb_Output_Registers[0] <- mwActuators
REG_COMMANDS = 32769  # GVL.mb_Output_Registers[1] -> command word

ACTUATOR_BITS = {0: "ConveyorRun", 1: "PusherExtend"}
COMMAND_BITS = {0: "StartRequest", 1: "StopRequest", 2: "ResetRequest", 3: "AutoMode"}


class ModbusError(RuntimeError):
    pass


def _transact(host: str, pdu: bytes, timeout: float = 5.0) -> bytes:
    """Send one PDU, return the response PDU body (after the function code)."""
    mbap = struct.pack(">HHHB", 1, 0, len(pdu) + 1, PLC_UNIT_ID)
    sock = socket.create_connection((host, PLC_PORT), timeout=timeout)
    try:
        sock.sendall(mbap + pdu)
        head = sock.recv(8)
        if len(head) < 8:
            raise ModbusError("short reply header - no response from server")
        _, _, length, _, func = struct.unpack(">HHHBB", head)
        body = sock.recv(length - 2)
        if func & 0x80:
            raise ModbusError(f"modbus exception code {body[0]}")
        return body
    finally:
        sock.close()


def read_holding(host: str, start: int, count: int) -> list[int]:
    body = _transact(host, struct.pack(">BHH", 0x03, start, count))
    nbytes = body[0]
    return list(struct.unpack(">" + "H" * (nbytes // 2), body[1 : 1 + nbytes]))


def write_single(host: str, register: int, value: int) -> int:
    """Write one register. Returns the value the PLC echoed back."""
    body = _transact(host, struct.pack(">BHH", 0x06, register, value))
    _, echoed = struct.unpack(">HH", body)
    return echoed


def decode_bits(word: int, names: dict[int, str]) -> str:
    return "  ".join(f"{name}={bool(word & (1 << bit))}" for bit, name in names.items())
