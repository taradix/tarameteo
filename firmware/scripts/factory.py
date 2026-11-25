"""Give a board its identity: issue a never-expiring cert and flash it into NVS.

Uses the board's MAC as its sensor ID (the cert CN), picks a random BLE passkey,
issues the cert through the CA, then writes cert, key, CA and passkey into the
nvs partition, which an app-only flash never touches. Overwrites the whole
partition: a second run keeps the ID but issues a fresh cert and passkey.

Needs PKI_API_TOKEN (the CA_TOKEN) and the board on USB.
"""

import re
import secrets
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory

from tarameteo.ca_client import CAClient
from tarameteo.crypto import (
    KeyAlgorithm,
    key_matches_cert,
)
from tarameteo.pki import NO_EXPIRY
from tarameteo.pki_cli import (
    DEFAULT_API_TOKEN,
    DEFAULT_API_URL,
    IssueStatus,
    issue,
)

PARTITIONS = Path(__file__).parent.parent / "partitions.csv"


def nvs_partition(partitions: Path) -> tuple[str, str]:
    """Offset and size of the nvs partition, so this script can't drift from the table."""
    for line in partitions.read_text().splitlines():
        row = [field.strip() for field in line.split(",")]
        if row[0] == "nvs":
            return row[3], row[4]
    raise SystemExit(f"No nvs partition in {partitions}")


def board_mac(port: list[str]) -> str:
    """Base MAC from eFuse, as 12 lowercase hex digits."""
    out = subprocess.run(
        [sys.executable, "-m", "esptool", "--chip", "esp32c3", *port, "read-mac"],
        check=True, capture_output=True, text=True,
    ).stdout
    match = re.search(r"MAC:\s*((?:[0-9a-f]{2}:){5}[0-9a-f]{2})", out, re.IGNORECASE)
    if match is None:
        raise SystemExit(f"No MAC in esptool output:\n{out}")
    return match.group(1).replace(":", "").lower()


def nvs_csv(key: Path, cert: Path, ca_cert: Path, passkey: int) -> str:
    """Input for esp_idf_nvs_partition_gen; keys match FactoryIdentity::loadFromNVS."""
    return "\n".join([
        "key,type,encoding,value",
        "tarameteo_certs,namespace,,",
        f"cli_cert,file,string,{cert}",
        f"cli_key,file,string,{key}",
        f"ca_cert,file,string,{ca_cert}",
        f"passkey,data,u32,{passkey}",
    ]) + "\n"


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", help="Serial port (default: esptool autodetect)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="CA URL (default: %(default)s)")
    parser.add_argument("--api-token", default=DEFAULT_API_TOKEN, help="Bearer token for the CA")
    args = parser.parse_args(argv)

    port = ["--port", args.port] if args.port else []
    # NOTE: the last 24 MAC bits are unique within one Espressif OUI but not across
    # them, and a re-run keeps the ID; check it against the API before big batches.
    sensor_id = f"tm-{board_mac(port)[-6:]}"
    passkey = 100000 + secrets.randbelow(900000)  # always 6 digits on the sticker
    offset, size = nvs_partition(PARTITIONS)

    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        key, cert, ca_cert = tmp / "client.key", tmp / "client.pem", tmp / "ca.pem"
        with CAClient.from_url(args.api_url, args.api_token) as ca_client:
            result = issue(
                key, cert, ca_cert,
                ca_client=ca_client,
                common_name=sensor_id,
                no_expiry=True,
                key_algorithm=KeyAlgorithm.RSA,
            )
        if result.status is not IssueStatus.ISSUED:
            print(result.to_text(), end="", file=sys.stderr)
            return 1

        # The firmware only checks PEM format, so catch a bad pair here.
        cert_pem = cert.read_text()
        if not key_matches_cert(key.read_text(), cert_pem):
            raise SystemExit("Issued certificate does not match its key")
        if result.expires_at != NO_EXPIRY:
            raise SystemExit(f"Certificate expires at {result.expires_at}; is the CA up to date?")

        csv_path, image = tmp / "nvs.csv", tmp / "nvs.bin"
        csv_path.write_text(nvs_csv(key, cert, ca_cert, passkey))
        subprocess.run(
            [sys.executable, "-m", "esp_idf_nvs_partition_gen", "generate", str(csv_path), str(image), size],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "esptool", "--chip", "esp32c3", *port, "write-flash", offset, str(image)],
            check=True,
        )

    print(f"\nSticker: {sensor_id}  passkey {passkey}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
