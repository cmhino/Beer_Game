// Beer Game CISLOG — app.js v2.2
"use strict";

const G = {
  ws: null, roomId: null, nome: null, papel: null, nomePapel: null,
  eCriador: false, semana: 0, totalSemanas: 36,
  snap: null, decidiu: false,
  ultimoPedido: null,   // último pedido CONFIRMADO pelo jogador; null = ainda não jogou
  hist: { semanas:[], estoque:[], backlog:[], pedido:[] },
  obsHist: { semanas:[], est:{}, ped:{} },  // para observador
  chart: null, obsChartEst: null, obsChartPed: null,
  rptCharts: {},
  relatorio: null,
  config: { semanas:36, estoque_inicial:12 },
};

const NOME_PAPEL = {
  varejista:"Varejista", atacadista:"Atacadista",
  distribuidor:"Distribuidor", fabrica:"Fábrica", observador:"Observador"
};
const CORES = {
  varejista:"#D4882E", atacadista:"#2A7D4F",
  distribuidor:"#185FA5", fabrica:"#C4392C"
};

// ─── INIT ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const p = new URLSearchParams(window.location.search);
  G.roomId       = (p.get("room") || "").toUpperCase();
  G.nome         = p.get("nome") || "Jogador";
  G.papel        = p.get("papel") || "observador";
  G.eCriador     = p.get("criador") === "1";
  G.config.semanas        = parseInt(p.get("semanas") || "36");
  G.config.estoque_inicial= parseInt(p.get("estoque") || "12");
  G.config.ai_model       = p.get("ai") || "equilibrado";
  G.totalSemanas          = G.config.semanas;
  if (!G.roomId) { window.location.href = "/"; return; }
  if (localStorage.getItem("theme") === "dark") applyTheme("dark");
  conectar();
});

// ─── WS ───────────────────────────────────────────────────────────────────────
function wsUrl() {
  const pr = location.protocol === "https:" ? "wss:" : "ws:";
  return `${pr}//${location.host}/ws/${G.roomId}`;
}

function conectar() {
  mostrarTela("loading");
  G.ws = new WebSocket(wsUrl());
  G.ws.onopen = () => {
    setConexao(true);
    if (G.eCriador) {
      enviar({ tipo:"criar_sala", nome:G.nome, papel:G.papel,
               config: G.config });
    } else {
      enviar({ tipo:"entrar_sala", nome:G.nome, papel_desejado:G.papel });
    }
  };
  G.ws.onmessage = (ev) => {
    try { handleMsg(JSON.parse(ev.data)); }
    catch(e) { console.error(e); }
  };
  G.ws.onclose = () => { setConexao(false); setTimeout(conectar, 3000); };
  G.ws.onerror = () => G.ws.close();
}

function enviar(msg) {
  if (G.ws && G.ws.readyState === WebSocket.OPEN)
    G.ws.send(JSON.stringify(msg));
}

// ─── DISPATCHER ───────────────────────────────────────────────────────────────
function handleMsg(msg) {
  const t = msg.tipo;
  if (t === "sala_criada")          { G.roomId = msg.room_id; }
  else if (t === "bem_vindo")        { receberBoasVindas(msg); }
  else if (t === "estado_lobby")     { atualizarLobby(msg); mostrarTela("lobby"); }
  else if (t === "jogo_iniciado")    { iniciarTela(msg); }
  else if (t === "snapshot")         { processarSnapshot(msg); }
  else if (t === "snapshot_obs")     { processarSnapshotObs(msg); }
  else if (t === "aguardar_decisao") { processarAguardar(msg); }
  else if (t === "decisao_registrada") { atualizarPendentes(msg.pendentes); }
  else if (t === "fim_jogo")         { mostrarRelatorio(msg.relatorio); }
  else if (t === "jogador_desconectado") { mostrarToast(`${msg.nome} desconectou`,"amber"); }
  else if (t === "erro")             { mostrarToast("❌ " + msg.mensagem, "red"); }
}

function receberBoasVindas(msg) {
  G.papel     = msg.papel;
  G.nomePapel = msg.nome_papel || NOME_PAPEL[msg.papel] || msg.papel;
  if (msg.config) { G.config = msg.config; G.totalSemanas = msg.config.semanas || 36; }
}

