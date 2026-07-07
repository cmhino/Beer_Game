# -*- coding: utf-8 -*-
"""
Armazenagem da tabela mestre da partida.
- SQLite (canônico, legível por máquina)  -> partidas/<nome>.db
- CSV separado por ';' com decimais ','   -> partidas/<nome>.csv  (amigável ao Excel pt-BR)
- XLSX (se openpyxl estiver instalado)    -> partidas/<nome>.xlsx
"""
import csv
import json
import os
import sqlite3
import datetime

from engine import ROLES, PREFIX, ROLE_LABEL, build_columns

PASTA_PADRAO = "partidas"


def _tipo_sql(col: str) -> str:
    if col == "timestamp" or col.endswith("_controlador") or col == "fase":
        return "TEXT"
    if "custo" in col:
        return "REAL"
    return "INTEGER"


class GameTable:
    def __init__(self, config, modo: str = "individual", jogadores: dict = None):
        self.columns = build_columns()
        self.rows = []
        self.config = config
        self.modo = modo
        self.jogadores = jogadores or {}
        self.criada_em = datetime.datetime.now()

    # ------------------------------------------------------------------ rows
    def add_row(self, row: dict):
        self.rows.append({c: row.get(c) for c in self.columns})

    def add_rows(self, rows):
        for r in rows:
            self.add_row(r)

    # ---------------------------------------------------------------- resumo
    def resumo(self) -> dict:
        jogo = [r for r in self.rows if r["fase"] == "jogo"]
        res = {"semanas_jogadas": len(jogo), "custo_total_cadeia": 0.0, "elos": {}}
        if not jogo:
            return res
        ultima = jogo[-1]
        res["custo_total_cadeia"] = ultima["custo_total_cadeia"]
        for r in ROLES:
            p = PREFIX[r]
            res["elos"][r] = {
                "rotulo": ROLE_LABEL[r],
                "custo_total": ultima[f"{p}_custo_acum"],
                "backlog_max": max(x[f"{p}_backlog"] for x in jogo),
                "estoque_max": max(x[f"{p}_estoque_final"] for x in jogo),
                "pedido_max": max(x[f"{p}_pedido_colocado"] for x in jogo),
                "pedido_min": min(x[f"{p}_pedido_colocado"] for x in jogo),
            }
        return res

    # ------------------------------------------------------------ persistir
    def save_all(self, pasta: str = PASTA_PADRAO, nome: str = None):
        """Grava db + csv (+ xlsx se possível). Retorna a lista de caminhos gerados."""
        os.makedirs(pasta, exist_ok=True)
        nome = nome or self.criada_em.strftime("beergame_%Y%m%d_%H%M%S")
        caminhos = []
        caminhos.append(self._save_sqlite(os.path.join(pasta, nome + ".db")))
        caminhos.append(self._save_csv(os.path.join(pasta, nome + ".csv")))
        x = self._save_xlsx(os.path.join(pasta, nome + ".xlsx"))
        if x:
            caminhos.append(x)
        return caminhos

    def _save_sqlite(self, caminho: str):
        if os.path.exists(caminho):
            os.remove(caminho)
        con = sqlite3.connect(caminho)
        cur = con.cursor()
        cols_sql = ", ".join(f'"{c}" {_tipo_sql(c)}' for c in self.columns)
        cur.execute(f"CREATE TABLE semanas ({cols_sql})")
        cur.execute("CREATE TABLE partida (criada_em TEXT, modo TEXT, jogadores TEXT, config TEXT)")
        cur.execute("INSERT INTO partida VALUES (?,?,?,?)", (
            self.criada_em.isoformat(timespec="seconds"), self.modo,
            json.dumps(self.jogadores, ensure_ascii=False),
            json.dumps(self.config.to_dict(), ensure_ascii=False)))
        marks = ",".join("?" * len(self.columns))
        cur.executemany(
            f"INSERT INTO semanas VALUES ({marks})",
            [tuple(r[c] for c in self.columns) for r in self.rows])
        con.commit()
        con.close()
        return caminho

    def _fmt_csv(self, v):
        if isinstance(v, float):
            return f"{v:.2f}".replace(".", ",")   # decimal pt-BR
        return v

    def _save_csv(self, caminho: str):
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(self.columns)
            for r in self.rows:
                w.writerow([self._fmt_csv(r[c]) for c in self.columns])
        return caminho

    def _save_xlsx(self, caminho: str):
        try:
            from openpyxl import Workbook
        except ImportError:
            return None
        wb = Workbook()
        ws = wb.active
        ws.title = "semanas"
        ws.append(self.columns)
        for r in self.rows:
            ws.append([r[c] for c in self.columns])
        res = self.resumo()
        ws2 = wb.create_sheet("resumo")
        ws2.append(["Elo", "Custo total (R$)", "Backlog máx.", "Estoque máx.",
                    "Pedido máx.", "Pedido mín."])
        for r in ROLES:
            e = res["elos"].get(r)
            if e:
                ws2.append([e["rotulo"], e["custo_total"], e["backlog_max"],
                            e["estoque_max"], e["pedido_max"], e["pedido_min"]])
        ws2.append([])
        ws2.append(["Custo total da cadeia", res["custo_total_cadeia"]])
        wb.save(caminho)
        return caminho
