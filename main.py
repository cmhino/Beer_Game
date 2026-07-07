# -*- coding: utf-8 -*-
"""
Beer Game (CISLOG) — ponto de entrada.

Uso normal (interface gráfica):   python main.py
Simulação rápida sem GUI:         python main.py --sim [semanas]
"""
import sys


def simulacao_cli(semanas=36):
    from engine import GameEngine, GameConfig, ROLES, PREFIX, ROLE_LABEL
    from ai_player import make_ai_players
    from storage import GameTable
    cfg = GameConfig(semanas=semanas)
    eng, ais = GameEngine(cfg), make_ai_players(cfg)
    tab = GameTable(cfg, modo="simulacao", jogadores={r: "IA" for r in ROLES})
    tab.add_rows(eng.setup_rows())
    while not eng.finished():
        views = eng.begin_week()
        decis = {}
        for r in ROLES:
            ais[r].observe(views[r])
            decis[r] = ais[r].decide(views[r])
        tab.add_row(eng.complete_week(decis, {r: "ia" for r in ROLES}))
    caminhos = tab.save_all()
    res = tab.resumo()
    print(f"Simulação de {semanas} semanas concluída. "
          f"Custo total da cadeia: R$ {res['custo_total_cadeia']:.2f}")
    for r in ROLES:
        e = res["elos"][r]
        print(f"  {e['rotulo']:<13} custo R$ {e['custo_total']:>8.2f}   "
              f"pedido máx {e['pedido_max']:>3}   backlog máx {e['backlog_max']:>3}")
    print("Arquivos:", *caminhos, sep="\n  ")


if __name__ == "__main__":
    if "--sim" in sys.argv:
        n = 36
        for a in sys.argv[1:]:
            if a.isdigit():
                n = int(a)
        simulacao_cli(n)
    else:
        from gui import App
        App().mainloop()