// ─── LOBBY ────────────────────────────────────────────────────────────────────
function atualizarLobby(msg) {
  const { room_id, jogadores, iniciado } = msg;
  G.roomId = room_id;
  el("lobby-room-code").textContent = room_id;
  el("share-url").value = `${location.origin}/?room=${room_id}`;
  const btnStart = el("btn-start");
  if (btnStart) btnStart.classList.toggle("hidden", !G.eCriador || iniciado);

  const tbody = el("lobby-tbody"); if (!tbody) return;
  tbody.innerHTML = "";
  ["varejista","atacadista","distribuidor","fabrica"].forEach(p => {
    const info = jogadores[p] || {nome:"(IA)",tipo:"ia",online:false};
    const voce = p === G.papel;
    tbody.innerHTML += `<tr>
      <td>${NOME_PAPEL[p]}</td>
      <td>${info.nome}${voce ? ' <span class="badge-voce">você</span>' : ''}</td>
      <td><span class="badge-${info.tipo==='humano'?'humano':'ia'}">
        ${info.tipo==='humano'?'👤 humano':'🤖 IA'}
      </span></td></tr>`;
  });
}

function iniciarJogo()  { enviar({ tipo:"iniciar_jogo" }); }
function copyLink() {
  navigator.clipboard.writeText(el("share-url").value)
    .then(() => mostrarToast("Link copiado!", "green"));
}

// ─── INICIAR TELA ─────────────────────────────────────────────────────────────
function iniciarTela(msg) {
  G.semana = msg.semana || 1;
  G.totalSemanas = msg.total_semanas || G.totalSemanas;
  const isObs = G.papel === "observador";
  mostrarTela(isObs ? "obs" : "game");
  if (!isObs) iniciarChart();
  else iniciarChartsObs();
}

// ─── SNAPSHOT (JOGADOR) ───────────────────────────────────────────────────────
function processarSnapshot(s) {
  G.snap   = s;
  G.semana = s.semana || G.semana;
  atualizarMetricas(s);
  atualizarPipeline(s);
  adicionarHist(s);
  atualizarChart();
  atualizarHeader();
}

function atualizarMetricas(s) {
  setText("mv-estoque",    s.estoque ?? "–");
  setText("mv-backlog",    s.backlog ?? "–");
  setText("mv-pedido-rec", s.pedido_recebido ?? "–");
  setText("mv-enviado",    s.enviado ?? "–");
  setText("mv-custo",      fmt(s.custo_semana));
  setText("mv-custo-acum", fmt(s.custo_acum));
  // Semáforo estoque
  const e = s.estoque ?? 0, b = s.backlog ?? 0;
  setCls("mc-estoque","metric-card "+(e===0?"status-alert":e<6?"status-warn":"status-ok"));
  setCls("mc-backlog", "metric-card "+(b>10?"status-alert":b>0?"status-warn":"status-ok"));
}

function atualizarPipeline(s) {
  // Pipeline semântico — dois fluxos opostos:
  //
  // FLUXO DE BENS  (fornecedor → elo → cliente):
  //   em_transito  →  ESTOQUE  →  enviado
  //
  // FLUXO DE INFORMAÇÃO / PEDIDOS  (cliente → elo → fornecedor):
  //   pedido_recebido  →  (decisão atual = slot vazio)  →  pedidos_pendentes
  //
  // "em_transito"       = soma dos slots de transporte vindos do fornecedor (2 slots cheios)
  // "pedidos_pendentes" = soma dos slots de info indo ao fornecedor  (1 slot cheio + 1 vazio = a decisão atual)
  // Ambos são totais; individual slots não são enviados pelo servidor.

  const em_transito       = s.em_transito       ?? "–";
  const pedidos_pendentes = s.pedidos_pendentes  ?? "–";
  const estoque           = s.estoque            ?? "–";
  const enviado           = s.enviado            ?? "–";
  const pedido_recebido   = s.pedido_recebido    ?? "–";

  // Fluxo de bens
  setText("pv-bens-transito",  em_transito);
  setText("pv-bens-estoque",   estoque);
  setText("pv-bens-enviado",   enviado);

  // Fluxo de pedidos — o slot vazio mostra "?" (aguardando decisão atual)
  setText("pv-ped-recebido",   pedido_recebido);
  setText("pv-ped-pendentes",  pedidos_pendentes);

  // Semáforo visual no slot de trânsito
  const tr = typeof em_transito === "number" ? em_transito : parseInt(em_transito) || 0;
  const trCls = "pipe-node "+(tr === 0 ? "status-alert" : tr < 4 ? "status-warn" : "");
  setCls("pn-transito", trCls);
}

