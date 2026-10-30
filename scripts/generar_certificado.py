# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Genera un certificado https propio (autofirmado) para usar la app en la red del colegio.

Hace falta para grabar con el celular: los navegadores solo dan el micrófono en una página segura
(https, o `localhost`), y `http://192.168.x.x` no lo es. Con este certificado el servidor se abre por https;
la primera vez, cada celular o PC muestra «conexión no privada» y hay que tocar «Avanzado → continuar».
(Sin esa advertencia: usar un dominio propio con certificado válido, ver docs/fases/fase-6.)

    python -m scripts.generar_certificado                  # localhost + las direcciones de este equipo
    python -m scripts.generar_certificado 192.168.1.50     # y además esta dirección (o nombre)

Deja `certs/cert.pem` y `certs/key.pem` (la carpeta está en .gitignore: la llave no se sube). Para usarlos:

    uvicorn api:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
    cd frontend && npm run dev:https
"""
import argparse
import datetime
import hashlib
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CARPETA = Path("certs")
VIGENCIA_DIAS = 365


def direcciones_de_este_equipo() -> list[str]:
    """Las direcciones IPv4 con las que otros equipos de la red pueden llegar a este."""
    encontradas: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            encontradas.add(info[4][0])
    except OSError:
        pass
    try:  # la dirección de la interfaz que sale a la red (no envía nada)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            encontradas.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in encontradas if not ip.startswith("127."))


def _nombre_alternativo(valor: str) -> x509.GeneralName:
    try:
        return x509.IPAddress(ipaddress.ip_address(valor))
    except ValueError:
        return x509.DNSName(valor)


def generar(carpeta: Path, extras: list[str], ahora: datetime.datetime | None = None) -> tuple[Path, Path, list[str]]:
    """Crea la llave y el certificado en `carpeta`. Devuelve (cert, llave, nombres incluidos)."""
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    nombres = ["localhost", "127.0.0.1", "::1", socket.gethostname(), *direcciones_de_este_equipo(), *extras]
    nombres = list(dict.fromkeys(n for n in nombres if n))  # sin repetidos, en orden

    llave = ec.generate_private_key(ec.SECP256R1())
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ClaseAIdia (certificado propio)")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(sujeto)  # autofirmado
        .public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(minutes=5))
        .not_valid_after(ahora + datetime.timedelta(days=VIGENCIA_DIAS))
        .add_extension(x509.SubjectAlternativeName([_nombre_alternativo(n) for n in nombres]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(llave, hashes.SHA256())
    )

    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_cert, ruta_llave = carpeta / "cert.pem", carpeta / "key.pem"
    ruta_llave.write_bytes(
        llave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    ruta_llave.chmod(0o600)  # en Windows no tiene efecto; en Linux/Mac, solo el dueño la lee
    ruta_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return ruta_cert, ruta_llave, nombres


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera un certificado https propio para la red del colegio.")
    ap.add_argument("direcciones", nargs="*", help="direcciones o nombres extra con los que se abrirá la app (p. ej. 192.168.1.50)")
    ap.add_argument("--carpeta", type=Path, default=CARPETA)
    args = ap.parse_args(argv)

    cert, llave, nombres = generar(args.carpeta, args.direcciones)
    huella = hashlib.sha256(x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(serialization.Encoding.DER)).hexdigest()
    print(f"Certificado: {cert}\nLlave:       {llave}  (privada: no la compartas ni la subas)")
    print(f"Válido por {VIGENCIA_DIAS} días para: {', '.join(nombres)}")
    print(f"Huella SHA-256: {':'.join(huella[i:i + 2] for i in range(0, len(huella), 2)).upper()}")
    print("\nSi abres la app con una dirección que no está en esa lista, vuelve a correr el comando agregándola.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
