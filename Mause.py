
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MouseQR - Controle de mouse pelo celular via QR Code.
Plataforma: Linux Mint / Ubuntu com ambiente gráfico X11.

Execução:
    python3 MouseQR.py

O script prepara um ambiente virtual próprio, instala as
dependências e inicia o servidor de controle.

Não executa comandos de terminal enviados pelo celular.
Não implementa teclado remoto nem acesso a arquivos.
"""

import os
import sys
import json
import socket
import secrets
import shutil
import subprocess
import threading
import venv
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ============================================================
# CONFIGURAÇÃO
# ============================================================

APP_NAME = "MouseQR"
BASE_DIR = Path(__file__).resolve().parent

# Diretório exclusivo do MouseQR.
VENV_DIR = BASE_DIR / ".mouseqr-venv"

HOST = "0.0.0.0"
PORT = 8765

DEPENDENCIES = [
    "pyautogui",
    "qrcode[pil]",
]


# ============================================================
# INSTALAÇÃO AUTOMÁTICA
# ============================================================

def run_command(command, check=True):
    print("\n$", " ".join(map(str, command)), flush=True)
    return subprocess.run(command, check=check)


def install_system_support():
    """
    Instala o suporte venv e Tk do Linux Mint/Ubuntu.
    Solicita autorização administrativa apenas para o apt.
    Não apaga nem formata arquivos.
    """
    if shutil.which("apt-get") is None:
        raise RuntimeError(
            "apt-get não encontrado. Este instalador foi "
            "preparado para Linux Mint/Ubuntu, não Termux."
        )

    version = f"{sys.version_info.major}.{sys.version_info.minor}"

    if os.geteuid() == 0:
        prefix = []
    else:
        if shutil.which("sudo") is None:
            raise RuntimeError(
                "O suporte venv está ausente e o sudo não foi encontrado."
            )
        prefix = ["sudo"]

    print("\nInstalando suporte do sistema para Python...")

    run_command(prefix + ["apt-get", "update"])

    # Primeiro tenta o pacote específico da versão atual.
    specific = [
        f"python{version}-venv",
        "python3-tk",
    ]

    result = subprocess.run(
        prefix + ["apt-get", "install", "-y"] + specific,
        check=False,
    )

    if result.returncode == 0:
        return

    # Alternativa para distribuições que utilizam o pacote genérico.
    fallback = ["python3-venv", "python3-tk"]

    run_command(prefix + ["apt-get", "install", "-y"] + fallback)


def ensure_venv():
    """
    Cria ou repara o ambiente virtual dedicado.
    Não remove arquivos para tentar recuperar a instalação.
    """
    if VENV_DIR.exists() and not VENV_DIR.is_dir():
        raise RuntimeError(
            f"{VENV_DIR} existe, mas não é uma pasta."
        )

    python = VENV_DIR / "bin" / "python"

    if python.exists():
        test = subprocess.run(
            [str(python), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

        if test.returncode == 0:
            return python

    print("\nCriando ou reparando ambiente virtual...")

    try:
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    except Exception as exc:
        print(f"\nFalha ao preparar o venv: {exc}")
        install_system_support()
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    if not python.exists():
        raise RuntimeError("O Python do ambiente virtual não foi criado.")

    # Verifica se o pip está realmente disponível.
    test = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if test.returncode != 0:
        install_system_support()
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    subprocess.run(
        [str(python), "-m", "pip", "--version"],
        check=True,
    )

    return python


def install_dependencies(python):
    print("\nInstalando dependências do MouseQR...")

    run_command([
        str(python),
        "-m", "pip",
        "install", "--upgrade", "pip",
    ])

    run_command([
        str(python),
        "-m", "pip",
        "install", *DEPENDENCIES,
    ])

    # Validação sem iniciar o controle do mouse.
    run_command([
        str(python),
        "-c",
        "import qrcode; print('qrcode instalado corretamente')",
    ])


# ============================================================
# REDE E QR CODE
# ============================================================

def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # Descobre a interface escolhida pela tabela de rotas.
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def make_qr(url):
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )

    qr.add_data(url)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    image_path = BASE_DIR / "mouseqr.png"
    image.save(image_path)

    print("\nQR CODE")
    print("=" * 45)
    qr.print_ascii(invert=True)
    print("=" * 45)
    print(f"Imagem salva em: {image_path}")


# ============================================================
# INTERFACE WEB
# ============================================================

class MouseHandler(BaseHTTPRequestHandler):

    def send_response_data(self, status, data, content_type):
        body = data.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

        self.wfile.write(body)

    def send_json(self, status, value):
        self.send_response_data(
            status,
            json.dumps(value, ensure_ascii=False),
            "application/json; charset=utf-8",
        )

    def send_error_json(self, status, message):
        self.send_json(status, {"ok": False, "error": message})

    def is_valid_path(self, path):
        token = self.server.session_token
        return path == f"/{token}" or path.startswith(f"/{token}/")

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if not self.is_valid_path(path):
            self.send_error_json(404, "Rota não encontrada")
            return

        token = self.server.session_token

        if path == f"/{token}/api/status":
            self.send_json(200, {
                "application": APP_NAME,
                "status": "online",
                "mouse_control": True,
            })
            return

        if path.rstrip("/") != f"/{token}":
            self.send_error_json(404, "Rota não encontrada")
            return

        html = r"""
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1,
               maximum-scale=1, user-scalable=no">