function adicionarHist(s) {
  const sem = s.semana; if (!sem) return;
  const idx = G.hist.semanas.indexOf(sem);
  if (idx >= 0) {
    G.hist.estoque[idx] = s.estoque ?? 0;
    G.hist.backlog[idx] = s.backlog ?? 0;
    G.hist.pedido[idx]  = s.pedido_recebido ?? 0;
    return;
  }
  G.hist.semanas.push(sem);
  G.hist.estoque.push(s.estoque ?? 0);
  G.hist.backlog.push(s.backlog ?? 0);
  G.hist.pedido.push(s.pedido_recebido ?? 0);
}

// ─── SNAPSHOT OBS ─────────────────────────────────────────────────────────────
function processarSnapshotObs(msg) {
  const { semana, total_semanas, views } = msg;
  G.semana = semana || G.semana;
  G.totalSemanas = total_semanas || G.totalSemanas;
  atualizarHeader();
  atualizarGridObs(views, semana);
  acumularHistObs(views, semana);
  atualizarChartsObs();
}

function atualizarGridObs(views, semana) {
  const grid = el("obs-grid"); if (!grid) return;
  grid.innerHTML = "";
  ["varejista","atacadista","distribuidor","fabrica"].forEach(p => {
    const v = views[p] || {};
    const est = v.estoque ?? 0, bl = v.backlog ?? 0;
    const cor = est===0?"status-alert":est<6?"status-warn":"status-ok";
    const corBl = bl>10?"status-alert":bl>0?"status-warn":"status-ok";
    const nomej = v.jogador || "";
    grid.innerHTML += `
      <div style="background:var(--bg-card);border:1px solid var(--border);
                  border-radius:var(--radius);padding:14px 16px;
                  border-top:4px solid ${CORES[p]}">
        <div style="font-size:13px;font-weight:600;color:${CORES[p]};margin-bottom:8px">
          ${NOME_PAPEL[p]}${nomej ? ` <span style="color:var(--text-muted);font-weight:400">· ${nomej}</span>` : ""}
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center">
          <div>
            <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase">Estoque</div>
            <div style="font-size:22px;font-weight:700" class="${cor}">${est}</div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase">Backlog</div>
            <div style="font-size:22px;font-weight:700" class="${corBl}">${bl}</div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase">Custo acum.</div>
            <div style="font-size:16px;font-weight:600">${fmt(v.custo_acum)}</div>
          </div>
        </div>
        <div style="margin-top:8px;font-size:12px;color:var(--text-muted)">
          Em trânsito: <b>${v.em_transito ?? "–"}</b> · 
          Pedidos pend.: <b>${v.pedidos_pendentes ?? "–"}</b>
        </div>
      </div>`;
  });
  setText("obs-semana", semana || G.semana);
  setText("obs-total", G.totalSemanas);
}

function acumularHistObs(views, semana) {
  if (!semana) return;
  const hist = G.obsHist;
  if (!hist.semanas.includes(semana)) {
    hist.semanas.push(semana);
    ["varejista","atacadista","distribuidor","fabrica"].forEach(p => {
      if (!hist.est[p]) hist.est[p] = [];
      if (!hist.ped[p]) hist.ped[p] = [];
      const v = views[p] || {};
      hist.est[p].push(v.estoque ?? 0);
      hist.ped[p].push(v.pedido_recebido ?? 0);
    });
  }
}

// ─── AGUARDAR DECISÃO ─────────────────────────────────────────────────────────
function processarAguardar(msg) {
  G.semana = msg.semana || G.semana;
  G.decidiu = false;
  atualizarHeader();
  if (G.papel !== "observador") {
    const pd = el("panel-decisao"), pa = el("panel-aguardando");
    if (msg.pendentes.includes(G.papel)) {
      if (pd) pd.classList.remove("hidden");
      if (pa) pa.classList.add("hidden");
      setText("dec-semana", G.semana);
      const btn = el("btn-confirmar");
      if (btn) { btn.disabled = false; btn.textContent = "✓ Confirmar pedido"; }
      sugerirPedido();
    }
  }
}

