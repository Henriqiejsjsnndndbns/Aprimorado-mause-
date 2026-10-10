#!/usr/bin/env python3
# QRConnect — conexão simples pelo QR Code
# Linux Mint / Ubuntu

import os
import sys
import io
import json
import socket
import secrets
import shutil
import subprocess
import importlib.util
import webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASTA = Path(__file__).resolve().parent
VENV = PASTA / ".qrconnect-venv"
PORTA = 8765


def executar(comando, check=True):
    return subprocess.run(comando, check=check)


def tem_qrcode(python):
    resultado = subprocess.run(
        [
            str(python), "-c",
            "import qrcode; from qrcode.image.svg import SvgPathImage"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return resultado.returncode == 0


def instalar_apt():
    if not shutil.which("apt-get"):
        return False

    prefixo = [] if os.geteuid() == 0 else ["sudo"]

    if prefixo and not shutil.which("sudo"):
        return False

    print("Atualizando a lista de pacotes...")
    if executar(prefixo + ["apt-get", "update"], check=False).returncode:
        print("Aviso: não foi possível atualizar os repositórios.")
        return False

    # Instalado separadamente: um pacote ausente não bloqueia os demais.
    resultado = executar(
        prefixo + ["apt-get", "install", "-y", "python3-qrcode"],
        check=False,
    )

    return resultado.returncode == 0


def instalar_pip():
    if VENV.exists() and not (VENV / "bin" / "python").exists():
        raise RuntimeError(
            f"Ambiente incompleto: {VENV}. "
            "Inspecione essa pasta antes de alterá-la."
        )

    python = VENV / "bin" / "python"

    if not python.exists():
        print("Preparando ambiente virtual...")
        executar([sys.executable, "-m", "venv", str(VENV)])

    print("Instalando biblioteca QR Code...")
    executar([
        str(python), "-m", "pip",
        "install", "--disable-pip-version-check", "qrcode"
    ])

    if not tem_qrcode(python):
        raise RuntimeError("A biblioteca qrcode não passou na validação.")

    return python


def preparar():
    atual = Path(sys.executable)

    if tem_qrcode(atual):
        return atual

    print("A biblioteca QR Code não está disponível.")

    instalar_apt()

    if tem_qrcode(atual):
        return atual

    # Pacotes APT são instalados no Python do sistema.
    sistema = Path("/usr/bin/python3")

    if sistema.exists() and tem_qrcode(sistema):
        return sistema

    # Se falta suporte ao venv, instala o pacote correspondente.
    versao = f"{sys.version_info.major}.{sys.version_info.minor}"
    prefixo = [] if os.geteuid() == 0 else ["sudo"]

    if shutil.which("apt-get"):
        if prefixo and not shutil.which("sudo"):
            raise RuntimeError("É necessário sudo para instalar o suporte venv.")

        pacote = f"python{versao}-venv"
        resultado = executar(
            prefixo + ["apt-get", "install", "-y", pacote],
            check=False,
        )

        if resultado.returncode:
            executar(
                prefixo + ["apt-get", "install", "-y", "python3-venv"]
            )

    return instalar_pip()


def obter_ip():
    conexao = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        conexao.connect(("192.0.2.1", 80))
        ip = conexao.getsockname()[0]

        if ip.startswith("127."):
            raise RuntimeError(
                "Nenhum endereço de rede local foi encontrado. "
                "Conecte o computador à rede."
            )

        return ip
    finally:
        conexao.close()


def iniciar():
    import qrcode
    from qrcode.image.svg import SvgPathImage

    token = secrets.token_urlsafe(24)
    rota = "/conectar/" + token
    ip = obter_ip()
    url = f"http://{ip}:{PORTA}{rota}"

    qr = qrcode.QRCode(box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    imagem = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    imagem.save(buffer)
    qr_svg = buffer.getvalue()

    class Site(BaseHTTPRequestHandler):

        def responder(self, codigo, conteudo, tipo):
            if isinstance(conteudo, str):
                conteudo = conteudo.encode("utf-8")

            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(conteudo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(conteudo)

        def do_GET(self):
            caminho = self.path.split("?", 1)[0]

            # O painel e a imagem QR só ficam disponíveis no próprio PC.
            local = self.client_address[0] in ("127.0.0.1", "::1")

            if caminho == "/" and local:
                pagina = """
<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QR Connect</title>
<style>
body{background:#10151d;color:#eef3f9;font:17px system-ui;
text-align:center;padding:25px 12px}
main{max-width:460px;margin:auto;background:#1b2635;
padding:22px;border-radius:16px}
img{width:250px;max-width:100%;background:white;padding:8px;
border-radius:8px}
p{overflow-wrap:anywhere;color:#bdc9d8}
</style>
<main>
<h1>QR Connect</h1>
<p>Escaneie o código com a câmera do celular.</p>
<img src="/qr.svg" alt="QR Code de conexão">
<p>Endereço para conexão:</p>
<p>__URL__</p>
<p>O celular e o computador precisam estar na mesma rede.</p>
</main>
</html>
""".replace("__URL__", url)

                self.responder(200, pagina, "text/html; charset=utf-8")
                return

            if caminho == "/qr.svg" and local:
                self.responder(200, qr_svg, "image/svg+xml")
                return

            if caminho == rota:
                pagina = """
<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conectado</title>
<style>
body{font:18px system-ui;background:#10151d;color:white;
text-align:center;padding:40px 15px}
main{max-width:420px;margin:auto;background:#1b2635;
padding:25px;border-radius:15px}
</style>
<main>
<h1>Conexão estabelecida</h1>
<p>O celular conseguiu acessar o servidor do computador.</p>
<p>QR Connect está funcionando.</p>
</main>
</html>
"""
                self.responder(200, pagina, "text/html; charset=utf-8")
                return

            self.responder(404, "Não encontrado", "text/plain; charset=utf-8")

        def log_message(self, formato, *args):
            print("[QR Connect] Requisição recebida")

    servidor = ThreadingHTTPServer(("0.0.0.0", PORTA), Site)

    print("\nQR Connect está funcionando.")
    print("Endereço local:", url)
    print("O painel QR será aberto no navegador do computador.")
    print("Para encerrar, pressione Ctrl+C.")

    webbrowser.open(f"http://127.0.0.1:{PORTA}/")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando QR Connect.")
    finally:
        servidor.server_close()


def main():
    if "--iniciar" in sys.argv:
        iniciar()
        return

    python = preparar()

    # Se outra instalação Python for necessária, reinicia com ela.
    if os.path.abspath(str(python)) != os.path.abspath(sys.executable):
        os.execv(
            str(python),
            [str(python), str(Path(__file__).resolve()), "--iniciar"],
        )

    iniciar()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as erro:
        print(
            f"\nFalha ao executar um comando (código {erro.returncode}).",
            file=sys.stderr,
        )
        sys.exit(1)
    except (RuntimeError, OSError, ImportError) as erro:
        print(f"\nERRO: {erro}", file=sys.stderr)
        sys.exit(1)
