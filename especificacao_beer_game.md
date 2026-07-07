# Especificação Técnica — Beer Game (CISLOG) em Python

**Versão:** 1.0 | **Plataforma-alvo:** Windows (.exe via PyInstaller) | **Linguagem:** Python 3.11+

---

## 1. Visão geral do jogo

O Beer Game simula uma cadeia de suprimentos de cerveja com 4 elos em série. Pedidos fluem a montante (do cliente para a fábrica) e produtos fluem a jusante (da fábrica para o cliente), ambos com atrasos:

```
Cliente → VAREJISTA → ATACADISTA → DISTRIBUIDOR → FÁBRICA
          (pedidos sobem ↑ | produtos descem ↓)
```

Regras clássicas que o software deve implementar:

| Parâmetro | Valor padrão (configurável) |
|---|---|
| Atraso de informação (pedido chegar ao fornecedor) | 2 semanas |
| Atraso de transporte (produto chegar ao cliente) | 2 semanas |
| Atraso de produção na fábrica (substitui o transporte do fornecedor) | 2 semanas |
| Estoque inicial de cada elo | 12 unidades |
| Unidades em trânsito em cada slot do pipeline no início | 4 unidades |
| Custo de manutenção de estoque | R$ 0,50 / unidade / semana |
| Custo de pendência (backlog) | R$ 1,00 / unidade / semana |
| Demanda do consumidor final | 4 un/semana (semanas 1–4), salto para 8 un/semana a partir da semana 5 |
| Duração da partida | 36 semanas (configurável: 20–52) |
| Visibilidade | Cada elo enxerga apenas seu próprio estoque, backlog e o pedido recebido do elo a jusante |

**Sequência de eventos dentro de cada semana (idêntica para os 4 elos, executada pelo motor do jogo):**

1. Receber a entrega que estava no último slot do pipeline de transporte (avançar pipeline).
2. Receber o pedido que estava no último slot do pipeline de informação (avançar pipeline).
3. Atender a demanda: pedido recebido + backlog acumulado, limitado ao estoque disponível. O que não puder ser atendido vira backlog.
4. Registrar custos da semana: `0,50 × estoque_final + 1,00 × backlog_final`.
5. Decidir e colocar o pedido ao fornecedor (única decisão do jogador; a fábrica "pede" à sua própria linha de produção).
6. Avançar a semana quando os 4 elos tiverem confirmado seus pedidos (barreira de sincronização).

---

## 2. Arquitetura do software

### 2.1 Módulos

```
beer_game/
├── main.py            # ponto de entrada, seleção de modo (menu)
├── engine/
│   ├── game_state.py  # estado da partida, regras, avanço de semana
│   ├── node.py        # classe Elo (varejista, atacadista, distribuidor, fábrica)
│   └── pipeline.py    # filas de atraso (transporte e informação)
├── ai/
│   └── ai_player.py   # IA básica com previsão + política de pedido
├── net/
│   ├── server.py      # host TCP (também roda o motor do jogo)
│   ├── client.py      # cliente TCP
│   └── protocol.py    # mensagens JSON, serialização
├── data/
│   ├── storage.py     # DataFrame mestre + persistência SQLite/CSV/XLSX
│   └── schema.py      # definição das colunas (Seção 4)
├── ui/
│   ├── lobby.py       # tela de criação/entrada de sala
│   ├── board.py       # tela do jogo (estoque, backlog, pedidos, gráfico)
│   └── report.py      # tela final: curvas de pedidos, efeito chicote, custos
└── build.spec         # configuração do PyInstaller
```

### 2.2 Interface gráfica

Recomendação: **Tkinter** (nativo do Python, empacota leve no PyInstaller, sem dependências externas). Alternativa: PySide6 se quiser visual mais moderno, ao custo de um .exe de ~80 MB.