function atualizarPendentes(pendentes) {
  if (!G.decidiu) return;
  const wl = el("waiting-list"); if (!wl) return;
  ["varejista","atacadista","distribuidor","fabrica"].forEach(p => {
    const decidiu = !pendentes.includes(p);
    // atualizar badge se existir
  });
  const wl2 = el("waiting-list");
  if (wl2) wl2.innerHTML = ["varejista","atacadista","distribuidor","fabrica"].map(p => {
    const ok = !pendentes.includes(p);
    return `<span class="badge-${ok?'decided':'waiting'}">${ok?'✓':'⏳'} ${NOME_PAPEL[p]}</span>`;
  }).join("");
}

function sugerirPedido() {
  const s = G.snap; if (!s) return;
  const inp = el("input-pedido"); if (!inp) return;

  // Regra: o campo de pedido pertence ao jogador.
  // Só é inicializado automaticamente na semana 1 (antes de qualquer confirmação).
  // Nas semanas seguintes, mantém sempre o ÚLTIMO PEDIDO CONFIRMADO e nunca é sobrescrito.
  if (G.ultimoPedido === null) {
    // Primeira semana: sugere a demanda inicial como ponto de partida
    inp.value = s.pedido_recebido ?? 4;
  } else {
    // Semanas seguintes: restaurar exatamente o último pedido confirmado
    inp.value = G.ultimoPedido;
  }

  // Informações contextuais abaixo do campo (sem tocar no valor do input)
  const pend = s.pedidos_pendentes ?? "–";
  const tran = s.em_transito ?? "–";
  setText("sugestao-txt",
    `Último pedido confirmado: ${G.ultimoPedido ?? "—"} · ` +
    `Demanda recebida: ${s.pedido_recebido ?? "–"} · ` +
    `Em trânsito: ${tran} · Pedidos pend.: ${pend}`);
}

function adj(delta) {
  const e = el("input-pedido");
  e.value = Math.max(0, parseInt(e.value||"0") + delta);
}

function confirmarPedido() {
  const qtd = parseInt(el("input-pedido").value);
  if (isNaN(qtd) || qtd < 0) { mostrarToast("Quantidade inválida","red"); return; }
  G.decidiu = true;
  G.ultimoPedido = qtd;   // ← guarda o pedido confirmado para restaurar na próxima rodada
  enviar({ tipo:"decisao_pedido", semana:G.semana, quantidade:qtd });
  const btn = el("btn-confirmar");
  if (btn) { btn.disabled = true; btn.textContent = `✓ Pedido ${qtd} confirmado`; }
  const pd = el("panel-decisao"), pa = el("panel-aguardando");
  if (pd) pd.classList.add("hidden");
  if (pa) {
    pa.classList.remove("hidden");
    const wl = el("waiting-list");
    if (wl) wl.innerHTML = ["varejista","atacadista","distribuidor","fabrica"]
      .filter(p => p !== G.papel)
      .map(p => `<span class="badge-waiting">⏳ ${NOME_PAPEL[p]}</span>`).join("");
    const btnIA = el("btn-ia-decide");
    if (btnIA) btnIA.classList.toggle("hidden", !G.eCriador);
  }
}

function iaDecide()     { enviar({ tipo:"ia_decide_todos" }); }
function terminarJogo() { if(confirm("Encerrar a simulação agora?")) enviar({tipo:"terminar_simulacao"}); }

// ─── CHARTS JOGADOR ───────────────────────────────────────────────────────────
function iniciarChart() {
  const ctx = el("chart-hist"); if (!ctx || G.chart) return;
  G.chart = new Chart(ctx, {
    type:"line",
    data:{ labels:[], datasets:[
      { label:"Estoque", data:[], borderColor:"#2A7D4F",
        backgroundColor:"rgba(42,125,79,0.08)", borderWidth:2, tension:.3, fill:true, pointRadius:3 },
      { label:"Backlog",  data:[], borderColor:"#C4392C",
        backgroundColor:"rgba(196,57,44,0.08)", borderWidth:2, borderDash:[5,3],
        tension:.3, fill:true, pointRadius:3 }
    ]},
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:false }, tooltip:{ mode:"index", intersect:false } },
      scales:{ x:{ ticks:{ autoSkip:true, maxTicksLimit:12 } }, y:{ beginAtZero:true } } }
  });
}

function atualizarChart() {
  if (!G.chart) return;
  G.chart.data.labels = G.hist.semanas;
  G.chart.data.datasets[0].data = G.hist.estoque;
  G.chart.data.datasets[1].data = G.hist.backlog;
  G.chart.update("none");
}

