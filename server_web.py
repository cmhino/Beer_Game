# -*- coding: utf-8 -*-
"""
Beer Game CISLOG — Servidor Web v2.2 (FastAPI + WebSocket)
"""
import asyncio, random, string, sys, time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

_BASE = Path(__file__).parent
sys.path.insert(0, str(_BASE))

MODULES_OK = False
GameEngine = GameConfig = AIPlayer = make_ai_players = StorageManager = None

try:
    from engine import GameEngine, GameConfig
    print("[OK] engine.py")
except ImportError as e:
    print(f"[ERRO] engine.py: {e}")

try:
    from ai_player import AIPlayer, make_ai_players
    print("[OK] ai_player.py  (AIPlayer, make_ai_players)")
except ImportError as e:
    print(f"[WARN] ai_player.py: {e}")

try:
    from storage import StorageManager
    print("[OK] storage.py")
except ImportError as e:
    print(f"[WARN] storage.py: {e}")

MODULES_OK = (GameEngine is not None and GameConfig is not None)

app = FastAPI(title="Beer Game CISLOG", version="2.2-web")

PAPEIS = ["varejista", "atacadista", "distribuidor", "fabrica"]
NOME_PAPEL = {"varejista":"Varejista","atacadista":"Atacadista",
              "distribuidor":"Distribuidor","fabrica":"Fábrica","observador":"Observador"}
CONFIG_PADRAO = dict(semanas=36, estoque_inicial=12, modelos_ia={})

# ── Utilitários ────────────────────────────────────────────────────────────────

def gerar_codigo():
    chars = string.ascii_uppercase.replace("O","").replace("I","") + string.digits
    return "BG-" + "".join(random.choices(chars, k=4))

def _criar_game_config(d: dict):
    if GameConfig is None:
        return None
    try:
        return GameConfig.from_dict(d)
    except Exception:
        cfg = GameConfig()
        for k in ("semanas","estoque_inicial"):
            if k in d:
                setattr(cfg, k, int(d[k]))
        return cfg

def _view_para_ai(view: dict) -> dict:
    """Garante os campos que AIPlayer.observe/decide esperam."""
    return {
        "pedido_recebido":   view.get("pedido_recebido", 4),
        "estoque":           view.get("estoque", 0),
        "backlog":           view.get("backlog",  0),
        "em_transito":       view.get("em_transito", 0),
        "pedidos_pendentes": view.get("pedidos_pendentes", 0),
    }

def _ai_fallback(view: dict) -> int:
    return max(0, int(view.get("pedido_recebido", 4)))

# ── Jogador ────────────────────────────────────────────────────────────────────

class Jogador:
    def __init__(self, ws, nome, papel):
        self.ws, self.nome, self.papel, self.vivo = ws, nome, papel, True
    async def send(self, msg):
        if not self.vivo: return
        try:
            await self.ws.send_json(msg)
        except Exception:
            self.vivo = False

# ── SalaWeb ────────────────────────────────────────────────────────────────────

