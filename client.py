# -*- coding: utf-8 -*-
"""Cliente do Beer Game: conecta em IP:porta do host e conversa via JSON/TCP."""
import queue
import socket
import threading

from protocol import send_json, iter_json


class GameClient:
    def __init__(self, ip: str, porta: int, nome: str, papel_desejado: str = None):
        self.ui_queue = queue.Queue()
        self.papel = None
        self.vivo = False
        self.sock = socket.create_connection((ip, porta), timeout=8)
        self.sock.settimeout(None)
        self.vivo = True
        send_json(self.sock, {"tipo": "entrar_sala", "nome": nome,
                              "papel_desejado": papel_desejado})
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for msg in iter_json(self.sock):
            if msg.get("tipo") == "bem_vindo":
                self.papel = msg.get("papel")
            self.ui_queue.put(msg)
        self.vivo = False
        self.ui_queue.put({"tipo": "desconectado"})

    def send_decisao(self, semana: int, quantidade: int):
        if not self.vivo:
            return
        try:
            send_json(self.sock, {"tipo": "decisao_pedido", "semana": semana,
                                  "papel": self.papel, "quantidade": int(quantidade)})
        except OSError:
            self.vivo = False
            self.ui_queue.put({"tipo": "desconectado"})

    def close(self):
        self.vivo = False
        try:
            self.sock.close()
        except OSError:
            pass
