"""Self-signed HTTPS certificate for the LAN address (iOS Safari only grants the camera over HTTPS)."""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path


def lan_ip() -> str:
    """This computer's address on the local network (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _covers(cert_path: Path, ip: str) -> bool:
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    expires = cert.not_valid_after_utc
    return ipaddress.ip_address(ip) in san.get_values_for_type(x509.IPAddress) and expires > dt.datetime.now(dt.timezone.utc)


def ensure_certificate(cert_dir: Path, ip: str) -> tuple[Path, Path]:
    cert_path, key_path = cert_dir / "schiena.crt", cert_dir / "schiena.key"
    if cert_path.exists() and key_path.exists() and _covers(cert_path, ip):
        return cert_path, key_path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    cert_dir.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Schiena (local)")])
    now = dt.datetime.now(dt.timezone.utc)
    host = socket.gethostname()
    dns = {"localhost", host, host if host.endswith(".local") else f"{host}.local"}
    san = x509.SubjectAlternativeName(
        [x509.DNSName(d) for d in sorted(dns)]
        + [x509.IPAddress(ipaddress.ip_address(a)) for a in sorted({ip, "127.0.0.1"})]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=397))  # Apple rejects longer-lived TLS certificates
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
