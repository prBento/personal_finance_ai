# 💰 Zotto — Finance AI Data App: LLM-Powered Personal ERP
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🎯 About the Project

**Zotto** is an advanced Full-Stack Data Application designed to act as a **personal financial ERP**. The system uses Large Language Models (LLMs) to ingest chaotic, unstructured daily inputs — free-text messages, electronic invoice URLs, and complex PDF bills — and transforms them into a strictly governed, relational PostgreSQL database with full Accounts Payable/Receivable tracking.

The architecture is built around a **Transactional Outbox Pattern**: every input is persisted to a queue immediately, then processed asynchronously by a background worker with Exponential Backoff, meaning no transaction is ever lost even if the AI API is temporarily unavailable.

🤝 **AI Collaboration Note:** The product vision, business rules, and all architectural decisions were driven by me. Code development, refactoring, and technical structuring were built through an active pair-programming collaboration with **Gemini AI** (Google) and **Claude** (Anthropic).

---

### 🌟 Key Features

- **Multimodal Ingestion:** Accepts free-text messages, NFC-e electronic invoice URLs (web scraping), and PDF utility bills (text extraction) in a single unified pipeline.
- **Dual-Agent AI Pipeline:** Agent 1 extracts raw entities with `temperature=0.0`; Agent 2 enriches and categorizes with `temperature=0.1`. Separation of cognitive responsibility eliminates entire classes of LLM hallucination.
- **Resilient Outbox Queue:** All inputs are queued to PostgreSQL before any AI processing. A background worker retries failed items with Exponential Backoff (60s–3600s), with TPD-aware deferral to next day and a `max_attempts` limit to prevent zombie queue items.
- **Human-in-the-Loop Confirmation:** Every transaction is presented as a structured Markdown summary and requires explicit user confirmation before any database write occurs.
- **AP/AR Ledger with Installment Engine:** A custom installment calculator handles Brazilian credit card billing rules (closing day + due day → correct invoice cycle), splitting transactions across multiple months.
- **Grouped Invoice Dashboard (`/contas`):**
  - Installments from the same credit card are grouped under a consolidated "Fatura" header showing the total amount due.
  - Overdue bills are highlighted with a 🔴 indicator.
  - Fast-Forward button (⏭️) jumps directly to the furthest future month with pending bills.
  - Month navigation with auto-return to current month button.
  - Close Panel and Cancel Action escape hatches at every step.
- **Flexible Payment Options:**
  - Pay individual installments with optional early-payment discount.
  - Pay an entire credit card invoice in one click, with discount proportionally distributed across all items.
  - Soft-delete installments for bank reconciliation without affecting future months.
- **Isolated View:** Navigate to the last installment of any multi-month purchase to see its full repayment timeline in isolation.
- **Access Control Whitelist:** An `ALLOWED_CHAT_IDS` environment variable blocks all unauthorized Telegram users at the handler level.
- **Cloud-Native Deployment:** Runs on Railway PaaS with a `ThreadedConnectionPool` to manage database connections efficiently.

---

### 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.10+ |
| Conversational Interface | `python-telegram-bot` | 20.8 |
| AI Engine | Groq API (`llama-4-scout-17b`) | — |
| Database | PostgreSQL (Docker / Railway) | 15 |
| DB Driver | `psycopg2-binary` | 2.9.11 |
| Web Scraping | `BeautifulSoup4` | 4.14.3 |
| PDF Extraction | `PyPDF` | 6.9.1 |
| Date Arithmetic | `python-dateutil` | 2.9.0 |
| HTTP Client | `requests` | 2.32.5 |
| Env Management | `python-dotenv` | 1.2.2 |

---

### 🚀 How to Run Locally

