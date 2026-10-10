#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JARVIS QR CONNECT
Instalador e servidor de conexão por QR Code.
Destinado a Linux Mint / Ubuntu com Python 3.

Uso:
    python3 Teste.py
"""

import os
import sys
import json
import socket
import shutil
import subprocess
import urllib.parse
import venv
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ============================================================
# CONFIGURAÇÃO
# ============================================================

APP_NAME = "JARVIS QR CONNECT"
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / "venv"
HOST = "0.0.0.0"
PORT = 8765

REQUIRED_PACKAGES = [
    "qrcode[pil]",
]

# O QR contém somente o endereço local do servidor.
# Não contém senha, token de acesso ou credenciais.


# ============================================================
# UTILITÁRIOS
# ============================================================

def run_command(command, *, check=True):
    print("\n$", " ".join(map(str, command)))

    return subprocess.run(
        list(map(str, command)),
        check=check,
        text=True,
    )


def find_python():
    return shutil.which("python3") or sys.executable


def get_local_ip():
    """
    Descobre o endereço IPv4 utilizado para alcançar
    a rede externa sem enviar dados de aplicação.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def install_system_venv_support():
    """
    Tenta identificar a versão do Python e instalar
    o pacote venv correspondente em Debian/Ubuntu.
    Requer sudo quando não estiver executando como root.
    """
    version = f"{sys.version_info.major}.{sys.version_info.minor}"

    package = f"python{version}-venv"

    if shutil.which("apt-get") is None:
        raise RuntimeError(
            "apt-get não encontrado. Instale o suporte venv "
            "manualmente para esta distribuição."
        )

    print(f"\nInstalando suporte ao ambiente virtual: {package}")

    command = ["apt-get", "install", "-y", package]

    if os.geteuid() != 0:
        if shutil.which("sudo") is None:
            raise RuntimeError(
                "É necessário instalar o pacote "
                f"{package} com privilégios administrativos."
            )
        command.insert(0, "sudo")

    run_command(command)


def create_venv():
    """
    Não apaga ambientes existentes.
    Se um ambiente parcial impedir a criação, para e
    solicita inspeção manual em vez de apagar arquivos.
    """
    python = find_python()

    if VENV_DIR.exists():
        candidate = VENV_DIR / "bin" / "python"

        if candidate.exists():
            print("\nAmbiente virtual existente encontrado.")
            return candidate

        raise RuntimeError(
            f"A pasta {VENV_DIR} já existe, mas não contém "
            "um Python executável. Inspecione a pasta antes "
            "de renomeá-la ou recriá-la."
        )

    print("\nCriando ambiente virtual...")

    try:
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    except (Exception, SystemExit) as exc:
        print(f"\nFalha ao criar o ambiente virtual: {exc}")
        print("Tentando instalar o suporte venv do sistema...")

        install_system_venv_support()

        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    candidate = VENV_DIR / "bin" / "python"

    if not candidate.exists():
        raise RuntimeError("Python do ambiente virtual não encontrado.")

    return candidate


def install_dependencies(python):
    print("\nAtualizando ferramentas do pip...")

    run_command([
        python, "-m", "pip",
        "install", "--upgrade", "pip"
    ])

    print("\nInstalando dependências...")

    run_command([
        python, "-m", "pip",
        "install", *REQUIRED_PACKAGES
    ])

    # Valida os imports antes de iniciar o servidor.
    run_command([
        python, "-c",
        "import qrcode; from PIL import Image; "
        "print('Dependências verificadas com sucesso.')"
    ])


# ============================================================
# SERVIDOR WEB
# ============================================================

class RequestHandler(BaseHTTPRequestHandler):

    def send_page(self, status, content, content_type="text/html; charset=utf-8"):
        data = content.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/status":
            self.send_page(
                200,
                json.dumps({
                    "application": APP_NAME,
                    "status": "online",
                    "version": 1,
                }),
                "application/json; charset=utf-8",
            )
            return

        if self.path != "/":
            self.send_page(404, "Não encontrado")
            return

        html = """
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS QR CONNECT</title>
<style>
body {
    margin: 0;
    background: #10151d;
    color: #e8edf5;
    font-family: system-ui, sans-serif;
}
main {
    max-width: 620px;
    margin: 8vh auto;
    padding: 24px;
}
.card {
    padding: 24px;
    border: 1px solid #344154;
    border-radius: 16px;
    background: #18212d;
}
h1 { font-size: 1.7rem; }
.status { color: #80e0ad; }
button {
    padding: 12px 18px;
    border: 0;
    border-radius: 8px;
    font-size: 1rem;
    cursor: pointer;
}
pre {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}
</style>
</head>
<body>
<main>
<section class="card">
<h1>JARVIS QR CONNECT</h1>
<p class="status">● Servidor conectado</p>
<p>Esta página foi aberta pelo endereço local do computador.</p>
<button onclick="checkStatus()">Verificar conexão</button>
<pre id="result">Aguardando teste...</pre>
</section>
</main>
<script>
async function checkStatus() {
    const output = document.getElementById("result");
    output.textContent = "Verificando...";
    try {
        const response = await fetch("/api/status", {
            cache: "no-store"
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const data = await response.json();
        output.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        output.textContent = "Falha: " + error.message;
    }
}
checkStatus();
</script>
</body>
</html>
"""
        self.send_page(200, html)

    def log_message(self, fmt, *args):
        print("[HTTP]", fmt % args)


# ============================================================
# QR CODE
# ============================================================

def show_qr(url, python):
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )

    qr.add_data(url)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")

    image_path = BASE_DIR / "jarvis-connect-qr.png"
    image.save(image_path)

    print("\nQR CODE GERADO")
    print(f"Imagem: {image_path}")

    # Exibição no terminal, se houver suporte.
    try:
        qr.print_ascii(invert=True)
    except Exception:
        pass


# ============================================================
# EXECUÇÃO
# ============================================================

def main():
    print("=" * 56)
    print(APP_NAME)
    print("=" * 56)

    if sys.platform != "linux":
        raise RuntimeError(
            "Este instalador foi preparado para Linux Mint/Ubuntu."
        )

    python = create_venv()
    install_dependencies(python)

    ip = get_local_ip()
    url = f"http://{ip}:{PORT}/"

    show_qr(url, python)

    print("\n" + "=" * 56)
    print("SERVIDOR PRONTO")
    print("=" * 56)
    print(f"Endereço para o celular: {url}")
    print(f"Estado: http://{ip}:{PORT}/api/status")
    print("\nO celular e o computador precisam estar na mesma rede.")
    print("Para encerrar o servidor, pressione Ctrl+C.")
    print("Este servidor não fornece controle remoto do computador.")

    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    server.daemon_threads = True

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
    finally:
        server.server_close()
        print("Servidor encerrado.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\nERRO: comando falhou com código {exc.returncode}")
        sys.exit(exc.returncode or 1)
    except Exception as exc:
        print(f"\nERRO: {exc}")
        sys.exit(1)
