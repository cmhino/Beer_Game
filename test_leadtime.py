# -*- coding: utf-8 -*-
"""Lead times: elos = 2 sem (pedido) + 2 sem (transporte); fábrica = 1 + 2."""
from engine import GameEngine, GameConfig, ROLES

cfg = GameConfig(semanas=8, demanda_inicial=4, demanda_nova=4, semana_mudanca=99)
eng = GameEngine(cfg)
rows = []
while not eng.finished():
    eng.begin_week()
    decis = {r: 4 for r in ROLES}
    if eng.semana == 1:
        decis["varejista"] = 10
        decis["fabrica"] = 10
    rows.append(eng.complete_week(decis, {r: "h" for r in ROLES}))

assert rows[2]["ATA_pedido_recebido"] == 10   # pedido sem.1 chega ao fornecedor na sem.3
assert rows[4]["VAR_recebido"] == 10          # mercadoria entra no estoque na sem.5
assert rows[3]["FAB_recebido"] == 10          # produção da sem.1 entra no estoque na sem.4
print("OK — lead times: elos 2+2=4 semanas; fábrica 1+2=3 semanas.")
