# -*- coding: utf-8 -*-
"""
Servidor (host) do Beer Game em rede.

O host é a autoridade única do estado. Cada cliente recebe apenas a visão do
seu papel (informação limitada). Papéis sem humano são jogados pela IA; se um
humano cair, a IA assume ("humano→ia") e o jogador pode reconectar e retomar.

Mensagens aceitas do cliente:
  {"tipo":"entrar_sala","nome":...,"papel_desejado":...}
  {"tipo":"decisao_pedido","semana":...,"quantidade":...}
Mensagens enviadas:
  bem_vindo, erro, lobby, inicio_jogo, estado_semana, semana_fechada,
  aviso, fim_de_jogo
"""
import queue
import socket
import threading

from engine import GameEngine, GameConfig, ROLES, ROLE_LABEL
from ai_player import make_ai_players
from storage import GameTable
from protocol import send_json, iter_json

OBSERVADOR = "observador"


class _Remote:
    """Conexão remota de um jogador."""
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.vivo = True

    def send(self, msg):
        if not self.vivo:
            return
        try:
            send_json(self.sock, msg)
        except OSError:
            self.vivo = False

    def close(self):
        self.vivo = False
        try:
            self.sock.close()
        except OSError:
            pass


class GameServer:
    def __init__(self, config: GameConfig, porta: int, host_nome: str, host_papel: str):
        """host_papel: um dos ROLES ou 'observador'."""
        self.cfg = config
        self.porta = porta
        self.host_nome = host_nome
        self.host_papel = host_papel
        # slots[papel] = {"tipo": "ia"|"local"|"remoto", "nome": str,
        #                 "conn": _Remote|None, "fallback": bool}
        self.slots = {r: {"tipo": "ia", "nome": "IA", "conn": None, "fallback": False}
                      for r in ROLES}
        if host_papel in ROLES:
            self.slots[host_papel] = {"tipo": "local", "nome": host_nome,
                                      "conn": None, "fallback": False}
        self.ui_queue = queue.Queue()        # mensagens para a interface do host
        self.decisoes = {r: queue.Queue() for r in ROLES}
        self.forcar_ia = threading.Event()   # host: "IA decide pelos ausentes agora"
        self.terminar_cedo = threading.Event()  # host: encerra na semana corrente
        self.jogo_iniciado = False
        self.encerrar = threading.Event()
        self.semana_atual = 0
        self._ultima_view = {}
        self._pendentes_lock = threading.Lock()
        self._pendentes = set()
        self._srv_sock = None
        self.table = None
        self.resultado = None               # (resumo, rows, caminhos) ao final

    # ------------------------------------------------------------- listening
    def start(self):
        self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv_sock.bind(("0.0.0.0", self.porta))
        self._srv_sock.listen(8)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._push_lobby()

    def _accept_loop(self):
        while not self.encerrar.is_set():
            try:
                sock, addr = self._srv_sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client_thread,
                             args=(_Remote(sock, addr),), daemon=True).start()

    # ------------------------------------------------------------ handshake
    def _papel_para(self, desejado: str) -> str:
        livres = [r for r in ROLES if self.slots[r]["tipo"] == "ia"
                  or (self.slots[r]["tipo"] == "remoto" and self.slots[r]["fallback"])]
        if not self.jogo_iniciado:
            livres = [r for r in ROLES if self.slots[r]["tipo"] == "ia"] \
                     + [r for r in ROLES if self.slots[r]["fallback"]]
        if desejado in livres:
            return desejado
        return livres[0] if livres else None

    def _client_thread(self, conn: _Remote):
        it = iter_json(conn.sock)
        try:
            primeiro = next(it)
        except StopIteration:
            conn.close()
            return
        if primeiro.get("tipo") != "entrar_sala":
            conn.send({"tipo": "erro", "msg": "Handshake inválido."})
            conn.close()
            return
        nome = str(primeiro.get("nome") or "Jogador")[:30]
        papel = self._papel_para(primeiro.get("papel_desejado"))
        if papel is None:
            conn.send({"tipo": "erro", "msg": "Sala cheia: todos os papéis já têm jogadores."})
            conn.close()
            return
        retomada = self.jogo_iniciado and self.slots[papel]["fallback"]
        self.slots[papel] = {"tipo": "remoto", "nome": nome, "conn": conn, "fallback": False}
        conn.send({"tipo": "bem_vindo", "papel": papel, "rotulo": ROLE_LABEL[papel],
                   "config": self.cfg.to_dict(), "jogo_iniciado": self.jogo_iniciado})
        self._push_lobby()
        if retomada and papel in self._ultima_view:
            with self._pendentes_lock:
                pendente = papel in self._pendentes
            conn.send({"tipo": "inicio_jogo", "config": self.cfg.to_dict()})
            conn.send({"tipo": "estado_semana", "view": self._ultima_view[papel],
                       "pendente": pendente})
        # loop de mensagens
        for msg in it:
            self._handle(papel, msg)
        # desconectou
        slot = self.slots[papel]
        if slot["conn"] is conn:
            slot["fallback"] = True
            slot["conn"] = None
            self._avisar_host(f"{nome} ({ROLE_LABEL[papel]}) desconectou — IA assumiu o papel.")
            self._push_lobby()
        conn.close()

    def _handle(self, papel: str, msg: dict):
        if msg.get("tipo") == "decisao_pedido":
            try:
                q = max(0, int(msg.get("quantidade")))
            except (TypeError, ValueError):
                return
            if int(msg.get("semana", -1)) == self.semana_atual:
                self.decisoes[papel].put(q)

    # ------------------------------------------------------------- broadcast
    def _envia(self, papel: str, msg: dict):
        slot = self.slots[papel]
        if slot["tipo"] == "local":
            self.ui_queue.put(msg)
        elif slot["tipo"] == "remoto" and slot["conn"] and slot["conn"].vivo:
            slot["conn"].send(msg)

    def _broadcast(self, msg: dict, incluir_host=True):
        for r in ROLES:
            self._envia(r, msg)
        if incluir_host and self.host_papel == OBSERVADOR:
            self.ui_queue.put(msg)

    def _push_lobby(self):
        jogadores = {r: {"nome": self.slots[r]["nome"],
                         "tipo": self.slots[r]["tipo"],
                         "fallback": self.slots[r]["fallback"],
                         "rotulo": ROLE_LABEL[r]} for r in ROLES}
        self._broadcast({"tipo": "lobby", "jogadores": jogadores,
                         "jogo_iniciado": self.jogo_iniciado})

    def _avisar_host(self, texto: str):
        self.ui_queue.put({"tipo": "aviso", "msg": texto})

    # ----------------------------------------------------------- jogo (host)
    def start_game(self):
        if self.jogo_iniciado:
            return
        self.jogo_iniciado = True
        self._broadcast({"tipo": "inicio_jogo", "config": self.cfg.to_dict()})
        threading.Thread(target=self._game_loop, daemon=True).start()

    def terminar_simulacao(self):
        """Encerra a partida na semana corrente e gera as estatísticas finais."""
        if self.jogo_iniciado:
            self.terminar_cedo.set()
            self.forcar_ia.set()   # fecha a semana em aberto com a IA, se preciso
            self._broadcast({"tipo": "aviso",
                             "msg": "O host encerrou a simulação — gerando o "
                                    "relatório final."})

    def decisao_local(self, quantidade: int):
        """Decisão do jogador host (chamada pela GUI)."""
        if self.host_papel in ROLES:
            self.decisoes[self.host_papel].put(max(0, int(quantidade)))

    def _controlador_humano(self, r: str) -> bool:
        s = self.slots[r]
        if s["tipo"] == "local":
            return True
        return s["tipo"] == "remoto" and not s["fallback"] and s["conn"] and s["conn"].vivo

    def _game_loop(self):
        eng = GameEngine(self.cfg)
        ais = make_ai_players(self.cfg, getattr(self.cfg, "modelos_ia", None))
        jogadores = {r: self.slots[r]["nome"] if self.slots[r]["tipo"] != "ia" else "IA"
                     for r in ROLES}
        self.table = GameTable(self.cfg, modo="rede", jogadores=jogadores)
        self.table.add_rows(eng.setup_rows())

        while (not eng.finished() and not self.encerrar.is_set()
               and not self.terminar_cedo.is_set()):
            views = eng.begin_week()
            self.semana_atual = eng.semana
            self._ultima_view = views
            for r in ROLES:
                ais[r].observe(views[r])
            # esvazia decisões atrasadas de semanas anteriores
            for r in ROLES:
                while not self.decisoes[r].empty():
                    try:
                        self.decisoes[r].get_nowait()
                    except queue.Empty:
                        break
            self.forcar_ia.clear()

            decis, ctrl = {}, {}
            with self._pendentes_lock:
                self._pendentes = {r for r in ROLES if self._controlador_humano(r)}
            for r in ROLES:
                pendente = r in self._pendentes
                self._envia(r, {"tipo": "estado_semana", "view": views[r],
                                "pendente": pendente})
                if not pendente:
                    decis[r] = ais[r].decide(views[r])
                    ctrl[r] = "ia" if self.slots[r]["tipo"] == "ia" else "humano→ia"
            if self.host_papel == OBSERVADOR:
                self.ui_queue.put({"tipo": "obs_semana", "semana": eng.semana,
                                   "aguardando": sorted(self._pendentes),
                                   "snapshot": eng.snapshot()})

            # espera as decisões humanas
            while True:
                with self._pendentes_lock:
                    pend = set(self._pendentes)
                if not pend or self.encerrar.is_set():
                    break
                for r in list(pend):
                    try:
                        q = self.decisoes[r].get(timeout=0.05)
                    except queue.Empty:
                        if not self._controlador_humano(r) or self.forcar_ia.is_set():
                            decis[r] = ais[r].decide(views[r])
                            ctrl[r] = "humano→ia"
                            with self._pendentes_lock:
                                self._pendentes.discard(r)
                            self._envia(r, {"tipo": "aviso",
                                            "msg": f"A IA decidiu por você na semana {eng.semana}."})
                        continue
                    decis[r] = q
                    ctrl[r] = "humano"
                    with self._pendentes_lock:
                        self._pendentes.discard(r)
                    if self.host_papel == OBSERVADOR:
                        self.ui_queue.put({"tipo": "obs_semana", "semana": eng.semana,
                                           "aguardando": sorted(self._pendentes),
                                           "snapshot": eng.snapshot()})

            if self.encerrar.is_set():
                break
            row = eng.complete_week(decis, ctrl)
            self.table.add_row(row)
            for r in ROLES:
                self._envia(r, {"tipo": "semana_fechada", "semana": row["semana"],
                                "pedido": decis[r]})
            if self.host_papel == OBSERVADOR:
                self.ui_queue.put({"tipo": "obs_fechou", "semana": row["semana"],
                                   "snapshot": eng.snapshot()})

        # fim de jogo
        caminhos = []
        if self.table is not None and not self.encerrar.is_set():
            caminhos = self.table.save_all()
            resumo = self.table.resumo()
            self.resultado = (resumo, self.table.rows, caminhos)
            self._broadcast({"tipo": "fim_de_jogo", "resumo": resumo,
                             "linhas": self.table.rows, "arquivos_host": caminhos})

    # --------------------------------------------------------------- término
    def shutdown(self):
        self.encerrar.set()
        try:
            if self._srv_sock:
                self._srv_sock.close()
        except OSError:
            pass
        for r in ROLES:
            s = self.slots[r]
            if s["conn"]:
                s["conn"].close()
