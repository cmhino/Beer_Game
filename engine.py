# -*- coding: utf-8 -*-
"""
Motor do Beer Game (CISLOG) — regras, pipelines e tabela mestre.
Sem dependências externas (somente biblioteca padrão).
"""
from collections import deque
from dataclasses import dataclass, asdict, field
import datetime

ROLES = ["varejista", "atacadista", "distribuidor", "fabrica"]
PREFIX = {"varejista": "VAR", "atacadista": "ATA", "distribuidor": "DIS", "fabrica": "FAB"}
ROLE_LABEL = {
    "varejista": "Varejista",
    "atacadista": "Atacadista",
    "distribuidor": "Distribuidor",
    "fabrica": "Fábrica",
}

# Colunas por elo (ordem fixa do esquema)
NODE_COLS = [
    "pedido_recebido", "recebido", "estoque_inicial", "demanda_total",
    "enviado", "backlog", "estoque_final", "pedido_colocado",
    "transp_slot1", "transp_slot2", "info_slot1", "info_slot2",
    "posicao_estoque", "custo_semana", "custo_acum", "controlador",
]
GLOBAL_COLS = ["semana", "fase", "demanda_cliente", "timestamp", "custo_total_cadeia"]


def build_columns():
    """Lista completa das 69 colunas da tabela mestre, na ordem do esquema."""
    cols = list(GLOBAL_COLS)
    for r in ROLES:
        p = PREFIX[r]
        cols += [f"{p}_{c}" for c in NODE_COLS]
    return cols


@dataclass
class GameConfig:
    semanas: int = 36
    custo_estoque: float = 0.50
    custo_backlog: float = 1.00
    demanda_inicial: int = 4
    demanda_nova: int = 8
    semana_mudanca: int = 5
    estoque_inicial: int = 12
    pipeline_inicial: int = 4
    # parâmetros da IA
    theta: float = 0.30          # suavização exponencial da previsão
    alpha: float = 0.30          # velocidade de correção do estoque
    estoque_seguranca: int = 4
    # modelo de IA por elo (vazio = "equilibrado" para todos). Ex.:
    # {"varejista": "enxuto", "fabrica": "cauteloso"}
    modelos_ia: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        base = cls()
        for k, v in (d or {}).items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base


