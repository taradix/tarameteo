"""Set up, show or reset a station over BLE, like the app does.

show prints the networks the board found when it powered on, its MQTT server,
its interval between readings, whether it updates its firmware, the firmware it
runs and the latest the backend offers, and writes nothing.

setup sends the WiFi and, when given, the location, label, MQTT server,
interval and auto-update, then prints the status notifications until the board reports ok or
an error. The board only saves what it was sent once it has joined the WiFi,
and keeps the settings left out. Before writing, it checks the SSID against
the networks the board found, and warns when the board didn't find it or
finds it weak.

reset makes the board forget everything setup saved (WiFi, location, label,
MQTT server, interval and auto-update), but not its factory identity, then sleep until it
is power-cycled.

The board listens for a few minutes after it powers on, so power-cycle a board
that already has WiFi. Every command needs an encrypted link: on Linux,
--passkey pairs with the sticker passkey and forgets the pairing when done
(--forget also drops one an interrupted run left behind); elsewhere, pair from
the OS Bluetooth settings.
"""

import asyncio
import struct
import sys
from argparse import ArgumentParser, ArgumentTypeError, BooleanOptionalAction
from contextlib import asynccontextmanager, nullcontext

import httpx
from bleak import BleakClient, BleakScanner


def uuid(n: int) -> str:
    """Matches BleProvisioningUUID in IBleProvisioner.h."""
    return f"6d5a{n:04x}-8b6e-4b3a-9c1d-2f7a5e0c1a01"


SSID, PASSWORD, LOCATION, COMMIT, STATUS, LABEL, NETWORKS, SERVER, PORT, INTERVAL, AUTO_UPDATE, FIRMWARE = (
    uuid(n) for n in range(2, 14)
)

# What Commit takes, like BleCommit in IBleProvisioner.h, and the status that answers each.
PROVISION, RESET = b"\x01", b"\x02"
DONE = {PROVISION: "ok", RESET: "reset"}

# Seconds between readings the board takes, like StationSettings::MIN_INTERVAL and MAX_INTERVAL.
MIN_INTERVAL = 60
MAX_INTERVAL = 86400

# The board tries the WiFi for up to WIFI_TIMEOUT_MS (30 s, config.h) before it answers.
RESULT_TIMEOUT = 60

# Below this, the board's WiFi tends to drop out (dBm), like WEAK in the app's Provision.kt.
WEAK_RSSI = -80

AGENT_PATH = "/ca/taram/station/agent"


@asynccontextmanager
async def passkey_agent(passkey: int):
    """Make a BlueZ agent the default, so pairing gets the passkey without a prompt.

    bleak's pair() relies on an agent being registered, so without one it fails
    with AuthenticationFailed, like a one-shot `bluetoothctl -- pair`.
    """
    from dbus_fast import BusType
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface, method

    class PasskeyAgent(ServiceInterface):
        def __init__(self):
            super().__init__("org.bluez.Agent1")

        @method()
        def RequestPasskey(self, device: "o") -> "u":  # noqa: F821
            return passkey

        @method()
        def Release(self):
            pass

        @method()
        def Cancel(self):
            pass

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    bus.export(AGENT_PATH, PasskeyAgent())
    introspection = await bus.introspect("org.bluez", "/org/bluez")
    manager = bus.get_proxy_object("org.bluez", "/org/bluez", introspection).get_interface("org.bluez.AgentManager1")
    await manager.call_register_agent(AGENT_PATH, "KeyboardOnly")
    # bleak pairs from its own bus connection, so only the default agent gets asked.
    await manager.call_request_default_agent(AGENT_PATH)
    try:
        yield
    finally:
        bus.disconnect()


def decode_networks(value: bytes) -> list[tuple[str, int]]:
    """Matches encodeNetworks() in NetworkList.h: [int8 RSSI][uint8 length][SSID], strongest first."""
    networks = []
    at = 0
    while at + 2 <= len(value):
        (rssi,) = struct.unpack_from("<b", value, at)
        end = at + 2 + value[at + 1]
        if end > len(value):
            break
        networks.append((value[at + 2 : end].decode(errors="replace"), rssi))
        at = end
    return networks


