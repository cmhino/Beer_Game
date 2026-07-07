# -*- coding: utf-8 -*-
"""Valida os três modelos de IA: nomes, execução e comportamento esperado."""
from engine import GameEngine, GameConfig, ROLES
from ai_player import (make_ai_players, MODELOS, MODELO_LABEL, MODELO_RESUMO,
                       EQUILIBRADO, ENXUTO, CAUTELOSO)

assert MODELOS == [EQUILIBRADO, ENXUTO, CAUTELOSO]
for m in MODELOS:
    assert m in MODELO_LABEL and m in MODELO_RESUMO

def roda(modelo):
    cfg = GameConfig(semanas=36)
    eng = GameEngine(cfg)
    ais = make_ai_players(cfg, {r: modelo for r in ROLES})
    ped = {r: [] for r in ROLES}
    custo_acum = 0
    while not eng.finished():
        v = eng.begin_week()
        dec = {}
        for r in ROLES:
            ais[r].observe(v[r]); dec[r] = ais[r].decide(v[r]); ped[r].append(dec[r])
        eng.complete_week(dec, {r: "ia" for r in ROLES})
    fab_max = max(ped["fabrica"])
    return fab_max

amp = {m: roda(m) for m in MODELOS}
print("Pico de pedido da fábrica (efeito chicote) por modelo:")
for m in MODELOS:
    print(f"  {MODELO_LABEL[m]:20s}: {amp[m]}")

# Cauteloso deve ter MENOS chicote que o Equilibrado; Enxuto também menos.
assert amp[CAUTELOSO] < amp[EQUILIBRADO], (amp[CAUTELOSO], amp[EQUILIBRADO])
assert amp[ENXUTO] < amp[EQUILIBRADO], (amp[ENXUTO], amp[EQUILIBRADO])

# modelos mistos por elo
cfg = GameConfig(semanas=12)
eng = GameEngine(cfg)
mix = {"varejista": ENXUTO, "atacadista": CAUTELOSO,
       "distribuidor": EQUILIBRADO, "fabrica": ENXUTO}
ais = make_ai_players(cfg, mix)
for r in ROLES:
    assert ais[r].modelo == mix[r]
while not eng.finished():
    v = eng.begin_week()
    for r in ROLES:
        ais[r].observe(v[r])
    eng.complete_week({r: ais[r].decide(v[r]) for r in ROLES},
                      {r: "ia" for r in ROLES})

# config carrega modelos_ia via to_dict/from_dict (rede)
cfg2 = GameConfig.from_dict(GameConfig(modelos_ia=mix).to_dict())
assert cfg2.modelos_ia == mix

print("OK — 3 modelos de IA validados (nomes, mistura por elo e serialização).")
