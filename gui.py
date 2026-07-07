# -*- coding: utf-8 -*-
"""Interface gráfica (Tkinter) do Beer Game: menu, modo individual e modo rede."""
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import theme
from engine import GameEngine, GameConfig, ROLES, PREFIX, ROLE_LABEL
from ai_player import (make_ai_players, MODELOS, MODELO_LABEL, MODELO_RESUMO,
                       EQUILIBRADO, ENXUTO, CAUTELOSO)
from storage import GameTable
from protocol import PORTA_PADRAO, ip_local
from widgets import (NodePanel, MiniChart, ChainDiagram, ProgressTimeline,
                     NodeFlow, show_report, CORES)

TITULO = "Beer Game — Simulação da Cadeia de Suprimentos (CISLOG)"


# ===================================================================== logo
def _dir_base():
    """Pasta do executável/script (onde o usuário pode colocar o logo.jpg)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def carregar_logo(altura=40):
    """Procura logo.jpg (ou logo.png) e devolve um PhotoImage (ou None).

    Ordem de busca (a primeira que existir vence):
      1. pasta do .exe/script  -> permite TROCAR o logo sem recompilar,
                                   bastando colocar um logo.jpg ao lado do .exe;
      2. diretório de trabalho atual;
      3. sys._MEIPASS          -> o logo EMBUTIDO no .exe pelo PyInstaller
                                   (--add-data "logo.jpg;."), usado por padrão.
    JPG requer Pillow; PNG funciona nativamente."""
    candidatos = []
    for pasta in (_dir_base(), os.getcwd(), getattr(sys, "_MEIPASS", "")):
        if pasta:
            candidatos += [os.path.join(pasta, "logo.jpg"),
                           os.path.join(pasta, "logo.png")]
    for cam in candidatos:
        if not os.path.exists(cam):
            continue
        try:
            from PIL import Image, ImageTk
            img = Image.open(cam)
            w = max(1, int(img.width * altura / img.height))
            return ImageTk.PhotoImage(img.resize((w, altura)))
        except Exception:
            if cam.lower().endswith(".png"):
                try:
                    img = tk.PhotoImage(file=cam)
                    fator = max(1, round(img.height() / altura))
                    return img.subsample(fator, fator)
                except tk.TclError:
                    pass
    return None


class Header(tk.Frame):
    """Faixa superior persistente: logo, título, semana corrente e tema."""

    def __init__(self, app):
        super().__init__(app, height=round(54 * theme.escala()))
        self.app = app
        self._info = ""
        self._logo_img = None
        self._montar()
        theme.registrar(self, self._montar)

    def _montar(self):
        c, f = theme.cores(), theme.fontes()
        self.configure(bg=c["header"], height=round(54 * theme.escala()))
        for w in self.winfo_children():
            w.destroy()
        esq = tk.Frame(self, bg=c["header"])
        esq.pack(side="left", padx=12, pady=6)
        alt_logo = round(40 * theme.escala())
        self._logo_img = carregar_logo(alt_logo)
        if self._logo_img is not None:
            # cartão branco atrás do logo: fica elegante tanto no tema claro
            # quanto no escuro (o logo tem fundo branco e tons claros).
            cartao = tk.Frame(esq, bg="#ffffff", bd=0, highlightthickness=1,
                              highlightbackground=c["accent"])
            cartao.pack(side="left", padx=(0, 10))
            tk.Label(cartao, image=self._logo_img, bg="#ffffff", bd=0)\
              .pack(padx=4, pady=2)
        else:
            self._logo_fallback(esq, c, alt_logo)
        tit = tk.Frame(esq, bg=c["header"])
        tit.pack(side="left")
        tk.Label(tit, text="Beer Game", bg=c["header"], fg=c["header_fg"],
                 font=f["titulo"]).pack(anchor="w")
        tk.Label(tit, text="Cadeia de Suprimentos · CISLOG", bg=c["header"],
                 fg=c["accent"], font=f["mini"]).pack(anchor="w")
        dirf = tk.Frame(self, bg=c["header"])
        dirf.pack(side="right", padx=12)

        # --- controle de tamanho de fonte (A-  A+) ---
        fonte = tk.Frame(dirf, bg=c["header"])
        fonte.pack(side="right", pady=12, padx=(8, 0))

        def botao(txt, cmd, estado="normal"):
            b = tk.Button(fonte, text=txt, command=cmd, bg=c["header"],
                          fg=c["header_fg"], activebackground=c["accent"],
                          activeforeground=c["accent_fg"], bd=1, relief="solid",
                          font=f["mini"], padx=6, cursor="hand2",
                          state=estado, disabledforeground=c["suave"])
            b.pack(side="left", padx=1)
            return b

        botao("A−", lambda: theme.mudar_escala(self.app, -1),
              "normal" if theme.pode_diminuir() else "disabled")
        tk.Label(fonte, text=f"{round(theme.escala() * 100)}%", bg=c["header"],
                 fg=c["header_fg"], font=f["mini"], width=5)\
          .pack(side="left", padx=2)
        botao("A+", lambda: theme.mudar_escala(self.app, +1),
              "normal" if theme.pode_aumentar() else "disabled")

        rot = "🌙 Escuro" if theme.atual == "claro" else "☀ Claro"
        tk.Button(dirf, text=rot, command=self._toggle, bg=c["header"],
                  fg=c["header_fg"], activebackground=c["accent"],
                  activeforeground=c["accent_fg"], bd=1, relief="solid",
                  font=f["mini"], padx=8, cursor="hand2").pack(side="right",
                                                               pady=12)
        self._lbl_info = tk.Label(dirf, text=self._info, bg=c["header"],
                                  fg=c["header_fg"], font=f["h2"])
        self._lbl_info.pack(side="right", padx=(0, 14))

    def _logo_fallback(self, master, c, alt=40):
        e = alt / 40.0
        cv = tk.Canvas(master, width=alt, height=alt, bg=c["header"],
                       highlightthickness=0)
        cv.pack(side="left", padx=(0, 10))
        cv.create_rectangle(8 * e, 12 * e, 28 * e, 36 * e, fill=c["accent"],
                            outline="#7a5210", width=1)     # caneca
        cv.create_arc(24 * e, 16 * e, 38 * e, 32 * e, start=300, extent=160,
                      style="arc", outline="#7a5210", width=3)   # alça
        for x, y, r in ((11, 10, 5), (18, 7, 6), (25, 10, 5)):
            cv.create_oval((x - r) * e, (y - r) * e, (x + r) * e, (y + r) * e,
                           fill="#fdf6e3", outline="")      # espuma

    def _toggle(self):
        theme.alternar(self.app)

    def set_info(self, texto: str):
        self._info = texto
        if self._lbl_info.winfo_exists():
            self._lbl_info.config(text=texto)


# ============================================================== infraestrutura
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITULO)
        self.geometry("1120x800")
        self.minsize(1000, 700)
        self._definir_icone()
        theme.aplicar(self)
        self.header = Header(self)
        self.header.pack(fill="x", side="top")
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self._frame = None
        self._cleanups = []
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.mostrar(MenuFrame)

    def _definir_icone(self):
        """Ícone da janela: usa beergame.ico no Windows e o logo via
        iconphoto nos demais sistemas. Procura no diretório do programa e no
        recurso embutido pelo PyInstaller (_MEIPASS)."""
        pastas = [p for p in (_dir_base(), getattr(sys, "_MEIPASS", ""),
                              os.getcwd()) if p]
        for pasta in pastas:
            ico = os.path.join(pasta, "beergame.ico")
            if os.path.exists(ico):
                try:
                    self.iconbitmap(ico)
                    return
                except tk.TclError:
                    break
        # fallback multiplataforma: iconphoto a partir do logo
        try:
            img = carregar_logo(64)
            if img is not None:
                self.iconphoto(True, img)
                self._icone_img = img      # mantém referência viva
        except Exception:
            pass

    def registrar_cleanup(self, fn):
        self._cleanups.append(fn)

    def _rodar_cleanups(self):
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                pass

    def mostrar(self, FrameClass, **kw):
        if FrameClass is MenuFrame:
            self._rodar_cleanups()   # voltar ao menu encerra servidor/conexões
            self.header.set_info("")
        if self._frame is not None:
            self._frame.destroy()
        self._frame = FrameClass(self, **kw)
        self._frame.pack(in_=self.container, fill="both", expand=True)

    def _fechar(self):
        self._rodar_cleanups()
        self.destroy()


class ConfigForm(ttk.LabelFrame):
    """Formulário com os parâmetros da partida."""

    CAMPOS = [("semanas", "Duração (semanas)", 36),
              ("demanda_inicial", "Demanda inicial (un/sem)", 4),
              ("demanda_nova", "Demanda após o choque", 8),
              ("semana_mudanca", "Semana do choque", 5),
              ("estoque_inicial", "Estoque inicial por elo (un)", 12),
              ("estoque_seguranca", "Estoque de segurança da IA", 4)]

    def __init__(self, master):
        super().__init__(master, text="  Parâmetros da partida  ", padding=8)
        self.vars = {}
        for i, (chave, rotulo, padrao) in enumerate(self.CAMPOS):
            ttk.Label(self, text=rotulo + ":").grid(row=i, column=0,
                                                    sticky="w", pady=2)
            v = tk.StringVar(value=str(padrao))
            self.vars[chave] = v
            ttk.Spinbox(self, from_=0, to=999, width=6, textvariable=v)\
               .grid(row=i, column=1, sticky="e", padx=(12, 0))
        ttk.Label(self, text="Estoque inicial sugerido: 12 (clássico) ou 16.",
                  style="Suave.TLabel").grid(row=len(self.CAMPOS), column=0,
                                             columnspan=2, sticky="w",
                                             pady=(6, 0))

    def config(self) -> GameConfig:
        cfg = GameConfig()
        for chave, var in self.vars.items():
            try:
                setattr(cfg, chave, int(var.get()))
            except ValueError:
                pass
        cfg.semanas = max(4, min(cfg.semanas, 104))
        cfg.estoque_inicial = max(0, cfg.estoque_inicial)
        return cfg


# ======================================================================= menu
class MenuFrame(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app, padding=30)
        self.app = app
        ttk.Label(self, text="Bem-vindo!", style="Titulo.TLabel")\
           .pack(pady=(26, 2))
        ttk.Label(self, text="Escolha um modo de jogo",
                  style="Suave.TLabel").pack(pady=(0, 26))
        opcoes = [
            ("🎮  Jogo individual  (humano e/ou IA nos 4 elos)",
             lambda: app.mostrar(IndividualSetupFrame)),
            ("🖧  Criar sala em rede  (este computador será o host)",
             lambda: app.mostrar(NetSetupFrame, host=True)),
            ("🔌  Entrar em sala  (conectar a um host por IP)",
             lambda: app.mostrar(NetSetupFrame, host=False)),
            ("✖  Sair", app._fechar),
        ]
        for txt, cmd in opcoes:
            ttk.Button(self, text=txt, width=54, command=cmd)\
               .pack(pady=6, ipady=7)

        # --- painel explicativo dos modelos de IA ---
        ia = ttk.LabelFrame(self, text="  Modelos de IA disponíveis  ",
                            padding=10)
        ia.pack(fill="x", pady=(18, 6), padx=10)
        cores_modelo = {EQUILIBRADO: theme.cores()["accent"],
                        ENXUTO: CORES["atacadista"],
                        CAUTELOSO: CORES["varejista"]}
        for m in MODELOS:
            linha = ttk.Frame(ia)
            linha.pack(fill="x", pady=2)
            tk.Label(linha, text="●", fg=cores_modelo[m],
                     bg=theme.cores()["bg"], font=theme.fontes()["rotulo_b"])\
              .pack(side="left", anchor="n", padx=(0, 6))
            txtf = ttk.Frame(linha)
            txtf.pack(side="left", fill="x", expand=True)
            ttk.Label(txtf, text=MODELO_LABEL[m], style="H2.TLabel")\
               .pack(anchor="w")
            ttk.Label(txtf, text=MODELO_RESUMO[m], style="Suave.TLabel",
                      wraplength=900, justify="left").pack(anchor="w")

        ttk.Label(self, text="Cadeia: Cliente → Varejista → Atacadista → "
                             "Distribuidor → Fábrica   ·   Custos: R$ 0,50/un "
                             "estoque · R$ 1,00/un backlog · lead time 4 sem "
                             "(fábrica 3)",
                  style="Suave.TLabel", justify="center")\
           .pack(side="bottom", pady=10)


# ========================================================= modo individual/IA
class IndividualSetupFrame(ttk.Frame):
    def __init__(self, app: App):
        super().__init__(app, padding=24)
        self.app = app
        ttk.Label(self, text="Jogo individual", style="Titulo.TLabel")\
           .grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.form = ConfigForm(self)
        self.form.grid(row=1, column=0, sticky="nw", padx=(0, 16))
        quadro = ttk.LabelFrame(self, text="  Quem controla cada elo?  ",
                                padding=8)
        quadro.grid(row=1, column=1, sticky="nw")
        ttk.Label(quadro, text="Elo", style="Suave.TLabel")\
           .grid(row=0, column=1, sticky="w")
        ttk.Label(quadro, text="Controle", style="Suave.TLabel")\
           .grid(row=0, column=2, padx=(12, 0))
        ttk.Label(quadro, text="Modelo de IA", style="Suave.TLabel")\
           .grid(row=0, column=3, padx=(12, 0))
        self.combos = {}
        self.combos_modelo = {}
        rotulos_modelo = [MODELO_LABEL[m] for m in MODELOS]
        for i, r in enumerate(ROLES):
            lin = i + 1
            tk.Label(quadro, text="■", fg=CORES[r],
                     bg=theme.cores()["bg"]).grid(row=lin, column=0, sticky="w")
            ttk.Label(quadro, text=ROLE_LABEL[r] + ":").grid(row=lin, column=1,
                                                             sticky="w", pady=3)
            cb = ttk.Combobox(quadro, values=["Humano", "IA"],
                              state="readonly", width=10)
            cb.set("Humano")
            cb.grid(row=lin, column=2, padx=(12, 0))
            cb.bind("<<ComboboxSelected>>", lambda e: self._sync_modelos())
            self.combos[r] = cb
            cbm = ttk.Combobox(quadro, values=rotulos_modelo,
                               state="disabled", width=18)
            cbm.set(MODELO_LABEL[EQUILIBRADO])
            cbm.grid(row=lin, column=3, padx=(12, 0))
            self.combos_modelo[r] = cbm
        ttk.Label(quadro, text="Marque IA em todos para uma simulação "
                               "automática completa.\nO modelo de IA fica "
                               "disponível quando o elo é controlado por IA.",
                  style="Suave.TLabel",
                  justify="left").grid(row=len(ROLES) + 1, column=0,
                                       columnspan=4, pady=(8, 0), sticky="w")
        botoes = ttk.Frame(self)
        botoes.grid(row=2, column=0, columnspan=2, sticky="w", pady=18)
        ttk.Button(botoes, text="Iniciar partida", style="Accent.TButton",
                   command=self._iniciar).pack(side="left", padx=(0, 8))
        ttk.Button(botoes, text="Voltar",
                   command=lambda: app.mostrar(MenuFrame)).pack(side="left")

    def _sync_modelos(self):
        """Habilita o seletor de modelo apenas para os elos controlados por IA."""
        for r in ROLES:
            estado = "readonly" if self.combos[r].get() == "IA" else "disabled"
            self.combos_modelo[r].configure(state=estado)

    def _modelo_de(self, rotulo):
        for m in MODELOS:
            if MODELO_LABEL[m] == rotulo:
                return m
        return EQUILIBRADO

    def _iniciar(self):
        controles = {r: ("humano" if self.combos[r].get() == "Humano" else "ia")
                     for r in ROLES}
        modelos = {r: self._modelo_de(self.combos_modelo[r].get())
                   for r in ROLES if controles[r] == "ia"}
        self.app.mostrar(IndividualBoardFrame, config=self.form.config(),
                         controles=controles, modelos=modelos)


class IndividualBoardFrame(ttk.Frame):
    def __init__(self, app: App, config: GameConfig, controles: dict,
                 modelos: dict = None):
        super().__init__(app, padding=10)
        self.app, self.cfg, self.controles = app, config, controles
        self.modelos = modelos or {}
        self.engine = GameEngine(config)
        self.ais = make_ai_players(config, self.modelos)
        self.table = GameTable(config, modo="individual",
                               jogadores={r: controles[r] for r in ROLES})
        self.table.add_rows(self.engine.setup_rows())
        self.hist_pedidos = {r: [] for r in ROLES}
        self.views = None
        self._ocupado = False
        self._terminando = False
        self.todos_ia = all(c == "ia" for c in controles.values())

        topo = ttk.Frame(self)
        topo.pack(fill="x")
        self.btn_avancar = ttk.Button(topo, text="Confirmar semana ▶",
                                      style="Accent.TButton",
                                      command=self._confirmar)
        self.btn_avancar.pack(side="left")
        self.btn_tudo = ttk.Button(topo, text="▶▶ Rodar até o fim",
                                   command=self._rodar_tudo)
        self.btn_tudo.pack(side="left", padx=8)
        self.btn_terminar = ttk.Button(topo, text="■ Terminar simulação",
                                       command=self._terminar)
        self.btn_terminar.pack(side="left")
        ttk.Button(topo, text="Abandonar", command=self._abandonar)\
           .pack(side="right")
        self.lbl_custo = ttk.Label(topo, text="", style="H2.TLabel")
        self.lbl_custo.pack(side="right", padx=14)

        self.progresso = ProgressTimeline(self)
        self.progresso.pack(fill="x", pady=(8, 4))

        grade = ttk.Frame(self)
        grade.pack(fill="both", expand=True, pady=4)
        self.paineis = {}
        for i, r in enumerate(ROLES):
            p = NodePanel(grade, r, com_entrada=(controles[r] == "humano"))
            p.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            if controles[r] == "ia":
                nome_modelo = MODELO_LABEL[self.modelos.get(r, EQUILIBRADO)]
                p.status.set(f"IA · {nome_modelo}")
            self.paineis[r] = p
        for col in (0, 1):
            grade.grid_columnconfigure(col, weight=1)
        for lin in (0, 1):
            grade.grid_rowconfigure(lin, weight=1)

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="x", pady=(4, 0))
        self.diagrama = ChainDiagram(self.abas, height=185)
        self.abas.add(self.diagrama, text="  Cadeia (animação)  ")
        self.grafico = MiniChart(self.abas, width=1040, height=185,
                                 titulo="Pedidos colocados por elo (ao vivo)")
        self.abas.add(self.grafico, text="  Gráfico ao vivo  ")

        self._comecar_semana()

    # ------------------------------------------------------------------ fluxo
    def _comecar_semana(self):
        self.views = self.engine.begin_week()
        for r in ROLES:
            self.ais[r].observe(self.views[r])
        self._atualiza_telas()

    def _atualiza_telas(self):
        for r in ROLES:
            self.paineis[r].update_view(self.views[r])
        sem = self.engine.semana
        total = sum(self.views[r]["custo_acum"] for r in ROLES)
        self.lbl_custo.config(
            text=f"Cadeia: R$ {total:.2f}".replace(".", ","))
        self.app.header.set_info(f"Semana {sem} de {self.cfg.semanas}")
        self.progresso.set(sem, self.cfg.semanas, self.cfg.semana_mudanca)
        self.diagrama.set_data(self.engine.snapshot())

    def _decisoes(self, exigir_humanos=True):
        decis, ctrl = {}, {}
        for r in ROLES:
            if self.controles[r] == "humano":
                q = self.paineis[r].ler_pedido()
                if q is None:
                    if exigir_humanos:
                        messagebox.showwarning(
                            "Beer Game", f"Informe um pedido válido para "
                            f"{ROLE_LABEL[r]}.", parent=self)
                        return None
                    q = 0
                decis[r], ctrl[r] = q, "humano"
            else:
                decis[r] = self.ais[r].decide(self.views[r])
                ctrl[r] = "ia"
        return decis, ctrl

    def _confirmar(self):
        if self._ocupado or not self.engine.aguardando_decisoes:
            return
        par = self._decisoes()
        if par is None:
            return
        self._aplicar_semana(*par, animar=True)

    def _aplicar_semana(self, decis, ctrl, animar):
        snap_a = self.engine.snapshot()
        row = self.engine.complete_week(decis, ctrl)
        self.table.add_row(row)
        for r in ROLES:
            self.hist_pedidos[r].append(decis[r])
            if self.controles[r] == "ia":
                self.paineis[r].status.set(f"IA pediu {decis[r]} un")
        self.grafico.plot([(ROLE_LABEL[r], CORES[r], self.hist_pedidos[r])
                           for r in ROLES], choque=self.cfg.semana_mudanca)
        if self.engine.finished() or self._terminando:
            self._fim()
            return
        self.views = self.engine.begin_week()
        for r in ROLES:
            self.ais[r].observe(self.views[r])
        if animar:
            self._ocupado = True
            self._botoes(False)
            self.diagrama.animar(snap_a, self.engine.snapshot(),
                                 ao_fim=self._pos_animacao)
        else:
            self._atualiza_telas()

    def _pos_animacao(self):
        if not self.winfo_exists():
            return
        self._ocupado = False
        self._botoes(True)
        self._atualiza_telas()

    def _botoes(self, ativo: bool):
        estado = "normal" if ativo else "disabled"
        for b in (self.btn_avancar, self.btn_tudo, self.btn_terminar):
            b.configure(state=estado)

    def _rodar_tudo(self):
        if self._ocupado or not self.engine.aguardando_decisoes:
            return
        if not self.todos_ia:
            if not messagebox.askyesno(
                    "Beer Game", "Há elos humanos. Rodar até o fim repetindo "
                    "o valor atualmente digitado em cada painel?", parent=self):
                return
        self._ocupado = True
        self._botoes(False)
        self._passo_automatico()

    def _passo_automatico(self):
        if not self.winfo_exists() or not self.engine.aguardando_decisoes:
            return
        par = self._decisoes(exigir_humanos=False)
        self._aplicar_semana(*par, animar=False)
        # 'finished()' já é True durante a decisão da última semana (a semana
        # é incrementada no begin_week); o critério correto é haver uma
        # semana em aberto aguardando decisões.
        if self.engine.aguardando_decisoes and not self._terminando \
                and self.winfo_exists():
            self.after(60, self._passo_automatico)

    def _terminar(self):
        if self._ocupado or not self.engine.aguardando_decisoes:
            return
        if not messagebox.askyesno(
                "Beer Game", f"Terminar a simulação na semana "
                f"{self.engine.semana} e gerar as estatísticas finais?",
                parent=self):
            return
        self._terminando = True
        par = self._decisoes(exigir_humanos=False)
        self._aplicar_semana(*par, animar=False)

    def _fim(self):
        caminhos = self.table.save_all()
        self._botoes(False)
        self.app.header.set_info("Partida encerrada")
        self.progresso.set(self.table.rows[-1]["semana"], self.cfg.semanas,
                           self.cfg.semana_mudanca)
        show_report(self.app, self.table.rows, self.table.resumo(), caminhos)

    def _abandonar(self):
        if messagebox.askyesno("Beer Game", "Abandonar a partida em andamento?",
                               parent=self):
            self.app.mostrar(MenuFrame)


# ================================================================== modo rede
class HostAdapter:
    """Faz o tabuleiro de rede funcionar para o jogador host (sem socket)."""

    def __init__(self, server):
        self.server = server
        self.ui_queue = server.ui_queue
        self.papel = server.host_papel
        self.is_host = True
        self.config_dict = server.cfg.to_dict()

    def send_decisao(self, semana, quantidade):
        self.server.decisao_local(quantidade)

    def close(self):
        self.server.shutdown()


class ClientAdapter:
    def __init__(self, client, config_dict):
        self.client = client
        self.ui_queue = client.ui_queue
        self.papel = client.papel
        self.is_host = False
        self.config_dict = config_dict
        self.server = None

    def send_decisao(self, semana, quantidade):
        self.client.send_decisao(semana, quantidade)

    def close(self):
        self.client.close()


class NetSetupFrame(ttk.Frame):
    def __init__(self, app: App, host: bool):
        super().__init__(app, padding=24)
        self.app, self.host = app, host
        titulo = "Criar sala (host)" if host else "Entrar em sala"
        ttk.Label(self, text=titulo, style="Titulo.TLabel")\
           .grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        quadro = ttk.LabelFrame(self, text="  Conexão  ", padding=8)
        quadro.grid(row=1, column=0, sticky="nw", padx=(0, 16))
        linha = 0
        ttk.Label(quadro, text="Seu nome:").grid(row=linha, column=0,
                                                 sticky="w", pady=3)
        self.e_nome = ttk.Entry(quadro, width=18)
        self.e_nome.insert(0, "Jogador")
        self.e_nome.grid(row=linha, column=1)
        linha += 1
        if not host:
            ttk.Label(quadro, text="IP do host:").grid(row=linha, column=0,
                                                       sticky="w", pady=3)
            self.e_ip = ttk.Entry(quadro, width=18)
            self.e_ip.insert(0, "192.168.0.")
            self.e_ip.grid(row=linha, column=1)
            linha += 1
        ttk.Label(quadro, text="Porta:").grid(row=linha, column=0,
                                              sticky="w", pady=3)
        self.e_porta = ttk.Entry(quadro, width=18)
        self.e_porta.insert(0, str(PORTA_PADRAO))
        self.e_porta.grid(row=linha, column=1)
        linha += 1
        ttk.Label(quadro, text="Papel desejado:").grid(row=linha, column=0,
                                                       sticky="w", pady=3)
        papeis = [ROLE_LABEL[r] for r in ROLES]
        if host:
            papeis.append("Observador (só acompanha)")
        self.cb_papel = ttk.Combobox(quadro, values=papeis, state="readonly",
                                     width=24)
        self.cb_papel.current(0)
        self.cb_papel.grid(row=linha, column=1)
        if host:
            ttk.Label(quadro, text=f"IP desta máquina: {ip_local()}",
                      foreground=theme.cores()["ok"])\
               .grid(row=linha + 1, column=0, columnspan=2, sticky="w",
                     pady=(8, 0))
            ttk.Label(quadro, text="(informe este IP aos demais jogadores;\n"
                                   "fora da mesma rede, será preciso liberar\n"
                                   "a porta no roteador ou usar VPN)",
                      style="Suave.TLabel", justify="left")\
               .grid(row=linha + 2, column=0, columnspan=2, sticky="w")

        if host:
            self.form = ConfigForm(self)
            self.form.grid(row=1, column=1, sticky="nw")

        botoes = ttk.Frame(self)
        botoes.grid(row=2, column=0, columnspan=2, sticky="w", pady=18)
        ttk.Button(botoes, text="Criar sala" if host else "Conectar",
                   style="Accent.TButton", command=self._ir)\
           .pack(side="left", padx=(0, 8))
        ttk.Button(botoes, text="Voltar",
                   command=lambda: app.mostrar(MenuFrame)).pack(side="left")

    def _papel_escolhido(self):
        idx = self.cb_papel.current()
        return ROLES[idx] if idx < 4 else "observador"

    def _ir(self):
        nome = self.e_nome.get().strip() or "Jogador"
        try:
            porta = int(self.e_porta.get())
        except ValueError:
            messagebox.showerror("Beer Game", "Porta inválida.", parent=self)
            return
        if self.host:
            from server import GameServer
            try:
                srv = GameServer(self.form.config(), porta, nome,
                                 self._papel_escolhido())
                srv.start()
            except OSError as exc:
                messagebox.showerror("Beer Game",
                                     f"Não foi possível abrir a porta "
                                     f"{porta}:\n{exc}", parent=self)
                return
            self.app.registrar_cleanup(srv.shutdown)
            self.app.mostrar(LobbyFrame, server=srv, client=None)
        else:
            from client import GameClient
            ip = self.e_ip.get().strip()
            try:
                cli = GameClient(ip, porta, nome, self._papel_escolhido())
            except OSError as exc:
                messagebox.showerror("Beer Game",
                                     f"Não foi possível conectar em "
                                     f"{ip}:{porta}\n{exc}", parent=self)
                return
            self.app.registrar_cleanup(cli.close)
            self.app.mostrar(LobbyFrame, server=None, client=cli)


class LobbyFrame(ttk.Frame):
    """Sala de espera (host e cliente)."""

    def __init__(self, app: App, server, client):
        super().__init__(app, padding=24)
        self.app, self.server, self.client = app, server, client
        self.config_dict = server.cfg.to_dict() if server else None
        ttk.Label(self, text="Sala de espera", style="Titulo.TLabel")\
           .pack(anchor="w", pady=(0, 10))
        if server:
            ttk.Label(self, text=f"Host nesta máquina — IP {ip_local()} · "
                                 f"porta {server.porta}",
                      foreground=theme.cores()["ok"]).pack(anchor="w")
        self.lista = ttk.Treeview(self, columns=("ocupante",),
                                  show="tree headings", height=4)
        self.lista.heading("#0", text="Papel")
        self.lista.heading("ocupante", text="Ocupado por")
        self.lista.column("#0", width=170)
        self.lista.column("ocupante", width=330)
        self.lista.pack(anchor="w", pady=10, fill="x")
        for r in ROLES:
            self.lista.tag_configure(r, foreground=CORES[r])
        self.lbl_status = ttk.Label(self, text="Aguardando jogadores… papéis "
                                                "sem humano serão jogados "
                                                "pela IA.")
        self.lbl_status.pack(anchor="w")
        botoes = ttk.Frame(self)
        botoes.pack(anchor="w", pady=14)
        if server:
            ttk.Button(botoes, text="▶ Iniciar jogo", style="Accent.TButton",
                       command=server.start_game).pack(side="left",
                                                       padx=(0, 8))
        ttk.Button(botoes, text="Cancelar / Voltar",
                   command=self._voltar).pack(side="left")
        self._poll_id = self.after(120, self._poll)

    def _voltar(self):
        self.after_cancel(self._poll_id)
        self.app.mostrar(MenuFrame)   # cleanups fecham server/cliente

    def _atualiza_lista(self, jogadores):
        self.lista.delete(*self.lista.get_children())
        for r in ROLES:
            j = jogadores.get(r, {})
            if j.get("tipo") == "ia":
                oc = "IA"
            elif j.get("fallback"):
                oc = f"{j.get('nome')} (caiu — IA assumiu)"
            else:
                oc = j.get("nome", "?") + (" (host)" if j.get("tipo") == "local"
                                           else "")
            self.lista.insert("", "end", text=ROLE_LABEL[r], values=(oc,),
                              tags=(r,))

    def _poll(self):
        fila = self.server.ui_queue if self.server else self.client.ui_queue
        try:
            while True:
                msg = fila.get_nowait()
                t = msg.get("tipo")
                if t == "lobby":
                    self._atualiza_lista(msg.get("jogadores", {}))
                elif t == "bem_vindo":
                    self.config_dict = msg.get("config")
                    self.lbl_status.config(
                        text=f"Conectado! Você é: {msg.get('rotulo')}.")
                elif t == "erro":
                    messagebox.showerror("Beer Game", msg.get("msg"),
                                         parent=self)
                    self._voltar()
                    return
                elif t == "desconectado":
                    messagebox.showerror("Beer Game",
                                         "Conexão perdida com o host.",
                                         parent=self)
                    self._voltar()
                    return
                elif t == "inicio_jogo":
                    self.after_cancel(self._poll_id)
                    self._entrar_no_jogo(msg)
                    return
        except queue.Empty:
            pass
        self._poll_id = self.after(120, self._poll)

    def _entrar_no_jogo(self, msg_inicio):
        if self.server:
            if self.server.host_papel == "observador":
                self.app.mostrar(ObserverFrame, server=self.server)
            else:
                self.app.mostrar(NetBoardFrame, adapter=HostAdapter(self.server))
        else:
            cfg = msg_inicio.get("config") or self.config_dict
            self.app.mostrar(NetBoardFrame,
                             adapter=ClientAdapter(self.client, cfg))


class NetBoardFrame(ttk.Frame):
    """Tabuleiro de um jogador em rede (host jogador ou cliente remoto)."""

    def __init__(self, app: App, adapter):
        super().__init__(app, padding=10)
        self.app, self.ad = app, adapter
        self.cfg = GameConfig.from_dict(adapter.config_dict or {})
        self.semana_atual = 0
        self.hist = {"pedido": [], "estoque_liq": []}
        self.fim_mostrado = False

        topo = ttk.Frame(self)
        topo.pack(fill="x")
        ttk.Label(topo, text=f"Você: {ROLE_LABEL.get(self.ad.papel, '?')}",
                  style="H2.TLabel").pack(side="left")
        ttk.Button(topo, text="Sair", command=self._sair).pack(side="right")
        if self.ad.is_host:
            ttk.Button(topo, text="■ Terminar simulação",
                       command=self._terminar).pack(side="right", padx=8)
            ttk.Button(topo, text="⚡ IA decide pelos ausentes",
                       command=self._forcar_ia).pack(side="right")

        self.progresso = ProgressTimeline(self)
        self.progresso.pack(fill="x", pady=(8, 4))
        self.progresso.set(0, self.cfg.semanas, self.cfg.semana_mudanca)

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True, pady=6)
        self.painel = NodePanel(corpo, self.ad.papel, com_entrada=True,
                                ao_confirmar=self._confirmar)
        self.painel.pack(side="left", fill="y", padx=(0, 10))
        self.painel.habilitar(False)
        direita = ttk.Frame(corpo)
        direita.pack(side="left", fill="both", expand=True)
        self.abas = ttk.Notebook(direita)
        self.abas.pack(fill="both", expand=True)
        aba_fluxo = ttk.Frame(self.abas)
        self.fluxo = NodeFlow(aba_fluxo, self.ad.papel, height=230)
        self.fluxo.pack(fill="x", anchor="n")
        ttk.Label(aba_fluxo, style="Suave.TLabel", justify="left",
                  wraplength=560,
                  text="Você só enxerga a sua posição: o que chega do "
                       "fornecedor, o que envia ao cliente de jusante e os "
                       "pedidos a caminho. Os chips avançam um slot por "
                       "semana (lead time).")\
           .pack(anchor="w", padx=10, pady=(8, 0))
        self.abas.add(aba_fluxo, text="  Meu fluxo (animação)  ")
        graf = ttk.Frame(self.abas)
        self.g_ped = MiniChart(graf, width=560, height=180,
                               titulo="Seus pedidos por semana")
        self.g_ped.pack(fill="both", expand=True)
        self.g_est = MiniChart(graf, width=560, height=180,
                               shade_negativo=True,
                               titulo="Seu estoque líquido (estoque − backlog)")
        self.g_est.pack(fill="both", expand=True, pady=(8, 0))
        self.abas.add(graf, text="  Gráficos  ")
        self._view_atual = None
        self._ocupado_anim = False

        self.lbl_status = ttk.Label(self, text="Aguardando início…",
                                    foreground=theme.cores()["alerta"])
        self.lbl_status.pack(anchor="w", pady=(4, 0))
        self.app.header.set_info("Aguardando início…")
        self._poll_id = self.after(120, self._poll)

    def _forcar_ia(self):
        if self.ad.is_host and self.ad.server:
            self.ad.server.forcar_ia.set()

    def _terminar(self):
        if not (self.ad.is_host and self.ad.server):
            return
        if messagebox.askyesno("Beer Game",
                               f"Terminar a simulação na semana "
                               f"{max(1, self.semana_atual)} e gerar as "
                               f"estatísticas finais para todos?",
                               parent=self):
            self.ad.server.terminar_simulacao()

    def _confirmar(self, painel):
        q = painel.ler_pedido()
        if q is None:
            messagebox.showwarning("Beer Game", "Informe um pedido válido.",
                                   parent=self)
            return
        self.ad.send_decisao(self.semana_atual, q)
        self.painel.habilitar(False)
        self.lbl_status.config(text=f"Pedido de {q} un enviado — aguardando "
                                    f"os demais elos…")

    def _poll(self):
        try:
            while True:
                msg = self.ad.ui_queue.get_nowait()
                self._trata(msg)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._poll_id = self.after(120, self._poll)

    def _trata(self, msg):
        t = msg.get("tipo")
        if t == "estado_semana":
            view = msg["view"]
            self.semana_atual = view["semana"]
            self.app.header.set_info(f"Semana {self.semana_atual} "
                                     f"de {self.cfg.semanas}")
            self.progresso.set(self.semana_atual, self.cfg.semanas,
                               self.cfg.semana_mudanca)
            self.painel.update_view(view)
            liq = view["estoque"] - view["backlog"]
            self.hist["estoque_liq"].append(liq)
            cor = CORES[self.ad.papel]
            self.g_est.plot([("Estoque líquido", cor, self.hist["estoque_liq"])],
                            choque=self.cfg.semana_mudanca)
            # animação do segmento do próprio elo (igual ao individual)
            if self._view_atual is not None:
                self.fluxo.animar(self._view_atual, view)
            else:
                self.fluxo.set_view(view)
            self._view_atual = view
            if msg.get("pendente"):
                self.painel.habilitar(True)
                self.lbl_status.config(text="Decida o seu pedido desta semana.")
            else:
                self.painel.habilitar(False)
        elif t == "semana_fechada":
            self.hist["pedido"].append(msg.get("pedido", 0))
            self.g_ped.plot([("Pedido", CORES[self.ad.papel],
                              self.hist["pedido"])],
                            choque=self.cfg.semana_mudanca)
        elif t == "aviso":
            self.lbl_status.config(text=msg.get("msg", ""))
        elif t == "lobby":
            pass
        elif t == "desconectado":
            if not self.fim_mostrado:
                messagebox.showerror("Beer Game",
                                     "Conexão perdida com o host.\nVocê pode "
                                     "reconectar pelo menu (Entrar em sala) "
                                     "para retomar o papel.", parent=self)
                self._sair(confirma=False)
        elif t == "fim_de_jogo":
            self.fim_mostrado = True
            self.painel.habilitar(False)
            self.app.header.set_info("Partida encerrada")
            self._relatorio(msg)

    def _relatorio(self, msg):
        linhas, resumo = msg.get("linhas", []), msg.get("resumo", {})
        caminhos = msg.get("arquivos_host") if self.ad.is_host else None

        def salvar_local():
            cfg = GameConfig.from_dict(self.ad.config_dict)
            t = GameTable(cfg, modo="rede(cliente)")
            t.add_rows(linhas)
            return t.save_all()

        show_report(self.app, linhas, resumo, caminhos,
                    salvar_local=None if self.ad.is_host else salvar_local)

    def _sair(self, confirma=True):
        if confirma and not self.fim_mostrado:
            if not messagebox.askyesno("Beer Game", "Sair da partida? A IA "
                                       "assumirá o seu papel.", parent=self):
                return
        self.after_cancel(self._poll_id)
        self.app.mostrar(MenuFrame)


class ObserverFrame(ttk.Frame):
    """Visão do host observador (ex.: professor conduzindo a dinâmica),
    com o diagrama animado da cadeia completo."""

    def __init__(self, app: App, server):
        super().__init__(app, padding=10)
        self.app, self.server = app, server
        self._snap_atual = None
        topo = ttk.Frame(self)
        topo.pack(fill="x")
        self.lbl = ttk.Label(topo, text="Observando a partida…",
                             style="H2.TLabel")
        self.lbl.pack(side="left")
        ttk.Button(topo, text="Encerrar sala", command=self._sair)\
           .pack(side="right")
        ttk.Button(topo, text="■ Terminar simulação",
                   command=self._terminar).pack(side="right", padx=8)
        ttk.Button(topo, text="⚡ IA decide pelos ausentes",
                   command=server.forcar_ia.set).pack(side="right")
        self.progresso = ProgressTimeline(self)
        self.progresso.pack(fill="x", pady=(8, 4))
        self.progresso.set(0, server.cfg.semanas, server.cfg.semana_mudanca)

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, pady=(4, 0))
        aba_cadeia = ttk.Frame(self.abas)
        self.diagrama = ChainDiagram(aba_cadeia, height=300)
        self.diagrama.pack(fill="x", anchor="n")
        self.abas.add(aba_cadeia, text="  Cadeia (animação)  ")
        c = theme.cores()
        quadro_log = ttk.Frame(self.abas)
        self.log = tk.Text(quadro_log, height=18, state="disabled",
                           bg=c["card"], fg=c["texto"], insertbackground=c["texto"],
                           relief="flat", highlightthickness=1,
                           highlightbackground=c["borda"])
        self.log.pack(fill="both", expand=True)
        self.abas.add(quadro_log, text="  Registro  ")
        self._poll_id = self.after(150, self._poll)

    def _terminar(self):
        if messagebox.askyesno("Beer Game",
                               "Terminar a simulação na semana corrente e "
                               "gerar as estatísticas finais para todos?",
                               parent=self):
            self.server.terminar_simulacao()

    def _escreve(self, txt):
        self.log.configure(state="normal")
        self.log.insert("end", txt + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _aplicar_snapshot(self, snap, animar):
        """Mostra (ou anima até) o snapshot da cadeia."""
        if snap is None:
            return
        if animar and self._snap_atual is not None:
            self.diagrama.animar(self._snap_atual, snap)
        else:
            self.diagrama.set_data(snap)
        self._snap_atual = snap

    def _poll(self):
        try:
            while True:
                msg = self.server.ui_queue.get_nowait()
                t = msg.get("tipo")
                if t == "obs_semana":
                    ag = msg.get("aguardando", [])
                    nomes = (", ".join(ROLE_LABEL[r] for r in ag)
                             if ag else "ninguém")
                    self.lbl.config(text=f"Semana {msg['semana']} — "
                                         f"aguardando: {nomes}")
                    self.app.header.set_info(f"Semana {msg['semana']} de "
                                             f"{self.server.cfg.semanas}")
                    self.progresso.set(msg["semana"], self.server.cfg.semanas,
                                       self.server.cfg.semana_mudanca)
                    # 1ª vez na semana: mostra o estado; chegadas seguintes só
                    # atualizam os pendentes (mesma semana, sem animar)
                    if msg.get("snapshot") is not None \
                            and self._snap_atual is not None \
                            and msg["snapshot"]["semana"] != self._snap_atual["semana"]:
                        self.diagrama.set_data(msg["snapshot"])
                        self._snap_atual = msg["snapshot"]
                    elif self._snap_atual is None:
                        self._aplicar_snapshot(msg.get("snapshot"), animar=False)
                    self._escreve(f"Semana {msg['semana']}: aguardando {nomes}")
                elif t == "obs_fechou":
                    # transição da semana fechada → anima a cadeia
                    self._aplicar_snapshot(msg.get("snapshot"), animar=True)
                elif t == "aviso":
                    self._escreve("⚠ " + msg.get("msg", ""))
                elif t == "lobby":
                    pass
                elif t == "fim_de_jogo":
                    self.lbl.config(text="Partida encerrada")
                    self.app.header.set_info("Partida encerrada")
                    self._escreve("Fim de jogo. Arquivos: "
                                  + "; ".join(msg.get("arquivos_host", [])))
                    show_report(self.app, msg.get("linhas", []),
                                msg.get("resumo", {}),
                                msg.get("arquivos_host"))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._poll_id = self.after(150, self._poll)

    def _sair(self):
        if messagebox.askyesno("Beer Game", "Encerrar a sala para todos?",
                               parent=self):
            self.after_cancel(self._poll_id)
            self.app.mostrar(MenuFrame)
