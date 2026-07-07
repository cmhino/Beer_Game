# -*- coding: utf-8 -*-
"""
Teste da GUI sob display virtual: percorre menu -> setup individual -> partida
completa (2 humanos simulados + 2 IAs) -> relatório. Também abre as telas de
host e de cliente para garantir que constroem sem erro.
"""
import tkinter as tk

from gui import (App, MenuFrame, IndividualSetupFrame, IndividualBoardFrame,
                 NetSetupFrame, LobbyFrame)
from engine import ROLES

erros = []


import time as _t


def bombear(app, vezes=8):
    for _ in range(vezes):
        app.update()


def bombear_tempo(app, segundos):
    fim = _t.time() + segundos
    while _t.time() < fim:
        app.update()
        _t.sleep(0.03)


app = App()
bombear(app)
assert isinstance(app._frame, MenuFrame)

# --- modo individual ---------------------------------------------------------
app.mostrar(IndividualSetupFrame)
bombear(app)
setup = app._frame
setup.form.vars["semanas"].set("10")
setup.combos["distribuidor"].set("IA")
setup.combos["fabrica"].set("IA")
setup._iniciar()
bombear(app)
board = app._frame
assert isinstance(board, IndividualBoardFrame)

semanas_jogadas = 0
limite = _t.time() + 60
while board.table.rows[-1]["semana"] < 10 and _t.time() < limite:
    if not board._ocupado and board.engine.aguardando_decisoes:
        board.paineis["varejista"].entrada.set(5)
        board.paineis["atacadista"].entrada.set(4)
        board._confirmar()
        semanas_jogadas += 1
    bombear_tempo(app, 0.1)
assert semanas_jogadas == 10, semanas_jogadas
assert board.table.rows[-1]["semana"] == 10
assert board.table.rows[-1]["VAR_pedido_colocado"] == 5
assert board.table.rows[-1]["DIS_controlador"] == "ia"
# relatório abriu como Toplevel
tops = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
assert tops, "relatório não abriu"
for t in tops:
    t.destroy()
print("GUI individual OK (10 semanas, 2 humanos + 2 IAs, relatório aberto)")


# --- terminar simulação antecipadamente (modo individual) --------------------
from tkinter import messagebox as _mb
app.mostrar(IndividualSetupFrame)
bombear(app)
setup2 = app._frame
setup2.form.vars["semanas"].set("30")
setup2.form.vars["estoque_inicial"].set("16")   # estoque inicial configurável
for r in ("varejista", "atacadista", "distribuidor", "fabrica"):
    setup2.combos[r].set("IA")
setup2._iniciar()
bombear(app)
b2 = app._frame
assert b2.cfg.estoque_inicial == 16
assert b2.table.rows[0]["VAR_estoque_final"] == 16   # setup respeita o estoque
# joga 5 semanas e encerra
for _ in range(5):
    while b2._ocupado or not b2.engine.aguardando_decisoes:
        bombear_tempo(app, 0.05)
    b2._confirmar()
    bombear_tempo(app, 0.5)
_orig = _mb.askyesno
_mb.askyesno = lambda *a, **k: True
while b2._ocupado or not b2.engine.aguardando_decisoes:
    bombear_tempo(app, 0.05)
b2._terminar()
_mb.askyesno = _orig
bombear_tempo(app, 0.4)
assert b2.table.rows[-1]["semana"] == 6, b2.table.rows[-1]["semana"]
tops2 = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
assert tops2, "relatório do término antecipado não abriu"
for t in tops2:
    t.destroy()
print("Terminar simulação OK (encerrou na semana 6 de 30, estoque inicial 16)")


# --- Rodar até o fim deve fechar a última semana e abrir o relatório ---------
app.mostrar(IndividualSetupFrame)
bombear(app)
setup3 = app._frame
setup3.form.vars["semanas"].set("8")
for r in ("varejista", "atacadista", "distribuidor", "fabrica"):
    setup3.combos[r].set("IA")
