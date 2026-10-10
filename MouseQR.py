#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MouseQR — mouse remoto pelo celular via QR Code.
Linux Mint / Ubuntu com sessão gráfica X11.

Uso:
    python3 MouseQR.py

O script instala dependências, prepara um ambiente virtual,
gera um QR Code e inicia o servidor de controle.
"""

import os
import sys
import json
import socket
import secrets
import shutil
import subprocess
import importlib.util
import threading
import venv
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".mouseqr-venv"
PORT = 8765
HOST = "0.0.0.0"


# ------------------------------------------------------------
# INSTALAÇÃO
# ------------------------------------------------------------

def executar(cmd, check=True):
    return subprocess.run(cmd, check=check)


def modulo_disponivel(nome):
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def instalar_apt():
    if not shutil.which("apt-get"):
        raise RuntimeError(
            "apt-get não encontrado. Este script requer Linux Mint/Ubuntu."
        )

    prefixo = [] if os.geteuid() == 0 else ["sudo"]

    if prefixo and not shutil.which("sudo"):
        raise RuntimeError("O sudo é necessário para instalar dependências.")

    executar(prefixo + ["apt-get", "update"])

    # Os pacotes são instalados individualmente para que um nome
    # indisponível não impeça a tentativa dos demais.
    pacotes = [
        "python3-venv",
        "python3-tk",
        "python3-pil",
        "python3-qrcode",
        "python3-pyautogui",
        "python3-xlib",
    ]

    for pacote in pacotes:
        resultado = executar(
            prefixo + ["apt-get", "install", "-y", pacote],
            check=False,
        )
        if resultado.returncode:
            print(f"Aviso: pacote {pacote} indisponível pelo apt.")


def preparar_python():
    """
    Usa o Python atual se todas as dependências estiverem disponíveis.
    Caso contrário, cria um venv dedicado e instala via pip.
    Não apaga pastas existentes.
    """
    modulos = ("pyautogui", "qrcode", "PIL")

    if all(modulo_disponivel(m) for m in modulos):
        return Path(sys.executable)

    print("Verificando dependências do sistema...")
    instalar_apt()

    if all(modulo_disponivel(m) for m in modulos):
        return Path(sys.executable)

    python_venv = VENV_DIR / "bin" / "python"

    if VENV_DIR.exists() and not python_venv.exists():
        raise RuntimeError(
            f"A pasta {VENV_DIR} já existe, mas o ambiente está incompleto. "
            "Inspecione a pasta antes de renomeá-la ou recriá-la."
        )

    if not python_venv.exists():
        print("Criando ambiente virtual...")
        try:
            venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        except Exception as erro:
            raise RuntimeError(
                "Não foi possível criar o ambiente virtual. "
                "Verifique se python3-venv corresponde à versão "
                f"do Python instalada. Detalhe: {erro}"
            ) from erro

    executar([
        str(python_venv), "-m", "pip",
        "install", "--upgrade", "pip",
    ])

    executar([
        str(python_venv), "-m", "pip",
        "install", "pyautogui", "qrcode[pil]",
    ])

    executar([
        str(python_venv), "-c",
        "import pyautogui, qrcode; from PIL import Image",
    ])

    return python_venv


# ------------------------------------------------------------
# REDE
# ------------------------------------------------------------

def obter_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        ip = s.getsockname()[0]
        if ip.startswith("127."):
            raise RuntimeError("Conecte o computador a uma rede local.")
        return ip
    finally:
        s.close()


# ------------------------------------------------------------
# SERVIDOR E INTERFACE
# ------------------------------------------------------------

def iniciar_servidor():
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "Sessão gráfica não detectada. Abra o terminal no Linux Mint."
        )

    import pyautogui
    import qrcode

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    token = secrets.token_urlsafe(24)
    base = "/" + token
    mutex = threading.Lock()

    class Handler(BaseHTTPRequestHandler):

        def responder(self, codigo, dados, tipo="application/json"):
            corpo = (
                dados.encode("utf-8")
                if isinstance(dados, str)
                else json.dumps(dados).encode("utf-8")
            )
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            caminho = urlsplit(self.path).path

            if caminho == base + "/status":
                self.responder(200, {"status": "online"})
                return

            if caminho != base:
                self.responder(404, {"erro": "Não encontrado"})
                return

            html = r"""