<title>MouseQR</title>

<style>
* { box-sizing: border-box; }

body {
    margin: 0;
    padding: 20px;
    background: #10151d;
    color: #edf2f8;
    font-family: system-ui, sans-serif;
}

main {
    max-width: 560px;
    margin: auto;
}

h1 { margin-bottom: 4px; }

.muted { color: #a8b5c7; }

.card {
    margin-top: 16px;
    padding: 16px;
    background: #1b2635;
    border: 1px solid #344357;
    border-radius: 14px;
}

.pad {
    height: 260px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    user-select: none;
    -webkit-user-select: none;
    touch-action: none;
    border: 2px dashed #61758d;
    background: #121c29;
    border-radius: 12px;
    color: #cbd7e6;
}

.buttons {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 12px;
}

button {
    min-height: 52px;
    border: 1px solid #44566d;
    border-radius: 10px;
    color: #ffffff;
    background: #29394e;
    font-size: 16px;
    font-weight: 600;
    touch-action: manipulation;
}

button:active { background: #466587; }

.status {
    min-height: 24px;
    overflow-wrap: anywhere;
}

small { line-height: 1.5; }

</style>
</head>

<body>
<main>
    <h1>MouseQR</h1>
    <div class="muted">Controle do mouse pela rede local</div>

    <section class="card">
        <strong>Touchpad</strong>
        <p class="muted">
            Arraste o dedo na área abaixo para mover o cursor.
        </p>

        <div id="pad" class="pad">
            Toque e arraste para mover
        </div>

        <div class="buttons">
            <button id="left">Clique esquerdo</button>
            <button id="right">Clique direito</button>
            <button id="up">Rolar para cima</button>
            <button id="down">Rolar para baixo</button>
        </div>
    </section>

    <section class="card">
        <strong>Conexão</strong>
        <p id="status" class="status">Verificando conexão...</p>
        <button id="check">Testar conexão</button>
    </section>

    <p class="muted">
        <small>
        A sessão é protegida por um token secreto.
        Mantenha o QR Code privado. Encerre o servidor no
        computador quando terminar.
        </small>
    </p>
</main>

<script>
"use strict";

const base = "/__TOKEN__";
const pad = document.getElementById("pad");
const status = document.getElementById("status");

let dragging = false;
let pointerId = null;
let lastX = 0;
let lastY = 0;
let pendingX = 0;
let pendingY = 0;
let sending = false;

async function post(action, data = {}) {
    const response = await fetch(base + "/api/" + action, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        cache: "no-store",
        body: JSON.stringify(data)
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok || result.ok === false) {
        throw new Error(result.error || "Falha na operação");
    }

    return result;
}

async function flushMovement() {
    if (sending || (!pendingX && !pendingY)) return;

    const dx = pendingX;
    const dy = pendingY;

    pendingX = 0;
    pendingY = 0;
    sending = true;

    try {
        await post("move", {dx, dy});
    } catch (error) {
        status.textContent = "Erro: " + error.message;
    } finally {
        sending = false;
    }
}

setInterval(flushMovement, 35);

pad.addEventListener("pointerdown", event => {
    dragging = true;
    pointerId = event.pointerId;
    lastX = event.clientX;
    lastY = event.clientY;

    pad.setPointerCapture(pointerId);
    event.preventDefault();
});

pad.addEventListener("pointermove", event => {
    if (!dragging || event.pointerId !== pointerId) return;

    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;

    lastX = event.clientX;
    lastY = event.clientY;

    pendingX += dx;
    pendingY += dy;

    // Limita o volume de cada movimento pendente.
    pendingX = Math.max(-400, Math.min(400, pendingX));
    pendingY = Math.max(-400, Math.min(400, pendingY));

    event.preventDefault();
});

function stopDragging(event) {
    if (event.pointerId !== pointerId) return;

    dragging = false;
    pointerId = null;
    flushMovement();
}

pad.addEventListener("pointerup", stopDragging);
pad.addEventListener("pointercancel", stopDragging);

async function action(label, operation) {
    status.textContent = label + "...";

    try {
        await operation();
        status.textContent = label + ": concluído";
    } catch (error) {
        status.textContent = "Falha: " + error.message;
    }
}

document.getElementById("left").addEventListener("click", () => {
    action("Clique esquerdo", () => post("click", {button: "left"}));
});

document.getElementById("right").addEventListener("click", () => {
    action("Clique direito", () => post("click", {button: "right"}));
});

document.getElementById("up").addEventListener("click", () => {
    action("Rolagem", () => post("scroll", {amount: 3}));
});

document.getElementById("down").addEventListener("click", () => {
    action("Rolagem", () => post("scroll", {amount: -3}));
});

document.getElementById("check").addEventListener("click", async () => {
    await action("Teste", async () => {
        const response = await fetch(base + "/api/status", {
            cache: "no-store"
        });

        if (!response.ok) throw new Error("Servidor indisponível");
        const data = await response.json();

        status.textContent = "Conectado: " + data.status;
    });
});

document.getElementById("check").click();
</script>
</body>
</html>
"""
        html = html.replace("__TOKEN__", token)
        self.send_response_data(200, html, "text/html; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        token = self.server.session_token

        if not self.is_valid_path(path):
            self.send_error_json(404, "Rota não encontrada")
            return

        routes = {
            f"/{token}/api/move",
            f"/{token}/api/click",
            f"/{token}/api/scroll",
        }

        if path not in routes:
            self.send_error_json(404, "Rota não encontrada")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 2048:
                self.send_error_json(400, "Tamanho de requisição inválido")
                return

            data = json.loads(self.rfile.read(length).decode("utf-8"))

            if not isinstance(data, dict):
                self.send_error_json(400, "Dados inválidos")
                return

            import pyautogui

            with self.server.mouse_lock:

                if path == f"/{token}/api/move":
                    dx = data.get("dx")
                    dy = data.get("dy")

                    if type(dx) not in (int, float) or type(dy) not in (int, float):
                        self.send_error_json(400, "Movimento inválido")
                        return

                    # Impede movimentos gigantes em uma única requisição.
                    dx = max(-400, min(400, int(dx)))
                    dy = max(-400, min(400, int(dy)))

                    pyautogui.moveRel(dx, dy, duration=0)

                elif path == f"/{token}/api/click":
                    button = data.get("button")

                    if button not in ("left", "right"):
                        self.send_error_json(400, "Botão inválido")
                        return

                    pyautogui.click(button=button)

                elif path == f"/{token}/api/scroll":
                    amount = data.get("amount")

                    if type(amount) is not int or amount not in (-3, 3):
                        self.send_error_json(400, "Rolagem inválida")
                        return

                    pyautogui.scroll(amount)

            self.send_json(200, {"ok": True})

        except pyautogui.FailSafeException:
            self.send_error_json(
                423,
                "Proteção do mouse ativada. Verifique o cursor no computador."
            )

        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_error_json(400, "JSON inválido")

        except Exception as exc:
            print(f"[MouseQR] Erro interno: {exc}", flush=True)
            self.send_error_json(500, "Não foi possível executar a ação")

    def log_message(self, fmt, *args):
        # Não registra URLs que contêm o token de sessão.
        print("[HTTP] Requisição recebida", flush=True)


# ============================================================
# SERVIDOR
# ============================================================

def start_server():
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "DISPLAY não encontrado. Execute o programa numa sessão "
            "gráfica do Linux Mint, sem sudo."
        )

    try:
        import pyautogui
        import qrcode
    except Exception as exc:
        raise RuntimeError(
            f"Falha ao carregar dependências: {exc}"
        ) from exc

    # Proteção: mover o mouse físico ao canto superior esquerdo
    # ativa o mecanismo de segurança do PyAutoGUI.
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    token = secrets.token_urlsafe(32)

    server = ThreadingHTTPServer((HOST, PORT), MouseHandler)
    server.session_token = token
    server.mouse_lock = threading.Lock()

    ip = local_ip()
    url = f"http://{ip}:{PORT}/{token}"

    make_qr(url)

    print("\n" + "=" * 52)
    print(APP_NAME, "ONLINE")
    print("=" * 52)
    print(f"Endereço privado para conexão: {url}")
    print(f"Porta: {PORT}")
    print("Celular e computador devem estar na mesma rede Wi-Fi.")
    print("Use Ctrl+C no computador para encerrar a sessão.")
    print("O token muda a cada inicialização.")
    print("=" * 52)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando MouseQR...")
    finally:
        server.server_close()


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def main():
    if sys.platform != "linux":
        raise RuntimeError("Este script requer Linux Mint/Ubuntu.")

    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        start_server()
        return

    print("=" * 52)
    print("MouseQR - instalador automático")
    print("=" * 52)

    python = ensure_venv()
    install_dependencies(python)

    print("\nInstalação concluída. Iniciando servidor...")
    result = subprocess.run([
        str(python),
        str(Path(__file__).resolve()),
        "--server",
    ])

    if result.returncode != 0:
        raise RuntimeError(
            f"O servidor encerrou com código {result.returncode}."
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperação cancelada.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nERRO: {exc}", file=sys.stderr)
        sys.exit(1)