class SalaWeb:
    def __init__(self, room_id, config):
        self.room_id  = room_id
        self.config   = config
        self.cfg      = _criar_game_config(config)
        self.engine   = GameEngine(self.cfg) if MODULES_OK else None
        self._ai: dict = {}
        if MODULES_OK and make_ai_players:
            try:
                self._ai = make_ai_players(self.cfg)
            except Exception as e:
                print(f"  [WARN] make_ai_players: {e}")

        self._views: dict  = {}   # {papel: view_dict} — atualizado em cada begin_week
        self._hist: dict   = {    # histórico acumulado por papel
            p: {"estoque":[], "backlog":[], "pedido":[], "custo_acum":[]}
            for p in PAPEIS
        }
        self._semanas_hist: list = []

        self.conexoes:    dict[str, Jogador] = {}
        self.observadores: list[Jogador]    = []
        self.decisoes:    dict[str, int]    = {}
        self.iniciado   = False
        self.finalizado = False
        self.host_papel = None
        self.criado_em  = int(time.time())
        self._lock = asyncio.Lock()

    # ── Getters ───────────────────────────────────────────────────────────────
    @property
    def semana_atual(self):
        return int(getattr(self.engine, "semana", getattr(self.engine, "semana_atual", 0)))

    @property
    def total_semanas(self):
        return self.cfg.semanas if self.cfg else self.config.get("semanas", 36)

    def _snap(self, papel):
        """Retorna view corrente do papel — prefere _views (do begin_week)."""
        if papel in self._views:
            return self._views[papel]
        if self.engine and hasattr(self.engine, "snapshot"):
            try:
                s = self.engine.snapshot(papel)
                if isinstance(s, dict): return s
            except Exception: pass
        return {"papel": papel, "semana": self.semana_atual}

    def _todos_snaps(self):
        """Dict com snapshot de todos os papéis (para observadores)."""
        return {p: self._snap(p) for p in PAPEIS}

    def _papeis_pendentes(self):
        return [p for p in PAPEIS if p not in self.decisoes]

    def _todos_decidiram(self):
        return all(p in self.decisoes for p in PAPEIS)

    def _humanos_online(self):
        return {p for p, j in self.conexoes.items() if j.vivo and p in PAPEIS}

    # ── Broadcast ─────────────────────────────────────────────────────────────
    async def broadcast(self, msg, excluir=None):
        for p, j in list(self.conexoes.items()):
            if p != excluir: await j.send(msg)
        for obs in self.observadores:
            await obs.send(msg)

    async def broadcast_snapshots(self):
        """Snapshots individuais → jogadores; snapshot completo → observadores."""
        for papel, jog in list(self.conexoes.items()):
            if jog.vivo:
                await jog.send({"tipo": "snapshot", **self._snap(papel)})
        snap_all = self._todos_snaps()
        for obs in self.observadores:
            await obs.send({"tipo": "snapshot_obs",
                            "semana": self.semana_atual,
                            "total_semanas": self.total_semanas,
                            "views": snap_all})

    # ── Histórico ─────────────────────────────────────────────────────────────
    def _acumular_historico(self):
        sem = self.semana_atual
        if sem in self._semanas_hist: return
        self._semanas_hist.append(sem)
        for p in PAPEIS:
            v = self._snap(p)
            self._hist[p]["estoque"].append(v.get("estoque", 0))
            self._hist[p]["backlog"].append(v.get("backlog", 0))
            self._hist[p]["pedido"].append(v.get("pedido_recebido", 0))
            self._hist[p]["custo_acum"].append(v.get("custo_acum", 0))

    # ── Lógica do jogo ────────────────────────────────────────────────────────
    async def _iniciar_semana(self):
        if self.engine and hasattr(self.engine, "begin_week"):
            try:
                self._views = self.engine.begin_week()
            except Exception as e:
                print(f"[WARN] begin_week: {e}")
        self._acumular_historico()
        await self.broadcast_snapshots()
        await self.broadcast({
            "tipo": "aguardar_decisao",
            "semana": self.semana_atual,
            "total_semanas": self.total_semanas,
            "pendentes": PAPEIS.copy(),
        })

    async def registrar_decisao(self, papel, quantidade):
        if papel not in PAPEIS or papel in self.decisoes: return
        self.decisoes[papel] = max(0, int(quantidade))
        print(f"  [DEC] {papel}: {quantidade}  (sem {self.semana_atual})")
        await self.broadcast({"tipo":"decisao_registrada","papel":papel,
                               "pendentes":self._papeis_pendentes()})
        await self._ia_preenche_ausentes()
        if self._todos_decidiram():
            await self._avancar_semana()

    async def _ia_preenche_ausentes(self):
        for papel in self._papeis_pendentes():
            jog = self.conexoes.get(papel)
            if jog and jog.vivo: continue
            ai = self._ai.get(papel)
            view = _view_para_ai(self._snap(papel))
            if ai:
                try:
                    if hasattr(ai, "observe"): ai.observe(view)
                    qtd = int(ai.decide(view)) if hasattr(ai, "decide") else _ai_fallback(view)
                except Exception as e:
                    print(f"  [WARN] AI {papel}: {e}")
                    qtd = _ai_fallback(view)
            else:
                qtd = _ai_fallback(view)
            self.decisoes[papel] = max(0, qtd)
            print(f"  [IA]  {papel}: {qtd}")

    async def forcar_ia_todos(self):
        await self._ia_preenche_ausentes()
        if self._todos_decidiram():
            await self._avancar_semana()

    async def _avancar_semana(self):
        humanos = self._humanos_online()
        ctrl = {p: ("humano" if p in humanos else "ia") for p in PAPEIS}
        try:
            if hasattr(self.engine, "complete_week"):
                self.engine.complete_week(self.decisoes.copy(), ctrl)
            elif hasattr(self.engine, "registrar_decisao"):
                for p, q in self.decisoes.items():
                    self.engine.registrar_decisao(p, q)
                if hasattr(self.engine, "avancar_semana"):
                    self.engine.avancar_semana()
        except Exception as e:
            print(f"[ERRO] _avancar_semana: {e}")
        finally:
            self.decisoes.clear()

        acabou = False
        try: acabou = self.engine.finished()
        except Exception: pass

        if acabou:
            await self._finalizar()
        else:
            await self._iniciar_semana()

    async def _finalizar(self):
        self.finalizado = True
        # montar relatório completo
        relatorio = self._montar_relatorio()
        try:
            if StorageManager:
                st = StorageManager()
                if hasattr(st, "salvar"): st.salvar(self.engine, self.room_id)
        except Exception as e:
            print(f"[WARN] storage: {e}")
        await self.broadcast({"tipo": "fim_jogo", "relatorio": relatorio})

    def _montar_relatorio(self):
        """Monta o relatório final completo com histórico para os gráficos."""
        # Tenta relatorio_final() do engine como base
        base = {}
        try:
            if hasattr(self.engine, "relatorio_final"):
                base = self.engine.relatorio_final() or {}
        except Exception: pass

        # Complementar com dados históricos coletados localmente
        elos = []
        for i, p in enumerate(PAPEIS):
            h = self._hist[p]
            v = self._snap(p)
            nome_jogador = (self.conexoes[p].nome
                            if p in self.conexoes else "(IA)")
            # Calcular stats a partir do histórico
            estoque_list = h["estoque"]
            backlog_list = h["backlog"]
            pedido_list  = h["pedido"]
            elos.append({
                "papel":          p,
                "nome_papel":     NOME_PAPEL[p],
                "jogador":        nome_jogador,
                "custo_acum":     round(v.get("custo_acum", 0), 2),
                "estoque_medio":  round(sum(estoque_list)/len(estoque_list), 1) if estoque_list else 0,
                "estoque_min":    min(estoque_list) if estoque_list else 0,
                "estoque_max":    max(estoque_list) if estoque_list else 0,
                "backlog_total":  sum(backlog_list),
                "backlog_max":    max(backlog_list) if backlog_list else 0,
                "pedido_max":     max(pedido_list) if pedido_list else 0,
                "pedido_medio":   round(sum(pedido_list)/len(pedido_list),1) if pedido_list else 0,
            })

        # Ordenar por custo (menor = melhor)
        elos_rank = sorted(elos, key=lambda e: e["custo_acum"])

        return {
            "room_id":     self.room_id,
            "semanas":     self._semanas_hist,
            "total_semanas": self.total_semanas,
            "elos":        elos,
            "ranking":     [e["papel"] for e in elos_rank],
            "historico": {
                p: {
                    "estoque":   self._hist[p]["estoque"],
                    "backlog":   self._hist[p]["backlog"],
                    "pedido":    self._hist[p]["pedido"],
                    "custo_acum":self._hist[p]["custo_acum"],
                }
                for p in PAPEIS
            },
            "custo_total": round(sum(e["custo_acum"] for e in elos), 2),
            **base,
        }

    def estado_lobby(self):
        jogadores = {}
        for p in PAPEIS:
            j = self.conexoes.get(p)
            jogadores[p] = ({"nome":j.nome,"tipo":"humano","online":True}
                            if j and j.vivo else {"nome":"(IA)","tipo":"ia","online":False})
        return {"tipo":"estado_lobby","room_id":self.room_id,
                "iniciado":self.iniciado,"config":self.config,"jogadores":jogadores}

