# -*- coding: utf-8 -*-
"""Teste rápido do motor + IA + armazenagem (sem GUI, sem rede)."""
from engine import GameEngine, GameConfig, ROLES, PREFIX, build_columns
from ai_player import make_ai_players
from storage import GameTable

cfg = GameConfig(semanas=36)
eng = GameEngine(cfg)
ais = make_ai_players(cfg)
tab = GameTable(cfg, modo="teste", jogadores={r: "IA" for r in ROLES})
tab.add_rows(eng.setup_rows())

assert len(build_columns()) == 69, f"esquema com {len(build_columns())} colunas (esperado 69)"

while not eng.finished():
    views = eng.begin_week()
    decis, ctrl = {}, {}
    for r in ROLES:
        ais[r].observe(views[r])
        decis[r] = ais[r].decide(views[r])
        ctrl[r] = "ia"
    tab.add_row(eng.complete_week(decis, ctrl))

# --- verificações -----------------------------------------------------------
jogo = [r for r in tab.rows if r["fase"] == "jogo"]
setup = [r for r in tab.rows if r["fase"] == "setup"]
assert [r["semana"] for r in setup] == [-3, -2, -1, 0]
assert jogo[0]["semana"] == 1 and jogo[-1]["semana"] == 36

# 1) regime estacionário antes do choque (semanas 1-4): pedidos = 4, estoque = 12
for r in jogo[:4]:
    for papel in ROLES:
        p = PREFIX[papel]
        assert r[f"{p}_pedido_colocado"] == 4, (r["semana"], papel, r[f"{p}_pedido_colocado"])
        assert r[f"{p}_estoque_final"] == 12
        assert r[f"{p}_backlog"] == 0
        assert r[f"{p}_custo_semana"] == 6.0

# 2) efeito chicote: amplitude dos pedidos cresce a montante
amp = {}
for papel in ROLES:
    p = PREFIX[papel]
    vals = [r[f"{p}_pedido_colocado"] for r in jogo]
    amp[papel] = max(vals) - min(vals)
print("Amplitude dos pedidos por elo:", amp)
assert amp["fabrica"] >= amp["varejista"], "esperava amplificação a montante"

# 3) conservação: nada negativo
for r in jogo:
    for papel in ROLES:
        p = PREFIX[papel]
        assert r[f"{p}_estoque_final"] >= 0 and r[f"{p}_backlog"] >= 0

# 4) custo total = soma dos elos
ult = jogo[-1]
soma = round(sum(ult[f"{PREFIX[p]}_custo_acum"] for p in ROLES), 2)
assert abs(soma - ult["custo_total_cadeia"]) < 0.01

caminhos = tab.save_all(pasta="/tmp/partidas_teste")
print("Arquivos gravados:", caminhos)
print("Custo total da cadeia:", ult["custo_total_cadeia"])
res = tab.resumo()
for papel, e in res["elos"].items():
    print(f"  {e['rotulo']:<13} custo={e['custo_total']:>8.2f}  "
          f"pedido_max={e['pedido_max']:>3}  backlog_max={e['backlog_max']:>3}")
print("OK — motor validado.")
