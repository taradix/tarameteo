"""Provision a board over BLE, like the app does: WiFi, location, label, MQTT server and interval.

Writes the provisioning characteristics, commits, and prints the status
notifications until the board reports ok or an error. The board only saves
what it was sent once it has joined the WiFi, and keeps its location, label,
MQTT server and interval between readings when they aren't given. It listens
for a few minutes after it powers on, so power-cycle a board that already has
WiFi. The fields need an encrypted link: on Linux, --passkey pairs with the
sticker passkey and forgets the pairing when done (--forget also drops one an
interrupted run left behind); elsewhere, pair from the OS Bluetooth settings.

Before writing, it checks the SSID against the networks the board found when
it powered on, and warns when the board didn't find it or finds it weak;
--list prints those networks, the MQTT server and the interval, and writes nothing.
"""

import asyncio
import struct
import sys
from argparse import ArgumentParser, ArgumentTypeError
from contextlib import asynccontextmanager, nullcontext

from bleak import BleakClient, BleakScanner


def uuid(n: int) -> str:
    """Matches BleProvisioningUUID in IBleProvisioner.h."""
    return f"6d5a{n:04x}-8b6e-4b3a-9c1d-2f7a5e0c1a01"


SSID, PASSWORD, LOCATION, COMMIT, STATUS, LABEL, NETWORKS, SERVER, PORT, INTERVAL = (uuid(n) for n in range(2, 12))

# Seconds between readings the board takes, like StationSettings::MIN_INTERVAL and MAX_INTERVAL.
MIN_INTERVAL = 60
MAX_INTERVAL = 86400

# The board tries the WiFi for up to WIFI_TIMEOUT_MS (30 s, config.h) before it answers.
RESULT_TIMEOUT = 60

# Below this, the board's WiFi tends to drop out (dBm), like WEAK in the app's Provision.kt.
WEAK_RSSI = -80

AGENT_PATH = "/ca/taram/provision/agent"


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
    """Where the board sends its readings, and how often."""
    host = (await client.read_gatt_char(SERVER)).decode()
    (port,) = struct.unpack("<H", await client.read_gatt_char(PORT))
    (interval,) = struct.unpack("<I", await client.read_gatt_char(INTERVAL))
    print(f"MQTT server: {host}:{port}")
    print(f"Interval: {interval} s between readings")


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


async def provision(args) -> int:
    device = await BleakScanner.find_device_by_name(args.name, timeout=args.timeout)
    if device is None:
        print(f"{args.name} not found", file=sys.stderr)
        return 1

    final: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def on_status(_, data: bytearray) -> None:
        status = data.decode()
        print("status:", status)
        if (status == "ok" or status.startswith("error:")) and not final.done():
            final.set_result(status)

    pair = args.passkey is not None
    agent = passkey_agent(args.passkey) if pair else nullcontext()
    client = BleakClient(device, pair=pair)
    if args.forget:
        await client.unpair()
    try:
        async with agent, client:
            networks = await read_networks(client)
            if args.list:
                print_networks(networks)
                await print_settings(client)
                return 0
            check_ssid(args.ssid, networks)
            await client.start_notify(STATUS, on_status)
            for char, value in fields_of(args):
                await client.write_gatt_char(char, value, response=True)
            await client.write_gatt_char(COMMIT, b"\x01", response=True)
            try:
                status = await asyncio.wait_for(final, RESULT_TIMEOUT)
            except TimeoutError:
                print("No final status from the board", file=sys.stderr)
                return 1
    finally:
        if pair:
            # Leave no bond behind, so the next run pairs afresh, e.g. after a
            # factory re-flash changed the passkey.
            await client.unpair()

    return 0 if status == "ok" else 1


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
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="Advertised name, the sensor ID on the sticker (tm-xxxxxx)")
    parser.add_argument("ssid", nargs="?")
    parser.add_argument("password", nargs="?")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the networks the board found, its MQTT server and interval, and write nothing",
    )
    parser.add_argument("--label", help="Name shown for the sensor (empty clears it)")
    parser.add_argument("--lat", type=float, help="Latitude, with --lon (omitted: keep the saved location)")
    parser.add_argument("--lon", type=float, help="Longitude, with --lat")
    parser.add_argument("--server", help="MQTT server host name or IPv4 address (omitted: keep the board's)")
    parser.add_argument(
        "--port", type=whole_number(1, 65535), help="MQTT server port, 1 to 65535 (omitted: keep the board's)"
    )
    parser.add_argument(
        "--interval",
        type=whole_number(MIN_INTERVAL, MAX_INTERVAL),
        help=f"Seconds between readings, {MIN_INTERVAL} to {MAX_INTERVAL} (omitted: keep the board's)",
    )
    parser.add_argument("--passkey", type=int, help="Sticker passkey, to pair first (Linux only)")
    parser.add_argument(
        "--forget", action="store_true", help="Forget a pairing left by an interrupted run first, with --passkey"
    )
    parser.add_argument("--timeout", type=float, default=30, help="Seconds to find the board (default: %(default)s)")
    args = parser.parse_args(argv)
    if not args.list and (args.ssid is None or args.password is None):
        parser.error("ssid and password are needed, unless --list")
    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon go together")
    if args.forget and args.passkey is None:
        parser.error("--forget needs --passkey to pair again")
    if args.passkey is not None and sys.platform != "linux":
        parser.error("--passkey needs BlueZ; pair from the OS Bluetooth settings instead")
    return asyncio.run(provision(args))


if __name__ == "__main__":
    sys.exit(main())