// ─── CHARTS OBSERVADOR ────────────────────────────────────────────────────────
function iniciarChartsObs() {
  const cfg = (id, label) => ({
    responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ display:true, position:"top",
      labels:{ boxWidth:12, font:{ size:11 } } } },
    scales:{ x:{ ticks:{ autoSkip:true, maxTicksLimit:12 } }, y:{ beginAtZero:true } }
  });
  const papeis = ["varejista","atacadista","distribuidor","fabrica"];
  ["obs-chart-est","obs-chart-ped"].forEach((id,idx) => {
    const ctx = el(id); if (!ctx) return;
    const cKey = idx===0?"obsChartEst":"obsChartPed";
    if (G[cKey]) return;
    G[cKey] = new Chart(ctx, {
      type:"line",
      data:{ labels:[], datasets: papeis.map(p => ({
        label: NOME_PAPEL[p], data:[],
        borderColor: CORES[p], borderWidth:2, tension:.3, fill:false, pointRadius:2
      }))},
      options: cfg(id, idx===0?"Estoque":"Pedidos")
    });
  });
}

function atualizarChartsObs() {
  const papeis = ["varejista","atacadista","distribuidor","fabrica"];
  [[G.obsChartEst, G.obsHist.est],[G.obsChartPed, G.obsHist.ped]].forEach(([ch,data]) => {
    if (!ch) return;
    ch.data.labels = G.obsHist.semanas;
    papeis.forEach((p,i) => { ch.data.datasets[i].data = data[p] || []; });
    ch.update("none");
  });
}

// ─── RELATÓRIO FINAL ──────────────────────────────────────────────────────────
function mostrarRelatorio(rpt) {
  if (!rpt) { mostrarToast("Jogo encerrado!","green"); return; }
  G.relatorio = rpt;
  mostrarTela("report");

  setText("rpt-sub", `Sala ${rpt.room_id || G.roomId} · ${rpt.total_semanas || G.totalSemanas} semanas`);

  const semanas = rpt.semanas || [];
  const hist    = rpt.historico || {};
  const elos    = rpt.elos || [];
  const ranking = rpt.ranking || [];
  const papeis  = ["varejista","atacadista","distribuidor","fabrica"];

  // PÓDIO
  const podio = el("rpt-podio");
  if (podio) {
    const medals = ["🥇","🥈","🥉","4️⃣"];
    podio.innerHTML = ranking.map((p, i) => {
      const info = elos.find(e => e.papel === p) || {};
      return `<div style="flex:1;min-width:140px;text-align:center;
                           background:var(--bg-card);border:1px solid var(--border);
                           border-top:4px solid ${CORES[p]};border-radius:var(--radius);
                           padding:16px 10px">
        <div style="font-size:28px">${medals[i]}</div>
        <div style="font-size:14px;font-weight:600;color:${CORES[p]}">${NOME_PAPEL[p]}</div>
        <div style="font-size:12px;color:var(--text-muted)">${info.jogador||"(IA)"}</div>
        <div style="font-size:20px;font-weight:700;margin-top:6px">${fmt(info.custo_acum)}</div>
        <div style="font-size:10px;color:var(--text-muted)">Custo total</div>
      </div>`;
    }).join("");
  }

  // TABELA
  const tbody = el("rpt-tbody"), tfoot = el("rpt-tfoot");
  if (tbody) {
    tbody.innerHTML = "";
    const ordenados = [...elos].sort((a,b)=>a.custo_acum-b.custo_acum);
    ordenados.forEach((e,i) => {
      const cls = i===0?"rank-1":i===ordenados.length-1?"rank-4":"";
      tbody.innerHTML += `<tr class="${cls}">
        <td>${medals_arr[i]}</td>
        <td style="color:${CORES[e.papel]};font-weight:600">${NOME_PAPEL[e.papel]}</td>
        <td>${e.jogador||"(IA)"}</td>
        <td><b>${fmt(e.custo_acum)}</b></td>
        <td>${e.estoque_medio}</td>
        <td>${e.backlog_total}</td>
        <td>${e.pedido_max}</td>
      </tr>`;
    });
    if (tfoot) {
      const total = elos.reduce((s,e)=>s+e.custo_acum,0);
      tfoot.innerHTML = `<tr style="background:var(--amber-faint)">
        <td colspan="3" style="font-weight:600">Total da cadeia</td>
        <td><b>${fmt(total)}</b></td>
        <td colspan="3"></td>
      </tr>`;
    }
  }

  // CHARTS — Estoque
  criarChartRelatorio("rpt-chart-est", semanas, papeis, p => hist[p]?.estoque||[], "Estoque");
  // CHARTS — Bullwhip (pedidos)
  criarChartRelatorio("rpt-chart-bull", semanas, papeis, p => hist[p]?.pedido||[], "Pedido");
  // CHARTS — Custo acumulado
  criarChartRelatorio("rpt-chart-custo", semanas, papeis, p => hist[p]?.custo_acum||[], "Custo acum.");
}

