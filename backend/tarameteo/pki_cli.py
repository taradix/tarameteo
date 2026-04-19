"""PKI command-line interface."""

import os
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
)
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from enum import Enum
from pathlib import Path

from attrs import define

from tarameteo.ca_client import (
    CAClient,
    IssueCertificateError,
    IssueCertificateRequest,
    validate_ttl_days,
)
from tarameteo.crypto import (
    KeyAlgorithm,
    KeySpec,
    cert_expires_at,
    generate_key_pem,
    key_matches_cert,
)
from tarameteo.duration import parse_duration
from tarameteo.fs import atomic_write
from tarameteo.pki import (
    create_csr_pem,
    self_sign_ca_key_pem,
)

DEFAULT_API_URL = os.getenv("PKI_API_URL", "https://meteo.taram.ca/api/certs")
DEFAULT_API_TOKEN = os.getenv("PKI_API_TOKEN")
DEFAULT_OUTPUT_DIR = Path(os.getenv("PKI_OUTPUT_DIR", ""))

class InitStatus(Enum):

    INITIALIZED = 0
    ERROR = 1


@define(frozen=True)
class InitResult:

    status: InitStatus
    reasons: tuple[str, ...] = ()
    key_path: Path | None = None
    cert_path: Path | None = None
    expires_at: datetime | None = None
    serial: int | None = None

    def to_text(self):
        lines = [self.status.name]
        for reason in self.reasons:
            lines.append(f"- {reason}")
        if self.key_path is not None:
            lines.append(f"key_path:  {self.key_path}")
        if self.cert_path is not None:
            lines.append(f"cert_path:  {self.cert_path}")
        if self.expires_at is not None:
            expires_at = self.expires_at.astimezone(UTC).isoformat()
            lines.append(f"expires_at: {expires_at}")
        if self.serial is not None:
            lines.append(f"serial:     {self.serial}")

        return "\n".join(lines) + "\n"


def init(
    key_path: Path,
    cert_path: Path,
    *,
    common_name: str,
    ttl_days: int | None = None,
    key_algorithm: KeyAlgorithm,
    force: bool = False,
) -> InitResult:
    if not force:
        exists = []
        if key_path.exists():
            exists.append(f"key exists: {key_path}")
        if cert_path.exists():
            exists.append(f"cert exists: {cert_path}")

        if exists:
            return InitResult(
                status=InitStatus.ERROR,
                reasons=tuple(exists),
                key_path=key_path,
                cert_path=cert_path,
            )

    key_spec = KeySpec(algorithm=key_algorithm)
    key_pem = generate_key_pem(key_spec)

    subject = f"/C=CA/ST=QC/L=Notre-Dame-du-Laus/O=Tarameteo/OU=PKI/CN={common_name}"
    try:
        response = self_sign_ca_key_pem(
            key_pem,
            subject=subject,
            ttl_days=ttl_days,
        )
    except ValueError as e:
        return InitResult(
            status=InitStatus.ERROR,
            reasons=(str(e),),
            key_path=key_path,
            cert_path=cert_path,
        )

    try:
        atomic_write(key_path, key_pem, 0o600)
        atomic_write(cert_path, response.cert_pem, 0o644)
    except Exception as e:
        return InitResult(
            status=InitStatus.ERROR,
            reasons=(f"{type(e).__name__}: {e}",),
            key_path=key_path,
            cert_path=cert_path,
        )

    return InitResult(
        status=InitStatus.INITIALIZED,
        reasons=(),
        key_path=key_path,
        cert_path=cert_path,
        expires_at=response.not_after,
        serial=response.serial_number,
    )


class CheckStatus(Enum):

    OK = 0
    RENEW = 1
    ROTATE = 2
    ERROR = 3