setup3._iniciar()
bombear(app)
b3 = app._frame
b3._rodar_tudo()
limite = _t.time() + 30
while _t.time() < limite and b3.table.rows[-1]["semana"] < 8:
    bombear_tempo(app, 0.1)
assert b3.table.rows[-1]["semana"] == 8, b3.table.rows[-1]["semana"]
bombear_tempo(app, 0.3)
tops3 = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
assert tops3, "relatório do Rodar até o fim não abriu"
for t in tops3:
    t.destroy()
print("Rodar até o fim OK (8 semanas fechadas e relatório aberto)")

# --- telas de rede (host) ----------------------------------------------------
app.mostrar(NetSetupFrame, host=True)
bombear(app)
ns = app._frame
ns.e_porta.delete(0, "end"); ns.e_porta.insert(0, "5610")
ns.cb_papel.current(0)            # host como varejista
ns._ir()
bombear(app)
lobby = app._frame
assert isinstance(lobby, LobbyFrame) and lobby.server is not None
srv = lobby.server

# conecta um cliente de verdade enquanto o lobby está aberto
from client import GameClient
cli = GameClient("127.0.0.1", 5610, "Tester", "atacadista")
import time
bombear_tempo(app, 0.8)
itens = lobby.lista.get_children()
ocupantes = [lobby.lista.item(i)["values"][0] for i in itens]
assert any("Tester" in str(o) for o in ocupantes), ocupantes
print("Lobby OK (cliente remoto apareceu na lista):", ocupantes)

# inicia o jogo: host vira NetBoardFrame e o cliente recebe estado pendente
srv.start_game()
bombear_tempo(app, 0.8)
from gui import NetBoardFrame
nb = app._frame
assert isinstance(nb, NetBoardFrame), type(nb)
assert nb.semana_atual == 1

# host decide semana 1 pela GUI; cliente decide via socket
nb.painel.entrada.set(4)
nb._confirmar(nb.painel)
msgs = []
t0 = time.time()
decidiu = False
while time.time() - t0 < 5:
    bombear_tempo(app, 0.15)
    while not cli.ui_queue.empty():
        m = cli.ui_queue.get_nowait()
        msgs.append(m.get("tipo"))
        if m.get("tipo") == "estado_semana" and m.get("pendente") and not decidiu:
            cli.send_decisao(m["view"]["semana"], 4)
            decidiu = True
    if "semana_fechada" in msgs:
        break
assert "semana_fechada" in msgs, msgs
bombear_tempo(app, 0.6)
assert nb.semana_atual == 2, nb.semana_atual
# o tabuleiro de rede tem o fluxo animado do próprio elo, alimentado por views
assert nb.fluxo is not None
assert nb._view_atual is not None and nb._view_atual["semana"] == 2
assert "ship_pipe" in nb._view_atual and "order_pipe" in nb._view_atual
print("Tabuleiro em rede OK (semana 1 fechada, host avançou para a semana 2, "
      "fluxo do elo animado)")

cli.close()
srv.shutdown()

# --- controle de tamanho de fonte (A- / A+) ---------------------------------
import theme as _theme
app.mostrar(MenuFrame)
bombear(app)
base = _theme.escala()
assert _theme.mudar_escala(app, +1) is True
bombear(app)
assert _theme.escala() > base, (_theme.escala(), base)
# texto cresce de fato
assert _theme.fontes()["num"][1] > _theme._TAM_BASE["num"]
# vai até o teto e satura
for _ in range(10):
    _theme.mudar_escala(app, +1)
bombear(app)
assert _theme.pode_aumentar() is False
assert _theme.mudar_escala(app, +1) is False
# volta ao 100%
while _theme.pode_diminuir() and abs(_theme.escala() - 1.0) > 1e-6:
    _theme.mudar_escala(app, -1)
bombear(app)
print(f"Controle de fonte OK (escala mín/máx; atual {round(_theme.escala()*100)}%)")

app._fechar()
print("OK — GUI validada sob Xvfb.")