async def read_networks(client: BleakClient) -> list[tuple[str, int]]:
    """The networks the board found when it powered on."""
    return decode_networks(await client.read_gatt_char(NETWORKS))


async def print_settings(client: BleakClient) -> None:
    """Where the board sends its readings, how often, and whether it updates its firmware."""
    host = (await client.read_gatt_char(SERVER)).decode()
    (port,) = struct.unpack("<H", await client.read_gatt_char(PORT))
    (interval,) = struct.unpack("<I", await client.read_gatt_char(INTERVAL))
    auto_update = (await client.read_gatt_char(AUTO_UPDATE)) != b"\x00"
    print(f"MQTT server: {host}:{port}")
    print(f"Interval: {interval} s between readings")
    print(f"Auto-update: {'on' if auto_update else 'off'}")


def latest_version(api: str, board: str) -> str:
    """The version the backend offers the board, else why not."""
    try:
        response = httpx.get(f"{api}/api/firmware/{board}", timeout=10)
        if response.status_code == httpx.codes.NOT_FOUND:
            return "none released"
        return response.raise_for_status().json()["version"]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return f"unknown ({e})"


async def print_firmware(client: BleakClient, api: str) -> None:
    """What the board runs, and the latest the backend offers it."""
    board, version = (await client.read_gatt_char(FIRMWARE)).decode().split(" ", 1)
    print(f"Firmware: {version} for {board}, latest: {latest_version(api, board)}")


def fields_of(args) -> list[tuple[str, bytes]]:
    """The characteristics to write before Commit; the board keeps the fields left out."""
    fields = [(SSID, args.ssid.encode()), (PASSWORD, args.password.encode())]
    if args.lat is not None:
        fields.append((LOCATION, struct.pack("<ff", args.lat, args.lon)))
    if args.label is not None:
        fields.append((LABEL, args.label.encode()))
    if args.server is not None:
        fields.append((SERVER, args.server.encode()))
    if args.port is not None:
        fields.append((PORT, struct.pack("<H", args.port)))
    if args.interval is not None:
        fields.append((INTERVAL, struct.pack("<I", args.interval)))
    if args.auto_update is not None:
        fields.append((AUTO_UPDATE, bytes([args.auto_update])))
    return fields


def print_networks(networks: list[tuple[str, int]]) -> None:
    if not networks:
        print("The board found no network it can join")
    for ssid, rssi in networks:
        print(f"{rssi:4d} dBm  {ssid}{'  (weak)' if rssi < WEAK_RSSI else ''}")


def check_ssid(ssid: str, networks: list[tuple[str, int]]) -> None:
    """Warns about an SSID the board may not join; a hidden network is never listed, so it goes ahead."""
    if not networks:
        return
    rssi = dict(networks).get(ssid)
    if rssi is None:
        print(f"warning: the board didn't find {ssid!r} (fine if it's hidden); it found:", file=sys.stderr)
        for found, found_rssi in networks:
            print(f"  {found_rssi:4d} dBm  {found}", file=sys.stderr)
    elif rssi < WEAK_RSSI:
        print(f"warning: {ssid!r} is weak where the board is ({rssi} dBm): its WiFi may drop out", file=sys.stderr)


async def show(client: BleakClient, args) -> int:
    print_networks(await read_networks(client))
    await print_settings(client)
    await print_firmware(client, args.api)
    return 0


async def commit(client: BleakClient, request: bytes, fields: list[tuple[str, bytes]]) -> int:
    """Writes the fields, then Commit, and waits for the board's final status: 0 when it is the one asked for."""
    final: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def on_status(_, data: bytearray) -> None:
        status = data.decode()
        print("status:", status)
        if (status in DONE.values() or status.startswith("error:")) and not final.done():
            final.set_result(status)

    await client.start_notify(STATUS, on_status)
    for char, value in fields:
        await client.write_gatt_char(char, value, response=True)
    await client.write_gatt_char(COMMIT, request, response=True)
    try:
        status = await asyncio.wait_for(final, RESULT_TIMEOUT)
    except TimeoutError:
        print("No final status from the board", file=sys.stderr)
        return 1
    return 0 if status == DONE[request] else 1


