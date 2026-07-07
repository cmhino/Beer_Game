# 🍺 Beer Game (CISLOG) — Simulação da Cadeia de Suprimentos

Implementação completa do Beer Game em Python, conforme a especificação
(`especificacao_beer_game.md`): cadeia **Cliente → Varejista → Atacadista →
Distribuidor → Fábrica**, atrasos de 2 semanas (informação) + 2 semanas
(transporte), custos de R$ 0,50/un de estoque e R$ 1,00/un de backlog,
choque de demanda 4 → 8 unidades na semana 5 (tudo configurável na tela).

Só usa a **biblioteca padrão do Python** (Tkinter incluso). Se o `openpyxl`
estiver instalado, também exporta `.xlsx` — caso contrário, gera `.db` e `.csv`.

## Como executar

```bat
python main.py            :: interface gráfica
python main.py --sim 36   :: simulação rápida 100% IA, sem janela
```

## Modos de jogo

| Modo | Como funciona |
|---|---|
| **Jogo individual** | Um único computador. Para cada elo você escolhe **Humano** ou **IA**. Com os 4 em Humano, você decide os 4 pedidos por semana; com os 4 em IA, vira uma simulação automática (botão *Rodar até o fim*). |
| **Criar sala (host)** | Este computador vira o servidor autoritativo. O host escolhe um papel **ou** entra como *Observador* (ex.: professor). Papéis sem humano são jogados pela IA. |
| **Entrar em sala** | Informe o IP e a porta do host (padrão **5555**). Cada jogador vê apenas as informações do seu elo. |

### Rede — passo a passo (4 computadores)
1. No PC 1, escolha **Criar sala**; anote o IP mostrado na tela.
2. Nos PCs 2–4, escolha **Entrar em sala**, digite o IP do host e o papel.
3. No lobby, o host clica em **▶ Iniciar jogo** (papéis vagos ficam com a IA).
4. A semana só avança quando **todos** os elos humanos confirmarem o pedido.
   O host pode clicar em **⚡ IA decide pelos ausentes** para destravar.
5. **Queda de conexão:** a IA assume na hora (coluna `controlador` registra
   `humano→ia`). O jogador pode reconectar pelo menu e **retomar o papel**.
6. Fora da mesma rede local é preciso liberar a porta no roteador do host
   (port forwarding) ou usar uma VPN como Tailscale/Hamachi.

## Modelos de IA

Os elos podem ser controlados por IA, com **três modelos** à escolha (no jogo
individual há um seletor de modelo por elo; no modo em rede o host define os
modelos dos elos automatizados). Todos partilham a mesma previsão de demanda
(suavização exponencial, θ = 0,3) e diferem na **política de pedido**:

- **Pedido Equilibrado** (padrão) — heurística clássica de Sterman (1989):
  `pedido = previsão + α·(alvo − posição de estoque)`. Imita o jogador humano
  típico; bom desempenho, mas pode amplificar o efeito chicote sob choque.
- **Reposição Enxuta** — política base-stock disciplinada (estilo APIOBPCS):
  ajusta separadamente o estoque e o pipeline (em trânsito), repondo só o
  necessário conforme o lead time real. Costuma **reduzir** o efeito chicote.
- **Cauteloso** — agente anti-chicote: suaviza fortemente os pedidos e leva
  melhor em conta o que já está a caminho (o pipeline), reagindo devagar e
  evitando exageros. É o que mais contém o chicote.

Comparação ilustrativa (4 elos com o mesmo modelo, 36 semanas, choque na
semana 5): pico de pedido da fábrica ≈ **99** (Equilibrado), **68** (Enxuta) e
**52** (Cauteloso) — quanto menor, menos efeito chicote.

## Tabela mestre (69 colunas)

Linhas = semanas; as semanas **−3 a 0** são o regime estacionário de setup que
preenche os pipelines (estoque 12, fluxo de 4 un por slot). Colunas globais:
`semana, fase, demanda_cliente, timestamp, custo_total_cadeia` + 16 colunas por
elo com prefixos `VAR_/ATA_/DIS_/FAB_` (pedido_recebido, recebido,
estoque_inicial, demanda_total, enviado, backlog, estoque_final,
pedido_colocado, transp_slot1/2, info_slot1/2, posicao_estoque, custo_semana,
custo_acum, controlador).

Ao final de cada partida, a pasta **`partidas/`** recebe:
`beergame_AAAAMMDD_HHMMSS.db` (SQLite), `.csv` (separador `;`, decimais com
vírgula — abre direto no Excel pt-BR) e `.xlsx` (abas *semanas* e *resumo*).
Nos clientes em rede, o relatório final tem o botão **Salvar cópia local**.

## Gerar o .exe (Windows)

No prompt do Miniconda:

```bat
conda create -n beergame python=3.12 -y
conda activate beergame
pip install pyinstaller openpyxl pillow
build.bat
```

O executável sai em `dist\BeerGame.exe` (arquivo único, sem console). O
`logo.jpg` e o ícone `beergame.ico` ficam **embutidos** no `.exe` (o `build.bat`
usa `--add-data` e `--icon`), então o executável já abre com o logo no
cabeçalho e o ícone do CISLOG na janela e na barra de tarefas — sem precisar
distribuir arquivos junto. Para trocar o logo/ícone: substitua o `logo.jpg`,
rode `python gerar_icone.py` para recriar o `beergame.ico` e gere o exe de novo.
Observações:
- Alguns antivírus desconfiam de exe `--onefile`; se ocorrer, use
  `--onedir` no `build.bat` (gera uma pasta em vez de um arquivo único).
