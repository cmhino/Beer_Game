# -*- coding: utf-8 -*-
"""Teste da rede sem GUI: servidor + 2 clientes humanos roteirizados + 2 IAs."""
import threading
import time

from engine import GameConfig
from server import GameServer
from client import GameClient

cfg = GameConfig(semanas=8)
srv = GameServer(cfg, porta=5599, host_nome="Professor", host_papel="observador")
srv.start()


def jogador(nome, papel, pedidos):
    cli = GameClient("127.0.0.1", 5599, nome, papel)
    enviados = 0
    fim = {}
    while True:
        msg = cli.ui_queue.get(timeout=20)
        t = msg.get("tipo")
        if t == "bem_vindo":
            assert msg["papel"] == papel, (nome, msg)
        elif t == "estado_semana" and msg.get("pendente"):
            sem = msg["view"]["semana"]
            q = pedidos[min(enviados, len(pedidos) - 1)]
            cli.send_decisao(sem, q)
            enviados += 1
        elif t == "fim_de_jogo":
            fim.update(msg)
            break
    cli.close()
    return nome, enviados, fim


resultados = {}


def run(nome, papel, pedidos):
    resultados[nome] = jogador(nome, papel, pedidos)


t1 = threading.Thread(target=run, args=("Celso", "varejista", [4, 4, 4, 4, 8, 8, 8, 8]))
t2 = threading.Thread(target=run, args=("Ana", "distribuidor", [4] * 8))
t1.start(); t2.start()
time.sleep(0.5)
srv.start_game()
t1.join(timeout=30); t2.join(timeout=30)
assert not t1.is_alive() and not t2.is_alive(), "clientes não terminaram"

for nome, enviados, fim in resultados.values():
    assert enviados == 8, (nome, enviados)
    assert fim["resumo"]["semanas_jogadas"] == 8
    assert len(fim["linhas"]) == 12  # 4 setup + 8 jogo

linhas = resultados["Celso"][2]["linhas"]
ctrl = [(r["VAR_controlador"], r["ATA_controlador"], r["DIS_controlador"], r["FAB_controlador"])
        for r in linhas if r["fase"] == "jogo"]
assert all(c == ("humano", "ia", "humano", "ia") for c in ctrl), ctrl
print("Arquivos do host:", resultados["Celso"][2]["arquivos_host"])
print("OK — rede validada (2 humanos + 2 IAs, 8 semanas).")
srv.shutdown()