@define(frozen=True)
class CheckResult:

    status: CheckStatus
    reasons: tuple[str, ...] = ()
    expires_in: timedelta | None = None
    expires_at: datetime | None = None
    key_age: timedelta | None = None
    key_mtime: datetime | None = None

    def to_text(self):
        lines = [self.status.name]
        for reason in self.reasons:
            lines.append(f"- {reason}")

        if self.expires_at is not None:
            expires_at = self.expires_at.astimezone(UTC).isoformat()
            lines.append(f"expires_at: {expires_at}")
        if self.expires_in is not None:
            days = self.expires_in.total_seconds() / 86400
            lines.append(f"expires_in: {days:.2f} days")
        if self.key_mtime is not None:
            key_mtime = self.key_mtime.astimezone(UTC).isoformat()
            lines.append(f"key_mtime:  {key_mtime}")
        if self.key_age is not None:
            days = self.key_age.total_seconds() / 86400
            lines.append(f"key_age:    {days:.2f} days")

        return "\n".join(lines) + "\n"


def check(
    key_path: Path,
    cert_path: Path,
    *,
    renew_before: timedelta | None = None,
    rotate_after: timedelta | None = None,
    now: datetime | None = None,
) -> CheckResult:
    now = now or datetime.now(UTC)
    reasons: list[str] = []

    missing = []
    if not key_path.exists():
        missing.append(f"missing key: {key_path}")
    if not cert_path.exists():
        missing.append(f"missing cert: {cert_path}")
    if missing:
        return CheckResult(CheckStatus.ERROR, tuple(missing) or ("missing files",))

    status = CheckStatus.OK
    cert_pem = cert_path.read_text()
    expires_at = cert_expires_at(cert_pem)
    expires_in = expires_at - now

    if expires_in.total_seconds() < 0:
        reasons.append("certificate is expired")
        status = CheckStatus.ROTATE
    elif renew_before is not None and expires_in <= renew_before:
        reasons.append(f"certificate expires within {renew_before}")
        status = CheckStatus.RENEW

    key_ts = key_path.stat().st_mtime
    key_mtime = datetime.fromtimestamp(key_ts, tz=UTC)
    key_age = now - key_mtime

    if rotate_after is not None and key_age >= rotate_after:
        reasons.append(f"private key age {key_age} >= rotate_after {rotate_after}")
        status = CheckStatus.ROTATE

    key_pem = key_path.read_text()
    if not key_matches_cert(key_pem, cert_pem):
        reasons.append("private key does not match certificate")
        status = CheckStatus.ROTATE

    return CheckResult(
        status=status,
        reasons=tuple(reasons),
        expires_in=expires_in,
        expires_at=expires_at,
        key_age=key_age,
        key_mtime=key_mtime,
    )


class RenewStatus(Enum):
    RENEWED = 0
    ERROR = 1


@define(frozen=True)
class RenewResult:

    status: RenewStatus
    reasons: tuple[str, ...] = ()
    cert_path: Path | None = None
    ca_cert_path: Path | None = None
    expires_at: datetime | None = None
    serial: int | None = None

    def to_text(self):
        lines = [self.status.name]
        for reason in self.reasons:
            lines.append(f"- {reason}")
        if self.cert_path is not None:
            lines.append(f"cert_path:    {self.cert_path}")
        if self.ca_cert_path is not None:
            lines.append(f"ca_cert_path: {self.ca_cert_path}")
        if self.expires_at is not None:
            expires_at = self.expires_at.astimezone(UTC).isoformat()
            lines.append(f"expires_at:   {expires_at}")
        if self.serial is not None:
            lines.append(f"serial:       {self.serial}")

        return "\n".join(lines) + "\n"


