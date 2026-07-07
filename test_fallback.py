# -*- coding: utf-8 -*-
"""Teste: cliente desconecta na semana 3 -> IA assume e o jogo termina normalmente."""
import threading
import time

from engine import GameConfig
from server import GameServer
from client import GameClient

cfg = GameConfig(semanas=6)
srv = GameServer(cfg, porta=5601, host_nome="Host", host_papel="varejista")
srv.start()
cli = GameClient("127.0.0.1", 5601, "Bruno", "atacadista")
time.sleep(0.3)
srv.start_game()

decid_cli = 0
def cli_loop():
    global decid_cli
    while cli.vivo:
        try:
            m = cli.ui_queue.get(timeout=5)
        except Exception:
            return
        if m.get("tipo") == "estado_semana" and m.get("pendente"):
            if decid_cli < 2:
                cli.send_decisao(m["view"]["semana"], 4)
                decid_cli += 1
            else:
                cli.close()   # simula queda na semana 3
                return
threading.Thread(target=cli_loop, daemon=True).start()

fim = None
decid_host = 0
t0 = time.time()
while fim is None and time.time() - t0 < 20:
    msg = srv.ui_queue.get(timeout=10)
    if msg.get("tipo") == "estado_semana" and msg.get("pendente"):
        srv.decisao_local(4)
        decid_host += 1
    elif msg.get("tipo") == "fim_de_jogo":
        fim = msg

assert fim is not None, "jogo não terminou"
assert decid_host == 6 and decid_cli == 2
jogo = [r for r in fim["linhas"] if r["fase"] == "jogo"]
ctrl_ata = [r["ATA_controlador"] for r in jogo]
assert ctrl_ata[:2] == ["humano", "humano"], ctrl_ata
assert all(c == "humano→ia" for c in ctrl_ata[2:]), ctrl_ata
print("Controladores do atacadista por semana:", ctrl_ata)
print("OK — fallback para IA validado.")
srv.shutdown()
