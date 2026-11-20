"""Provision a board over BLE, like the app does: WiFi, location and label.

Writes the provisioning characteristics, commits, and prints the status
notifications until the board reports ok or an error. The board only saves
what it was sent once it has joined the WiFi, and keeps its location and label
when they aren't given. It listens for a few minutes after it powers on, so
power-cycle a board that already has WiFi. The fields need an encrypted link,
so pair first with the sticker passkey:

    bluetoothctl -- pair <MAC>
"""

import asyncio
import struct
import sys
from argparse import ArgumentParser

from bleak import BleakClient, BleakScanner


def uuid(n: int) -> str:
    """Matches BleProvisioningUUID in IBleProvisioner.h."""
    return f"6d5a{n:04x}-8b6e-4b3a-9c1d-2f7a5e0c1a01"


SSID, PASSWORD, LOCATION, COMMIT, STATUS, LABEL = (uuid(n) for n in range(2, 8))

# The board tries the WiFi for up to WIFI_TIMEOUT_MS (30 s, config.h) before it answers.
RESULT_TIMEOUT = 60


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

    async with BleakClient(device) as client:
        await client.start_notify(STATUS, on_status)
        fields = [(SSID, args.ssid.encode()), (PASSWORD, args.password.encode())]
        if args.lat is not None:
            fields.append((LOCATION, struct.pack("<ff", args.lat, args.lon)))
        if args.label is not None:
            fields.append((LABEL, args.label.encode()))
        for char, value in fields:
            await client.write_gatt_char(char, value, response=True)
        await client.write_gatt_char(COMMIT, b"\x01", response=True)
        try:
            status = await asyncio.wait_for(final, RESULT_TIMEOUT)
        except TimeoutError:
            print("No final status from the board", file=sys.stderr)
            return 1

    return 0 if status == "ok" else 1


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="Advertised name, the sensor ID on the sticker (tm-xxxxxx)")
    parser.add_argument("ssid")
    parser.add_argument("password")
    parser.add_argument("--label", help="Name shown for the sensor (empty clears it)")
    parser.add_argument("--lat", type=float, help="Latitude, with --lon (omitted: keep the saved location)")
    parser.add_argument("--lon", type=float, help="Longitude, with --lat")
    parser.add_argument("--timeout", type=float, default=30, help="Seconds to find the board (default: %(default)s)")
    args = parser.parse_args(argv)
    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon go together")
    return asyncio.run(provision(args))


if __name__ == "__main__":
    sys.exit(main())
