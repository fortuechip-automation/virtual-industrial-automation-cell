# tools

Dependency-free diagnostics for the cell. Plain Python 3, standard library only —
they run from any machine on the lab network without a venv or pymodbus, which
matters when the thing you are debugging is the network path itself.

| Tool | Writes to the plant? | Purpose |
|---|---|---|
| `modbus_tcp.py` | — | minimal Modbus TCP client (function 0x03 and 0x06) shared by the others |
| `read_cell.py` | no | read the actuator and command words; explains *why* the cell is idle |
| `start_cell.py` | **yes** | start / stop / reset the cell, then verify the PLC acted |
| `measure_cycle.py` | no | measure cycle time on the **simulation** clock |

```bash
python3 tools/read_cell.py                 # why isn't it moving?
python3 tools/start_cell.py start          # StartRequest + AutoMode
python3 tools/measure_cycle.py 8           # time 8 cycles
python3 tools/start_cell.py stop           # clear the command word
```

Hosts default to the lab addresses in the top-level README and can be overridden
as the last argument.

## Two things about this PLC that are easy to get wrong

**There are two command paths, and only one is used.** `MAIN` ORs them together:

```
bStartRequest := GVL_ModbusIO.mwCommands.0 OR GVL.mb_Output_Registers[1].0;
```

Commands arrive through the symbol window (`mb_Output_Registers[1]`, register
32769), so `mwCommands` (`%MB4`) reads 0 permanently. A tool that samples
`mwCommands` will report an uncommanded cell while it is visibly cycling. The
same applies to actuators: read register 32768, not `mwActuators`.

**The `12288+` window works.** `GVL_ModbusIO` records that route as "UNPROVEN";
it is proven, and it is the only way to read the state code, fault code and part
count over Modbus, because `MAIN` mirrors only the actuator word into the symbol
window. Mapping is `12288+n -> %MB(2n)`:

| register | variable |
|---|---|
| 12288 | `mwSensors` (0 - Webots writes to 33024+ instead) |
| 12289 | `mwActuators` |
| 12290 | `mwCommands` (0 - see above) |
| 12291 | `mwStatus` |
| 12292 | `mwStateCode` |
| 12293 | `mwFaultCode` |
| 12294 | `mwPartCount` |

**Never diagnose a cycling machine from one sample.** `ConveyorRun` is false
during both pusher phases and while waiting for a part, so a single read cannot
tell "faulted" from "mid-cycle". Both tools sample over seconds and report the
set of states seen.

## Notes worth keeping

**The command word does not persist.** Register 32769 reads 0 after the PLC
restarts, so the cell comes back IDLE rather than resuming. That is safe
behaviour, but it means "not moving" usually means "not commanded" rather than
"broken" — `read_cell.py` distinguishes the two.

**Measure in the simulation's clock, not yours.** Webots runs at ~0.96x real
time. `measure_cycle.py` counts the supervisor's state publications, which are
emitted on the simulation clock, so the drift cannot contaminate the result. See
the docstring for the 112 ms tick subtlety that makes the naive version wrong.