Tela do jogo deve exibir, para o elo controlado pelo jogador: semana atual, estoque, backlog, pedido recebido nesta semana, entregas em trânsito (quantidade, sem revelar origem das decisões alheias), campo de entrada do pedido + botão "Confirmar pedido", custo acumulado, e um minigráfico do histórico próprio.

### 2.3 Modos de jogo

**Modo 1 — Multijogador em rede (1 a 4 humanos):** um computador atua como *host* (roda servidor + motor do jogo + sua própria interface de jogador). Os demais conectam informando `IP:porta`. Papéis não ocupados por humanos são preenchidos por IA — isso cobre naturalmente partidas com 2 ou 3 pessoas.

**Modo 2 — Individual (1 jogador, 4 elos):** o jogador decide o pedido dos 4 elos a cada semana, em sequência (varejista → fábrica). Útil para estudo e calibração. Sem rede; o motor roda localmente.

**Modo 3 — Misto / espectador:** qualquer combinação de elos pode ser marcada como "IA" no lobby, inclusive os 4 (simulação automática completa, útil para gerar baselines e testar o efeito chicote sem intervenção).

### 2.4 Rede (IP a IP)

- **Transporte:** sockets TCP puros (`socket` + `threading` da biblioteca padrão — nada a instalar). Porta padrão 5555, configurável.
- **Topologia:** estrela. O host é a autoridade única do estado do jogo; clientes apenas enviam decisões e recebem o estado filtrado do seu papel (preserva a informação limitada do jogo).
- **Protocolo:** mensagens JSON delimitadas por `\n`, com campo `tipo`. Exemplos:

```json
{"tipo": "entrar_sala", "nome": "Celso", "papel_desejado": "distribuidor"}
{"tipo": "estado_semana", "semana": 12, "papel": "distribuidor",
 "estoque": 7, "backlog": 0, "pedido_recebido": 9, "recebido": 6,
 "custo_acumulado": 41.5}
{"tipo": "decisao_pedido", "semana": 12, "papel": "distribuidor", "quantidade": 10}
{"tipo": "avancar_semana", "semana": 13}
{"tipo": "fim_de_jogo", "relatorio": "..."}
```

- **Sincronização:** o host só emite `avancar_semana` quando recebe as 4 decisões. Timeout configurável (ex.: 120 s) com opção do host de acionar a IA para o jogador ausente.
- **Tolerância a falhas:** se um cliente cair, a IA assume o papel temporariamente; o cliente pode reconectar e retomar.
- **Observação prática:** para jogar fora da mesma LAN será necessário liberar/encaminhar a porta no roteador do host ou usar VPN (ex.: Tailscale). Documentar isso na tela de lobby.

---

## 3. IA básica (jogador automático)

A IA usa um modelo de previsão simples e uma política de pedido do tipo *order-up-to* (estoque-alvo), que é a heurística padrão da literatura do Beer Game (Sterman, 1989).

**Passo 1 — Previsão de demanda** por suavização exponencial simples:

```
F(t) = θ · D(t) + (1 − θ) · F(t−1)        com θ = 0,30
```

onde `D(t)` é o pedido recebido do elo a jusante na semana t. Alternativa ainda mais simples (configurável): média móvel das últimas 4 semanas.

**Passo 2 — Posição de estoque:**

```
PI(t) = estoque_final − backlog + em_trânsito + pedidos_pendentes_no_fornecedor
```

**Passo 3 — Decisão de pedido:**

```
S_alvo  = F(t) × (L + 1) + estoque_segurança        L = lead time total (4 semanas)
Pedido  = max(0, round( F(t) + α · (S_alvo − PI(t)) ))    com α = 0,30
```

O parâmetro `α` (velocidade de correção do estoque) e o estoque de segurança (padrão: 4 un) ficam expostos na configuração — isso permite criar IAs "nervosas" (α alto, que amplificam o chicote) ou "calmas" (α baixo) para fins didáticos.

---

## 4. Estrutura de dados — tabela mestre da partida

### 4.1 Conceito

