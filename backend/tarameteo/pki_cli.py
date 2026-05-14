"""PKI command-line interface."""

import os
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
)
from datetime import (
    UTC,
    datetime,
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
    generate_key_pem,
)
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


class IssueStatus(Enum):

    ISSUED = 0
    ERROR = 1


@define(frozen=True)
class IssueResult:

    status: IssueStatus
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

def issue(
    key_path: Path,
    cert_path: Path,
    ca_cert_path: Path,
    *,
    ca_client: CAClient,
    common_name: str,
    ttl_days: int | None = None,
    key_algorithm: KeyAlgorithm,
    client_auth: bool = True,
    server_auth: bool = False,
    san_dns: list[str] | None = None,
    san_ip: list[str] | None = None,
) -> IssueResult:
    key_spec = KeySpec(algorithm=key_algorithm)
    key_pem = generate_key_pem(key_spec)
    csr_pem = create_csr_pem(key_pem, common_name, san_dns=san_dns, san_ip=san_ip)
    request = IssueCertificateRequest(
        csr_pem=csr_pem,
        ttl_days=ttl_days,
        client_auth=client_auth,
        server_auth=server_auth,
    )

    try:
        response = ca_client.issue_certificate(request)
    except IssueCertificateError as e:
        return IssueResult(
            status=IssueStatus.ERROR,
            reasons=(str(e),),
            key_path=key_path,
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    if not response.chain_pem:
        return IssueResult(
            status=RotateStatus.ERROR,
            reasons=("CA returned an empty certificate chain",),
            key_path=key_path,
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    try:
        atomic_write(key_path, key_pem, mode=0o600)
        atomic_write(cert_path, response.cert_pem)
        atomic_write(ca_cert_path, response.chain_pem[0])
    except Exception as e:
        return IssueResult(
            status=IssueStatus.ERROR,
            reasons=(f"{type(e).__name__}: {e}",),
            key_path=key_path,
            cert_path=cert_path,
            ca_cert_path=ca_cert_path,
        )

    return IssueResult(
        status=IssueStatus.ISSUED,
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
        default=KeyAlgorithm.RSA,
        help="Public key algorithm (default: %(default)s)",
    )

    issue_parser = command.add_parser(
        "issue",
        help="Issue a new private key and certificate.",
    )
    issue_parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="URL of the API (default: %(default)s)",
    )
    issue_parser.add_argument(
        "--api-token",
        default=DEFAULT_API_TOKEN,
        help="Bearer token for the API",
    )
    issue_parser.add_argument(
        "--ttl-days",
        type=ttl_days_arg,
        help="Certificate time-to-live in days (default: server default)",
    )
    issue_parser.add_argument(
        "--key-algorithm",
        type=KeyAlgorithm,
        choices=list(KeyAlgorithm),
        default=KeyAlgorithm.RSA,
        help="Public key algorithm (default: %(default)s)",
    )
    issue_parser.add_argument(
        "--san-dns",
        action="append",
        default=[],
        metavar="DNS",
        help="DNS SubjectAlternativeName (repeatable; presence requests a server-auth certificate)",
    )
    issue_parser.add_argument(
        "--san-ip",
        action="append",
        default=[],
        metavar="IP",
        help="IP SubjectAlternativeName (repeatable; presence requests a server-auth certificate)",
    )
    issue_parser.add_argument(
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

        case "issue":
            server_auth = bool(args.san_dns or args.san_ip)
            with CAClient.from_url(args.api_url, args.api_token) as ca_client:
                result = issue(
                    key_path=args.output_dir / f"{args.device_id}.key",
                    cert_path=args.output_dir / f"{args.device_id}.pem",
                    ca_cert_path=args.output_dir / "ca.pem",
                    ca_client=ca_client,
                    common_name=args.device_id,
                    ttl_days=args.ttl_days,
                    key_algorithm=args.key_algorithm,
                    client_auth=not server_auth,
                    server_auth=server_auth,
                    san_dns=args.san_dns,
                    san_ip=args.san_ip,
                )

        case command:
            args_parser.error(f"Programming error for command: {command}")

    print(result.to_text(), end="")

    return result.status.value

