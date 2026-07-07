# -*- coding: utf-8 -*-
"""Widgets visuais: cartão do elo, gráficos, diagrama animado da cadeia,
linha de progresso da partida e relatório final com pódio."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from engine import ROLES, PREFIX, ROLE_LABEL

CORES = {"varejista": "#1f77b4", "atacadista": "#2ca02c",
         "distribuidor": "#ff7f0e", "fabrica": "#d62728"}


def _ponto_na_poligonal(pts, frac):
    """Interpola um ponto ao longo de uma poligonal (lista de (x, y)),
    proporcional ao comprimento de cada trecho. frac ∈ [0, 1]."""
    if not pts:
        return (0, 0)
    if len(pts) == 1:
        return pts[0]
    segs = []
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        segs.append((a, b, d))
        total += d
    if total <= 0:
        return pts[-1]
    alvo = frac * total
    acum = 0.0
    for a, b, d in segs:
        if acum + d >= alvo or d == 0:
            t = 0 if d == 0 else (alvo - acum) / d
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acum += d
    return pts[-1]


# ============================================================== linha do tempo
class ProgressTimeline(tk.Canvas):
    """Barra de progresso da partida com marcador da semana do choque."""

    def __init__(self, master, height=34, **kw):
        super().__init__(master, height=height, highlightthickness=0, **kw)
        self._dados = None
        theme.registrar(self, self._redesenha)
        self.bind("<Configure>", lambda e: self._redesenha())

    def set(self, semana, total, choque=None):
        self._dados = (semana, total, choque)
        self._redesenha()

    def _redesenha(self):
        c = theme.cores()
        self.configure(bg=c["bg"])
        self.delete("all")
        if not self._dados:
            return
        semana, total, choque = self._dados
        w = max(self.winfo_width(), 200)
        h = int(self["height"])
        x0, x1, y0, y1 = 4, w - 4, 12, h - 4
        self.create_rectangle(x0, y0, x1, y1, fill=c["card"],
                              outline=c["borda"], width=1)
        frac = min(1.0, max(0.0, semana / max(1, total)))
        if frac > 0:
            self.create_rectangle(x0 + 1, y0 + 1, x0 + 1 + (x1 - x0 - 2) * frac,
                                  y1 - 1, fill=c["accent"], outline="")
        if choque and 1 <= choque <= total:
            xc = x0 + (x1 - x0) * (choque - 0.5) / total
            self.create_line(xc, y0 - 4, xc, y1, fill=c["perigo"],
                             width=2, dash=(3, 2))
            self.create_text(xc + 4, 1, text="⚡ choque", anchor="nw",
                             font=theme.fontes()["mini"], fill=c["perigo"])
        self.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                         text=f"Semana {semana} de {total}",
                         font=theme.fontes()["rotulo_b"], fill=c["texto"])


# ================================================================ mini gráfico
class MiniChart(tk.Canvas):
    """Gráfico de linhas com tooltip, marcador do choque e sombra de backlog."""

    def __init__(self, master, width=520, height=220, titulo="",
                 shade_negativo=False, **kw):
        super().__init__(master, width=width, height=height,
                         highlightthickness=1, **kw)
        self.titulo = titulo
        self.shade_negativo = shade_negativo
        self.m_esq, self.m_dir, self.m_top, self.m_inf = 46, 12, 44, 24
        self._dados = None
        self._geom = None      # (X(), Y(), n, x0) para o tooltip
        theme.registrar(self, self._redesenha)
        self.bind("<Configure>", lambda e: self._redesenha())
        self.bind("<Motion>", self._tooltip)
        self.bind("<Leave>", lambda e: self.delete("tip"))

    def plot(self, series, x0=1, choque=None):
        """series: lista de (rotulo, cor, [valores])."""
        self._dados = (series, x0, choque)
        self._redesenha()

    def _redesenha(self):
        c = theme.cores()
        self.configure(bg=c["canvas"], highlightbackground=c["borda"])
        self.delete("all")
        w = max(self.winfo_width(), int(self["width"]))
        h = max(self.winfo_height(), int(self["height"]))
        if self.titulo:
            self.create_text(w / 2, 13, text=self.titulo,
                             font=theme.fontes()["rotulo_b"], fill=c["texto"])
        if not self._dados:
            self._geom = None
            return
        series, x0, choque = self._dados
        dados = [v for _, _, vs in series for v in vs if v is not None]
        if not dados:
            self._geom = None
            return
        n = max(len(vs) for _, _, vs in series)
        y_min, y_max = min(0, min(dados)), max(dados)
        if y_max == y_min:
            y_max = y_min + 1
        gx0, gy0 = self.m_esq, h - self.m_inf
        gx1, gy1 = w - self.m_dir, self.m_top

        def X(i):
            return gx0 if n <= 1 else gx0 + (gx1 - gx0) * i / (n - 1)

        def Y(v):
            return gy0 - (gy0 - gy1) * (v - y_min) / (y_max - y_min)

        # sombra da região negativa (backlog)
        if self.shade_negativo and y_min < 0:
            self.create_rectangle(gx0, Y(0), gx1, gy0, fill=c["sombra_neg"],
                                  outline="")
        # grade e eixos
        for frac in (0.0, 0.5, 1.0):
            v = y_min + frac * (y_max - y_min)
            y = Y(v)
            self.create_line(gx0, y, gx1, y, fill=c["grade"])
            self.create_text(gx0 - 6, y, text=f"{v:.0f}", anchor="e",
                             font=theme.fontes()["mini"], fill=c["suave"])
        self.create_line(gx0, gy0, gx1, gy0, fill=c["eixo"])
        self.create_line(gx0, gy0, gx0, gy1, fill=c["eixo"])
        if y_min < 0:
            self.create_line(gx0, Y(0), gx1, Y(0), fill=c["eixo"], dash=(2, 2))
        for i in range(0, n, max(1, n // 8)):
            self.create_text(X(i), gy0 + 11, text=str(x0 + i),
                             font=theme.fontes()["mini"], fill=c["suave"])
        # marcador da semana do choque de demanda
        if choque is not None and x0 <= choque <= x0 + n - 1:
            xc = X(choque - x0)
            self.create_line(xc, gy0, xc, gy1, fill=c["perigo"],
                             width=1, dash=(4, 3))
            self.create_text(xc + 3, gy1 + 2, text="⚡ choque", anchor="nw",
                             font=theme.fontes()["mini"], fill=c["perigo"])
        # séries
        for rotulo, cor, vs in series:
            pts = [(X(i), Y(v)) for i, v in enumerate(vs) if v is not None]
            if len(pts) >= 2:
                self.create_line(*[k for p in pts for k in p], fill=cor, width=2)
            for x, y in pts[-1:]:
                self.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5,
                                 fill=cor, outline=cor)
        # legenda
        lx = gx0 + 6
        for rotulo, cor, _ in series:
            self.create_rectangle(lx, gy1 - 14, lx + 10, gy1 - 4,
                                  fill=cor, outline=cor)
            t = self.create_text(lx + 14, gy1 - 9, text=rotulo, anchor="w",
                                 font=theme.fontes()["mini"], fill=c["texto"])
            lx = self.bbox(t)[2] + 14
        self._geom = (X, Y, n, x0, gx0, gx1, gy0, gy1)

    def _tooltip(self, ev):
        self.delete("tip")
        if not self._geom or not self._dados:
            return
        X, Y, n, x0, gx0, gx1, gy0, gy1 = self._geom
        if not (gx0 - 6 <= ev.x <= gx1 + 6 and gy1 <= ev.y <= gy0):
            return
        c = theme.cores()
        passo = (gx1 - gx0) / max(1, n - 1)
        i = max(0, min(n - 1, round((ev.x - gx0) / max(1e-9, passo))))
        xi = X(i)
        self.create_line(xi, gy0, xi, gy1, fill=c["suave"], dash=(2, 2),
                         tags="tip")
        series = self._dados[0]
        linhas = [f"Semana {x0 + i}"]
        for rotulo, _, vs in series:
            if i < len(vs) and vs[i] is not None:
                v = vs[i]
                txt = f"{v:.1f}".rstrip("0").rstrip(".") if isinstance(v, float) \
                    else str(v)
                linhas.append(f"{rotulo}: {txt}")
        texto = "\n".join(linhas)
        tx = xi + 10 if xi < (gx0 + gx1) / 2 else xi - 10
        anchor = "nw" if xi < (gx0 + gx1) / 2 else "ne"
        tid = self.create_text(tx, gy1 + 6, text=texto, anchor=anchor,
                               font=theme.fontes()["mini"], fill=c["texto"],
                               tags="tip")
        bb = self.bbox(tid)
        self.create_rectangle(bb[0] - 4, bb[1] - 3, bb[2] + 4, bb[3] + 3,
                              fill=c["card"], outline=c["borda"], tags="tip")
        self.tag_raise(tid)


# ============================================================== cartão do elo
class NodePanel(tk.Frame):
    """Cartão do elo com faixa colorida, indicadores em destaque (semáforo)
    e, opcionalmente, o campo de pedido."""

    LINHAS = [("pedido_recebido", "Pedido recebido"),
              ("recebido", "Entrega recebida"),
              ("enviado", "Enviado"),
              ("em_transito", "Em trânsito p/ você"),
              ("custo_semana", "Custo da semana"),
              ("custo_acum", "Custo acumulado")]

    def __init__(self, master, papel, com_entrada=False, ao_confirmar=None, **kw):
        super().__init__(master, bd=0, highlightthickness=0, **kw)
        self.papel = papel
        self.com_entrada = com_entrada
        self.ao_confirmar = ao_confirmar
        self.status = tk.StringVar(value="")
        self._view = {}
        self._habilitado = True
        self._valor_pedido = "4"
        self.entrada = None
        self.botao = None
        self._montar()
        theme.registrar(self, self._retema)

    # ----------------------------------------------------------- construção
    def _montar(self):
        c, f = theme.cores(), theme.fontes()
        cor = CORES[self.papel]
        self.configure(bg=cor)
        self._miolo = tk.Frame(self, bg=c["card"])
        self._miolo.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        tk.Label(self, text=ROLE_LABEL[self.papel].upper(), bg=cor, fg="white",
                 font=f["h2"], pady=3).pack(fill="x", side="top", before=self._miolo)

        # indicadores grandes com semáforo
        grandes = tk.Frame(self._miolo, bg=c["card"])
        grandes.pack(fill="x", pady=(6, 2))
        self._lbl_num = {}
        for col, (chave, rotulo) in enumerate([("estoque", "ESTOQUE"),
                                               ("backlog", "BACKLOG")]):
            cel = tk.Frame(grandes, bg=c["card"])
            cel.grid(row=0, column=col, sticky="nsew")
            grandes.grid_columnconfigure(col, weight=1)
            tk.Label(cel, text=rotulo, bg=c["card"], fg=c["suave"],
                     font=f["mini"]).pack()
            lbl = tk.Label(cel, text="—", bg=c["card"], fg=c["texto"],
                           font=f["num"])
            lbl.pack()
            self._lbl_num[chave] = lbl

        # linhas compactas (2 colunas)
        corpo = tk.Frame(self._miolo, bg=c["card"])
        corpo.pack(fill="x", padx=8)
        self._lbl_val = {}
        for i, (chave, rotulo) in enumerate(self.LINHAS):
            r, base = divmod(i, 2)
            tk.Label(corpo, text=rotulo + ":", bg=c["card"], fg=c["suave"],
                     font=f["mini"], anchor="w")\
              .grid(row=r, column=base * 2, sticky="w", pady=1)
            lbl = tk.Label(corpo, text="—", bg=c["card"], fg=c["texto"],
                           font=f["rotulo_b"], anchor="e")
            lbl.grid(row=r, column=base * 2 + 1, sticky="e", padx=(4, 12), pady=1)
            self._lbl_val[chave] = lbl
        for col in (1, 3):
            corpo.grid_columnconfigure(col, weight=1)

        if self.com_entrada:
            fr = tk.Frame(self._miolo, bg=c["card"])
            fr.pack(pady=(6, 2))
            tk.Label(fr, text="Seu pedido:", bg=c["card"], fg=c["texto"],
                     font=f["rotulo_b"]).pack(side="left", padx=(0, 4))
            self.entrada = ttk.Spinbox(fr, from_=0, to=999, width=6)
            self.entrada.set(self._valor_pedido)
            self.entrada.pack(side="left")
            if self.ao_confirmar:
                self.botao = ttk.Button(fr, text="Confirmar", style="Accent.TButton",
                                        command=lambda: self.ao_confirmar(self))
                self.botao.pack(side="left", padx=(8, 0))
            self.habilitar(self._habilitado)
        else:
            self.entrada = None
            self.botao = None

        tk.Label(self._miolo, textvariable=self.status, bg=c["card"],
                 fg=c["alerta"], font=f["mini"]).pack(pady=(0, 4))
        if self._view:
            self.update_view(self._view)

    def _retema(self):
        if self.entrada is not None:
            try:
                self._valor_pedido = self.entrada.get()
            except tk.TclError:
                pass
        for w in self.winfo_children():
            w.destroy()
        self._montar()

    # ------------------------------------------------------------- conteúdo
    @staticmethod
    def _fmt(v):
        if isinstance(v, float):
            return f"{v:.2f}".replace(".", ",")
        return "—" if v is None else str(v)

    def update_view(self, view: dict):
        self._view = view
        c = theme.cores()
        est, bl = view.get("estoque"), view.get("backlog")
        self._lbl_num["estoque"].config(text=self._fmt(est))
        self._lbl_num["backlog"].config(text=self._fmt(bl))
        if est is not None:
            cor_e = c["perigo"] if est == 0 else (c["alerta"] if est <= 4
                                                  else c["ok"])
            self._lbl_num["estoque"].config(fg=cor_e)
        if bl is not None:
            cor_b = c["ok"] if bl == 0 else (c["alerta"] if bl < 10
                                             else c["perigo"])
            self._lbl_num["backlog"].config(fg=cor_b)
        for chave, lbl in self._lbl_val.items():
            v = view.get(chave)
            pre = "R$ " if "custo" in chave and v is not None else ""
            lbl.config(text=pre + self._fmt(v))

    def ler_pedido(self):
        try:
            return max(0, int(self.entrada.get()))
        except (TypeError, ValueError, tk.TclError):
            return None

    def habilitar(self, sim: bool):
        self._habilitado = sim
        estado = "normal" if sim else "disabled"
        if self.entrada is not None:
            self.entrada.configure(state=estado)
        if self.botao is not None:
            self.botao.configure(state=estado)


# ====================================================== diagrama da cadeia
class ChainDiagram(tk.Canvas):
    """Diagrama animado: Cliente → Varejista → Atacadista → Distribuidor →
    Fábrica, com mercadorias descendo (faixa superior) e pedidos subindo
    (faixa inferior). As quantidades 'viajam' a cada fechamento de semana."""

    NOMES = ["Cliente", "Varejista", "Atacadista", "Distribuidor", "Fábrica"]
    FRAMES, INTERVALO = 12, 28   # ~0,34 s por semana

    def __init__(self, master, height=185, **kw):
        super().__init__(master, height=height, highlightthickness=0, **kw)
        self._snap = None
        self._anim = None
        theme.registrar(self, lambda: self._desenha())
        self.bind("<Configure>", lambda e: self._desenha())

    # ------------------------------------------------------------- geometria
    def _layout(self):
        w = max(self.winfo_width(), 760)
        h = int(self["height"])
        n = 5
        margem, gap_min = 16, 64
        bw = min(132, (w - 2 * margem - (n - 1) * gap_min) / n)
        gap = (w - 2 * margem - n * bw) / (n - 1)
        cy = h * 0.56
        bh = 52
        boxes = []
        for i in range(n):
            x0 = margem + i * (bw + gap)
            boxes.append((x0, cy - bh / 2, x0 + bw, cy + bh / 2))
        lanes = []
        for i in range(n - 1):
            xa, xb = boxes[i][2] + 6, boxes[i + 1][0] - 6
            y_g, y_o = cy - bh / 2 - 16, cy + bh / 2 + 16
            lanes.append(dict(
                g_slots=[(xa + (xb - xa) * 0.32, y_g), (xa + (xb - xa) * 0.68, y_g)],
                o_slots=[(xa + (xb - xa) * 0.68, y_o), (xa + (xb - xa) * 0.32, y_o)],
                xa=xa, xb=xb, y_g=y_g, y_o=y_o))
        fx = (boxes[4][0] + boxes[4][2]) / 2
        py = boxes[4][1] - 18
        prod = dict(slots=[(fx - 36, py), (fx, py), (fx + 36, py)],
                    origem=(fx + 36, py))   # o pedido nasce no slot "pedido"
        return boxes, lanes, prod

    @staticmethod
    def _centro(b):
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

    # --------------------------------------------------------------- desenho
    def set_data(self, snap: dict):
        self._snap = snap
        self._desenha()

    def _chip(self, x, y, valor, tipo):
        c = theme.cores()
        fill = c["accent"] if tipo == "g" else c["chip_pedido"]
        fg = c["accent_fg"] if tipo == "g" else "#ffffff"
        self.create_rectangle(x - 14, y - 9, x + 14, y + 9, fill=fill,
                              outline="", tags="chip")
        self.create_text(x, y, text=str(valor), fill=fg,
                         font=theme.fontes()["mini"] + ("bold",), tags="chip")

    def _slot_vazio(self, x, y, rotulo=None):
        c = theme.cores()
        self.create_rectangle(x - 14, y - 9, x + 14, y + 9, outline=c["eixo"],
                              dash=(2, 2))
        if rotulo:
            self.create_text(x, y, text=rotulo, fill=c["suave"],
                             font=theme.fontes()["mini"])

    def _faixa_slots(self, slots, vals, tipo, rotulo_vazio=None, gap_inicio=False):
        """Desenha as molduras de todos os slots e os chips presentes.
        vals[j] ocupa o slot j (slot 0 = chega/consome na próxima semana).
        gap_inicio=True marca com '?' o último slot (o recém-aberto, à espera
        da decisão da semana), em vez de deixá-lo apenas tracejado."""
        n = len(slots)
        for j, pos in enumerate(slots):
            if j < len(vals):
                self._chip(*pos, vals[j], tipo)
            elif gap_inicio and j == n - 1:
                self._slot_vazio(*pos, "?")
            else:
                self._slot_vazio(*pos, rotulo_vazio if j == n - 1 else None)

    def _desenha(self, movers=None, frac=1.0, snap=None):
        snap = snap or self._snap
        c, f = theme.cores(), theme.fontes()
        self.configure(bg=c["canvas"])
        self.delete("all")
        if snap is None:
            return
        boxes, lanes, prod = self._layout()
        est, bl = snap["estoque"], snap["backlog"]
        # setas das faixas
        for ln in lanes:
            self.create_line(ln["xb"], ln["y_g"], ln["xa"], ln["y_g"],
                             arrow="last", fill=c["eixo"], width=1)
            self.create_line(ln["xa"], ln["y_o"], ln["xb"], ln["y_o"],
                             arrow="last", fill=c["eixo"], width=1)
        self.create_text(boxes[0][0] + 2, lanes[0]["y_g"] - 12, anchor="w",
                         text="mercadorias (2 sem) ⟵", font=f["mini"],
                         fill=c["suave"])
        self.create_text(boxes[0][0] + 2, lanes[0]["y_o"] + 12, anchor="w",
                         text="pedidos (2 sem) ⟶", font=f["mini"],
                         fill=c["suave"])
        # produção da fábrica
        x0, y0 = prod["origem"]
        self.create_line(boxes[4][2] - 8, boxes[4][1], boxes[4][2] - 8,
                         prod["slots"][1][1], prod["slots"][0][0] - 18,
                         prod["slots"][0][1], arrow="last", smooth=True,
                         fill=c["eixo"])
        self.create_text(self.winfo_width() - 6 if self.winfo_width() > 1
                         else 1090, prod["slots"][0][1] - 16, anchor="e",
                         text="pedido 1 sem + produção 2 sem",
                         font=f["mini"], fill=c["suave"])
        # caixas dos nós
        for i, b in enumerate(boxes):
            cor = "#666666" if i == 0 else CORES[ROLES[i - 1]]
            self.create_rectangle(*b, fill=c["card"], outline=cor, width=2)
            cx, cyb = self._centro(b)
            self.create_text(cx, b[1] + 12, text=self.NOMES[i],
                             font=f["rotulo_b"], fill=cor)
            if i == 0:
                self.create_text(cx, b[3] - 14, text=f"demanda {snap['demanda']}",
                                 font=f["mini"], fill=c["texto"])
            else:
                e, k = est[i - 1], bl[i - 1]
                cor_e = c["perigo"] if e == 0 else (c["alerta"] if e <= 4 else c["ok"])
                cor_b = c["ok"] if k == 0 else (c["alerta"] if k < 10 else c["perigo"])
                self.create_text(cx - 4, b[3] - 14, anchor="e",
                                 text=f"E {e}", font=f["mini"], fill=cor_e)
                self.create_text(cx + 4, b[3] - 14, anchor="w",
                                 text=f"B {k}", font=f["mini"], fill=cor_b)
        # chips estáticos (fora de animação) ou em movimento
        if movers is None:
            for i in range(3):                           # mercadorias p/ elo i
                ln = lanes[i + 1]
                self._faixa_slots(ln["g_slots"], snap["ship_in"][i], "g")
            for i in range(3):                           # pedidos p/ elo i+1
                ln = lanes[i + 1]
                self._faixa_slots(ln["o_slots"], snap["order_in"][i], "o",
                                  gap_inicio=True)
            self._faixa_slots(prod["slots"], snap["ship_in"][3], "g",
                              rotulo_vazio="ped.", gap_inicio=True)  # produção
            # cliente: último envio e demanda corrente
            self._chip((lanes[0]["xa"] + lanes[0]["xb"]) / 2, lanes[0]["y_g"],
                       snap["enviado"][0], "g")
            self._chip((lanes[0]["xa"] + lanes[0]["xb"]) / 2, lanes[0]["y_o"],
                       snap["demanda"], "o")
        else:
            for val, pts, tipo in movers:
                x, y = _ponto_na_poligonal(pts, frac)
                self._chip(x, y, val, tipo)

    # -------------------------------------------------------------- animação
    @staticmethod
    def _movers_lane(old, new, slots, origem, destino, tipo, tipo_novo=None):
        """Movimentos de uma faixa (com waypoints): o item do slot mais próximo
        do destino sai para o destino, os demais avançam um slot, e o item novo
        entra pela origem percorrendo o slot mais distante do destino até a sua
        posição final (trecho diagonal de entrada + trechos horizontais)."""
        mv = []
        n = len(slots)
        if old:
            mv.append((old[0], [slots[0], destino], tipo))
            for j in range(1, min(len(old), n)):
                mv.append((old[j], [slots[j], slots[j - 1]], tipo))
        if new:
            ult = min(len(new), n) - 1
            visitados = [slots[k] for k in range(n - 1, ult - 1, -1)]
            mv.append((new[-1], [origem] + visitados, tipo_novo or tipo))
        return mv

    def animar(self, antigo: dict, novo: dict, ao_fim=None):
        """Anima a transição de uma semana: chips deslizam entre os slots."""
        if self._anim is not None:
            self.after_cancel(self._anim)
            self._anim = None
        boxes, lanes, prod = self._layout()
        centros = [self._centro(b) for b in boxes]
        movers = []
        for i in range(3):  # mercadorias a caminho do elo i (caixas i+1 ← i+2)
            ln = lanes[i + 1]
            movers += self._movers_lane(antigo["ship_in"][i],
                                        novo["ship_in"][i], ln["g_slots"],
                                        centros[i + 2], centros[i + 1], "g")
        for i in range(3):  # pedidos do elo i ao fornecedor (caixas i+1 → i+2)
            ln = lanes[i + 1]
            movers += self._movers_lane(antigo["order_in"][i],
                                        novo["order_in"][i], ln["o_slots"],
                                        centros[i + 1], centros[i + 2], "o")
        movers += self._movers_lane(antigo["ship_in"][3], novo["ship_in"][3],
                                    prod["slots"], prod["origem"],
                                    centros[4], "g", tipo_novo="o")
        # ^ produção: o pedido (azul) nasce no slot "ped." e vira produção
        meio_g = ((lanes[0]["xa"] + lanes[0]["xb"]) / 2, lanes[0]["y_g"])
        meio_o = ((lanes[0]["xa"] + lanes[0]["xb"]) / 2, lanes[0]["y_o"])
        movers += [(novo["enviado"][0], [centros[1], meio_g], "g"),
                   (novo["demanda"], [centros[0], meio_o], "o")]
        movers = [m for m in movers if m[0] is not None]

        def passo(k=0):
            if not self.winfo_exists():
                return
            if k > self.FRAMES:
                self._anim = None
                self.set_data(novo)
                if ao_fim:
                    ao_fim()
                return
            self._desenha(movers=movers, frac=k / self.FRAMES, snap=antigo)
            self._anim = self.after(self.INTERVALO, lambda: passo(k + 1))

        passo()


# ===================================================== fluxo do próprio elo
class NodeFlow(tk.Canvas):
    """Diagrama animado do segmento de UM elo (para o jogador em rede, que só
    enxerga a própria posição). Segue a mesma orientação do modo individual:

        Cliente (jusante) ⟵ ... ⟵ VOCÊ ⟵ ... ⟵ Fornecedor (montante)

    - mercadorias (chips âmbar) descem a cadeia da DIREITA p/ ESQUERDA
      (faixa de cima): Fornecedor → você → Cliente;
    - pedidos (chips azuis) sobem a cadeia da ESQUERDA p/ DIREITA
      (faixa de baixo): Cliente → você → Fornecedor.
    Respeita a informação limitada: nenhum dado dos outros elos é exibido."""

    FRAMES, INTERVALO = 12, 28

    def __init__(self, master, papel, height=210, **kw):
        super().__init__(master, height=height, highlightthickness=1, **kw)
        self.papel = papel
        self.eh_fabrica = (papel == "fabrica")
        self._view = None
        self._anim = None
        theme.registrar(self, lambda: self._desenha())
        self.bind("<Configure>", lambda e: self._desenha())

    # ------------------------------------------------------------- geometria
    def _layout(self):
        w = max(self.winfo_width(), 520)
        h = int(self["height"])
        cy = h * 0.52
        bw, bh = 150, 60
        cx = w / 2
        me = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
        lbw = 116
        # cliente à ESQUERDA (jusante), fornecedor à DIREITA (montante)
        cli = (16, cy - bh / 2, 16 + lbw, cy + bh / 2)
        forn = (w - 16 - lbw, cy - bh / 2, w - 16, cy + bh / 2)
        y_g = cy - bh / 2 - 18      # faixa de mercadorias (em cima)
        y_o = cy + bh / 2 + 18      # faixa de pedidos (embaixo)
        # --- corredor à DIREITA (entre você e o fornecedor) ---
        rx_a, rx_b = me[2] + 8, forn[0] - 8
        # transporte chegando (mercadorias do fornecedor → você): desce p/ a
        # esquerda. slot0 = chega antes (mais perto de você, à esquerda).
        g_slots = [(rx_a + (rx_b - rx_a) * 0.34, y_g),
                   (rx_a + (rx_b - rx_a) * 0.68, y_g)]
        # pedidos a caminho do fornecedor (você → fornecedor): sobe p/ a
        # direita. slot0 = chega antes (mais perto do fornecedor, à direita).
        o_slots = [(rx_a + (rx_b - rx_a) * 0.68, y_o),
                   (rx_a + (rx_b - rx_a) * 0.34, y_o)]
        return dict(me=me, forn=forn, cli=cli, y_g=y_g, y_o=y_o,
                    g_slots=g_slots, o_slots=o_slots,
                    rx_a=rx_a, rx_b=rx_b, w=w)

    @staticmethod
    def _centro(b):
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

    def set_view(self, view):
        self._view = view
        self._desenha()

    # --------------------------------------------------------------- chips
    def _chip(self, x, y, valor, tipo):
        c = theme.cores()
        fill = c["accent"] if tipo == "g" else c["chip_pedido"]
        fg = c["accent_fg"] if tipo == "g" else "#ffffff"
        self.create_rectangle(x - 15, y - 10, x + 15, y + 10, fill=fill,
                              outline="", tags="chip")
        self.create_text(x, y, text=str(valor), fill=fg,
                         font=theme.fontes()["mini"] + ("bold",), tags="chip")

    def _slot(self, x, y, gap=False):
        c = theme.cores()
        self.create_rectangle(x - 15, y - 10, x + 15, y + 10, outline=c["eixo"],
                              dash=(2, 2))
        if gap:
            self.create_text(x, y, text="?", fill=c["suave"],
                             font=theme.fontes()["mini"])

    def _faixa(self, slots, vals, tipo, gap_inicio=False):
        n = len(slots)
        for j, pos in enumerate(slots):
            if j < len(vals):
                self._chip(*pos, vals[j], tipo)
            else:
                self._slot(*pos, gap=(gap_inicio and j == n - 1))

    # --------------------------------------------------------------- desenho
    def _desenha(self, movers=None, frac=1.0):
        c, f = theme.cores(), theme.fontes()
        self.configure(bg=c["canvas"], highlightbackground=c["borda"])
        self.delete("all")
        if self._view is None:
            return
        L = self._layout()
        cor = CORES[self.papel]
        forn_nome = "Produção" if self.eh_fabrica else "Fornecedor"
        v = self._view
        # --- setas das faixas no corredor da direita (você ↔ fornecedor) ---
        # mercadorias: do fornecedor (direita) para você (esquerda) ⟵
        self.create_line(L["rx_b"], L["y_g"], L["rx_a"], L["y_g"],
                         arrow="last", fill=c["eixo"])
        # pedidos: de você (esquerda) para o fornecedor (direita) ⟶
        self.create_line(L["rx_a"], L["y_o"], L["rx_b"], L["y_o"],
                         arrow="last", fill=c["eixo"])
        rotulo_g = ("produção (1+2 sem) ⟵" if self.eh_fabrica
                    else "mercadorias (2 sem) ⟵")
        rotulo_o = ("pedido p/ produção ⟶" if self.eh_fabrica
                    else "seus pedidos (2 sem) ⟶")
        self.create_text(L["rx_a"], L["y_g"] - 13, anchor="w",
                         text=rotulo_g, font=f["mini"], fill=c["suave"])
        self.create_text(L["rx_a"], L["y_o"] + 13, anchor="w",
                         text=rotulo_o, font=f["mini"], fill=c["suave"])
        # --- corredor da esquerda (você ↔ cliente de jusante) ---
        cli_x = (L["cli"][2] + L["me"][0]) / 2
        # mercadorias que você enviou ao cliente (você → cliente) ⟵
        self.create_line(L["me"][0] - 8, L["y_g"], L["cli"][2] + 8, L["y_g"],
                         arrow="last", fill=c["eixo"])
        # pedido recebido do cliente (cliente → você) ⟶
        self.create_line(L["cli"][2] + 8, L["y_o"], L["me"][0] - 8, L["y_o"],
                         arrow="last", fill=c["eixo"])
        # caixas
        for b, nome, cr in ((L["forn"], forn_nome, c["suave"]),
                            (L["cli"], "Cliente", c["suave"]),
                            (L["me"], ROLE_LABEL[self.papel], cor)):
            larg = 2 if b == L["me"] else 1
            self.create_rectangle(*b, fill=c["card"], outline=cr, width=larg)
        self.create_text(*self._centro(L["forn"]), text=forn_nome,
                         font=f["rotulo_b"], fill=c["suave"])
        self.create_text(*self._centro(L["cli"]),
                         text="Cliente\n(jusante)", font=f["mini"],
                         fill=c["suave"], justify="center")
        mx, my = self._centro(L["me"])
        self.create_text(mx, L["me"][1] + 13, text=ROLE_LABEL[self.papel],
                         font=f["rotulo_b"], fill=cor)
        e, bl = v["estoque"], v["backlog"]
        cor_e = c["perigo"] if e == 0 else (c["alerta"] if e <= 4 else c["ok"])
        cor_b = c["ok"] if bl == 0 else (c["alerta"] if bl < 10 else c["perigo"])
        self.create_text(mx - 6, my + 6, anchor="e", text=f"Estoque {e}",
                         font=f["mini"], fill=cor_e)
        self.create_text(mx + 6, my + 6, anchor="w", text=f"Backlog {bl}",
                         font=f["mini"], fill=cor_b)
        # chips
        if movers is None:
            self._faixa(L["g_slots"], v.get("ship_pipe", []), "g")
            self._faixa(L["o_slots"], v.get("order_pipe", []), "o",
                        gap_inicio=True)
            if v.get("enviado") is not None:    # você → cliente (mercadoria)
                self._chip(cli_x, L["y_g"], v["enviado"], "g")
            # pedido que o cliente fez a você (chip azul a caminho)
            self._chip(cli_x, L["y_o"], v.get("pedido_recebido", 0), "o")
        else:
            for val, pts, tipo in movers:
                x, y = _ponto_na_poligonal(pts, frac)
                self._chip(x, y, val, tipo)

    # -------------------------------------------------------------- animação
    def animar(self, antiga: dict, nova: dict, ao_fim=None):
        """Anima a transição entre duas semanas para o próprio elo, com a mesma
        lógica de 3 estágios do modo individual em ambas as faixas."""
        if self._anim is not None:
            self.after_cancel(self._anim)
            self._anim = None
        if antiga is None:
            self.set_view(nova)
            if ao_fim:
                ao_fim()
            return
        L = self._layout()
        me_c = self._centro(L["me"])
        forn_c = self._centro(L["forn"])
        cli_x = (L["cli"][2] + L["me"][0]) / 2
        movers = []

        def faixa(old, new, slots, origem, destino, tipo, tipo_novo=None):
            """Anima uma faixa de pipeline com a mesma lógica em todos os casos:
            cada item avança um slot rumo ao destino; o item que estava no slot
            mais próximo do destino sai para o destino; e o item novo entra a
            partir da origem, passando pelo PRIMEIRO slot (trecho diagonal) e
            seguindo até a sua posição final (trecho horizontal).
            Usa waypoints para que o novo item percorra os slots intermediários
            em vez de ir direto ao slot final."""
            mv = []
            n = len(slots)
            # itens já no pipeline avançam um slot (slot[j] -> slot[j-1]);
            # o do slot 0 sai para o destino.
            if old:
                mv.append((old[0], [slots[0], destino], tipo))
                for j in range(1, min(len(old), n)):
                    mv.append((old[j], [slots[j], slots[j - 1]], tipo))
            # item novo: entra pela origem e percorre os slots a partir do mais
            # distante do destino (junto da origem) até a sua posição final.
            # Ex.: pedido entra no slot perto de você (diagonal) e avança para o
            # slot seguinte rumo ao fornecedor (horizontal).
            if new:
                ult = min(len(new), n) - 1          # índice da posição final
                # slots percorridos: do mais distante do destino (n-1) até ult
                visitados = [slots[k] for k in range(n - 1, ult - 1, -1)]
                mv.append((new[-1], [origem] + visitados, tipo_novo or tipo))
            return mv

        # mercadorias: fornecedor (origem, direita) → slots → você (destino)
        movers += faixa(antiga.get("ship_pipe", []), nova.get("ship_pipe", []),
                        L["g_slots"], forn_c, me_c, "g")
        # pedidos: você (origem, centro) → slots → fornecedor (destino, direita).
        # Para a fábrica o "pedido" colocado vira produção (chip âmbar).
        movers += faixa(antiga.get("order_pipe", []), nova.get("order_pipe", []),
                        L["o_slots"], me_c, forn_c, "o",
                        tipo_novo="g" if self.eh_fabrica else "o")
        # corredor da esquerda: o que você acabou de enviar desliza até o cliente
        if nova.get("enviado") is not None:
            movers.append((nova["enviado"], [me_c, (cli_x, L["y_g"])], "g"))
        # e o novo pedido do cliente desliza do cliente até você
        movers.append((nova.get("pedido_recebido", 0),
                       [(cli_x, L["y_o"]), me_c], "o"))
        movers = [m for m in movers if m[0] is not None]

        def passo(k=0):
            if not self.winfo_exists():
                return
            if k > self.FRAMES:
                self._anim = None
                self.set_view(nova)
                if ao_fim:
                    ao_fim()
                return
            self._view = antiga
            self._desenha(movers=movers, frac=k / self.FRAMES)
            self._view = nova
            self._anim = self.after(self.INTERVALO, lambda: passo(k + 1))

        passo()


# ============================================================ relatório final
def _abrir_pasta(caminho):
    pasta = os.path.abspath(os.path.dirname(caminho) or ".")
    try:
        if sys.platform.startswith("win"):
            os.startfile(pasta)                      # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", pasta])
        else:
            subprocess.Popen(["xdg-open", pasta])
    except Exception:
        pass


def _choque_de(rows):
    jogo = [r for r in rows if r.get("fase") == "jogo"]
    if not jogo:
        return None
    d0 = jogo[0]["demanda_cliente"]
    for r in jogo:
        if r["demanda_cliente"] != d0:
            return r["semana"]
    return None


def show_report(parent, rows, resumo, caminhos=None, salvar_local=None):
    """Relatório final: custo em destaque, pódio dos elos e gráficos."""
    c, f = theme.cores(), theme.fontes()
    win = tk.Toplevel(parent)
    win.title("Beer Game — Relatório da partida")
    win.geometry("1010x690")
    win.configure(bg=c["bg"])
    jogo = [r for r in rows if r.get("fase") == "jogo"]
    choque = _choque_de(rows)

    topo = ttk.Frame(win, padding=(12, 10, 12, 4))
    topo.pack(fill="x")
    ttk.Label(topo, text="Resultado da partida", style="Titulo.TLabel")\
       .pack(side="left")
    custo = resumo.get("custo_total_cadeia", 0.0) or 0.0
    caixa = tk.Frame(topo, bg=c["accent"])
    caixa.pack(side="right")
    tk.Label(caixa, text="CUSTO TOTAL DA CADEIA", bg=c["accent"],
             fg=c["accent_fg"], font=f["mini"]).pack(padx=12, pady=(5, 0))
    tk.Label(caixa, text=f"R$ {custo:,.2f}".replace(",", "X").replace(".", ",")
             .replace("X", "."), bg=c["accent"], fg=c["accent_fg"],
             font=f["num"]).pack(padx=12, pady=(0, 5))

    # pódio (ranking por menor custo)
    podio = ttk.LabelFrame(win, text="  Ranking dos elos (menor custo vence)  ",
                           padding=8)
    podio.pack(fill="x", padx=12, pady=6)
    ordem = sorted((r for r in ROLES if r in resumo.get("elos", {})),
                   key=lambda r: resumo["elos"][r]["custo_total"])
    medalhas = ["🥇", "🥈", "🥉", "4º"]
    for col, r in enumerate(ordem):
        e = resumo["elos"][r]
        cel = tk.Frame(podio, bg=c["card"], highlightbackground=CORES[r],
                       highlightthickness=2)
        cel.grid(row=0, column=col, padx=6, sticky="nsew", ipadx=4)
        podio.grid_columnconfigure(col, weight=1)
        tk.Label(cel, text=medalhas[col], bg=c["card"],
                 font=("Segoe UI", 16)).pack(pady=(4, 0))
        tk.Label(cel, text=e["rotulo"], bg=c["card"], fg=CORES[r],
                 font=f["rotulo_b"]).pack()
        tk.Label(cel, text=f"R$ {e['custo_total']:.2f}".replace(".", ","),
                 bg=c["card"], fg=c["texto"], font=f["h2"]).pack()
        tk.Label(cel, text=f"pedidos {e['pedido_min']}–{e['pedido_max']} · "
                           f"backlog máx {e['backlog_max']}",
                 bg=c["card"], fg=c["suave"], font=f["mini"]).pack(pady=(0, 4))

    graficos = ttk.Frame(win, padding=8)
    graficos.pack(fill="both", expand=True)
    g1 = MiniChart(graficos, width=480, height=265,
                   titulo="Pedidos colocados por semana (efeito chicote)")
    g1.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
    g2 = MiniChart(graficos, width=480, height=265, shade_negativo=True,
                   titulo="Estoque líquido (estoque − backlog) por semana")
    g2.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")
    graficos.grid_columnconfigure(0, weight=1)
    graficos.grid_columnconfigure(1, weight=1)
    if jogo:
        s1, s2 = [], []
        for papel in ROLES:
            p = PREFIX[papel]
            s1.append((ROLE_LABEL[papel], CORES[papel],
                       [r[f"{p}_pedido_colocado"] for r in jogo]))
            s2.append((ROLE_LABEL[papel], CORES[papel],
                       [r[f"{p}_estoque_final"] - r[f"{p}_backlog"]
                        for r in jogo]))
        g1.plot(s1, x0=jogo[0]["semana"], choque=choque)
        g2.plot(s2, x0=jogo[0]["semana"], choque=choque)

    rodape = ttk.Frame(win, padding=(12, 4, 12, 10))
    rodape.pack(fill="x")
    esq = ttk.Frame(rodape)
    esq.pack(side="left", fill="x", expand=True)
    if caminhos:
        ttk.Label(esq, text="Arquivos gravados:", style="Suave.TLabel")\
           .pack(anchor="w")
        for cam in caminhos:
            ttk.Label(esq, text="  • " + cam, style="Suave.TLabel")\
               .pack(anchor="w")
        ttk.Button(esq, text="📂 Abrir pasta de partidas",
                   command=lambda: _abrir_pasta(caminhos[0]))\
           .pack(anchor="w", pady=4)
    if salvar_local:
        def _salvar():
            try:
                novos = salvar_local()
                messagebox.showinfo("Beer Game",
                                    "Cópia local gravada em:\n" + "\n".join(novos),
                                    parent=win)
            except Exception as exc:
                messagebox.showerror("Beer Game", f"Falha ao gravar: {exc}",
                                     parent=win)
        ttk.Button(esq, text="💾 Salvar cópia local (.db / .csv / .xlsx)",
                   command=_salvar).pack(anchor="w", pady=4)
    ttk.Button(rodape, text="Fechar", style="Accent.TButton",
               command=win.destroy).pack(side="right", anchor="s")
    return win
