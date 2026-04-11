# 💰 Zotto — Finance AI Data App: LLM-Powered Personal ERP

[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![Railway](https://img.shields.io/badge/Railway-131415?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app)
[![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)

*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento** — GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🎯 About the Project

**Zotto** is a Full-Stack Data Application acting as a **personal financial ERP**. It uses Large Language Models to ingest unstructured daily inputs — free-text messages, electronic invoice URLs, and complex PDF bills — and transforms them into a strictly governed relational PostgreSQL database with full Accounts Payable/Receivable tracking, a real-time Cash Flow Statement, and a Streamlit BI dashboard for financial intelligence.

🤝 **AI Collaboration Note:** Product vision, business rules, and architectural decisions by me. Code development through pair-programming with **Gemini AI** (Google) and **Claude** (Anthropic).

---

### 🗺️ System Architecture — Message Flow

Every message follows a deterministic path from Telegram to the database. Here's how:

```text
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM USER                            │
└──────────┬──────────────────┬──────────────────┬───────────────┘
           │ Text / URL       │ PDF document      │ /command
           ▼                  ▼                   ▼
┌──────────────────────────────────────────────────────────────┐
│               security_check decorator (ALLOWED_CHAT_IDS)    │
└──────────┬───────────────────────────────────┬───────────────┘
           │ ingestion                         │ /contas /extrato /help
           ▼                                   ▼
┌───────────────────────┐            ┌──────────────────────┐
│  PostgreSQL           │            │  Command handlers    │
│  process_queue        │            │  (direct DB reads)   │
│  status=PENDING       │            └──────────────────────┘
└──────────┬────────────┘
           │ every 10s
           ▼
┌───────────────────────────────┐
│   queue_processor (worker)    │  ← rate limit? reschedule with backoff
└──────┬─────────────┬──────────┘
       │ URL         │ PDF / text
       ▼             ▼
┌──────────┐  ┌────────────┐
│BeautifulS│  │PyPDF text  │
│oup scrape│  │extraction  │
└──────┬───┘  └──────┬─────┘
       └──────┬───────┘
              ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Agent 1 — Extract      │────▶│  Agent 2 — Enrich        │
│  temp=0.0               │     │  temp=0.1                │
│  CoT date reasoning     │     │  disambiguation rules    │
└─────────────────────────┘     └──────────┬───────────────┘
                                            │
                                            ▼
                               ┌────────────────────────┐
                               │  Math validation       │
                               │  discount detector     │
                               │  duplicate check       │
                               └──────────┬─────────────┘
                                          │
                                          ▼
                          ┌───────────────────────────────┐
                          │  State Machine                │
                          │  → ask method / location      │◀─── user replies
                          │  → ask card / first date      │
                          │  → show summary (Sim/Não)     │
                          └──────────────┬────────────────┘
                                         │ confirmed
                                         ▼
                          ┌───────────────────────────────┐
                          │  PostgreSQL                   │
                          │  transactions                 │◀──── Streamlit
                          │  transaction_items            │      dashboard.py
                          │  installments                 │      reads here
                          └───────────────────────────────┘
```

**Deployment modes:**
- `prod` → FastAPI + Uvicorn → Telegram pushes to `POST /webhook`
- `dev` → `run_polling()` → bot asks Telegram every few seconds
- `dashboard` → Streamlit service on Railway, same PostgreSQL plugin

---

### 🌟 Key Features

- **Multimodal Ingestion:** Free-text, NFC-e URLs, and PDF utility bills in one pipeline.
- **Dual-Agent AI:** Agent 1 extracts (`temp=0.0`); Agent 2 categorizes (`temp=0.1`). Disambiguation ruleset prevents common misclassifications (Total Pass → Academy, iFood → Food, streaming → Subscriptions, NF-e → always Expense).
- **Hidden Discount Detection:** If `sum(items) > invoice_total`, the difference is automatically registered as a discount.
- **Resilient Outbox Queue:** Exponential Backoff (60s–3600s), TPD-aware 90-minute deferral, `max_attempts` dead-item protection, busy-state deferral without consuming retry attempts.
- **AP/AR Dashboard (`/contas`):** Accordion credit card grouping, income vs expense differentiation, smart anticipation logic, dynamic method override, overdue alerts, Fast-Forward, Isolated View.
- **Cash Flow Statement (`/extrato`):** Saldo Atual + Projetado, Benefit Wallet isolation (VA/VR), dynamic installment index (`8/10`), `[B]` tag, `*` for pending items.
- **Streamlit BI Dashboard (`dashboard.py`):**
  - **Saúde do Mês** — KPIs with savings rate, correct cash-basis values (`paid_amount` for PAID, `expected_amount` for PENDING), benefit wallet isolation.
  - **Tendências** — Monthly income/expense series, savings rate evolution, category trends (multi-select), card participation breakdown, accumulated discount savings.
  - **Cartões & Parcelas** — Income commitment gauge (adjustable horizon), debt curve (burn rate), active installment drill-down.
  - **Projeção de Caixa** — Projected monthly + cumulative balance, tabular summary.
  - **Operacional — Itens** — Hierarchical treemap (macro → category → subcategory), sunburst drill-down, top items & brands, frequency vs ticket scatter, day-of-month heatmap, full audit table with triple filters.
- **Cash Basis Accounting:** Paid installment `month` updates to payment month. `/extrato` and Streamlit reflect when money moved.
- **Cloud-Native:** Two Railway services sharing one PostgreSQL plugin.

---

### 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.12 |
| Conversational Interface | `python-telegram-bot` | 20.8 |
| Web Server (prod) | FastAPI + Uvicorn | 0.135.3 / 0.44.0 |
| AI Engine | Groq API (`llama-4-scout-17b`) | — |
| Database | PostgreSQL (Docker / Railway) | 15 |
| DB Driver | `psycopg2-binary` | 2.9.11 |
| BI Dashboard | Streamlit + Plotly | — |
| Web Scraping | `BeautifulSoup4` | 4.14.3 |
| PDF Extraction | `PyPDF` | 6.9.1 |
| Date Arithmetic | `python-dateutil` | 2.9.0 |

---

### 🤖 Creating your Telegram Bot

1. Open Telegram → search `@BotFather` → `/newbot` → copy the **HTTP API Token**.
2. Send any message to your new bot, then talk to `@userinfobot` to find your personal `chat_id` for `ALLOWED_CHAT_IDS`.

---

### 🚀 How to Run Locally

**Prerequisites:** Python 3.12, Docker, Groq API key ([console.groq.com](https://console.groq.com)).

1. **Clone:** `git clone https://github.com/prBento/personal_finance_ai.git && cd personal_finance_ai`

2. **Create `.env`** (never commit):
   ```env
   ENVIRONMENT=dev
   TELEGRAM_TOKEN_DEV=your_dev_bot_token
   TELEGRAM_TOKEN_PROD=your_prod_bot_token
   GROQ_API_KEY_DEV=your_dev_groq_key
   GROQ_API_KEY_PROD=your_prod_groq_key
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
   ALLOWED_CHAT_IDS=your_telegram_chat_id
   RAILWAY_DB_URL=postgresql://postgres:password@host:5432/railway
   ```

3. **Start DB:** `docker-compose up -d`

4. **Run bot:** `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python bot.py`

5. **Run dashboard (separate terminal):** `streamlit run dashboard.py`

6. **Sync Production Data to Local (Optional):** To test the dashboard locally with real data, use the sync script. It securely consumes credentials from your `.env` file. Ensure you have `RAILWAY_DB_URL` added to your `.env`, then run in PowerShell:
   ```powershell
   .\sync_db.ps1
   ```
   *This script creates a disposable container that downloads production data and injects it directly into your local database in memory, without creating files and preserving UTF-8 formatting.*

---

### ☁️ Cloud Deployment (Railway)

The project runs as **two independent Railway services** sharing a single PostgreSQL plugin.

#### Service 1 — Bot (FastAPI + Webhook)

1. Create a Railway project → add **PostgreSQL** plugin.
2. Connect your GitHub repo. Railway detects `.python-version` (Python 3.12) and installs `requirements.txt` automatically.
3. In the service **Variables** tab, add:
   - `ENVIRONMENT=prod`
   - `TELEGRAM_TOKEN_PROD`, `GROQ_API_KEY_PROD`
   - `DATABASE_URL` (use Railway's **internal** URL from the PostgreSQL plugin)
   - `ALLOWED_CHAT_IDS`
4. Ensure the `Procfile` reads `web: python bot.py` (not `worker`) so Railway assigns a public URL and the `PORT` variable for the webhook server.
5. After deploy, register the webhook with Telegram:
   ```
   [https://api.telegram.org/bot](https://api.telegram.org/bot)<TOKEN>/setWebhook?url=https://<your-bot-service-url>/webhook
   ```

#### Service 2 — Dashboard (Streamlit)

1. In the **same Railway project**, click **+ New Service → GitHub Repo** and connect the same repository again (Railway allows multiple services per repo).
2. In the new service's **Settings → Start Command**, set:
   ```
   streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0
   ```
3. In the service **Variables** tab, add only:
   - `DATABASE_URL` (same internal URL from the PostgreSQL plugin — both services share it)
4. Optionally set a custom domain or use the Railway-generated URL to access the dashboard.
5. The dashboard connects directly to the same PostgreSQL instance the bot writes to — no extra configuration needed.

---

### 🗂️ Project Structure

```text
personal_finance_ai/
├── bot.py              # Handlers, State Machine, queue worker, AI pipeline, FastAPI server
├── database.py         # All DB functions, connection pool, CTE queries, table creation
├── dashboard.py        # Streamlit BI dashboard (5 analytical tabs)
├── prompts.py          # AI Prompts (Extraction & Enrichment)
├── Procfile            # Railway bot service: "web: python bot.py"
├── docker-compose.yml  # Local PostgreSQL
├── requirements.txt    # Python dependencies (includes streamlit, plotly)
├── sync_db.ps1         # PowerShell script to sync production DB to local DB
├── .python-version     # Forces Python 3.12 on Railway Nixpacks
├── ARCHITECTURE.md     # Full technical specification
├── BACKLOG.md          # Product backlog and roadmap
└── .env                # Secrets (git-ignored)
```

---

### 🚦 Conventional Commits

| Prefix | Use for |
|--------|---------|
| `feat:` | New feature | `fix:` | Bug fix |
| `refactor:` | No behavior change | `docs:` | Documentation |
| `chore:` | Build or config | | |

---

### 🗺️ Development Roadmap

#### ✅ V1 — Production Foundation
Core ingestion, Outbox + Backoff, NFC-e + PDF, installment engine, connection pool, whitelist, DATE columns.

#### ✅ V2 — Accounting Engine & UX
- Accordion AP/AR dashboard with group invoice payment.
- `/extrato` with cash-basis accounting, benefit wallet, installment index (`8/10`).
- Dynamic payment method override at settlement time.
- Credit card anticipation (moves installment to next invoice cycle, stays PENDING).
- FastAPI webhook architecture. Interactive `/help` menu.
- Hidden discount detector. Disambiguation ruleset.

#### ✅ V3 — Scale & Visualization
- Streamlit BI dashboard on Railway (second service, shared PostgreSQL).
- 5-tab analytical dashboard: Saúde do Mês, Tendências, Cartões & Parcelas, Projeção de Caixa, Operacional.
- Correct cash-basis KPIs (`paid_amount` for PAID), savings rate metric.
- Benefit wallet isolation in Streamlit (same logic as `/extrato`).
- Hierarchical item analysis: treemap, sunburst, frequency×ticket scatter, day heatmap.
- Accumulated discount/anticipation savings curve.
- Income commitment gauge with adjustable horizon slider.
- Blacklist filter for locations (starts empty, select items to exclude).
- Extract prompts to `prompts.py`.

#### 🚧 V4 — Hardening & Intelligence
- [ ] Replace `print()` with `logging` module for structured log levels.
- [ ] Multi-transaction support per LLM response.
- [ ] PDF password decryption mid-conversation.
- [ ] Replace `psycopg2` with `asyncpg` (non-blocking DB calls in FastAPI event loop).
- [ ] Budget targets per category (stored in DB, configurable via dashboard).

---
---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto

**Zotto** é uma Aplicação de Dados Full-Stack que atua como um **ERP financeiro pessoal**. Usa LLMs para ingerir inputs não estruturados do dia a dia — mensagens de texto livre, URLs de notas fiscais (NFC-e) e PDFs complexos de contas — e os transforma em um banco de dados PostgreSQL rigidamente governado. O projeto rastreia Contas a Pagar/Receber, gera um Extrato de Fluxo de Caixa em tempo real e fornece um Dashboard BI no Streamlit para inteligência financeira.

🤝 **Colaboração IA:** Decisões de produto, regras de negócio e arquitetura por mim. Código desenvolvido em pair-programming com **Gemini AI** (Google) e **Claude** (Anthropic).

---

### 🗺️ Arquitetura do Sistema — Fluxo de Mensagens

Toda mensagem segue um caminho determinístico do Telegram até o banco de dados. Veja como funciona:

```text
┌─────────────────────────────────────────────────────────────────┐
│                        USUÁRIO TELEGRAM                         │
└──────────┬──────────────────┬──────────────────┬───────────────┘
           │ Texto / URL      │ Documento PDF    │ /comandos
           ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│       Decorator security_check (ALLOWED_CHAT_IDS)            │
└──────────┬───────────────────────────────────┬───────────────┘
           │ Ingestão                          │ /contas /extrato /help
           ▼                                   ▼
┌───────────────────────┐            ┌──────────────────────┐
│  PostgreSQL           │            │  Handlers de comando │
│  process_queue        │            │  (leitura direta BD) │
│  status=PENDING       │            └──────────────────────┘
└──────────┬────────────┘
           │ a cada 10s
           ▼
┌───────────────────────────────┐
│   queue_processor (worker)    │  ← rate limit? reagenda com backoff
└──────┬─────────────┬──────────┘
       │ URL         │ PDF / texto
       ▼             ▼
┌──────────┐  ┌────────────┐
│Scrape via│  │Extração de │
│BeautifulS│  │texto PyPDF │
└──────┬───┘  └──────┬─────┘
       └──────┬───────┘
              ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Agente 1 — Extração    │────▶│  Agente 2 — Enriquec.    │
│  temp=0.0               │     │  temp=0.1                │
│  CoT datas              │     │  regras desambiguação    │
└─────────────────────────┘     └──────────┬───────────────┘
                                            │
                                            ▼
                               ┌────────────────────────┐
                               │  Validação matemática  │
                               │  detector de desconto  │
                               │  verificação duplicata │
                               └──────────┬─────────────┘
                                          │
                                          ▼
                          ┌───────────────────────────────┐
                          │  Máquina de Estados           │
                          │  → pede método / local        │◀─── usuário responde
                          │  → pede cartão / 1ª data      │
                          │  → mostra resumo (Sim/Não)    │
                          └──────────────┬────────────────┘
                                         │ confirmado
                                         ▼
                          ┌───────────────────────────────┐
                          │  PostgreSQL                   │
                          │  transactions                 │◀──── Streamlit
                          │  transaction_items            │      dashboard.py
                          │  installments                 │      lê aqui
                          └───────────────────────────────┘
```

**Modos de Deploy:**
- `prod` → FastAPI + Uvicorn → Telegram envia via `POST /webhook`
- `dev` → `run_polling()` → bot pesquisa ativamente no Telegram
- `dashboard` → Serviço Streamlit no Railway, usando o mesmo plugin PostgreSQL

---

### 🌟 Funcionalidades Principais

- **Ingestão Multimodal:** Texto livre, URLs de NFC-e e faturas em PDF em um único pipeline.
- **IA de Duplo Agente:** Agente 1 extrai dados (`temp=0.0`); Agente 2 categoriza (`temp=0.1`). Regras de desambiguação evitam erros comuns (ex: Total Pass → Academia, iFood → Alimentação, NF-e → sempre Despesa).
- **Detecção de Desconto Oculto:** Se a `soma(itens) > total_nota`, a diferença é automaticamente registrada como desconto aplicado.
- **Fila Outbox Resiliente:** Backoff Exponencial (60s–3600s), adiamento de 90 min para limite TPD, proteção contra limite de tentativas (`max_attempts`), pausa de fila sem consumir tentativas se o usuário estiver respondendo.
- **Dashboard AP/AR (`/contas`):** Agrupamento por cartão em acordeon, diferenciação de receitas/despesas, lógica de antecipação, mudança de método de pagamento na hora da baixa, alertas de vencimento, avanço rápido e Visão Isolada.
- **Extrato Financeiro (`/extrato`):** Saldo Atual vs Projetado, isolamento da Carteira de Benefícios (VA/VR), índice dinâmico de parcelas (`8/10`), tag `[B]`, e `*` para lançamentos previstos.
- **Dashboard BI Streamlit (`dashboard.py`):**
  - **Saúde do Mês** — KPIs com taxa de poupança, valores corretos em regime de caixa (`paid_amount` para PAGO, `expected_amount` para PENDENTE), isolamento de benefícios.
  - **Tendências** — Série mensal de receitas/despesas, evolução da poupança, tendências por categoria (multi-select), participação por cartão e economia acumulada.
  - **Cartões & Parcelas** — Gauge de comprometimento de renda (horizonte ajustável), curva de dívida (burn rate) e detalhamento de parcelamentos ativos.
  - **Projeção de Caixa** — Saldo projetado mensal + acumulado e resumo em tabela.
  - **Operacional (Itens)** — Treemap hierárquico (macro → categoria → subcategoria), sunburst, top itens e marcas, scatter de frequência vs ticket, heatmap por dia do mês e tabela de auditoria com filtros triplos.
- **Contabilidade em Regime de Caixa:** O `mês` da parcela se ajusta ao mês de pagamento real. O `/extrato` e o Streamlit refletem a movimentação exata do dinheiro.
- **Cloud-Native:** Dois serviços no Railway compartilhando um único plugin PostgreSQL.

---

### 🛠️ Stack Tecnológico

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.12 |
| Interface Bot | `python-telegram-bot` | 20.8 |
| Servidor Web (prod) | FastAPI + Uvicorn | 0.135.3 / 0.44.0 |
| Motor IA | Groq API (`llama-4-scout-17b`) | — |
| Banco de Dados | PostgreSQL (Docker / Railway) | 15 |
| Driver BD | `psycopg2-binary` | 2.9.11 |
| Dashboard BI | Streamlit + Plotly | — |
| Web Scraping | `BeautifulSoup4` | 4.14.3 |
| Leitura PDF | `PyPDF` | 6.9.1 |
| Aritmética de Datas | `python-dateutil` | 2.9.0 |

---

### 🤖 Criando seu Bot no Telegram

1. Abra o Telegram → busque por `@BotFather` → digite `/newbot` → copie o **Token da API HTTP**.
2. Envie qualquer mensagem para o seu novo bot, e em seguida converse com o `@userinfobot` para descobrir o seu `chat_id` pessoal. Insira esse número no seu `ALLOWED_CHAT_IDS`.

---

### 🚀 Como Rodar Localmente

**Pré-requisitos:** Python 3.12, Docker, Chave de API do Groq ([console.groq.com](https://console.groq.com)).

1. **Clonar:** `git clone https://github.com/prBento/personal_finance_ai.git && cd personal_finance_ai`

2. **Criar `.env`** (nunca faça commit):
   ```env
   ENVIRONMENT=dev
   TELEGRAM_TOKEN_DEV=seu_token_dev
   TELEGRAM_TOKEN_PROD=seu_token_prod
   GROQ_API_KEY_DEV=sua_chave_groq_dev
   GROQ_API_KEY_PROD=sua_chave_groq_prod
   DB_USER=seu_usuario_bd
   DB_PASSWORD=sua_senha_bd
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
   ALLOWED_CHAT_IDS=seu_chat_id_telegram
   RAILWAY_DB_URL=postgresql://postgres:senha@host:5432/railway
   ```

3. **Subir BD Local:** `docker-compose up -d`

4. **Rodar bot:** `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python bot.py`

5. **Rodar dashboard (em outro terminal):** `streamlit run dashboard.py`

6. **Sincronizar Banco de Produção (Opcional):** Para testar o painel localmente com dados reais, utilize o script de sincronização. Ele consome as credenciais do seu arquivo `.env` de forma segura. Certifique-se de ter adicionado a variável `RAILWAY_DB_URL` no seu `.env` e rode no PowerShell:
   ```powershell
   .\sync_db.ps1
   ```
   *O script gera um container descartável que baixa os dados de produção e os injeta diretamente no seu banco local em memória, sem gerar arquivos e preservando o formato UTF-8.*

---

### ☁️ Deploy na Nuvem (Railway)

O projeto roda como **dois serviços independentes** no mesmo projeto Railway, compartilhando um único plugin PostgreSQL.

#### Serviço 1 — Bot (FastAPI + Webhook)

1. Crie um projeto no Railway → adicione o plugin **PostgreSQL**.
2. Conecte o repositório GitHub. O Railway detecta o `.python-version` (Python 3.12) e instala o `requirements.txt` automaticamente.
3. Na aba **Variables** do serviço, adicione:
   - `ENVIRONMENT=prod`
   - `TELEGRAM_TOKEN_PROD`, `GROQ_API_KEY_PROD`
   - `DATABASE_URL` (URL **interna** do plugin PostgreSQL do Railway)
   - `ALLOWED_CHAT_IDS`
4. Garanta que o arquivo `Procfile` contenha `web: python bot.py` para o Railway provisionar a URL pública e a variável `PORT` para o servidor webhook.
5. Após o deploy, registre o webhook enviando este link no seu navegador:
   ```
   [https://api.telegram.org/bot](https://api.telegram.org/bot)<TOKEN>/setWebhook?url=https://<url-do-seu-servico>/webhook
   ```

#### Serviço 2 — Dashboard (Streamlit)

1. No **mesmo projeto Railway**, clique em **+ New Service → GitHub Repo** e conecte o mesmo repositório novamente (o Railway permite múltiplos serviços para o mesmo repositório).
2. Na aba **Settings → Start Command** do novo serviço, defina:
   ```
   streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0
   ```
3. Na aba **Variables** deste serviço, adicione apenas:
   - `DATABASE_URL` (a mesma URL interna do plugin PostgreSQL — os dois serviços a compartilham)
4. Defina um domínio customizado ou use a URL gerada pelo Railway para acessar o dashboard.
5. O dashboard se conecta diretamente à mesma instância PostgreSQL onde o bot escreve os dados.

---

### 🗂️ Estrutura do Projeto

```text
personal_finance_ai/
├── bot.py              # Handlers, Máquina de Estados, worker de fila, IA e servidor FastAPI
├── database.py         # Funções de BD, connection pool, queries complexas e criação de tabelas
├── dashboard.py        # Dashboard BI no Streamlit (5 abas analíticas)
├── prompts.py          # Prompts da IA (Extração e Enriquecimento)
├── Procfile            # Serviço bot do Railway: "web: python bot.py"
├── docker-compose.yml  # Banco PostgreSQL local
├── requirements.txt    # Dependências (inclui streamlit, plotly, fastapi)
├── sync_db.ps1         # Script PowerShell para clonar a base de prod para o ambiente local
├── .python-version     # Força o Python 3.12 no Nixpacks do Railway
├── ARCHITECTURE.md     # Especificação técnica completa do projeto
├── BACKLOG.md          # Backlog de produto e roadmap
└── .env                # Variáveis secretas (ignorado pelo git)
```

---

### 🚦 Commits Convencionais

| Prefixo | Uso |
|---------|---------|
| `feat:` | Nova funcionalidade | `fix:` | Correção de bug |
| `refactor:` | Mudança sem impacto visual/funcional | `docs:` | Documentação |
| `chore:` | Build, pacotes ou configuração | | |

---

### 🗺️ Roadmap de Desenvolvimento

#### ✅ V1 — Fundação de Produção
Ingestão central, Outbox + Backoff, NFC-e + PDF, motor de parcelamento, connection pool, whitelist de segurança, colunas em formato DATE.

#### ✅ V2 — Motor Contábil e UX
- Dashboard AP/AR com menu acordeon e pagamento em massa de faturas.
- `/extrato` rodando 100% em regime de caixa, com carteira benefício isolada e índice de parcelas (`8/10`).
- Sobrescrita de método de pagamento no momento da baixa.
- Antecipação de cartão de crédito (move a parcela para o fechamento da fatura seguinte, mas mantém PENDENTE).
- Arquitetura FastAPI webhook. Menu `/help` interativo.
- Detecção algorítmica de desconto oculto. Regras de desambiguação de IA.

#### ✅ V3 — Escala e Visualização
- Dashboard Streamlit BI no Railway (segundo serviço, mesmo PostgreSQL).
- 5 abas analíticas: Saúde do Mês, Tendências, Cartões & Parcelas, Projeção de Caixa, Operacional.
- KPIs em regime de caixa absoluto (`paid_amount` vs `expected_amount`) e métrica de taxa de poupança.
- Isolamento da carteira de benefício no Streamlit (mesma lógica do `/extrato`).
- Análise de itens (regime de competência): treemap hierárquico, sunburst, frequência vs ticket, heatmap de dias.
- Gráfico de curva de descontos acumulados e antecipações.
- Gauge de comprometimento de renda com slider de horizonte futuro.
- Filtro de locais em formato Blacklist (inicia vazio, ocultando apenas os itens selecionados).
- Refatoração dos prompts para o arquivo central `prompts.py`.

#### 🚧 V4 — Hardening e Inteligência
- [ ] Substituir `print()` pelo módulo `logging` com níveis estruturados.
- [ ] Suporte a multi-transação (várias compras na mesma resposta do LLM).
- [ ] Quebra de senha de PDFs de operadoras de celular durante a conversa.
- [ ] Substituir `psycopg2` por `asyncpg` (chamadas não-bloqueantes no event loop do FastAPI).
- [ ] Metas de orçamento por categoria (armazenadas no banco e geridas pelo painel).