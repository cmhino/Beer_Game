# Beer Game CISLOG — Versão Web

## Pré-requisitos

- Windows com **Miniconda** instalado (mesmo ambiente do jogo Tkinter)
- Ambiente conda `beergame` com Python 3.12

---

## 1 · Preparar a pasta

Copie os seguintes arquivos do projeto original para esta mesma pasta:

```
beer_game_web/           ← esta pasta
├── engine.py            ← copiar do projeto original
├── ai_player.py         ← copiar do projeto original
├── storage.py           ← copiar do projeto original
├── server_web.py        ← já está aqui ✓
├── requirements_web.txt ← já está aqui ✓
├── run_web.bat          ← já está aqui ✓
└── static/
    ├── index.html       ← já está aqui ✓
    ├── game.html        ← já está aqui ✓
    ├── app.js           ← já está aqui ✓
    └── style.css        ← já está aqui ✓
```

> **Dica:** O `server_web.py` importa `engine.py`, `ai_player.py` e `storage.py`
> diretamente. Nenhuma alteração nesses arquivos é necessária.

---

## 2 · Iniciar o servidor (primeira vez)

```bat
:: No Prompt do Anaconda, dentro da pasta beer_game_web:
conda activate beergame
pip install fastapi "uvicorn[standard]"
python server_web.py
```

Ou simplesmente dê **duplo clique** em `run_web.bat`.

Você verá:
```
[OK] engine.py, ai_player.py, storage.py importados com sucesso
==================================================
  Beer Game CISLOG — Servidor Web
  Acesse: http://localhost:8000
  Status: http://localhost:8000/api/status
==================================================
```

---

## 3 · Testar com múltiplas abas (mesma máquina)

Esta é a forma mais rápida de testar antes de usar em rede.

1. Abra **http://localhost:8000** no navegador
2. Preencha "Criar nova sala":
   - Seu nome: `Prof. Celso`
   - Papel: `Observador`
   - Clique em **Criar sala e entrar**
3. Copie o código de sala exibido (ex: `BG-A3F7`)
4. Abra **3 novas abas** com o mesmo navegador:
   - Aba 2: `http://localhost:8000/?room=BG-A3F7` → nome: Aluno1, papel: Varejista
   - Aba 3: `http://localhost:8000/?room=BG-A3F7` → nome: Aluno2, papel: Atacadista
   - Aba 4: `http://localhost:8000/?room=BG-A3F7` → nome: Aluno3, papel: Distribuidor
   - (Fábrica fica com a IA)
5. Na aba do Observador, clique **▶ Iniciar Jogo**
6. Nas abas dos jogadores, confirme pedidos semana a semana

---

## 4 · Testar em rede local (vários computadores)

1. Descubra o IP da máquina onde o servidor está rodando:
   ```bat
   ipconfig
   ```
   Anote o endereço IPv4 (ex: `192.168.1.15`)

2. Nos outros computadores da mesma rede, acesse:
   ```
   http://192.168.1.15:8000
   ```

3. Não é necessário abrir portas no roteador — funciona em rede local diretamente.

> **Nota:** Para acessos da internet (fora da rede local), use o Render.com
> conforme a seção 6.

---

## 5 · Verificar o servidor

Acesse `http://localhost:8000/api/status` para ver as salas ativas:

```json
{
  "ok": true,
  "modules_ok": true,
  "salas_ativas": 2,
  "salas": {
    "BG-A3F7": { "iniciado": true, "semana": 8, "jogadores": {...} },
    "BG-B9K2": { "iniciado": false, "semana": 0, "jogadores": {} }
  }
}
```

---

## 6 · Deploy gratuito no Render.com

### 6.1 Preparar o repositório

```
beer_game_web/
├── engine.py
├── ai_player.py
├── storage.py
├── server_web.py
├── requirements_web.txt   ← Render usa este arquivo
└── static/
    ├── index.html
    ├── game.html
    ├── app.js
    └── style.css
```

Crie um repositório no GitHub com esses arquivos.

### 6.2 Configurar no Render

1. Acesse https://render.com e faça login com GitHub
2. Clique em **New → Web Service**
3. Conecte o repositório
4. Configure:

| Campo | Valor |
|-------|-------|
| **Name** | `beer-game-cislog` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements_web.txt` |
| **Start Command** | `uvicorn server_web:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | `Free` |

5. Clique em **Create Web Service**

### 6.3 Após o deploy

- URL: `https://beer-game-cislog.onrender.com`
- A primeira requisição após inatividade leva ~30s (cold start)
- Para evitar o cold start: configure um "cron job" que acessa `/api/status` a cada 14 minutos (serviço gratuito como UptimeRobot)

---

## 7 · Protocolo WebSocket — Resumo rápido

| Mensagem | Direção | Quando |
|----------|---------|--------|
| `criar_sala` | C→S | Host abre nova sala |
| `entrar_sala` | C→S | Jogador entra |
| `iniciar_jogo` | C→S | Host inicia |
| `decisao_pedido` | C→S | Jogador confirma pedido |
| `ia_decide_todos` | C→S | Host aciona IA para ausentes |
| `estado_lobby` | S→C | Atualização da sala |
| `snapshot` | S→C | Estado atual do elo (por semana) |
| `aguardar_decisao` | S→C | Nova semana iniciou |
| `decisao_registrada` | S→C | Um papel confirmou |
| `fim_jogo` | S→C | Jogo encerrado + relatório |

Veja `websocket_api.md` para a especificação completa com exemplos JSON.

---

## 8 · Diferenças em relação à versão Tkinter

| Funcionalidade | Tkinter (TCP) | Web (WebSocket) |
|----------------|---------------|-----------------|
| Conexão | IP:porta (5555) | Código de sala (BG-XXXX) |
| Port forwarding | Necessário | Não necessário |
| Múltiplos jogos | 1 servidor = 1 jogo | Vários simultâneos |
| Acesso externo | VPN/Hamachi | URL pública (Render) |
| Interface | Tkinter (.exe) | Navegador qualquer |
| Exportação | XLSX+CSV local | JSON no browser |
| engine.py | Mesmo arquivo | Mesmo arquivo |
| ai_player.py | Mesmo arquivo | Mesmo arquivo |

---

## 9 · Solução de problemas

**`engine.py` não encontrado**
→ Copie os 3 arquivos Python do projeto original para esta pasta.

**Porta 8000 ocupada**
→ Edite `server_web.py`, última linha: mude `port=8000` para `port=8001`.

**WebSocket não conecta no Render**
→ Verifique se o Start Command usa `$PORT` (não porta fixa).

**Cold start lento no Render**
→ Crie uma conta gratuita no UptimeRobot e configure um monitor HTTP
  para `https://seuapp.onrender.com/api/status` a cada 5 minutos.
