# 🏛️ Technical Specification & System Architecture
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento** — GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

**Project:** Zotto — Finance AI Data App

---

### 1. Architecture Overview

**Hybrid AI Architecture** with strict separation between intelligence and determinism. LLMs handle unstructured-to-structured translation only. Prompts are isolated in a dedicated `prompts.py` file to separate prompt engineering from application logic. Python handles all financial math, state management, and governance.

**Dual-mode deployment:** In `prod`, FastAPI + Uvicorn serves a Telegram Webhook endpoint on the Railway-provisioned PORT. In `dev`, the same codebase falls back to Long Polling — no Ngrok required. 

**Three-surface architecture:** Data enters through the Telegram Bot (operational), is stored in PostgreSQL, and is read by the Streamlit dashboard (analytical). Both surfaces share the same database. To bridge the gap, the Telegram Bot acts as a gateway to the Streamlit app via **Telegram Mini Apps (Web Apps)** natively.

---

### 2. Core Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | **Entry Interface** | `python-telegram-bot` | Async handlers, State Machine, Inline UI, WebApp integration |
| 2 | **Web Server (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Outbox Queue** | PostgreSQL `process_queue` | Decouples ingestion from processing. Guaranteed delivery. |
| 4 | **Document Intelligence** | `BeautifulSoup4`, `PyPDF` | NFC-e URL scraping and PDF text extraction |
| 5 | **AI Prompt Engine** | `prompts.py` | Centralized system instructions separating AI logic from backend code. |
| 6 | **AI Agent 1** | Groq `llama-4-scout-17b` | Raw entity extraction. `temperature=0.0`. Chain-of-Thought date parsing. |
| 7 | **AI Agent 2** | Groq `llama-4-scout-17b` | Categorization with disambiguation rules. `temperature=0.1`. |
| 8 | **AP/AR Dashboard** | Telegram Inline UI | Progressive disclosure UI, monospace summary, accordion invoice view, isolated view |
| 9 | **Cash Flow Statement** | Telegram Inline UI | `/extrato` with "Invisible Grid" UI, benefit wallet separation, and dynamic installment index |
| 10| **Payment Engine** | `database.py` | Anticipation logic, cash-basis reallocation, dynamic method override |
| 11| **BI Dashboard** | Streamlit + Plotly | 5-tab analytical surface served natively inside Telegram via `/dashboard` |
| 12| **Database** | PostgreSQL | Relational AP/AR ledger. SCD audit columns. CTE-powered queries. |

---

### 3. Functional Requirements (FRs)

* **FR01** — Multimodal ingestion: free-text, NFC-e URL, PDF.
* **FR02** — Dual LLM pipeline with disambiguation ruleset.
* **FR03** — Hidden discount detection: `if sum(items) > invoice_total` → auto-register difference as discount.
* **FR04** — Custom installment engine with Brazilian credit card billing rules.
* **FR05** — Human-in-the-Loop confirmation before every database write.
* **FR06** — AP/AR Dashboard (`/contas`): Progressive disclosure UI with monospace header, accordion credit card grouping, overdue alerts.
* **FR07** — Smart payment settlement: dynamic method override at pay time.
* **FR08** — Group invoice payment with proportional discount distribution.
* **FR09** — Installment soft-delete (`CANCELED`) for bank reconciliation.
* **FR10** — Cash Flow Statement (`/extrato`): "Invisible Grid" design, benefit wallet isolation, pending item `*` indicator.
* **FR11** — Interactive help system: inline button menu with topic-specific sub-pages.
* **FR12** — Duplicate detection: exact `invoice_number` match + fuzzy `(location ILIKE + amount + date)`.
* **FR13** — Streamlit BI Dashboard: 5-tab financial intelligence surface with correct cash-basis KPIs, savings rate, hierarchical item analysis.
* **FR14** — Global BI Filters: Date filtering and Blacklist-style location filter (starts empty, user selects what to hide).
* **FR15** — Telegram Mini App Integration: `/dashboard` command serves the Streamlit BI interface securely inside the Telegram UI via `WebAppInfo`.

---

### 4. Non-Functional Requirements (NFRs)

* **NFR01** — Resilience: Outbox Pattern + `FOR UPDATE SKIP LOCKED`.
* **NFR02** — Exponential Backoff: standard errors 60s–3600s; TPD rate limit defers 90 minutes.
* **NFR03** — Dead item prevention: `max_attempts` (default 5).
* **NFR04** — Busy-state deferral: `reschedule_queue_item_busy` defers without consuming a retry attempt.
* **NFR05** — Connection Pool: `ThreadedConnectionPool` (1–10).
* **NFR06** — Fault-tolerant JSON: strips LLM hallucinations before parsing.
* **NFR09** — Cash Basis Accounting: paid installment `month` updated to payment month.
* **NFR11** — Dual deployment: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.
* **NFR14** — DevEx DB Syncing: Local environment can safely pull production data via a disposable Docker pipeline (`sync_db.ps1`) reading dynamic credentials from `.env` to prevent credential leaks.
* **NFR15** — DevEx Tunneling: Local testing of Web Apps requires secure HTTPS tunnels (e.g., ngrok) injected via the `DASHBOARD_URL` environment variable.

---

### 5. Architectural Decisions: The "Why?"

#### 5.14. Web App Integration (Mini App)
Instead of forcing the user to leave the Telegram environment to view complex charts on a browser, we use Telegram's `WebAppInfo` feature. The Streamlit dashboard acts as a headless PWA injected securely inside the Telegram interface, maintaining the context loop and improving UX drastically. Since Telegram requires `https://`, local testing relies on `ngrok` tunnels configured via `.env` without polluting the core codebase.

---

### 6. Database Schema

```sql
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf
    status [PENDING | PROCESSING | COMPLETED | DEAD | CANCELLED]
    attempts, max_attempts, next_attempt

transactions  ←─────────────────────────────────────────┐
    id, transaction_type, invoice_number                 │ FK ON DELETE CASCADE
    transaction_date (DATE), location_name               │
    card_bank, card_variant                              │
    status [Ativa | PAID]                                │
    original_amount, discount_applied, total_amount      │
    macro_category, payment_method                       │
    is_installment, installment_count                    │
                                                         │
transaction_items ─── transaction_id (FK) ───────────────┤
    description, brand, unit_price, quantity             │
    cat_macro, cat_category, cat_subcategory, cat_product│
                                                         │
installments ──────── transaction_id (FK) ───────────────┘
    month (MM/YYYY)  ← mutable: updated to payment month (cash basis)
    due_date (DATE)  ← immutable: original contractual date
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount
```

---

### 7. Deployment Architecture

```text
Railway Project
├── Plugin: PostgreSQL ─────────────────────────────────────┐
│   └── DATABASE_URL (internal)                             │ shared
│                                                           │
├── Service 1: Bot (web)                                    │
│   ├── Procfile: "web: python bot.py"                      │
│   ├── DASHBOARD_URL (points to Service 2)                 │
│   ├── GET  /health   → liveness probe                     │
│   └── POST /webhook  → telegram_app.process_update()      │
│       └── job_queue (10s) → queue_processor()             │
│                                                           │
└── Service 2: Dashboard                                    │
    ├── Start Command:                                      │
    │   streamlit run dashboard.py                          │
    │     --server.port $PORT                               │
    │     --server.address 0.0.0.0                          │
    └── DATABASE_URL ──────────────────────────────────────►┘

Local (dev)
├── sync_db.ps1           → Copies Prod DB to Local RAM safely using .env
├── ngrok http            → Tunnels Local Streamlit for Telegram Mini App testing
├── python bot.py         → run_polling()
└── streamlit run dashboard.py
```

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Zotto — Finance AI Data App

---

### 1. Visão Geral da Arquitetura

**Arquitetura de IA Híbrida** com separação estrita entre inteligência e determinismo. Os LLMs lidam exclusivamente com a tradução de dados não estruturados para estruturados. Os prompts da IA são isolados em um arquivo `prompts.py` dedicado. 

**Arquitetura de três superfícies:** Os dados entram pelo Bot do Telegram (operacional), são armazenados no PostgreSQL, e lidos pelo dashboard Streamlit (analítico). Para fechar essa lacuna de forma nativa, o Bot do Telegram atua como um portal para o Streamlit através do uso de **Mini Apps (Web Apps)** nativos do próprio Telegram.

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface de Entrada** | `python-telegram-bot` | Handlers assíncronos, Máquina de Estados, Integração WebApp |
| 2 | **Servidor Web (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Fila Outbox** | PostgreSQL `process_queue` | Desacopla a ingestão do processamento. |
| 4 | **Inteligência de Docs** | `BeautifulSoup4`, `PyPDF` | Scraping NFC-e e extração de texto de PDF |
| 5 | **Motor de Prompts IA**| `prompts.py` | Centraliza instruções do sistema, separando IA do back-end. |
| 6 | **IA Agente 1 & 2** | Groq `llama-4-scout-17b` | Extração bruta (temp=0.0) e Categorização (temp=0.1). |
| 7 | **Dashboard AP/AR** | Telegram Inline UI | Disclosure progressivo, header monospace, acordeons |
| 8 | **Extrato Financeiro** | Telegram Inline UI | `/extrato` com "Grid Invisível" e carteira de benefício separada |
| 9 | **Motor de Pagamento** | `database.py` | Realocação em regime de caixa, sobrescrita de método |
| 10| **Dashboard BI** | Streamlit + Plotly | Superfície analítica injetada no Telegram via `/dashboard` |
| 11| **Banco de Dados** | PostgreSQL | Livro Caixa AP/AR relacional. |

---

### 3. Requisitos Funcionais (FRs)

* **FR01** — Ingestão multimodal: texto livre, URL de NFC-e, faturas em PDF.
* **FR02** — Pipeline de LLM duplo com regras de desambiguação.
* **FR03** — Detecção de desconto oculto: `if sum(items) > invoice_total`.
* **FR04** — Motor próprio de parcelamento (regras bancárias brasileiras).
* **FR05** — Human-in-the-Loop antes de cada gravação no BD.
* **FR06** — Dashboard AP/AR (`/contas`): UI com disclosure progressivo, visão isolada, navegação "fast-forward".
* **FR07** — Baixa de pagamento inteligente: sobrescrita dinâmica de método na hora de pagar.
* **FR10** — Extrato Financeiro (`/extrato`): Design "Grid Invisível", tag `[B]`, índice dinâmico (`8/10`).
* **FR13** — Dashboard BI Streamlit: Inteligência financeira em 5 abas com KPIs corretos em regime de caixa.
* **FR14** — Filtros Globais BI: Filtro Blacklist (começa vazio, usuário escolhe o que ocultar).
* **FR15** — Integração Mini App Telegram: Comando `/dashboard` serve a interface do Streamlit de forma segura dentro da interface do Telegram usando `WebAppInfo`.

---

### 4. Requisitos Não Funcionais (NFRs)

* **NFR01** — Resiliência: Padrão Outbox + `FOR UPDATE SKIP LOCKED`.
* **NFR02** — Backoff Exponencial e limite TPD.
* **NFR04** — Adiamento por "Estado Ocupado".
* **NFR09** — Contabilidade em Regime de Caixa: coluna `month` muda para o mês do pagamento real.
* **NFR10** — Indexação CTE: `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)`.
* **NFR14** — Experiência do Desenvolvedor (DevEx DB): Script Docker `sync_db.ps1` lê credenciais dinamicamente do `.env`.
* **NFR15** — DevEx Tunneling: O teste local do Web App exige túneis HTTPS seguros (ex: `ngrok`) injetados através da variável de ambiente `DASHBOARD_URL`.

---

### 5. Decisões Arquiteturais: O "Por quê?"

#### 5.14. Integração Web App (Mini App)
Em vez de forçar o usuário a sair do ambiente do Telegram para abrir um navegador e analisar gráficos, utilizamos o recurso `WebAppInfo` do Telegram. O dashboard em Streamlit age como um PWA (Progressive Web App) e é injetado com segurança dentro da interface modal do celular, mantendo a imersão e elevando a UX a níveis de app nativo de banco. Para testes locais (que exigem `https://`), a dependência é resolvida elegantemente usando túneis como o `ngrok` controlados apenas pelo arquivo `.env`.

---

### 7. Arquitetura de Deploy

```text
Projeto Railway
├── Plugin: PostgreSQL ─────────────────────────────────────┐
│   └── DATABASE_URL (URL interna)                          │ partilhado
│                                                           │
├── Serviço 1: Bot (web)                                    │
│   ├── Procfile: "web: python bot.py"                      │
│   ├── DASHBOARD_URL (aponta para o Serviço 2)             │
│   ├── GET  /health   → liveness probe                     │
│   └── POST /webhook  → telegram_app.process_update()      │
│                                                           │
└── Serviço 2: Dashboard                                    │
    ├── Start Command:                                      │
    │   streamlit run dashboard.py                          │
    │     --server.port $PORT                               │
    │     --server.address 0.0.0.0                          │
    └── DATABASE_URL ──────────────────────────────────────►┘

Ambiente Local (dev)
├── sync_db.ps1           → Clona Prod -> Local via RAM consumindo o .env
├── ngrok http            → Cria túnel HTTPS para testar o Telegram Mini App
├── python bot.py         → run_polling()
└── streamlit run dashboard.py
```