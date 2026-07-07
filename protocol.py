# -*- coding: utf-8 -*-
"""Protocolo: mensagens JSON (UTF-8) delimitadas por '\\n' sobre TCP."""
import json
import socket

PORTA_PADRAO = 5555
ENC = "utf-8"


def send_json(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode(ENC)
    sock.sendall(data)


def iter_json(sock: socket.socket):
    """Gera dicts conforme as mensagens chegam. Encerra quando o socket fecha."""
    buf = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line.decode(ENC))
            except (ValueError, UnicodeDecodeError):
                continue  # mensagem malformada: ignora


def ip_local() -> str:
    """Melhor palpite do IP desta máquina na rede local."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