- O Windows Firewall pedirá permissão na primeira vez que você **criar uma
  sala** — aceite para a porta TCP escolhida.

## Lead times (regras de tempo)

- **Varejista, Atacadista e Distribuidor**: o pedido leva **2 semanas** para
  chegar ao fornecedor (pipeline de informação) e a mercadoria leva
  **2 semanas** de transporte — lead time total de **4 semanas**.
  Ex.: pedido de 10 colocado na semana 1 → chega ao fornecedor na semana 3 →
  entra no estoque de quem pediu na **semana 5** (se houver estoque no
  fornecedor; faltas geram backlog e atrasam a entrega).
- **Fábrica**: o pedido de produção leva **1 semana** para ser processado e
  **2 semanas** para ser produzido — lead time total de **3 semanas**.
  Ex.: ordem de 10 na semana 1 → entra no estoque da fábrica na **semana 4**.
- O diagrama da cadeia mostra esses pipelines: cada faixa tem os slots do
  lead time (molduras tracejadas quando vazios) e os chips avançam um slot
  por semana. Validação automática em `test_leadtime.py`.

## Visual e personalização

- **Tema claro/escuro** — botão 🌙/☀ no canto superior direito, a qualquer momento.
- **Logo personalizável** — o `logo.jpg` fica **embutido no próprio `.exe`**
  (o `build.bat` o inclui via `--add-data`), então o executável já abre com
  ele sem precisar distribuir nenhum arquivo junto. Para trocar o logo há
  dois caminhos: (a) substituir o `logo.jpg` da pasta do projeto **antes** de
  gerar o `.exe` (fica embutido o novo), ou (b) colocar um `logo.jpg` (ou
  `logo.png`) **ao lado do `.exe` já pronto** — esse externo tem prioridade
  sobre o embutido, permitindo trocar o logo sem recompilar. Para JPG é
  preciso ter o Pillow (`pip install pillow`); PNG funciona sem nada extra.
  Sem nenhum logo, o jogo desenha uma caneca estilizada.
- **Cartões coloridos com semáforo** — estoque e backlog em números grandes
  que mudam de cor (verde/amarelo/vermelho) conforme a situação do elo.
- **Diagrama animado da cadeia** (modo individual) — aba "Cadeia (animação)":
  as mercadorias (chips âmbar) e os pedidos (chips azuis) viajam entre os
  elos a cada semana confirmada, ambos com os mesmos estágios de lead time;
  o slot recém-aberto à espera da decisão aparece marcado com "?". A fábrica
  mostra o estágio de processamento do pedido ("ped.") e os dois de produção.
- **Gráficos interativos** — passe o mouse para ver os valores de cada
  semana; a linha tracejada vermelha marca o choque de demanda e a área
  rosada destaca o backlog (estoque líquido negativo).
- **Controle de tamanho de fonte** — botões **A−/A+** no cabeçalho (85% a
  175%) ampliam toda a interface de uma vez (textos, números, cartões, logo)
  para facilitar a leitura em telas grandes ou projeção em sala.
- **Animação do fluxo no jogo em rede**:
  - cada jogador vê a aba **"Meu fluxo (animação)"** com o seu próprio
    segmento (Fornecedor → você → Cliente), com mercadorias e pedidos
    deslizando pelos slots de lead time — respeitando a informação limitada
    (nenhum dado dos outros elos é revelado);
  - o **observador** (professor) vê o **diagrama completo da cadeia
    animado**, idêntico ao do modo individual, ideal para projeção.
- **Barra de progresso da partida** — semana atual vs. total, com o marcador
  ⚡ do choque.
- **Relatório final com pódio** — ranking dos elos por custo, custo total da
  cadeia em destaque e botão para abrir a pasta `partidas/`.

## Opções do professor

- **Modelo de IA por elo** — escolha entre Pedido Equilibrado, Reposição
  Enxuta e Cauteloso para cada elo automatizado (ver seção "Modelos de IA").
- **Estoque inicial por elo** configurável na tela de parâmetros
  (12 = clássico, 16 = variante comum, ou qualquer valor).
- **■ Terminar simulação** — disponível no modo individual, para o host e
  para o observador em rede: encerra a partida na semana corrente e gera
  imediatamente o relatório e os arquivos finais (útil quando a turma já
  visualizou o efeito chicote e o tempo da aula está acabando).

## Estrutura do código

```
main.py         ponto de entrada (GUI ou --sim)
engine.py       regras do jogo, pipelines, tabela de 69 colunas
ai_player.py    IA: 3 modelos (Equilibrado, Enxuta, Cauteloso)
storage.py      SQLite / CSV / XLSX e resumo da partida
protocol.py     JSON por linha sobre TCP (porta padrão 5555)
server.py       host autoritativo, sincronização semanal, fallback p/ IA
client.py       cliente de rede
theme.py        paletas claro/escuro, fontes e estilos ttk
widgets.py      cartões dos elos, gráficos, diagrama animado, relatório
gerar_icone.py  regenera beergame.ico a partir do logo
gui.py         telas: menu, individual, host, lobby, tabuleiro, observador
test_*.py      testes automatizados (motor, lead times, rede, queda, GUI,
               animação de rede e controle de fonte)
```
