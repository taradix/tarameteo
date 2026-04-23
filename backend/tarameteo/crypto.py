"""Crypto keys, algorithms, signing privimitives, serialization."""

from datetime import (
    UTC,
    datetime,
)
from enum import Enum

from attrs import (
    define,
    field,
)
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import (
    ec,
    rsa,
)

PrivateKey = rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey


class KeyAlgorithm(Enum):

    RSA = "rsa"
    EC = "ec"

    def __str__(self):
        return self.value


@define(frozen=True)
class KeySpec:

    algorithm: KeyAlgorithm = KeyAlgorithm.EC
    rsa_bits: int = 2048
    curve: ec.EllipticCurve = field(factory=ec.SECP256R1)


DEFAULT_KEY_SPEC = KeySpec()


def cert_expires_at(cert_pem: str) -> datetime:
    """Datetime when the certificate expires."""
    cert = load_cert(cert_pem)
    return cert.not_valid_after_utc


def cert_is_current(cert_pem: str, now: datetime | None = None) -> bool:
    """True if the certificate is within its validity window."""
    now = now or datetime.now(UTC)

    cert = load_cert(cert_pem)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc

    return not_before <= now <= not_after


def generate_key_pem(key_spec: KeySpec = DEFAULT_KEY_SPEC) -> str:
    """Generate a private key in PEM format."""
    if key_spec.algorithm is KeyAlgorithm.RSA:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_spec.rsa_bits,
        )
    elif key_spec.algorithm is KeyAlgorithm.EC:
        private_key = ec.generate_private_key(key_spec.curve)
    else:
        raise AssertionError(f"Unhandled key algorithm: {key_spec.algorithm}")

    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return key_pem.decode("utf-8")


def key_matches_cert(key_pem: str, cert_pem: str) -> bool:
    """True if the private key corresponds to the certificate's public key."""
    key_pub = load_key(key_pem).public_key()
    cert_pub = load_cert(cert_pem).public_key()
    return cert_pub.public_numbers() == key_pub.public_numbers()


def load_cert(cert_pem: str) -> x509.Certificate:
    """Load a certificate from PEM encoded data."""
    return x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))


def load_csr(csr_pem: str) -> x509.CertificateSigningRequest:
    """Load a certificate signing request (CSR) from PEM encoded data."""
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    if not csr.is_signature_valid:
        raise ValueError("CSR signature is invalid")

    return csr


def load_key(key_pem: str, password: str | None = None) -> PrivateKey:
    key = serialization.load_pem_private_key(
        key_pem.encode("utf-8"),
        password=None if password is None else password.encode("utf-8"),
    )
    # The return type from cryptography is broader; narrow it for our usage.
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise TypeError(f"Unsupported private key type: {type(key)!r}")

    return key
