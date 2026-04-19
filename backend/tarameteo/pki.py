"""CSRs, X.509 certs, CA/issuance, chains, profiles/policy."""

from contextlib import suppress
from datetime import (
    UTC,
    datetime,
    timedelta,
)

from cryptography import x509
from cryptography.hazmat.primitives import (
    hashes,
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    NameOID,
)
from pydantic import (
    BaseModel,
    Field,
)

from tarameteo.crypto import (
    PrivateKey,
    load_cert,
    load_csr,
    load_key,
)

DEFAULT_TTL_DAYS = 30


class CertificateMaterial(BaseModel):
    """Material produced by issuing (or self-signing) an X.509 certificate."""

    cert_pem: str
    chain_pem: list[str] = Field(default_factory=list)
    serial_number: int
    not_before: datetime
    not_after: datetime
    subject: str
    issuer: str


def create_csr_pem(key_pem: str, common_name: str) -> str:
    """Create a Certificate Signing Request from an existing private key."""
    key = load_key(key_pem)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]))
        .sign(key, hashes.SHA256())
    )

    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def sign_csr_pem(
    csr_pem: str,
    *,
    ca_key_pem: str,
    ca_cert_pem: str,
    ttl_days: int | None = None,
    client_auth: bool = True,
    server_auth: bool = False,
) -> CertificateMaterial:
    """Issue a leaf certificate from a CSR using a CA key+certificate."""
    if ttl_days is None:
        ttl_days = DEFAULT_TTL_DAYS

    csr = load_csr(csr_pem)
    ca_cert = load_cert(ca_cert_pem)
    ca_key = load_key(ca_key_pem)

    builder = _build_base_certificate(
        subject=csr.subject,
        issuer=ca_cert.subject,
        public_key=csr.public_key(),
        ttl_days=ttl_days,
    )

    builder = _add_leaf_extensions(
        builder,
        leaf_public_key=csr.public_key(),
        issuer_public_key=ca_cert.public_key(),
        client_auth=client_auth,
        server_auth=server_auth,
    )

    return _sign_builder(builder, signer_key=ca_key, chain_pem=[ca_cert_pem])


def self_sign_ca_key_pem(
    ca_key_pem: str,
    *,
    subject: str,
    ttl_days: int | None = None,
) -> CertificateMaterial:
    """Create a self-signed CA certificate from a CA private key."""
    if ttl_days is None:
        ttl_days = DEFAULT_TTL_DAYS

    ca_key = load_key(ca_key_pem)
    name = _parse_subject(subject)

    builder = _build_base_certificate(
        subject=name,
        issuer=name,
        public_key=ca_key.public_key(),
        ttl_days=ttl_days,
    )

    builder = _add_ca_extensions(
        builder,
        ca_public_key=ca_key.public_key(),
        issuer_public_key=ca_key.public_key(),
    )

    return _sign_builder(builder, signer_key=ca_key)


def _parse_subject(subject: str) -> x509.Name:
    """
    Parse an OpenSSL subject: /C=CA/ST=QC/L=Montreal/O=Tarameteo/OU=PKI/CN=Tarameteo Root CA"
    """
    if not subject.startswith("/"):
        raise ValueError("Subject must start with '/' (e.g. /CN=.../O=...)")

    mapping = {
        "C": NameOID.COUNTRY_NAME,
        "ST": NameOID.STATE_OR_PROVINCE_NAME,
        "L": NameOID.LOCALITY_NAME,
        "O": NameOID.ORGANIZATION_NAME,
        "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
        "CN": NameOID.COMMON_NAME,
    }

    rdns: list[x509.NameAttribute] = []
    for part in (p for p in subject.split("/") if p):
        if "=" not in part:
            raise ValueError(f"Invalid subject component: {part!r}")

        k, v = part.split("=", 1)
        oid = mapping.get(k)
        if oid is None:
            raise ValueError(f"Unsupported subject field {k!r} in {subject!r}")

        rdns.append(x509.NameAttribute(oid, v))

    if not rdns:
        raise ValueError("Subject contained no RDNs")

    return x509.Name(rdns)


def _build_base_certificate(
    *,
    subject: x509.Name,
    issuer: x509.Name,
    public_key,
    ttl_days: int,
    now: datetime | None = None,
) -> x509.CertificateBuilder:
    now = now or datetime.now(UTC)
    not_before = now - timedelta(minutes=2)
    not_after = now + timedelta(days=ttl_days)
    serial = x509.random_serial_number()

    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(serial)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )


def _add_leaf_extensions(
    builder: x509.CertificateBuilder,
    *,
    leaf_public_key,
    issuer_public_key,
    client_auth: bool = True,
    server_auth: bool = False,
) -> x509.CertificateBuilder:
    builder = builder.add_extension(
        x509.BasicConstraints(
            ca=False,
            path_length=None,
        ),
        critical=True,
    )

    builder = builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=server_auth,
            data_encipherment=False,
            key_agreement=isinstance(leaf_public_key, ec.EllipticCurvePublicKey),
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )

    eku: list[x509.ObjectIdentifier] = []
    if client_auth:
        eku.append(ExtendedKeyUsageOID.CLIENT_AUTH)
    if server_auth:
        eku.append(ExtendedKeyUsageOID.SERVER_AUTH)
    if eku:
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=False)

    builder = _add_subject_and_authority_key_ids(
        builder,
        subject_public_key=leaf_public_key,
        issuer_public_key=issuer_public_key,
    )

    return builder


def _add_ca_extensions(
    builder: x509.CertificateBuilder,
    *,
    ca_public_key,
    issuer_public_key,
) -> x509.CertificateBuilder:
    builder = builder.add_extension(
        x509.BasicConstraints(
            ca=True,
            path_length=None,
        ),
        critical=True,
    )

    builder = builder.add_extension(
        x509.KeyUsage(
            digital_signature=False,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )

    builder = _add_subject_and_authority_key_ids(
        builder,
        subject_public_key=ca_public_key,
        issuer_public_key=issuer_public_key,
    )

    return builder


def _add_subject_and_authority_key_ids(
    builder: x509.CertificateBuilder,
    *,
    subject_public_key,
    issuer_public_key,
) -> x509.CertificateBuilder:
    """Add Subject Key Identifier / Authority Key Identifier."""
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(subject_public_key),
        critical=False,
    )
    with suppress(Exception):
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_public_key),
            critical=False,
        )

    return builder


def _sign_builder(
    builder: x509.CertificateBuilder,
    *,
    signer_key: PrivateKey,
    chain_pem: list[str] | None = None,
) -> CertificateMaterial:
    """Sign a prepared CertificateBuilder."""
    cert = builder.sign(private_key=signer_key, algorithm=hashes.SHA256())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return CertificateMaterial(
        cert_pem=cert_pem,
        chain_pem=list(chain_pem or []),
        serial_number=cert.serial_number,
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
    )
