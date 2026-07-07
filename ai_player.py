# -*- coding: utf-8 -*-
"""
Modelos de IA (jogadores automáticos) do Beer Game.

São oferecidos três modelos, com nomes fáceis de entender:

1. "Pedido Equilibrado"  (EQUILIBRADO) — modelo padrão, heurística de Sterman
   (1989). Prevê a demanda por média móvel exponencial e ajusta o pedido para
   levar a posição de estoque a um alvo. Comportamento "humano típico":
   funciona bem, mas pode amplificar o efeito chicote sob choque de demanda.

2. "Reposição Enxuta"    (ENXUTO) — política base-stock de pesquisa operacional.
   Pede de forma disciplinada para repor exatamente a demanda prevista mais a
   lacuna até um nível-alvo dimensionado pelo lead time real. Tende a REDUZIR
   bastante o efeito chicote: é o "jeito certo" de pedir.

3. "Cauteloso"           (CAUTELOSO) — agente anti-chicote. Suaviza fortemente
   os pedidos e considera melhor o estoque em trânsito (o "pipeline") — fator
   que Sterman apontou como a causa central do efeito chicote. Reage devagar e
   evita exageros, ao custo de aceitar um pouco mais de atraso (backlog).

Todos compartilham a mesma previsão de demanda por suavização exponencial e a
mesma interface (observe / decide), de modo que podem ser misturados livremente
entre os elos.
"""
from engine import ROLES

# identificadores e rótulos amigáveis dos modelos
EQUILIBRADO = "equilibrado"
ENXUTO = "enxuto"
CAUTELOSO = "cauteloso"

MODELOS = [EQUILIBRADO, ENXUTO, CAUTELOSO]

MODELO_LABEL = {
    EQUILIBRADO: "Pedido Equilibrado",
    ENXUTO: "Reposição Enxuta",
    CAUTELOSO: "Cauteloso",
}

MODELO_RESUMO = {
    EQUILIBRADO: "Padrão. Imita o jogador humano típico: prevê a demanda e "
                 "ajusta o estoque a um alvo. Bom desempenho, mas pode "
                 "amplificar o efeito chicote.",
    ENXUTO: "Disciplinado (base-stock). Repõe só o necessário conforme o lead "
            "time real. Costuma reduzir bastante o efeito chicote.",
    CAUTELOSO: "Conservador (anti-chicote). Suaviza os pedidos e leva melhor "
               "em conta o que já está a caminho. Reage devagar e evita "
               "exageros.",
}

# cobertura-base (em semanas de demanda) por papel — calibrada para que, com a
# demanda inicial constante, o sistema fique estacionário até o choque.
COBERTURA = {"varejista": 5, "atacadista": 5, "distribuidor": 5, "fabrica": 4}


class AIPlayer:
    """Jogador IA com modelo selecionável.

    A previsão de demanda (suavização exponencial) é comum a todos os modelos;
    o que muda é a POLÍTICA DE PEDIDO em decide()."""

    def __init__(self, papel: str, config, modelo: str = EQUILIBRADO):
        self.papel = papel
        self.cfg = config
        self.modelo = modelo if modelo in MODELOS else EQUILIBRADO
        self.previsao = float(config.demanda_inicial)
        self._ultimo_pedido = float(config.demanda_inicial)

    # ----------------------------------------------------------- previsão
    def observe(self, view: dict):
        """Atualiza a previsão com o pedido recebido na semana (chamar toda
        semana, mesmo quando um humano controla o elo — permite a IA assumir
        no meio do jogo sem perder o histórico)."""
        d = view["pedido_recebido"]
        self.previsao = self.cfg.theta * d + (1.0 - self.cfg.theta) * self.previsao

    # ------------------------------------------------------------- decisão
    def decide(self, view: dict) -> int:
        f = self.previsao
        estoque_liq = view["estoque"] - view["backlog"]
        em_transito = view["em_transito"]
        pendentes = view["pedidos_pendentes"]

        if self.modelo == ENXUTO:
            q = self._decide_enxuto(f, estoque_liq, em_transito, pendentes)
        elif self.modelo == CAUTELOSO:
            q = self._decide_cauteloso(f, estoque_liq, em_transito, pendentes)
        else:
            q = self._decide_equilibrado(f, estoque_liq, em_transito, pendentes)

        q = max(0, int(q + 0.5))
        self._ultimo_pedido = q
        return q

    # --- 1) Pedido Equilibrado (Sterman padrão) ---------------------------
    def _decide_equilibrado(self, f, estoque_liq, em_transito, pendentes):
        pi = estoque_liq + em_transito + pendentes
        alvo = f * COBERTURA[self.papel] + self.cfg.estoque_seguranca
        return f + self.cfg.alpha * (alvo - pi)

    # --- 2) Reposição Enxuta (base-stock dimensionado pelo lead time) -----
    def _lead_time(self) -> int:
        """Lead time total de reposição em semanas: elos 2 (pedido) + 2
        (transporte) = 4; fábrica 1 (processa) + 2 (produz) = 3."""
        return 3 if self.papel == "fabrica" else 4

    def _decide_enxuto(self, f, estoque_liq, em_transito, pendentes):
        # Política de reposição "order-up-to" desacoplada (estilo APIOBPCS):
        # ajusta SEPARADAMENTE o estoque e o pipeline (em trânsito). Desacoplar
        # o ajuste do pipeline — e fazê-lo de forma suave — é o que mantém a
        # reposição disciplinada e contém o efeito chicote.
        #   q = previsão
        #       + g_inv * (estoque_alvo  − estoque_líquido)
        #       + g_wip * (pipeline_alvo − pipeline_atual)
        lt = self._lead_time()
        # estoque-alvo calibrado para o equilíbrio inicial (cobertura curta);
        # pipeline-alvo = demanda esperada durante o lead time.
        estoque_alvo = f * 2 + self.cfg.estoque_seguranca
        pipeline_alvo = f * lt
        pipeline_atual = em_transito + pendentes
        g_inv, g_wip = 0.25, 0.25
        return (f + g_inv * (estoque_alvo - estoque_liq)
                + g_wip * (pipeline_alvo - pipeline_atual))

    # --- 3) Cauteloso (anti-chicote, com amortecimento) -------------------
    def _decide_cauteloso(self, f, estoque_liq, em_transito, pendentes):
        # Ajustes mais suaves (alpha menor) e MAIOR peso ao pipeline: ao
        # descontar melhor o que já vem a caminho, evita pedir demais —
        # justamente o que combate o efeito chicote.
        alpha = self.cfg.alpha * 0.5
        beta = 1.0                      # considera 100% do estoque em trânsito
        pi = estoque_liq + beta * em_transito + pendentes
        alvo = f * COBERTURA[self.papel] + self.cfg.estoque_seguranca
        bruto = f + alpha * (alvo - pi)
        # amortece variações bruscas em relação ao último pedido (suavização)
        suavizado = 0.6 * bruto + 0.4 * self._ultimo_pedido
        return suavizado


def make_ai_players(config, modelos=None):
    """Cria um jogador IA por elo.

    modelos: opcional, dict {papel: nome_do_modelo}. Papéis ausentes usam o
    modelo padrão (EQUILIBRADO)."""
    modelos = modelos or {}
    return {r: AIPlayer(r, config, modelos.get(r, EQUILIBRADO)) for r in ROLES}
