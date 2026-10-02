"""Certificado https propio para la red del colegio: que sirva de verdad (handshake TLS), no solo que se escriba un archivo."""
import socket
import ssl
import threading

import pytest
from cryptography import x509

from scripts.generar_certificado import generar


@pytest.fixture()
def certificado(tmp_path):
    return generar(tmp_path / "certs", ["192.168.1.50", "aula.local"])


def _handshake(cert, llave, nombre_esperado):
    """Servidor TLS real con el certificado; un cliente que confía solo en él y exige que el nombre calce."""
    servidor = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    servidor.load_cert_chain(cert, llave)
    cliente = ssl.create_default_context()
    cliente.load_verify_locations(cert)  # autofirmado: es su propia raíz de confianza
    with socket.socket() as escucha:
        escucha.bind(("127.0.0.1", 0))
        escucha.listen(1)
        puerto = escucha.getsockname()[1]

        def atender():
            try:
                conexion, _ = escucha.accept()
                with servidor.wrap_socket(conexion, server_side=True) as s:
                    s.recv(1)
            except (ssl.SSLError, OSError):
                pass

        hilo = threading.Thread(target=atender, daemon=True)
        hilo.start()
        with socket.create_connection(("127.0.0.1", puerto), timeout=5) as crudo:
            with cliente.wrap_socket(crudo, server_hostname=nombre_esperado) as s:
                s.send(b"x")
        hilo.join(timeout=5)


def test_el_certificado_sirve_para_localhost_y_para_las_direcciones_pedidas(certificado):
    cert, llave, nombres = certificado
    for nombre in ("localhost", "127.0.0.1", "192.168.1.50", "aula.local"):
        _handshake(str(cert), str(llave), nombre)
    assert {"localhost", "127.0.0.1", "192.168.1.50", "aula.local"} <= set(nombres)


def test_no_sirve_para_un_nombre_que_no_se_pidio(certificado):
    cert, llave, _ = certificado
    with pytest.raises(ssl.SSLCertVerificationError):
        _handshake(str(cert), str(llave), "otra-direccion.example")


def test_es_de_un_ano_y_solo_para_servidor(certificado):
    cert, _, _ = certificado
    c = x509.load_pem_x509_certificate(cert.read_bytes())
    dias = (c.not_valid_after_utc - c.not_valid_before_utc).days
    assert 360 <= dias <= 370
    assert c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False  # no puede firmar otros certificados


def test_la_llave_queda_en_una_carpeta_que_git_ignora():
    ignorado = open(".gitignore", encoding="utf-8").read().splitlines()
    assert "certs/" in ignorado
