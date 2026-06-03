# Build Log

## Baseline Infrastructure

The initial VM infrastructure for the virtual industrial automation cell has been created on Proxmox.

### VM Stack

| VM                          |      IP Address | Purpose                     |
| --------------------------- | --------------: | --------------------------- |
| `twincat-eng`               | `192.168.1.181` | TwinCAT engineering/runtime |
| `webots-sim`                | `192.168.1.182` | Webots simulation           |
| `automation-ignition-scada` | `192.168.1.183` | Ignition SCADA              |
| `postgres-historian`        | `192.168.1.184` | PostgreSQL historian        |
| `gateway`                   | `192.168.1.187` | OPC UA/MQTT/Python gateway  |

### Completed Setup

* Created all five project VMs in Proxmox.
* Configured static DHCP reservations in the main OPNsense router.
* Confirmed SSH access to all Linux VMs.
* Configured NoMachine access for the Windows TwinCAT engineering VM.
* Installed and launched Webots on the `webots-sim` VM.
* Installed PostgreSQL 16 on the `postgres-historian` VM.
* Created the `industrial_cell` database.
* Created the initial historian schema for telemetry, events, alarms, and production counts.

### Current Project Phase

The project is currently in the software installation and integration phase.

The next major milestone is to create a simple OPC UA server on the `gateway` VM and connect Ignition SCADA to it as an OPC UA client.
