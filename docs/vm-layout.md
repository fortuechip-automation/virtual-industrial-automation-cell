# VM Layout

This project is deployed on a Proxmox VE host as a multi-VM industrial automation lab.

| VMID | VM | OS | vCPU | RAM | Disk | Purpose |
|---:|---|---|---:|---:|---:|---|
| 400 | `twincat-eng` | Windows 10/11 | 6 | 16 GB | 150 GB | TwinCAT IDE/runtime |
| 401 | `webots-sim` | Ubuntu Desktop | 4–6 | 12 GB | 100 GB | Simulation |
| 402 | `gateway` | Ubuntu Server | 2–4 | 4–8 GB | 60 GB | OPC UA/MQTT bridge |
| 403 | `automation-ignition-scada` | Ubuntu Server | 4 | 8–12 GB | 100 GB | SCADA dashboard |
| 404 | `postgres-historian` | Ubuntu Server | 2–4 | 8–16 GB | 150 GB | Database/historian |

## Notes

- All VMs are hosted on Proxmox VE.
- Static DHCP reservations are configured in the main OPNsense router.
- Linux VMs are managed primarily through SSH.
- The Windows TwinCAT VM is accessed using NoMachine and Proxmox Console.
- The first project phase uses the main LAN for simplicity.
- A future phase may move the lab behind a virtual OPNsense firewall or isolated OT subnet.
