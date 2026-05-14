"""PlatformIO pre-build script: issue mTLS certificates for the target sensor.

Reads the SENSOR_ID environment variable, calls ``tarameteo-pki issue`` via the
CA service, and writes the PEM files to ``firmware/certs/`` where they are picked
up by ``board_build.embed_txtfiles``.
"""

import os
import subprocess
import sys
from pathlib import Path

Import("env")  # noqa: F821 — PlatformIO injects this

CERTS_DIR = Path(env.subst("$PROJECT_DIR")) / "certs"
SENSOR_ID = os.environ.get("SENSOR_ID", "").strip()

# Only run for the esp32 environment (skip native tests, analysis, etc.)
current_env = env.subst("$PIOENV")
if current_env != "esp32":
    pass  # Nothing to do for non-device builds
elif not SENSOR_ID:
    sys.stderr.write(
        "\n** ERROR: SENSOR_ID environment variable is required for esp32 builds.\n"
        "   Example: SENSOR_ID=outdoor-north pio run -e esp32 --target upload\n\n"
    )
    env.Exit(1)
else:
    CERTS_DIR.mkdir(exist_ok=True)

    cert_path = CERTS_DIR / "client.pem"
    key_path = CERTS_DIR / "client.key"
    ca_path = CERTS_DIR / "ca.pem"

    # Skip if certs already exist for this sensor (allows offline re-builds)
    marker = CERTS_DIR / ".sensor_id"
    if marker.exists() and marker.read_text().strip() == SENSOR_ID:
        print(f"embed_certs: Reusing existing certs for '{SENSOR_ID}'")
    else:
        print(f"embed_certs: Issuing certificates for sensor '{SENSOR_ID}'...")

        api_url = os.environ.get("CA_API_URL", "http://localhost:8000")
        api_token = os.environ.get("CA_API_TOKEN", "")

        cmd = [
            sys.executable, "-m", "tarameteo.pki_cli",
            "--output-dir", str(CERTS_DIR),
            "issue",
            "--api-url", api_url,
        ]
        if api_token:
            cmd += ["--api-token", api_token]
        cmd.append(SENSOR_ID)

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            sys.stderr.write(
                f"\n** ERROR: Failed to issue certificates for '{SENSOR_ID}'.\n"
                f"   Command: {' '.join(cmd)}\n"
                f"   Output: {result.stdout}\n"
                f"   Errors: {result.stderr}\n\n"
            )
            env.Exit(1)

        # The CLI writes {SENSOR_ID}.pem, {SENSOR_ID}.key, ca.pem — rename to
        # canonical names expected by board_build.embed_txtfiles.
        issued_cert = CERTS_DIR / f"{SENSOR_ID}.pem"
        issued_key = CERTS_DIR / f"{SENSOR_ID}.key"

        if issued_cert.exists():
            issued_cert.rename(cert_path)
        if issued_key.exists():
            issued_key.rename(key_path)
        # ca.pem is already correctly named

        if not cert_path.exists() or not key_path.exists() or not ca_path.exists():
            sys.stderr.write(
                f"\n** ERROR: Expected cert files not found in {CERTS_DIR}.\n"
                f"   Contents: {list(CERTS_DIR.iterdir())}\n\n"
            )
            env.Exit(1)

        # Write marker so we can skip on rebuild
        marker.write_text(SENSOR_ID)

        print(f"embed_certs: Certificates issued successfully for '{SENSOR_ID}'")
