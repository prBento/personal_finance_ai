# 💰 Zotto — Finance AI Data App: LLM-Powered Personal ERP

[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![Railway](https://img.shields.io/badge/Railway-131415?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app)
[![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)

*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento** — GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🎯 About the Project

**Zotto** is a Full-Stack Data Application acting as a **personal financial ERP**. It uses Large Language Models to ingest unstructured daily inputs — free-text messages, electronic invoice URLs, and complex PDF bills — and transforms them into a strictly governed relational PostgreSQL database with full Accounts Payable/Receivable tracking and a real-time Cash Flow Statement.

🤝 **AI Collaboration Note:** Product vision, business rules, and architectural decisions by me. Code development through pair-programming with **Gemini AI** (Google) and **Claude** (Anthropic).

---

### 🗺️ System Architecture — Message Flow

Every message follows a deterministic path from Telegram to the database. Here's how:

```
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
                          │  transactions                 │
                          │  transaction_items            │
                          │  installments                 │
                          └───────────────────────────────┘
```

**Deployment modes:**
- `prod` → FastAPI + Uvicorn → Telegram pushes to `POST /webhook`
- `dev` → `run_polling()` → bot asks Telegram every few seconds

---

### 🌟 Key Features

- **Multimodal Ingestion:** Free-text, NFC-e URLs, and PDF utility bills in one pipeline.
- **Dual-Agent AI:** Agent 1 extracts (`temp=0.0`); Agent 2 categorizes (`temp=0.1`). Disambiguation ruleset prevents common misclassifications (Total Pass → Academy, iFood → Food, streaming → Subscriptions, NF-e → always Expense).
- **Hidden Discount Detection:** If `sum(items) > invoice_total`, the difference is automatically registered as a discount.
- **Resilient Outbox Queue:** Exponential Backoff (60s–3600s), TPD-aware 90-minute deferral, `max_attempts` dead-item protection, busy-state deferral without consuming retry attempts.
- **AP/AR Dashboard (`/contas`):**
  - Accordion credit card grouping (expand ⏵ / collapse ⏷) with "Pay Full Invoice" button.
  - Income (🟢/🟡) vs Expense (🔹/🔴) visual differentiation in all action texts.
  - Dynamic method override at settlement time (pay with a different card/method than originally recorded).
  - Smart anticipation: credit card → moves to next invoice cycle (stays PENDING); cash/Pix → marks PAID immediately.
  - Overdue alerts, month navigation, Fast-Forward (⏭️), Isolated View, escape hatches.
- **Cash Flow Statement (`/extrato`):**
  - Saldo Atual (actual) and Saldo Projetado (projected).
  - Benefit Wallet isolation (VA/VR/prepaid shown separately from liquid cash).
  - Monospaced ledger with `[B]` tag for benefit items, dynamic `8/10` installment index, `*` for pending.
- **Cash Basis Accounting:** Paid installment `month` updates to payment month. `/extrato` reflects when money moved; `/contas` retains original `due_date` for bill management.
- **Interactive Help:** `/help` as a topic-based inline button menu with sub-pages and back navigation.
- **Cloud-Native:** FastAPI webhook on Railway with `ThreadedConnectionPool`.

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
   ```

3. **Start DB:** `docker-compose up -d`

4. **Install & run:**
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt && python bot.py
   ```
   `create_tables()` runs automatically on startup.

---

### ☁️ Cloud Deployment (Railway)

1. Create a Railway project → add **PostgreSQL** plugin.
2. Connect your GitHub repo.
3. In the service **Variables** tab, add:
   - `ENVIRONMENT=prod`
   - `TELEGRAM_TOKEN_PROD`, `GROQ_API_KEY_PROD`
   - `DATABASE_URL` (use Railway's internal URL)
   - `ALLOWED_CHAT_IDS`
4. **Important:** Ensure the Procfile reads `web: python bot.py` (not `worker`) so Railway assigns a public URL and `PORT` variable for the webhook server.
5. After deploy, register the webhook URL with Telegram:
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-railway-url>/webhook
   ```

---

### 🗂️ Project Structure

```
personal_finance_ai/
├── bot.py              # Handlers, State Machine, queue worker, AI pipeline, FastAPI server
├── database.py         # All DB functions, connection pool, CTE queries, table creation
├── Procfile            # Railway: "web: python bot.py"
├── docker-compose.yml  # Local PostgreSQL
├── requirements.txt    # Python dependencies
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

#### 🚧 V3 — Scale & Visualization
- [ ] Procfile fix: `worker:` → `web:` for Railway webhook provisioning.
- [ ] `CREATE VIEW monthly_summary` for Streamlit aggregations.
- [ ] Streamlit Financial Dashboard (spend analysis, category breakdowns, monthly cash flow).
- [ ] Replace `print()` with `logging` module for structured log levels.
- [ ] Extract prompts to `prompts.py`.
- [ ] Multi-transaction support per LLM response.
- [ ] PDF password decryption mid-conversation.
- [ ] Replace `psycopg2` with `asyncpg` (non-blocking DB calls in the FastAPI event loop).
- [ ] Fix benefit wallet detection: add `card_bank`/`card_variant` to `get_cash_flow_by_month` query.

---
---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto

**Zotto** é uma Aplicação de Dados Full-Stack que atua como um **ERP financeiro pessoal**. Usa LLMs para ingerir inputs caóticos do dia a dia e os transforma em um banco de dados PostgreSQL rigidamente governado, com rastreamento completo de Contas a Pagar/Receber e um Extrato de Fluxo de Caixa em tempo real.

🤝 **Colaboração IA:** Decisões de produto e arquitetura por mim. Código em pair-programming com **Gemini AI** e **Claude**.

---

### 🗺️ Fluxo de Mensagens

```
┌─────────────────────────────────────────────────┐
│                  USUÁRIO TELEGRAM               │
└──────────┬──────────────┬──────────────┬────────┘
           │ Texto / URL  │ PDF          │ /comando
           ▼              ▼              ▼
┌──────────────────────────────────────────────────┐
│       security_check (ALLOWED_CHAT_IDS)          │
└──────────┬────────────────────────┬──────────────┘
           │ ingestão               │ /contas /extrato
           ▼                        ▼
┌─────────────────────┐   ┌──────────────────────┐
│ process_queue       │   │ Handlers de comando  │
│ PostgreSQL          │   │ (leitura direta BD)  │
└──────────┬──────────┘   └──────────────────────┘
           │ a cada 10s
           ▼
┌──────────────────────────────┐
│  queue_processor (worker)    │ ← rate limit? reagenda com backoff
└──────┬──────────────────┬────┘
       │ URL              │ PDF / texto
       ▼                  ▼
 BeautifulSoup       PyPDF texto
       └────────┬──────────┘
                ▼
 ┌──────────────────────────┐   ┌─────────────────────────┐
 │  Agente 1 — Extração     │──▶│  Agente 2 — Enriquecim. │
 │  temp=0.0 · CoT datas    │   │  temp=0.1 · categorias  │
 └──────────────────────────┘   └─────────────┬───────────┘
                                              │
                                              ▼
                             ┌─────────────────────────────┐
                             │  Validação matemática       │
                             │  detector de desconto       │
                             │  verificação de duplicata   │
                             └──────────────┬──────────────┘
                                            │
                                            ▼
                          ┌────────────────────────────────┐
                          │  Máquina de Estados            │
                          │  → pede método / local         │◀── usuário responde
                          │  → pede cartão / 1ª parcela    │
                          │  → mostra resumo (Sim/Não)     │
                          └──────────────┬─────────────────┘
                                         │ confirmado
                                         ▼
                          ┌──────────────────────────────┐
                          │  PostgreSQL                  │
                          │  transactions · items        │
                          │  installments                │
                          └──────────────────────────────┘
```

---

### 🌟 Funcionalidades Principais

- **Ingestão Multimodal:** Texto livre, URLs NFC-e e PDFs em um único pipeline.
- **Pipeline Dual de Agentes:** Extração (`temp=0.0`) + categorização (`temp=0.1`) com regras de desambiguação.
- **Detecção de Desconto Oculto:** Se `sum(itens) > total_nota`, a diferença é registrada automaticamente.
- **Fila Outbox Resiliente:** Backoff Exponencial, adiamento de 90min para TPD, proteção contra itens zumbi.
- **Dashboard AP/AR (`/contas`):** Acordeon por cartão, sobrescrita de método no ato da baixa, antecipação inteligente (cartão → move para próxima fatura; à vista → marca PAGO), indicadores de vencimento, Modo Isolado.
- **Extrato (`/extrato`):** Saldo Atual e Projetado, isolamento de Carteira Benefício (VA/VR), tag `[B]`, índice `8/10`.
- **Regime de Caixa:** Campo `month` atualizado para o mês real do pagamento.
- **Menu de Ajuda Interativo:** `/help` com sub-páginas por tópico e navegação inline.

---

### 🛠️ Stack Tecnológico

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.12 |
| Interface | `python-telegram-bot` | 20.8 |
| Servidor Web (prod) | FastAPI + Uvicorn | 0.135.3 / 0.44.0 |
| Motor IA | Groq API (`llama-4-scout-17b`) | — |
| Banco | PostgreSQL (Docker / Railway) | 15 |
| Driver BD | `psycopg2-binary` | 2.9.11 |
| Scraping | `BeautifulSoup4` | 4.14.3 |
| PDF | `PyPDF` | 6.9.1 |
| Datas | `python-dateutil` | 2.9.0 |

---

### 🚀 Como Rodar Localmente

```bash
git clone https://github.com/prBento/personal_finance_ai.git
cd personal_finance_ai
# Crie o .env com as variáveis acima
docker-compose up -d
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && python bot.py
```

---

### ☁️ Deploy no Railway

1. Crie projeto → plugin **PostgreSQL**.
2. Conecte o repositório GitHub.
3. Na aba **Variables**, adicione todas as variáveis de produção.
4. **Importante:** O `Procfile` deve conter `web: python bot.py` (não `worker`) para o Railway provisionar URL pública e a variável `PORT`.
5. Após o deploy, registre o webhook:
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<sua-url-railway>/webhook
   ```

---

### 🗺️ Roadmap

#### ✅ V1 — Fundação de Produção
#### ✅ V2 — Motor Contábil e UX
Acordeon, `/extrato`, regime de caixa, antecipação de cartão, sobrescrita de método, FastAPI webhook, `/help` interativo, detector de desconto, desambiguação.

#### 🚧 V3 — Escala e Visualização
- Procfile: `worker:` → `web:`
- Streamlit Dashboard
- Logging estruturado
- `asyncpg` para event loop não-bloqueante
- Multi-transação por resposta do LLM
- PDF com senha