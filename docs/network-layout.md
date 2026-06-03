# Network Layout

This document records the current network layout for the Virtual Industrial Automation Cell project.

The first phase of the project uses the main home/lab LAN for simplicity. Static DHCP reservations are configured in the main OPNsense router so that each VM keeps a predictable IP address while still using DHCP.

## Current Network Phase

```text
Main OPNsense Router
192.168.1.1
        |
        v
Proxmox Host
        |
        +-- twincat-eng
        +-- webots-sim
        +-- automation-ignition-scada
        +-- postgres-historian
        +-- gateway
```

## Static DHCP Reservations

| VM                          |      IP Address | Role                           |
| --------------------------- | --------------: | ------------------------------ |
| `twincat-eng`               | `192.168.1.181` | TwinCAT engineering/runtime VM |
| `webots-sim`                | `192.168.1.182` | Webots simulation VM           |
| `automation-ignition-scada` | `192.168.1.183` | Ignition SCADA VM              |
| `postgres-historian`        | `192.168.1.184` | PostgreSQL historian VM        |
| `gateway`                   | `192.168.1.187` | OPC UA/MQTT/Python gateway VM  |

## Current Design Decision

The project currently uses the main LAN instead of an isolated OT subnet.

This was chosen because the first priority is to build and test the core automation workflow:

```text
Webots Simulation
        |
        v
Gateway
        |
        +-- Ignition SCADA
        +-- PostgreSQL Historian
        +-- TwinCAT Engineering
```

Using the main LAN during the early phase makes it easier to:

* Install software packages
* Access VMs by SSH
* Use NoMachine for graphical access
* Open Ignition from a browser
* Troubleshoot services before adding routing complexity

## Access Methods

| VM                          | Access Method                             |
| --------------------------- | ----------------------------------------- |
| `twincat-eng`               | NoMachine / Proxmox Console               |
| `webots-sim`                | SSH / Proxmox Console / graphical desktop |
| `automation-ignition-scada` | SSH / Ignition web interface              |
| `postgres-historian`        | SSH / PostgreSQL client                   |
| `gateway`                   | SSH                                       |

## Important Ports

| Service          | VM                          |   Port |
| ---------------- | --------------------------- | -----: |
| SSH              | Linux VMs                   |   `22` |
| NoMachine        | `twincat-eng`               | `4000` |
| Ignition Gateway | `automation-ignition-scada` | `8088` |
| PostgreSQL       | `postgres-historian`        | `5432` |
| OPC UA Gateway   | `gateway`                   | `4840` |
| MQTT, planned    | `gateway`                   | `1883` |

## Current Status

* Static DHCP reservations are configured in the main OPNsense router.
* Linux VM SSH access has been tested.
* NoMachine access has been configured for the Windows TwinCAT VM.
* Webots is installed and launching on `webots-sim`.
* PostgreSQL is installed and running on `postgres-historian`.

## Future Network Phase

A later phase may introduce a virtual OPNsense firewall and an isolated industrial automation lab subnet.

The future design may look like this:

```text
Main OPNsense Router
192.168.1.1
        |
        v
Virtual OPNsense Lab Router
        |
        v
Industrial Automation Lab Network
172.30.10.0/24
```

Possible future IP plan:

| VM                          |   Future Lab IP |
| --------------------------- | --------------: |
| `twincat-eng`               | `172.30.10.181` |
| `webots-sim`                | `172.30.10.182` |
| `automation-ignition-scada` | `172.30.10.183` |
| `postgres-historian`        | `172.30.10.184` |
| `gateway`                   | `172.30.10.187` |

## Future Networking Goals

The future isolated OT lab network may be used to demonstrate:

* OT/IT network separation
* Firewall rules
* Routing between LAN and lab network
* Controlled access to industrial services
* Industrial DMZ concepts
* Safer testing of automation services

This will be added after the core automation workflow is functioning on the main LAN.
