import asyncio
import random
from asyncua import Server


async def main():
    server = Server()

    # OPC UA endpoint exposed by the gateway VM
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/industrial-cell/server/")
    server.set_server_name("Industrial Automation Cell Gateway")

    # Namespace for this project
    namespace_uri = "http://industrial-cell.local/opcua"
    idx = await server.register_namespace(namespace_uri)

    # Create object tree
    objects = server.nodes.objects
    cell = await objects.add_object(idx, "Cell_01")

    # Machine variables
    machine_state = await cell.add_variable(idx, "MachineState", "IDLE")
    conveyor_running = await cell.add_variable(idx, "ConveyorRunning", False)
    conveyor_speed = await cell.add_variable(idx, "ConveyorSpeed", 0.0)
    entry_sensor = await cell.add_variable(idx, "EntrySensor", False)
    exit_sensor = await cell.add_variable(idx, "ExitSensor", False)
    part_count = await cell.add_variable(idx, "PartCount", 0)
    fault_active = await cell.add_variable(idx, "FaultActive", False)

    # Allow SCADA/client writes to these variables later
    await machine_state.set_writable()
    await conveyor_running.set_writable()
    await conveyor_speed.set_writable()
    await entry_sensor.set_writable()
    await exit_sensor.set_writable()
    await part_count.set_writable()
    await fault_active.set_writable()

    print("Starting OPC UA server...")
    print("Endpoint: opc.tcp://0.0.0.0:4840/industrial-cell/server/")
    print("Browse path: Objects > Cell_01")
    print("Press Ctrl+C to stop.")

    count = 0

    async with server:
        while True:
            # Simple fake machine behaviour
            running = random.choice([True, True, True, False])
            speed = 1.5 if running else 0.0
            entry = random.choice([True, False])
            exit_ = random.choice([True, False])
            fault = random.choice([False, False, False, False, True])

            if running and exit_ and not fault:
                count += 1

            state = "FAULT" if fault else ("RUNNING" if running else "IDLE")

            await machine_state.write_value(state)
            await conveyor_running.write_value(running)
            await conveyor_speed.write_value(speed)
            await entry_sensor.write_value(entry)
            await exit_sensor.write_value(exit_)
            await part_count.write_value(count)
            await fault_active.write_value(fault)

            print(
                f"State={state} | Running={running} | Speed={speed} | "
                f"Entry={entry} | Exit={exit_} | Count={count} | Fault={fault}"
            )

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