const medals_arr = ["🥇","🥈","🥉","4️⃣"];

function criarChartRelatorio(canvasId, labels, papeis, dataFn, labelSuffix) {
  const ctx = el(canvasId); if (!ctx) return;
  const key = canvasId;
  if (G.rptCharts[key]) G.rptCharts[key].destroy();
  G.rptCharts[key] = new Chart(ctx, {
    type:"line",
    data:{ labels, datasets: papeis.map(p => ({
      label: NOME_PAPEL[p], data: dataFn(p),
      borderColor: CORES[p], borderWidth:2.5,
      tension:.3, fill:false, pointRadius:2
    }))},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:true, position:"top",
        labels:{ boxWidth:12, font:{ size:11 } } } },
      scales:{ x:{ ticks:{ autoSkip:true, maxTicksLimit:12 } }, y:{ beginAtZero:true } }
    }
  });
}

function exportarRelatorio() {
  const blob = new Blob([JSON.stringify(G.relatorio,null,2)],{type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `beergame_${G.roomId}_relatorio.json`;
  a.click();
}

// ─── HEADER ───────────────────────────────────────────────────────────────────
function atualizarHeader() {
  setText("hdr-semana", `Semana ${G.semana} / ${G.totalSemanas}`);
  setText("hdr-papel",  G.nomePapel || NOME_PAPEL[G.papel] || G.papel);
  setText("hdr-room",   G.roomId);
  setText("dec-semana", G.semana);
  setText("obs-semana", G.semana);
  setText("obs-total",  G.totalSemanas);
}

// ─── UI HELPERS ───────────────────────────────────────────────────────────────
function mostrarTela(nome) {
  ["loading","lobby","game","obs","report"].forEach(n => {
    const e = el(`screen-${n}`);
    if (e) e.classList.toggle("hidden", n !== nome);
  });
  const hdr = el("game-header");
  if (hdr) hdr.classList.toggle("hidden", nome !== "game" && nome !== "obs");
  // controles do host no painel obs
  const hc = el("host-controls");
  if (hc) hc.classList.toggle("hidden", !G.eCriador);
}

function setConexao(online) {
  const e = el("hdr-conn"); if (!e) return;
  e.className = online ? "conn-online" : "conn-offline";
  e.title = online ? "Conectado" : "Reconectando...";
}

function setText(id, val) {
  const e = el(id);
  if (e) e.textContent = (val !== undefined && val !== null) ? val : "–";
}
function setCls(id, cls) {
  const e = el(id); if (e) e.className = cls;
}
function el(id) { return document.getElementById(id); }
function fmt(v) {
  if (v === undefined || v === null) return "–";
  return Number(v).toLocaleString("pt-BR",{minimumFractionDigits:0,maximumFractionDigits:1});
}

let _toastTmr = null;
function mostrarToast(msg, cor="amber") {
  let e = el("toast");
  if (!e) {
    e = document.createElement("div"); e.id = "toast";
    e.style.cssText = "position:fixed;bottom:20px;left:50%;transform:translateX(-50%);"
      + "padding:10px 20px;border-radius:8px;font-size:14px;font-weight:500;"
      + "z-index:9999;transition:opacity .3s;box-shadow:0 4px 12px rgba(0,0,0,.2);";
    document.body.appendChild(e);
  }
  const c = {green:["#EAF6EE","#2A7D4F"],amber:["#FFF8E1","#B87000"],red:["#FDECEA","#C4392C"]};
  const [bg,txt] = c[cor]||c.amber;
  Object.assign(e.style,{background:bg,color:txt,border:`1px solid ${txt}`,opacity:"1"});
  e.textContent = msg;
  clearTimeout(_toastTmr);
  _toastTmr = setTimeout(()=>{ e.style.opacity="0"; },3500);
}

function toggleTheme() {
  applyTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark");
}
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme",t);
  localStorage.setItem("theme",t);
}

setInterval(()=>enviar({tipo:"ping"}),25000);