# ── Repositório ────────────────────────────────────────────────────────────────
rooms: dict[str, SalaWeb] = {}

# ── WebSocket ──────────────────────────────────────────────────────────────────
@app.websocket("/ws/{room_id}")
async def ws_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    room_id = room_id.upper()
    sala:   Optional[SalaWeb] = rooms.get(room_id)
    jogador: Optional[Jogador] = None

    try:
        async for msg in ws.iter_json():
            tipo = msg.get("tipo","")

            if tipo == "criar_sala":
                if room_id in rooms:
                    await ws.send_json({"tipo":"erro","mensagem":"Sala já existe."}); continue
                if not MODULES_OK:
                    await ws.send_json({"tipo":"erro","mensagem":"engine.py não encontrado."}); continue
                config = {**CONFIG_PADRAO, **msg.get("config",{})}
                sala = SalaWeb(room_id, config); rooms[room_id] = sala
                papel = msg.get("papel","observador"); nome = msg.get("nome","Host")
                jogador = Jogador(ws, nome, papel)
                if papel in PAPEIS:
                    sala.conexoes[papel] = jogador; sala.host_papel = papel
                else:
                    sala.observadores.append(jogador); sala.host_papel = "observador"
                await ws.send_json({"tipo":"sala_criada","room_id":room_id})
                await ws.send_json(sala.estado_lobby())
                print(f"[SALA] Criada: {room_id}  host={nome}({papel})")

            elif tipo == "entrar_sala":
                sala = rooms.get(room_id)
                if not sala:
                    await ws.send_json({"tipo":"erro","mensagem":f"Sala '{room_id}' não encontrada."}); continue
                papel = msg.get("papel_desejado","observador"); nome = msg.get("nome","Jogador")
                if papel in PAPEIS:
                    ex = sala.conexoes.get(papel)
                    if ex and ex.vivo:
                        await ws.send_json({"tipo":"erro","mensagem":f"Papel '{NOME_PAPEL[papel]}' já ocupado."}); continue
                    jogador = Jogador(ws, nome, papel); sala.conexoes[papel] = jogador
                else:
                    papel = "observador"; jogador = Jogador(ws, nome, "observador")
                    sala.observadores.append(jogador)
                await ws.send_json({"tipo":"bem_vindo","papel":papel,
                    "nome_papel":NOME_PAPEL.get(papel,papel),"room_id":room_id,"config":sala.config})
                await sala.broadcast(sala.estado_lobby())
                if sala.iniciado and papel in PAPEIS:
                    await ws.send_json({"tipo":"snapshot",**sala._snap(papel)})
                    await ws.send_json({"tipo":"aguardar_decisao","semana":sala.semana_atual,
                        "total_semanas":sala.total_semanas,"pendentes":sala._papeis_pendentes()})
                elif sala.iniciado and papel == "observador":
                    snaps = sala._todos_snaps()
                    await ws.send_json({"tipo":"snapshot_obs","semana":sala.semana_atual,
                        "total_semanas":sala.total_semanas,"views":snaps})
                print(f"[SALA] {nome}({papel}) → {room_id}")

            elif tipo == "iniciar_jogo":
                if sala and not sala.iniciado:
                    sala.iniciado = True
                    await sala.broadcast({"tipo":"jogo_iniciado","semana":sala.semana_atual,
                        "total_semanas":sala.total_semanas})
                    await sala._iniciar_semana()
                    print(f"[SALA] Iniciado: {room_id}")

            elif tipo == "decisao_pedido":
                if sala and sala.iniciado and jogador and jogador.papel in PAPEIS:
                    async with sala._lock:
                        await sala.registrar_decisao(jogador.papel, int(msg.get("quantidade",0)))

            elif tipo == "ia_decide_todos":
                if sala and sala.iniciado:
                    async with sala._lock: await sala.forcar_ia_todos()

            elif tipo == "terminar_simulacao":
                if sala and sala.iniciado and not sala.finalizado:
                    async with sala._lock: await sala._finalizar()

            elif tipo == "ping":
                await ws.send_json({"tipo":"pong"})

    except WebSocketDisconnect: pass
    except Exception as e:
        print(f"[ERRO] ws/{room_id}: {type(e).__name__}: {e}")
    finally:
        if jogador:
            jogador.vivo = False
            if sala and jogador.papel in PAPEIS:
                await sala.broadcast({"tipo":"jogador_desconectado",
                    "papel":jogador.papel,"nome":jogador.nome})
                print(f"[SALA] {jogador.nome}({jogador.papel}) saiu de {room_id}")