Uma única tabela larga ("uma linha por semana"), mantida em memória como `pandas.DataFrame` e persistida a cada avanço de semana. **Linhas:** semanas de **−3 a N** (N = duração da partida). **Colunas:** todos os indicadores dos 4 elos, com prefixo por elo: `VAR_` (varejista), `ATA_` (atacadista), `DIS_` (distribuidor), `FAB_` (fábrica).

### 4.2 Por que as semanas −3 a 0

Os atrasos somam um pipeline de 4 períodos entre a decisão de um elo e a chegada física do produto (2 de informação + 2 de transporte/produção). Para que a semana 1 comece em regime estacionário, é preciso que já existam pedidos e cargas "em voo" dentro desses pipelines. As linhas −3, −2, −1 e 0 registram exatamente esse preenchimento: cada uma representa um ciclo fictício em equilíbrio (demanda 4, pedido 4, envio 4, recebimento 4, estoque 12, backlog 0, custo 0). Ao carregar a partida, o motor lê essas 4 linhas e popula os slots dos pipelines — nenhuma lógica especial de inicialização fica escondida em código; o setup é dado, auditável e editável (permite criar cenários iniciais alternativos só alterando essas linhas).

### 4.3 Colunas globais

| Coluna | Tipo | Descrição |
|---|---|---|
| `semana` | int | −3 a N (chave primária) |
| `fase` | str | `setup` (semanas ≤ 0) ou `jogo` |
| `demanda_cliente` | int | Demanda do consumidor final (entra no varejista) |
| `timestamp` | datetime | Momento em que a semana foi fechada |
| `custo_total_cadeia` | float | Soma dos custos acumulados dos 4 elos |

### 4.4 Colunas por elo (repetidas 4×, trocando o prefixo)

Exemplo com o prefixo `VAR_` (varejista). O mesmo bloco existe para `ATA_`, `DIS_` e `FAB_`:

| Coluna | Tipo | Descrição |
|---|---|---|
| `VAR_pedido_recebido` | int | Pedido que chegou do elo a jusante nesta semana (no varejista = `demanda_cliente`) |
| `VAR_recebido` | int | Unidades que chegaram do transporte (saíram do slot 2 do pipeline) |
| `VAR_estoque_inicial` | int | Estoque após o recebimento, antes de atender demanda |
| `VAR_demanda_total` | int | `pedido_recebido + backlog da semana anterior` |
| `VAR_enviado` | int | Unidades efetivamente despachadas ao jusante = `min(demanda_total, estoque_inicial)` |
| `VAR_backlog` | int | Pendência ao fim da semana = `demanda_total − enviado` |
| `VAR_estoque_final` | int | `estoque_inicial − enviado` |
| `VAR_pedido_colocado` | int | **Decisão do jogador/IA** — pedido enviado ao fornecedor |
| `VAR_transp_slot1` | int | Pipeline de transporte: carga que chegará em 2 semanas |
| `VAR_transp_slot2` | int | Pipeline de transporte: carga que chegará na próxima semana |
| `VAR_info_slot1` | int | Pipeline de informação: pedido que o fornecedor verá em 2 semanas |
| `VAR_info_slot2` | int | Pipeline de informação: pedido que o fornecedor verá na próxima semana |
| `VAR_posicao_estoque` | int | `estoque_final − backlog + transp_slot1 + transp_slot2 + info_slot1 + info_slot2` (usada pela IA e pelos relatórios) |
| `VAR_custo_semana` | float | `0,50 × estoque_final + 1,00 × backlog` |
| `VAR_custo_acum` | float | Acumulado desde a semana 1 |
| `VAR_controlador` | str | `humano`, `ia` ou `humano→ia` (registra quem decidiu naquela semana — importante para auditoria em caso de queda de conexão) |

No bloco `FAB_`, os slots `transp_slot1/2` representam a **produção em andamento** (cerveja em fabricação) e os slots `info_slot1/2` não existem — o pedido da fábrica entra direto na fila de produção. Manter as colunas com valor igual ao pedido para uniformidade do esquema, ou preenchê-las com `NULL`; recomendo a primeira opção para simplificar os cálculos vetorizados.