def renew(
    key_path: Path,
    cert_path: Path,
    ca_cert_path: Path,
    *,
    ca_client: CAClient,
    common_name: str,
    ttl_days: int | None = None,
) -> RenewResult:
    try:
        key_pem = key_path.read_text()
    except Exception as e:
        return RenewResult(
            status=RenewStatus.ERROR,
            reasons=(f"{type(e).__name__}: {e}",),
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    csr_pem = create_csr_pem(key_pem, common_name)
    request = IssueCertificateRequest(csr_pem=csr_pem, ttl_days=ttl_days)

    try:
        response = ca_client.issue_certificate(request)
    except IssueCertificateError as e:
        return RenewResult(
            status=RenewStatus.ERROR,
            reasons=(str(e),),
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    try:
        atomic_write(cert_path, response.cert_pem)
        atomic_write(ca_cert_path, response.chain_pem[0])
    except Exception as e:
        return RenewResult(
            status=RenewStatus.ERROR,
            reasons=(f"{type(e).__name__}: {e}",),
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    return RenewResult(
        status=RenewStatus.RENEWED,
        reasons=(),
        cert_path=cert_path,
        ca_cert_path=ca_cert_path,
        expires_at=response.not_after,
        serial=response.serial_number,
    )


class RotateStatus(Enum):

    ROTATED = 0
    ERROR = 1


@define(frozen=True)
class RotateResult:

    status: RotateStatus
    reasons: tuple[str, ...] = ()
    key_path: Path | None = None
    cert_path: Path | None = None
    ca_cert_path: Path | None = None
    expires_at: datetime | None = None
    serial: int | None = None

    def to_text(self):
        lines = [self.status.name]
        for reason in self.reasons:
            lines.append(f"- {reason}")
        if self.key_path is not None:
            lines.append(f"key_path:     {self.key_path}")
        if self.cert_path is not None:
            lines.append(f"cert_path:    {self.cert_path}")
        if self.ca_cert_path is not None:
            lines.append(f"ca_cert_path: {self.ca_cert_path}")
        if self.expires_at is not None:
            expires_at = self.expires_at.astimezone(UTC).isoformat()
            lines.append(f"expires_at:   {expires_at}")
        if self.serial is not None:
            lines.append(f"serial:       {self.serial}")

        return "\n".join(lines) + "\n"

def rotate(
    key_path: Path,
    cert_path: Path,
    ca_cert_path: Path,
    *,
    ca_client: CAClient,
    common_name: str,
    ttl_days: int | None = None,
    key_algorithm: KeyAlgorithm,
) -> RotateResult:
    key_spec = KeySpec(algorithm=key_algorithm)
    key_pem = generate_key_pem(key_spec)
    csr_pem = create_csr_pem(key_pem, common_name)
    request = IssueCertificateRequest(csr_pem=csr_pem, ttl_days=ttl_days)

    try:
        response = ca_client.issue_certificate(request)
    except IssueCertificateError as e:
        return RotateResult(
            status=RotateStatus.ERROR,
            reasons=(str(e),),
            key_path=key_path,
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    try:
        atomic_write(key_path, key_pem, mode=0o600)
        atomic_write(cert_path, response.cert_pem)
        atomic_write(ca_cert_path, response.chain_pem[0])
    except Exception as e:
        return RotateResult(
            status=RotateStatus.ERROR,
            reasons=(f"{type(e).__name__}: {e}",),
            key_path=key_path,
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    return RotateResult(
        status=RotateStatus.ROTATED,
        reasons=(),
        key_path=key_path,
        cert_path=cert_path,
        ca_cert_path=ca_cert_path,
        expires_at=response.not_after,
        serial=response.serial_number,
    )


def make_args_parser():
    args_parser = ArgumentParser()
    args_parser.add_argument(
        "-o", "--output-dir",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help="Output directory for certificates (default: %(default)s)",
    )
    command = args_parser.add_subparsers(dest="command")

    init_parser = command.add_parser(
        "init",
        help="Initialize Certificate Authority (CA) key and certificate",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwriting CA key and certificate",
    )
    init_parser.add_argument(
        "--common-name",
        default="Root CA",
        help="Common name for the subject of the certificate (default: %(default)s)",
    )
    init_parser.add_argument(
        "--ttl-days",
        type=int,
        help="Certificate time-to-live in days (default: server default)",
    )
    init_parser.add_argument(
        "--key-algorithm",
        type=KeyAlgorithm,
        choices=list(KeyAlgorithm),
        default=KeyAlgorithm.EC,
        help="Public key algorithm (default: %(default)s)",
    )

    check_parser = command.add_parser(
        "check",
        help="Check certificate (0 is valid, 1 renew certificate, 2 rotate key)",
    )
    check_parser.add_argument(
        "--renew-before",
        type=parse_duration,
        default=parse_duration("14d"),
        help="Renew the certification before this time (default: %(default)s)",
    )
    check_parser.add_argument(
        "--rotate-after",
        type=parse_duration,
        default=parse_duration("365d"),
        help="Rotate the private key after this time (default: %(default)s)",
    )
    check_parser.add_argument(
        "device_id",
        help="Device identifier (used as Common Name in certificate)",
    )

    renew_parser = command.add_parser(
        "renew",
        help="Renew certificate.",
    )
    renew_parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="URL of the API (default: %(default)s)",
    )
    renew_parser.add_argument(
        "--api-token",
        default=DEFAULT_API_TOKEN,
        help="Bearer token for the API",
    )
    renew_parser.add_argument(
        "--ttl-days",
        type=ttl_days_arg,
        help="Certificate time-to-live in days (default: server default)",
    )
    renew_parser.add_argument(
        "device_id",
        help="Device identifier (used as Common Name in certificate)",
    )

    rotate_parser = command.add_parser(
        "rotate",
        help="Rotate private key.",
    )
    rotate_parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="URL of the API (default: %(default)s)",
    )
    rotate_parser.add_argument(
        "--api-token",
        default=DEFAULT_API_TOKEN,
        help="Bearer token for the API",
    )
    rotate_parser.add_argument(
        "--ttl-days",
        type=ttl_days_arg,
        help="Certificate time-to-live in days (default: server default)",
    )
    rotate_parser.add_argument(
        "--key-algorithm",
        type=KeyAlgorithm,
        choices=list(KeyAlgorithm),
        default=KeyAlgorithm.EC,
        help="Public key algorithm (default: %(default)s)",
    )
    rotate_parser.add_argument(
        "device_id",
        help="Device identifier (used as Common Name in certificate)",
    )

    return args_parser


def ttl_days_arg(value: str) -> int:
    try:
        return validate_ttl_days(int(value))
    except ValueError as e:
        raise ArgumentTypeError(str(e)) from e


def main(argv=None) -> int:
    args_parser = make_args_parser()
    args = args_parser.parse_args(argv)

    # Check --output-dir
    if args.output_dir.exists() and not args.output_dir.is_dir():
        args_parser.error(f"--output-dir {args.output_dir!r} exists but is not a directory")

    match args.command:
        case "init":
            result = init(
                key_path=args.output_dir / "ca.key",
                cert_path=args.output_dir / "ca.pem",
                common_name=args.common_name,
                ttl_days=args.ttl_days,
                key_algorithm=args.key_algorithm,
                force=args.force,
            )

        case "check":
            result = check(
                key_path=args.output_dir / f"{args.device_id}.key",
                cert_path=args.output_dir / f"{args.device_id}.pem",
                renew_before=args.renew_before,
                rotate_after=args.rotate_after,
            )

        case "renew":
            with CAClient.from_url(args.api_url, args.api_token) as ca_client:
                result = renew(
                    key_path=args.output_dir / f"{args.device_id}.key",
                    cert_path=args.output_dir / f"{args.device_id}.pem",
                    ca_cert_path=args.output_dir / "ca.pem",
                    ca_client=ca_client,
                    common_name=args.device_id,
                    ttl_days=args.ttl_days,
                )

        case "rotate":
            with CAClient.from_url(args.api_url, args.api_token) as ca_client:
                result = rotate(
                    key_path=args.output_dir / f"{args.device_id}.key",
                    cert_path=args.output_dir / f"{args.device_id}.pem",
                    ca_cert_path=args.output_dir / "ca.pem",
                    ca_client=ca_client,
                    common_name=args.device_id,
                    ttl_days=args.ttl_days,
                    key_algorithm=args.key_algorithm,
                )

        case command:
            args_parser.error(f"Programming error for command: {command}")

    print(result.to_text(), end="")

    return result.status.value