# ── HTTP ───────────────────────────────────────────────────────────────────────
STATIC = _BASE / "static"

@app.get("/")
async def root():       return FileResponse(STATIC / "index.html")

@app.get("/game")
async def game_pg():    return FileResponse(STATIC / "game.html")

@app.get("/professor")
async def prof_pg():    return FileResponse(STATIC / "professor.html")

@app.get("/api/status")
async def api_status():
    return {"ok":True,"modules_ok":MODULES_OK,"salas_ativas":len(rooms),
            "salas":{rid:{"iniciado":s.iniciado,"finalizado":s.finalizado,
                          "semana":s.semana_atual,"total":s.total_semanas,
                          "jogadores":{p:j.nome for p,j in s.conexoes.items() if j.vivo}}
                     for rid,s in rooms.items()}}

@app.get("/api/rooms")
async def api_rooms():
    resultado = []
    for rid, s in rooms.items():
        jogadores = {}
        for p in PAPEIS:
            j = s.conexoes.get(p)
            jogadores[p] = {"nome":j.nome if j else "(IA)",
                             "tipo":"humano" if j and j.vivo else "ia",
                             "online": j.vivo if j else False}
        resultado.append({
            "room_id":     rid,
            "iniciado":    s.iniciado,
            "finalizado":  s.finalizado,
            "semana":      s.semana_atual,
            "total_semanas": s.total_semanas,
            "jogadores":   jogadores,
            "observadores": len(s.observadores),
            "criado_em":   s.criado_em,
        })
    resultado.sort(key=lambda x: x["criado_em"], reverse=True)
    return resultado

@app.get("/api/nova_sala")
async def nova_sala():
    for _ in range(10):
        c = gerar_codigo()
        if c not in rooms: return {"room_id":c}
    return JSONResponse({"erro":"falha ao gerar código"},status_code=500)

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

if __name__ == "__main__":
    if not MODULES_OK:
        print(f"\n[ERRO FATAL] engine.py não encontrado em {_BASE}\n"); sys.exit(1)
    print("\n"+"="*55)
    print("  🍺  Beer Game CISLOG — Servidor Web v2.2")
    print("  Jogo:      http://localhost:8000")
    print("  Professor: http://localhost:8000/professor")
    print("  Status:    http://localhost:8000/api/status")
    print("="*55+"\n")
    uvicorn.run("server_web:app", host="0.0.0.0", port=8000, reload=True)