Total: 5 colunas globais + 16 × 4 = **69 colunas**.

### 4.5 Exemplo das linhas de setup e primeiras semanas (recorte do varejista)

| semana | fase | demanda_cliente | VAR_pedido_recebido | VAR_recebido | VAR_enviado | VAR_backlog | VAR_estoque_final | VAR_pedido_colocado | VAR_transp_slot1 | VAR_transp_slot2 | VAR_custo_semana |
|---|---|---|---|---|---|---|---|---|---|---|---|
| −3 | setup | 4 | 4 | 4 | 4 | 0 | 12 | 4 | 4 | 4 | 0,00 |
| −2 | setup | 4 | 4 | 4 | 4 | 0 | 12 | 4 | 4 | 4 | 0,00 |
| −1 | setup | 4 | 4 | 4 | 4 | 0 | 12 | 4 | 4 | 4 | 0,00 |
| 0 | setup | 4 | 4 | 4 | 4 | 0 | 12 | 4 | 4 | 4 | 0,00 |
| 1 | jogo | 4 | 4 | 4 | 4 | 0 | 12 | … | 4 | 4 | 6,00 |
| 2 | jogo | 4 | 4 | 4 | 4 | 0 | 12 | … | … | 4 | 6,00 |
| 5 | jogo | 8 | 8 | 4 | 8 | 0 | 8 | … | … | … | 4,00 |

(Os custos das semanas de setup são zero por convenção; a contagem começa na semana 1.)

### 4.6 Persistência

- **Durante a partida:** gravação incremental em **SQLite** (`partida.db`, tabela `semanas` com o esquema acima + tabela `partidas` com metadados: id, data, modo, jogadores, parâmetros usados, seed). SQLite é arquivo único, sem servidor, e empacota nativamente no .exe (`sqlite3` é stdlib).
- **Ao final:** exportação automática para **CSV** e **XLSX** (uma aba com a tabela mestre, uma aba-resumo com custos por elo e gráficos do efeito chicote — pedido colocado por elo ao longo das semanas).
- **Replay:** como a tabela contém o estado completo, qualquer partida pode ser recarregada e reassistida semana a semana.

---

## 5. Empacotamento (.exe)

- **PyInstaller** com `--onefile --windowed --name BeerGame`.
- Dependências externas mínimas: `pandas` e `openpyxl` (export XLSX) e, se optar por gráficos embutidos, `matplotlib`. Rede, GUI (tkinter) e SQLite são biblioteca padrão — isso mantém o .exe na faixa de 40–70 MB.
- O mesmo executável contém host e cliente (escolha no menu inicial); não há necessidade de distribuir dois binários.
- Atenção no seu ambiente Miniconda: gerar o build dentro de um ambiente limpo (`conda create -n beergame python=3.11 pandas openpyxl matplotlib pyinstaller`) para evitar que o PyInstaller arraste pacotes desnecessários do ambiente base e infle o executável.
- Antivírus do Windows às vezes sinaliza executáveis `--onefile` não assinados; se for distribuir para terceiros, considerar `--onedir` (pasta com o .exe + DLLs) que gera menos falsos positivos.

---

## 6. Roteiro de implementação sugerido

1. **Motor + tabela** (sem GUI, sem rede): regras da Seção 1 operando sobre o DataFrame da Seção 4; validar com os 4 elos em IA e conferir o efeito chicote nas curvas de pedido.
2. **Modo individual** com GUI Tkinter sobre o motor.
3. **IA configurável** (θ, α, estoque de segurança) e modo misto.
4. **Rede TCP** host/cliente com o protocolo da Seção 2.4, mantendo o motor exclusivamente no host.
5. **Relatórios e exportação** (CSV/XLSX, gráficos, ranking de custo por elo).
6. **Build PyInstaller** e teste em máquina limpa (sem Python instalado).