**Prerequisites:** Python 3.10+, Docker, and a Groq API key (free at [console.groq.com](https://console.groq.com)).

1. **Clone the repository:**
   ```bash
   git clone https://github.com/prBento/finance-ai-app.git
   cd finance-ai-app
   ```

2. **Set up the Environment Variables:**
   Create a `.env` file in the root directory. **Never commit this file.**
   ```env
   # Environment
   ENVIRONMENT=dev

   # Telegram Tokens (one per environment)
   TELEGRAM_TOKEN_DEV=your_dev_bot_token
   TELEGRAM_TOKEN_PROD=your_prod_bot_token

   # Groq API Keys
   GROQ_API_KEY_DEV=your_dev_groq_key
   GROQ_API_KEY_PROD=your_prod_groq_key

   # Database
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}

   # Security Whitelist (comma-separated Telegram chat IDs)
   ALLOWED_CHAT_IDS=your_telegram_chat_id
   ```
   > **Tip:** Send any message to your bot and check the terminal logs to find your `chat_id`.

3. **Spin up the Database:**
   ```bash
   docker-compose up -d
   ```

4. **Install Dependencies & Run:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python bot.py
   ```
   On startup, `create_tables()` runs automatically and creates all tables, indexes, and constraints if they do not exist.

---

### 🧠 AI Architecture: Why a Dual-Agent Pipeline?

For the extraction engine, we chose a **Two-Agent Sequential Pipeline** over a single monolithic prompt:

1. **Isolated Failure Modes:** If Agent 1 (Extractor) fails, Agent 2 (Enricher) never runs. Errors are diagnosed at the exact stage where they occur.
2. **Calibrated Temperature per Task:** Data extraction requires determinism (`temperature=0.0`). Category classification tolerates minimal variation (`temperature=0.1`).
3. **Chain-of-Thought Date Reasoning:** Agent 1 contains a `_raciocinio_vencimento` field that forces the model to reason step-by-step about due dates — the single most effective technique to prevent the most common extraction error in PDF utility bills.
4. **Math Validation Post-LLM:** After both agents run, Python recalculates totals and fills in missing unit prices. The LLM extracts; Python validates.

---

### 🗂️ Project Structure

```
finance-ai-app/
├── bot.py              # Telegram handlers, State Machine, queue worker, AI pipeline
├── database.py         # All DB functions, connection pool, table creation
├── Procfile            # Railway process definition
├── docker-compose.yml  # Local PostgreSQL setup
├── requirements.txt    # Python dependencies
├── ARCHITECTURE.md     # Full technical specification
├── BACKLOG.md          # Product backlog and roadmap
└── .env                # Environment variables (git-ignored)
```

---

### 🚦 Git & Commit Standards

This project follows the **Conventional Commits** specification:

| Prefix | Use for |
|--------|---------|
| `feat:` | New feature or behavior |
| `fix:` | Bug fix |
| `refactor:` | Code change with no behavior change |
| `docs:` | Documentation only |
| `chore:` | Build, config, or dependency changes |

---

### 🗺️ Development Roadmap

#### ✅ V1 — Production Foundation (Completed)
- [x] Core ingestion: Telegram Bot + Groq dual-agent parsing.
- [x] Outbox Pattern with Exponential Backoff and dead-item protection.
- [x] Document Intelligence: NFC-e URL scraper + PDF text extractor.
- [x] Multi-agent routing for Income and Expense logic.
- [x] Custom installment engine with Brazilian credit card billing rules.
- [x] `ThreadedConnectionPool` for cloud-safe database connections.
- [x] `ALLOWED_CHAT_IDS` whitelist security.
- [x] DATE-typed columns for all date fields + SQL indexes.
- [x] `try/finally` safe PDF cleanup (no temp file leaks).
- [x] `transactions.status` sync when all installments are paid.
- [x] Busy-state queue deferral without consuming retry attempts.

#### ✅ V1.5 — AP/AR Dashboard Overhaul (Completed)
- [x] Grouped invoice view: card installments consolidated under "Fatura" header.
- [x] Group invoice payment with proportional discount distribution.
- [x] Individual installment payment with anticipation/discount support.
- [x] Soft-delete (CANCELED) for bank reconciliation.
- [x] Isolated View: filter panel to single transaction's full timeline.
- [x] Fast-Forward (⏭️) button to jump to furthest pending month.
- [x] Return to Current Month button during time navigation.
- [x] Close Panel and Cancel Action escape hatches in all flows.
- [x] Overdue bill warnings with 🔴 indicators and global banner.
- [x] `/help` command with user manual.

#### 🚧 V2 — Scale & Visualization (In Progress)
- [ ] **Task 10 (Streamlit):** Real-time Financial Dashboard for spend analysis, category breakdowns, and monthly cash flow.
- [ ] **Task 11 (FastAPI):** Transition from Long Polling to Webhooks for lower latency and resource usage.
- [ ] **Task 12 (Cloud):** Full cloud hardening with structured logging (`logging` module).
- [ ] **Task 13 (Anticipation):** Commands for early installment payment with discount yield calculation.
- [ ] **Task 14 (UX/UI):** Show card bank and variant next to each pending installment.
- [ ] **DEBT-03 (Analytics View):** `CREATE VIEW monthly_summary` to feed Streamlit aggregations.
- [ ] **BACK-01 (Multi-transaction):** Process arrays of multiple transactions from a single LLM response.
- [ ] **BACK-03 (PDF Decrypt):** Request PDF password mid-conversation via State Machine.

---
---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto

**Zotto** é uma Aplicação de Dados Full-Stack avançada, projetada para atuar como um **ERP financeiro pessoal**. O sistema usa Modelos de Linguagem de Larga Escala (LLMs) para ingerir entradas caóticas e não estruturadas do dia a dia — mensagens de texto livre, URLs de notas fiscais eletrônicas e PDFs complexos de contas — e as transforma em um banco de dados PostgreSQL relacional rigidamente governado, com rastreamento completo de Contas a Pagar e a Receber.

🤝 **Nota de Colaboração com IA:** A visão do produto, as regras de negócio e todas as decisões arquiteturais foram direcionadas por mim. O desenvolvimento do código foi construído através de uma colaboração ativa de pair-programming com **Gemini AI** (Google) e **Claude** (Anthropic).

---

### 🌟 Funcionalidades Principais

- **Ingestão Multimodal:** Aceita mensagens de texto livre, URLs de NFC-e (web scraping) e PDFs de contas de consumo em um único pipeline.
- **Pipeline Dual de Agentes de IA:** Agente 1 extrai entidades brutas com `temperature=0.0`; Agente 2 enriquece e categoriza com `temperature=0.1`.
- **Fila Outbox Resiliente:** Todos os inputs são enfileirados antes de qualquer processamento pela IA. Worker em background tenta com Backoff Exponencial, com adiamento inteligente para limite TPD diário.
- **Confirmação Human-in-the-Loop:** Toda transação requer confirmação explícita do usuário antes da escrita no banco.
- **Dashboard de Contas (`/contas`) com Agrupamento de Faturas:**
  - Parcelas do mesmo cartão agrupadas sob um header "Fatura" com total consolidado.
  - Contas vencidas destacadas com indicador 🔴.
  - Botão Fast-Forward (⏭️) para pular ao mês mais distante com pendências.
  - Navegação temporal com botão de retorno ao mês atual.
  - Escape hatches "Fechar Painel" e "Cancelar Ação" em todos os fluxos.
- **Opções Flexíveis de Pagamento:**
  - Pagar parcelas avulsas com desconto de antecipação.
  - Pagar toda a fatura de um cartão em um clique, com desconto distribuído proporcionalmente.
  - Soft-delete de parcelas para conciliação bancária.
- **Modo Isolado:** Visualize a linha do tempo completa de pagamentos de uma compra específica em isolamento.
- **Whitelist de Controle de Acesso:** `ALLOWED_CHAT_IDS` bloqueia usuários não autorizados.
- **Deploy Cloud-Native:** Railway PaaS com `ThreadedConnectionPool`.

---

### 🛠️ Stack Tecnológico

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.10+ |
| Interface Conversacional | `python-telegram-bot` | 20.8 |
| Motor de IA | Groq API (`llama-4-scout-17b`) | — |
| Banco de Dados | PostgreSQL (Docker / Railway) | 15 |
| Driver de BD | `psycopg2-binary` | 2.9.11 |
| Web Scraping | `BeautifulSoup4` | 4.14.3 |
| Extração de PDF | `PyPDF` | 6.9.1 |
| Aritmética de Datas | `python-dateutil` | 2.9.0 |
| Cliente HTTP | `requests` | 2.32.5 |
| Gestão de Env | `python-dotenv` | 1.2.2 |

---

### 🚀 Como Rodar Localmente

**Pré-requisitos:** Python 3.10+, Docker, e uma chave de API da Groq (gratuita em [console.groq.com](https://console.groq.com)).

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/prBento/finance-ai-app.git
   cd finance-ai-app
   ```

2. **Configure as Variáveis de Ambiente:**
   Crie um arquivo `.env` na raiz. **Nunca faça commit deste arquivo.**
   ```env
   ENVIRONMENT=dev
   TELEGRAM_TOKEN_DEV=seu_token_bot_dev
   TELEGRAM_TOKEN_PROD=seu_token_bot_prod
   GROQ_API_KEY_DEV=sua_chave_groq_dev
   GROQ_API_KEY_PROD=sua_chave_groq_prod
   DB_USER=seu_usuario
   DB_PASSWORD=sua_senha
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
   ALLOWED_CHAT_IDS=seu_chat_id_do_telegram
   ```
   > **Dica:** Envie qualquer mensagem para o bot e veja nos logs do terminal para encontrar seu `chat_id`.

3. **Suba o Banco de Dados:**
   ```bash
   docker-compose up -d
   ```

4. **Instale as Dependências e Inicie:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python bot.py
   ```

---

### 🗺️ Roadmap de Desenvolvimento

#### ✅ V1 — Fundação de Produção (Concluído)
- [x] Ingestão base com pipeline dual-agente via Groq.
- [x] Outbox Pattern com Backoff Exponencial e proteção contra itens zumbi.
- [x] Inteligência de Documentos: scraper NFC-e + extrator de PDF.
- [x] Motor customizado de parcelas com regras de cartão brasileiro.
- [x] Pool de conexões, whitelist de segurança, colunas DATE, índices SQL.
- [x] Adiamento por estado ocupado sem consumir tentativas.

#### ✅ V1.5 — Overhaul do Dashboard AP/AR (Concluído)
- [x] Visão agrupada de faturas por cartão com total consolidado.
- [x] Pagamento em grupo com distribuição proporcional de desconto.
- [x] Pagamento individual com suporte a antecipação/desconto.
- [x] Soft-delete (CANCELED) para conciliação bancária.
- [x] Modo Isolado: filtrar painel para uma única transação.
- [x] Fast-Forward (⏭️) para o mês mais distante com pendências.
- [x] Botão de retorno ao mês atual durante navegação.
- [x] Escape hatches em todos os fluxos críticos.
- [x] Alertas de vencimento com indicadores 🔴 e banner global.
- [x] Comando `/help` com manual do usuário.

#### 🚧 V2 — Escala e Visualização (Em Progresso)
- [ ] **Task 10 (Streamlit):** Dashboard Financeiro em tempo real.
- [ ] **Task 11 (FastAPI):** Transição para Webhooks.
- [ ] **Task 12 (Nuvem):** Logging estruturado com módulo `logging`.
- [ ] **Task 13 (Antecipação):** Cálculo de rendimento de desconto.
- [ ] **Task 14 (UX):** Banco/variante do cartão no `/contas`.
- [ ] **DEBT-03:** `CREATE VIEW monthly_summary` para o Streamlit.
- [ ] **BACK-01:** Processar múltiplas transações por resposta do LLM.
- [ ] **BACK-03:** Descriptografar PDF com senha via chat.