class GameEngine:
    """
    Sequência semanal (executada em duas fases):
      Fase A (begin_week): receber entregas, receber pedidos, atender demanda,
                           calcular custos, despachar ao elo de jusante.
      Fase B (complete_week): aplicar as decisões de pedido dos 4 elos,
                              avançar pipelines de informação/produção e
                              registrar a linha da semana na tabela.
    """

    def __init__(self, config: GameConfig):
        self.cfg = config
        p = config.pipeline_inicial
        self.semana = 0
        self.estoque = [config.estoque_inicial] * 4
        self.backlog = [0] * 4
        self.custo_acum = [0.0] * 4
        # ship_in[i]: cargas a caminho do elo i (2 slots de transporte).
        # Para a fábrica (i=3) são 3 slots: 1 semana de processamento do
        # pedido + 2 semanas de produção (pedido em t entra no estoque em t+3).
        self.ship_in = [deque([p, p]) for _ in range(3)] + [deque([p, p, p])]
        # order_in[i]: pedidos a caminho do elo i, colocados pelo elo i-1 (2 slots). i = 1..3
        self.order_in = [None] + [deque([p, p]) for _ in range(3)]
        self._fase_a = None  # dados intermediários entre as fases

    # ------------------------------------------------------------------ utils
    def demanda_cliente(self, semana: int) -> int:
        if semana < self.cfg.semana_mudanca:
            return self.cfg.demanda_inicial
        return self.cfg.demanda_nova

    def finished(self) -> bool:
        return self.semana >= self.cfg.semanas

    @property
    def aguardando_decisoes(self) -> bool:
        """True entre begin_week() e complete_week()."""
        return self._fase_a is not None

    def snapshot(self) -> dict:
        """Foto do estado para o diagrama da cadeia."""
        return {
            "semana": self.semana,
            "estoque": list(self.estoque),
            "backlog": list(self.backlog),
            "ship_in": [list(d) for d in self.ship_in],
            "order_in": [list(self.order_in[i]) for i in range(1, 4)],
            "demanda": self.demanda_cliente(max(1, self.semana)),
            "enviado": (list(self._fase_a["enviado"]) if self._fase_a
                        else [0, 0, 0, 0]),
        }

    # ------------------------------------------------------------ setup rows
    def setup_rows(self):
        """Linhas das semanas -3 a 0: regime estacionário que preenche os pipelines."""
        cfg = self.cfg
        p = cfg.pipeline_inicial
        rows = []
        for t in range(-3, 1):
            row = {
                "semana": t, "fase": "setup",
                "demanda_cliente": cfg.demanda_inicial,
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "custo_total_cadeia": 0.0,
            }
            for r in ROLES:
                pf = PREFIX[r]
                fab = (r == "fabrica")
                row.update({
                    f"{pf}_pedido_recebido": p,
                    f"{pf}_recebido": p,
                    f"{pf}_estoque_inicial": cfg.estoque_inicial + p,
                    f"{pf}_demanda_total": p,
                    f"{pf}_enviado": p,
                    f"{pf}_backlog": 0,
                    f"{pf}_estoque_final": cfg.estoque_inicial,
                    f"{pf}_pedido_colocado": p,
                    f"{pf}_transp_slot1": p,
                    f"{pf}_transp_slot2": p,
                    f"{pf}_info_slot1": 0 if fab else p,
                    f"{pf}_info_slot2": p,
                    f"{pf}_posicao_estoque": cfg.estoque_inicial + (3 * p if fab else 4 * p),
                    f"{pf}_custo_semana": 0.0,
                    f"{pf}_custo_acum": 0.0,
                    f"{pf}_controlador": "setup",
                })
            rows.append(row)
        return rows

    # --------------------------------------------------------------- fase A
    def begin_week(self):
        """Executa recebimentos, atendimento e custos. Retorna a visão de cada elo."""
        assert self._fase_a is None, "complete_week() não foi chamado para a semana anterior"
        self.semana += 1
        t = self.semana
        cfg = self.cfg

        # 1) todos os POPs antes de qualquer APPEND (simultaneidade)
        recebido = [self.ship_in[i].popleft() for i in range(4)]
        pedido_recebido = [0] * 4
        pedido_recebido[0] = self.demanda_cliente(t)          # cliente -> varejista (sem atraso)
        for i in range(1, 4):
            pedido_recebido[i] = self.order_in[i].popleft()   # pedido colocado há 2 semanas

        estoque_inicial, demanda_total, enviado = [0] * 4, [0] * 4, [0] * 4
        custo_semana = [0.0] * 4
        for i in range(4):
            self.estoque[i] += recebido[i]
            estoque_inicial[i] = self.estoque[i]
            demanda_total[i] = pedido_recebido[i] + self.backlog[i]
            enviado[i] = min(demanda_total[i], self.estoque[i])
            self.estoque[i] -= enviado[i]
            self.backlog[i] = demanda_total[i] - enviado[i]
            custo_semana[i] = (cfg.custo_estoque * self.estoque[i]
                               + cfg.custo_backlog * self.backlog[i])
            self.custo_acum[i] += custo_semana[i]

        # despachos desta semana entram no pipeline de transporte do elo de jusante
        for i in range(1, 4):
            self.ship_in[i - 1].append(enviado[i])
        # o envio do varejista (i=0) sai do sistema (vai ao consumidor)

        self._fase_a = dict(t=t, recebido=recebido, pedido_recebido=pedido_recebido,
                            estoque_inicial=estoque_inicial, demanda_total=demanda_total,
                            enviado=enviado, custo_semana=custo_semana)

        # visões individuais (informação limitada: cada elo só vê o que é seu)
        views = {}
        for i, r in enumerate(ROLES):
            pendentes = sum(self.order_in[i + 1]) if i < 3 else 0
            # pipelines do próprio elo (para animar o segmento em rede):
            # transporte que está chegando a este elo e pedidos que ele já
            # colocou e ainda estão a caminho do fornecedor.
            ship_pipe = list(self.ship_in[i])
            order_pipe = (list(self.order_in[i + 1]) if i < 3
                          else list(self.ship_in[3]))   # fábrica: fila de produção
            views[r] = {
                "semana": t,
                "papel": r,
                "pedido_recebido": pedido_recebido[i],
                "recebido": recebido[i],
                "estoque": self.estoque[i],
                "backlog": self.backlog[i],
                "enviado": enviado[i],
                "em_transito": sum(self.ship_in[i]),
                "pedidos_pendentes": pendentes,
                "ship_pipe": ship_pipe,
                "order_pipe": order_pipe,
                "eh_fabrica": (i == 3),
                "custo_semana": round(custo_semana[i], 2),
                "custo_acum": round(self.custo_acum[i], 2),
            }
        return views

    # --------------------------------------------------------------- fase B
    def complete_week(self, decisions: dict, controladores: dict = None):
        """Aplica os pedidos decididos e devolve a linha completa da semana."""
        assert self._fase_a is not None, "begin_week() deve ser chamado antes"
        fa = self._fase_a
        controladores = controladores or {r: "humano" for r in ROLES}
        pedido = [max(0, int(decisions[r])) for r in ROLES]

        # pedidos entram no pipeline de informação do fornecedor;
        # o pedido da fábrica entra direto na sua fila de produção
        for i in range(3):
            self.order_in[i + 1].append(pedido[i])
        self.ship_in[3].append(pedido[3])

        row = {
            "semana": fa["t"], "fase": "jogo",
            "demanda_cliente": self.demanda_cliente(fa["t"]),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "custo_total_cadeia": round(sum(self.custo_acum), 2),
        }
        for i, r in enumerate(ROLES):
            pf = PREFIX[r]
            ship = list(self.ship_in[i])          # [chega na próxima semana, chega em 2 semanas, ...]
            if i < 3:
                info = list(self.order_in[i + 1])  # pedidos deste elo a caminho do fornecedor
                info_s1, info_s2 = info[1], info[0]
            else:
                info = []                          # fábrica: pedido em processamento (1ª semana)
                info_s1, info_s2 = 0, ship[2]
            posicao = (self.estoque[i] - self.backlog[i] + sum(ship) + sum(info))
            row.update({
                f"{pf}_pedido_recebido": fa["pedido_recebido"][i],
                f"{pf}_recebido": fa["recebido"][i],
                f"{pf}_estoque_inicial": fa["estoque_inicial"][i],
                f"{pf}_demanda_total": fa["demanda_total"][i],
                f"{pf}_enviado": fa["enviado"][i],
                f"{pf}_backlog": self.backlog[i],
                f"{pf}_estoque_final": self.estoque[i],
                f"{pf}_pedido_colocado": pedido[i],
                f"{pf}_transp_slot1": ship[1],
                f"{pf}_transp_slot2": ship[0],
                f"{pf}_info_slot1": info_s1,
                f"{pf}_info_slot2": info_s2,
                f"{pf}_posicao_estoque": posicao,
                f"{pf}_custo_semana": round(fa["custo_semana"][i], 2),
                f"{pf}_custo_acum": round(self.custo_acum[i], 2),
                f"{pf}_controlador": controladores.get(r, "humano"),
            })
        self._fase_a = None
        return row
