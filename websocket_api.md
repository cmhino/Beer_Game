# Beer Game CISLOG — Especificação da API WebSocket

## Visão geral

Comunicação: **JSON sobre WebSocket** (substitui o protocolo TCP+newline do `protocol.py`).

- Endpoint: `ws://host:8000/ws/{ROOM_ID}`
- Produção: `wss://seuapp.render.com/ws/{ROOM_ID}`
- Todas as mensagens têm o campo `"tipo"` identificador.

---

## Mensagens: Cliente → Servidor

### `criar_sala`
Enviada pelo host ao se conectar pela primeira vez.

```json
{
  "tipo": "criar_sala",
  "nome": "Prof. Celso",
  "papel": "observador",
  "config": {
    "semanas": 36,
    "estoque_inicial": 12,
    "ai_model": "equilibrado"
  }
}
```
- `papel`: `varejista|atacadista|distribuidor|fabrica|observador`
- `ai_model`: `equilibrado|enxuto|cauteloso`

---

### `entrar_sala`
Enviada por cada jogador ao se conectar.

```json
{
  "tipo": "entrar_sala",
  "nome": "Aluno 1",
  "papel_desejado": "varejista"
}
```
- Se o papel já estiver ocupado, o servidor responde com `erro`.

---

### `iniciar_jogo`
Enviada pelo host para iniciar a simulação.

```json
{ "tipo": "iniciar_jogo" }
```
- Válida apenas antes do jogo começar.

---

### `decisao_pedido`
Enviada pelo jogador com a quantidade pedida na semana atual.

```json
{
  "tipo":       "decisao_pedido",
  "semana":     5,
  "quantidade": 8
}
```
- `quantidade` ≥ 0
- Ignorada se o jogador já decidiu nessa semana.

---

### `ia_decide_todos`
Host solicita que a IA decida pelos jogadores pendentes.

```json
{ "tipo": "ia_decide_todos" }
```

---

### `terminar_simulacao`
Host encerra o jogo antes do fim das semanas.

```json
{ "tipo": "terminar_simulacao" }
```

---

### `ping`
Keepalive (evita timeout de WebSocket em hospedagens gratuitas).

```json
{ "tipo": "ping" }
```

---

## Mensagens: Servidor → Cliente

### `sala_criada`
Confirmação de criação da sala.

```json
{ "tipo": "sala_criada", "room_id": "BG-A3F7" }
```

---

### `bem_vindo`
Confirmação de entrada do jogador.

```json
{
  "tipo":       "bem_vindo",
  "papel":      "varejista",
  "nome_papel": "Varejista",
  "room_id":    "BG-A3F7",
  "config":     { "semanas": 36, "estoque_inicial": 12, "ai_model": "equilibrado" }
}
```

---

### `estado_lobby`
Transmitido para todos quando um jogador entra ou sai (antes do início).

```json
{
  "tipo":    "estado_lobby",
  "room_id": "BG-A3F7",
  "iniciado": false,
  "config":  { "semanas": 36, "estoque_inicial": 12, "ai_model": "equilibrado" },
  "jogadores": {
    "varejista":    { "nome": "Aluno 1", "tipo": "humano", "online": true  },
    "atacadista":   { "nome": "Aluno 2", "tipo": "humano", "online": true  },
    "distribuidor": { "nome": "(IA)",    "tipo": "ia",     "online": false },
    "fabrica":      { "nome": "(IA)",    "tipo": "ia",     "online": false }
  }
}
```

---

### `jogo_iniciado`
Transmitido a todos quando o host inicia.

```json
{
  "tipo":          "jogo_iniciado",
  "semana":        1,
  "total_semanas": 36
}
```

---

### `snapshot`
Estado completo do elo — enviado a cada jogador individualmente
(jogador A recebe apenas dados do papel A).