<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MouseQR</title>
<style>
body{font:17px system-ui;background:#111923;color:#fff;
max-width:520px;margin:auto;padding:20px}
#pad{height:250px;background:#223348;border:2px solid #678;
border-radius:14px;display:grid;place-items:center;
touch-action:none;user-select:none}
button{width:48%;height:52px;margin-top:10px;font-size:15px}
</style>
<h2>MouseQR</h2>
<p>Arraste o dedo na área para mover o cursor.</p>
<div id="pad">Touchpad</div>
<button onclick="acao('click',{button:'left'})">Clique esquerdo</button>
<button onclick="acao('click',{button:'right'})">Clique direito</button>
<button onclick="acao('scroll',{amount:3})">Rolar para cima</button>
<button onclick="acao('scroll',{amount:-3})">Rolar para baixo</button>
<p id="status">Conectado</p>
<script>
const base="__BASE__";
const pad=document.getElementById("pad");
const status=document.getElementById("status");
let ativo=false,x=0,y=0,fila=Promise.resolve();

function acao(tipo,dados){
 fila=fila.then(async()=>{
  const r=await fetch(base+"/"+tipo,{
   method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(dados)
  });
  const j=await r.json();
  if(!r.ok) throw Error(j.erro||"Falha");
 }).catch(e=>status.textContent="Erro: "+e.message);
}

pad.addEventListener("pointerdown",e=>{
 ativo=true;x=e.clientX;y=e.clientY;
 pad.setPointerCapture(e.pointerId);
});
pad.addEventListener("pointermove",e=>{
 if(!ativo)return;
 const dx=Math.round(e.clientX-x),dy=Math.round(e.clientY-y);
 x=e.clientX;y=e.clientY;
 if(dx||dy)acao("move",{dx,dy});
});
pad.addEventListener("pointerup",()=>ativo=false);
pad.addEventListener("pointercancel",()=>ativo=false);
</script>
</html>
""".replace("__BASE__", base)

            self.responder(200, html, "text/html; charset=utf-8")

        def do_POST(self):
            caminho = urlsplit(self.path).path
            rotas = {
                base + "/move",
                base + "/click",
                base + "/scroll",
            }

            if caminho not in rotas:
                self.responder(404, {"erro": "Não encontrado"})
                return

            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if not 0 < tamanho <= 2048:
                    raise ValueError("Tamanho inválido")

                dados = json.loads(
                    self.rfile.read(tamanho).decode("utf-8")
                )
                if not isinstance(dados, dict):
                    raise ValueError("Dados inválidos")

                with mutex:
                    if caminho == base + "/move":
                        dx, dy = dados.get("dx"), dados.get("dy")
                        if type(dx) not in (int, float) or type(dy) not in (int, float):
                            raise ValueError("Movimento inválido")
                        pyautogui.moveRel(
                            max(-300, min(300, int(dx))),
                            max(-300, min(300, int(dy))),
                        )

                    elif caminho == base + "/click":
                        botao = dados.get("button")
                        if botao not in ("left", "right"):
                            raise ValueError("Botão inválido")
                        pyautogui.click(button=botao)

                    else:
                        quantidade = dados.get("amount")
                        if type(quantidade) is not int or quantidade not in (-3, 3):
                            raise ValueError("Rolagem inválida")
                        pyautogui.scroll(quantidade)

                self.responder(200, {"ok": True})

            except (ValueError, json.JSONDecodeError) as erro:
                self.responder(400, {"erro": str(erro)})
            except pyautogui.FailSafeException:
                self.responder(423, {"erro": "Proteção do mouse ativada"})
            except Exception as erro:
                print("Erro de controle:", erro)
                self.responder(500, {"erro": "Falha no controle do mouse"})

        def log_message(self, formato, *args):
            print("[MouseQR] Requisição recebida")

    ip = obter_ip()
    url = f"http://{ip}:{PORT}{base}"

    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(
        BASE_DIR / "mouseqr.png"
    )

    servidor = ThreadingHTTPServer((HOST, PORT), Handler)

    print("\nMouseQR iniciado.")
    print("QR Code:", BASE_DIR / "mouseqr.png")
    print("Endereço:", url)
    print("Celular e computador devem estar na mesma rede.")
    print("Pressione Ctrl+C para encerrar.")

    try:
        servidor.serve_forever()
    finally:
        servidor.server_close()


def main():
    python = preparar_python()

    # Executa novamente no ambiente correto se foi criado um venv.
    if Path(sys.executable).resolve() != python.resolve():
        os.execv(
            str(python),
            [str(python), str(Path(__file__).resolve()), "--server"],
        )

    iniciar_servidor()


if __name__ == "__main__":
    try:
        if "--server" in sys.argv:
            iniciar_servidor()
        else:
            main()
    except KeyboardInterrupt:
        print("\nMouseQR encerrado.")
    except Exception as erro:
        print(f"\nERRO: {erro}", file=sys.stderr)
        sys.exit(1)
