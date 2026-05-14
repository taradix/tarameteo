"""TLS runtime config."""

from datetime import (
    UTC,
    datetime,
)
from pathlib import Path

from attrs import define

from tarameteo.crypto import key_matches_cert as _key_matches_cert
from tarameteo.crypto import load_cert
from tarameteo.fs import atomic_write


@define(frozen=True)
class TLSCredentials:

    key_path: Path
    cert_path: Path
    ca_path: Path | None = None

    @classmethod
    def from_device_id(cls, device_id: str, output_dir: Path = Path()) -> "TLSCredentials":
        return cls(
            key_path=output_dir / f"{device_id}.key",
            cert_path=output_dir / f"{device_id}.pem",
            ca_path=output_dir / "ca.crt",
        )

    def exists(self) -> bool:
        """True if the files exist on disk."""
        return all([
            self.key_path.exists(),
            self.cert_path.exists(),
            self.ca_path is None or self.ca_path.exists(),
        ])

    def key_matches_cert(self) -> bool:
        """True if the private key corresponds to the certificate's public key."""
        return _key_matches_cert(self.key_path.read_text(), self.cert_path.read_text())

    def is_current(self, now: datetime | None = None) -> bool:
        """True if the certificate is within its validity window."""
        now = now or datetime.now(UTC)

        cert = load_cert(self.cert_path.read_text())
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc

        return not_before <= now <= not_after

    def is_valid(self, now: datetime | None = None) -> bool:
        """True if exists, and is current, and key matches cert."""
        return all([
            self.exists(),
            self.is_current(now),
            self.key_matches_cert(),
        ])

    def save(self, key_pem: str, cert_pem: str, ca_pem: str | None = None) -> None:
        """Save the PEMs to files securely."""
        atomic_write(self.key_path, key_pem, mode=0o600)
        atomic_write(self.cert_path, cert_pem)
        if ca_pem is not None:
            atomic_write(self.ca_path, ca_pem)