async def setup(client: BleakClient, args) -> int:
    check_ssid(args.ssid, await read_networks(client))
    return await commit(client, PROVISION, fields_of(args))


async def reset(client: BleakClient, args) -> int:
    return await commit(client, RESET, [])


async def run(args) -> int:
    """Finds and connects to the board, pairing first with --passkey, then runs the command."""
    device = await BleakScanner.find_device_by_name(args.name, timeout=args.timeout)
    if device is None:
        print(f"{args.name} not found", file=sys.stderr)
        return 1

    pair = args.passkey is not None
    agent = passkey_agent(args.passkey) if pair else nullcontext()
    client = BleakClient(device, pair=pair)
    if args.forget:
        await client.unpair()
    try:
        async with agent, client:
            return await args.command(client, args)
    finally:
        if pair:
            # Leave no bond behind, so the next run pairs afresh, e.g. after a
            # factory re-flash changed the passkey.
            await client.unpair()


def whole_number(low: int, high: int):
    """An argparse type for a whole number from low to high, saying so when it isn't."""

    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            number = None
        if number is None or not low <= number <= high:
            raise ArgumentTypeError(f"must be a whole number from {low} to {high}, not {value!r}")
        return number

    return parse


def main(argv=None) -> int:
    # What every command takes: which board, and how to reach it.
    board = ArgumentParser(add_help=False)
    board.add_argument("name", help="Advertised name, the sensor ID on the sticker (tm-xxxxxx)")
    board.add_argument("--passkey", type=int, help="Sticker passkey, to pair first (Linux only)")
    board.add_argument(
        "--forget", action="store_true", help="Forget a pairing left by an interrupted run first, with --passkey"
    )
    board.add_argument("--timeout", type=float, default=30, help="Seconds to find the board (default: %(default)s)")

    parser = ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(title="commands", required=True, metavar="{show,setup,reset}")

    show_parser = commands.add_parser(
        "show", parents=[board], help="Print the networks the board found, its settings and firmware"
    )
    show_parser.add_argument(
        "--api", default="https://meteo.taram.ca", help="Backend to ask for the latest firmware (default: %(default)s)"
    )
    show_parser.set_defaults(command=show)

    setup_parser = commands.add_parser(
        "setup", parents=[board], help="Send the WiFi and settings; the board keeps the ones left out"
    )
    setup_parser.add_argument("ssid")
    setup_parser.add_argument("password")
    setup_parser.add_argument("--label", help="Name shown for the sensor (empty clears it)")
    setup_parser.add_argument("--lat", type=float, help="Latitude, with --lon (omitted: keep the saved location)")
    setup_parser.add_argument("--lon", type=float, help="Longitude, with --lat")
    setup_parser.add_argument("--server", help="MQTT server host name or IPv4 address (omitted: keep the board's)")
    setup_parser.add_argument(
        "--port", type=whole_number(1, 65535), help="MQTT server port, 1 to 65535 (omitted: keep the board's)"
    )
    setup_parser.add_argument(
        "--interval",
        type=whole_number(MIN_INTERVAL, MAX_INTERVAL),
        help=f"Seconds between readings, {MIN_INTERVAL} to {MAX_INTERVAL} (omitted: keep the board's)",
    )
    setup_parser.add_argument(
        "--auto-update",
        action=BooleanOptionalAction,
        help="Install the firmware the backend offers (omitted: keep the board's, on for a new board)",
    )
    setup_parser.set_defaults(command=setup)

    reset_parser = commands.add_parser(
        "reset", parents=[board], help="Make the board forget its WiFi and settings, keeping its identity"
    )
    reset_parser.set_defaults(command=reset)

    args = parser.parse_args(argv)
    if args.command is setup and (args.lat is None) != (args.lon is None):
        setup_parser.error("--lat and --lon go together")
    if args.forget and args.passkey is None:
        parser.error("--forget needs --passkey to pair again")
    if args.passkey is not None and sys.platform != "linux":
        parser.error("--passkey needs BlueZ; pair from the OS Bluetooth settings instead")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
