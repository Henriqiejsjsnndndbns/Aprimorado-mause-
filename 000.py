#!/usr/bin/env python3
# MouseQR — controle do mouse pelo celular via QR Code
# Linux Mint / Ubuntu com ambiente gráfico X11

import os
import sys
import json
import socket
import secrets
import shutil
import subprocess
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

PORT = 8765


def instalar_dependencias():
    modulos = ("pyautogui", "qrcode", "PIL")

    if all(importlib.util.find_spec(m) for m in modulos):
        return

    if not shutil.which("apt-get"):
        raise RuntimeError("Este script requer Linux Mint/Ubuntu.")

    comando = [] if os.geteuid() == 0 else ["sudo"]

    if comando and not shutil.which("sudo"):
        raise RuntimeError("Instale as dependências com apt.")

    pacotes = [
        "python3-pyautogui",
        "python3-qrcode",
        "python3-pil",
        "python3-xlib",
        "python3-tk",
    ]

    subprocess.run(
        comando + ["apt-get", "update"],
        check=True
    )
    subprocess.run(
        comando + ["apt-get", "install", "-y"] + pacotes,
        check=True
    )


def obter_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        ip = s.getsockname()[0]
        if ip.startswith("127."):
            raise RuntimeError("Conecte o computador à rede Wi-Fi.")
        return ip
    finally:
        s.close()


def main():
    instalar_dependencias()

    import pyautogui
    import qrcode

    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "Abra o terminal dentro da sessão gráfica do Linux Mint."
        )

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    token = secrets.token_urlsafe(24)
    base = "/" + token
    bloqueio = __import__("threading").Lock()

    class Handler(BaseHTTPRequestHandler):

        def responder(self, codigo, dados, tipo="application/json"):
            corpo = (
                dados.encode()
                if isinstance(dados, str)
                else json.dumps(dados).encode()
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

            pagina = """
<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MouseQR</title>
<style>
body{font:17px system-ui;background:#101820;color:white;
padding:20px;max-width:500px;margin:auto}
#pad{height:250px;background:#223344;border:2px solid #678;
border-radius:14px;display:grid;place-items:center;
touch-action:none;user-select:none}
button{width:48%;height:55px;margin-top:10px;
font-size:15px;border-radius:8px}
</style>
<h2>MouseQR</h2>
<p>Arraste o dedo para mover o mouse.</p>
<div id="pad">Touchpad</div>
<div>
<button onclick="acao('click',{button:'left'})">Clique esquerdo</button>
<button onclick="acao('click',{button:'right'})">Clique direito</button>
<button onclick="acao('scroll',{amount:3})">Rolar para cima</button>
<button onclick="acao('scroll',{amount:-3})">Rolar para baixo</button>
</div>
<p id="status">Conectado</p>
<script>
const base = "__BASE__";
const pad = document.querySelector("#pad");
const status = document.querySelector("#status");
let ativo = false, x = 0, y = 0, fila = Promise.resolve();

function enviar(tipo, dados) {
  fila = fila.then(async () => {
    const r = await fetch(base + "/" + tipo, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(dados)
    });
    if (!r.ok) throw Error("HTTP " + r.status);
  }).catch(e => status.textContent = "Erro: " + e.message);
}

function acao(tipo, dados) {
  enviar(tipo, dados);
}
window.acao = acao;

pad.addEventListener("pointerdown", e => {
  ativo = true; x = e.clientX; y = e.clientY;
  pad.setPointerCapture(e.pointerId);
});
pad.addEventListener("pointermove", e => {
  if (!ativo) return;
  const dx = Math.round(e.clientX - x);
  const dy = Math.round(e.clientY - y);
  x = e.clientX; y = e.clientY;
  if (dx || dy) enviar("move", {dx,dy});
});
pad.addEventListener("pointerup", () => ativo = false);
pad.addEventListener("pointercancel", () => ativo = false);
</script>
</html>
""".replace("__BASE__", base)

            self.responder(
                200, pagina,
                "text/html; charset=utf-8"
            )

        def do_POST(self):
            caminho = urlsplit(self.path).path

            if caminho not in (
                base + "/move",
                base + "/click",
                base + "/scroll",
            ):
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

                with bloqueio:
                    if caminho == base + "/move":
                        dx, dy = dados.get("dx"), dados.get("dy")
                        if type(dx) not in (int, float) or type(dy) not in (int, float):
                            raise ValueError("Movimento inválido")
                        pyautogui.moveRel(
                            max(-300, min(300, int(dx))),
                            max(-300, min(300, int(dy))),
                            duration=0
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

            except ValueError as e:
                self.responder(400, {"erro": str(e)})
            except pyautogui.FailSafeException:
                self.responder(423, {"erro": "Proteção do mouse ativada"})
            except Exception:
                self.responder(500, {"erro": "Falha ao controlar o mouse"})

        def log_message(self, formato, *args):
            print("[MouseQR] Requisição recebida")

    ip = obter_ip()
    url = f"http://{ip}:{PORT}{base}"

    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save("mouseqr.png")

    servidor = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    print("\nMouseQR iniciado.")
    print("Leia o QR Code salvo em mouseqr.png.")
    print("Endereço:", url)
    print("Notebook e celular precisam estar na mesma rede.")
    print("Pressione Ctrl+C para encerrar.")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando MouseQR.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as erro:
        print("ERRO:", erro, file=sys.stderr)
        sys.exit(1)