```json
{
  "tipo":           "snapshot",
  "papel":          "varejista",
  "semana":         5,
  "estoque_inicial": 12,
  "pedido_recebido": 8,
  "recebido":        4,
  "enviado":         8,
  "backlog":         0,
  "estoque_final":   8,
  "posicao_estoque": 8,
  "pedido_colocado": null,
  "transp_slot1":    4,
  "transp_slot2":    4,
  "info_slot1":      4,
  "info_slot2":      4,
  "custo_semana":    8.0,
  "custo_acum":      40.0
}
```
- `pedido_colocado: null` → jogador ainda não decidiu nesta semana.

---

### `aguardar_decisao`
Informa que a semana avançou e todos devem decidir.

```json
{
  "tipo":          "aguardar_decisao",
  "semana":        5,
  "total_semanas": 36,
  "pendentes":     ["varejista", "atacadista", "distribuidor", "fabrica"]
}
```

---

### `decisao_registrada`
Notifica todos quando um papel confirma seu pedido.

```json
{
  "tipo":      "decisao_registrada",
  "papel":     "varejista",
  "pendentes": ["atacadista", "distribuidor"]
}
```

---

### `fim_jogo`
Enviado ao final das semanas ou após `terminar_simulacao`.

```json
{
  "tipo": "fim_jogo",
  "relatorio": {
    "semanas": [1, 2, 3, ...],
    "elos": [
      {
        "papel":         "varejista",
        "custo_acum":    340.5,
        "estoque_medio": 9.2,
        "backlog_max":   3
      }
    ],
    "historico_pedidos": {
      "varejista":    [4, 4, 4, 6, 8, ...],
      "atacadista":   [4, 4, 5, 7, 9, ...],
      "distribuidor": [4, 4, 5, 8, 12,...],
      "fabrica":      [4, 4, 6, 9, 14,...]
    }
  }
}
```

---

### `jogador_desconectado`
Transmitido a todos quando um jogador perde conexão.

```json
{
  "tipo":  "jogador_desconectado",
  "papel": "atacadista",
  "nome":  "Aluno 2"
}
```
A IA assume automaticamente o papel desconectado.

---

### `erro`
Resposta de erro a uma mensagem inválida.

```json
{ "tipo": "erro", "mensagem": "Papel 'varejista' já está ocupado." }
```

---

### `pong`
Resposta ao keepalive.

```json
{ "tipo": "pong" }
```

---

## Fluxo completo de uma partida

```
Host abre /game?room=BG-A3F7&criador=1
  → WS conecta
  → envia: criar_sala
  ← recebe: sala_criada + estado_lobby

Aluno 1 abre /game?room=BG-A3F7&papel=varejista
  → envia: entrar_sala
  ← recebe: bem_vindo (papel=varejista)
  ← todos recebem: estado_lobby

... outros jogadores entram ...

Host clica "Iniciar Jogo"
  → envia: iniciar_jogo
  ← todos recebem: jogo_iniciado
  ← cada um recebe: snapshot (do seu papel)
  ← todos recebem: aguardar_decisao { pendentes: [todos] }

--- Semana 1 ---
Varejista digita 5, clica Confirmar
  → envia: decisao_pedido { semana:1, quantidade:5 }
  ← todos recebem: decisao_registrada { papel:"varejista", pendentes:[ata,dis,fab] }

... outros confirmam ...

Quando todos confirmaram:
  ← cada um recebe: snapshot (semana 2)
  ← todos recebem: aguardar_decisao { semana:2, pendentes:[todos] }

--- Repete até semana 36 ---

  ← todos recebem: fim_jogo { relatorio: {...} }
```

---

## Múltiplos jogos simultâneos

Cada sala é identificada pelo `room_id` (ex: `BG-A3F7`).
O servidor mantém um `dict[room_id → SalaWeb]` em memória.
Não há limite de salas simultâneas além da RAM disponível
(tipicamente 50–100 salas ativas em servidores gratuitos).

```
ws://servidor/ws/BG-A3F7  ←→  SalaWeb(engine_1, conexoes_1)
ws://servidor/ws/BG-B9K2  ←→  SalaWeb(engine_2, conexoes_2)
ws://servidor/ws/BG-X5M1  ←→  SalaWeb(engine_3, conexoes_3)
```
