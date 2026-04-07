# 💰 Zotto — Finance AI Data App: LLM-Powered Personal ERP
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento** — GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🎯 About the Project

**Zotto** is a Full-Stack Data Application acting as a **personal financial ERP**. It uses Large Language Models to ingest unstructured daily inputs — free-text messages, electronic invoice URLs, and complex PDF bills — and transforms them into a strictly governed, relational PostgreSQL database with full Accounts Payable/Receivable tracking and a real-time Cash Flow Statement.

🤝 **AI Collaboration Note:** Product vision, business rules, and architectural decisions by me. Code development through pair-programming with **Gemini AI** (Google) and **Claude** (Anthropic).

---

### 🌟 Key Features

- **Multimodal Ingestion:** Free-text, NFC-e URLs (web scraping), and PDF utility bills in one pipeline.
- **Dual-Agent AI Pipeline:** Agent 1 extracts (`temperature=0.0`); Agent 2 categorizes (`temperature=0.1`). Includes a disambiguation ruleset to prevent common misclassifications (e.g., Total Pass → Academy, iFood → Food, streaming → Subscriptions).
- **Hidden Discount Detection:** If the mathematical sum of invoice items exceeds the invoice total, the backend automatically registers the difference as a discount — catching what the LLM missed.
- **Resilient Outbox Queue:** All inputs queued before any AI processing. Exponential Backoff (60s–3600s), TPD-aware deferral to next day at 09:00, and `max_attempts` dead-item protection.
- **Human-in-the-Loop Confirmation:** Structured Markdown summary before every database write.
- **AP/AR Dashboard (`/contas`):**
  - Credit card installments grouped under a consolidated "Fatura" header.
  - Incomes (🟢/🟡) visually differentiated from Expenses (🔹/🔴) with adapted action texts throughout all flows.
  - Overdue alerts, month navigation, Fast-Forward (⏭️), Return to Current Month.
  - Isolated View for tracking a single multi-month purchase timeline.
  - Close Panel and Cancel Action escape hatches at every step.
- **Cash Flow Statement (`/extrato`):**
  - Saldo Atual (actual) and Saldo Projetado (projected including pending items).
  - **Benefit Wallet separation:** VA/VR/prepaid balances displayed and calculated independently from the main wallet.
  - Monospaced transaction list with dynamic installment index (e.g., `Samsung  05/04 - (1.200,00)  8/10`).
  - Pending items marked with `*`; month navigation with Return to Current Month.
- **Cash Basis Accounting:** When a credit card invoice is paid, installment `month` fields update to the payment month. The `/extrato` shows when money actually moved; `/contas` retains original due dates for bill management.
- **Group Invoice Payment:** Pay entire credit card invoice in one click, with optional discount distributed proportionally across all items.
- **Installment Cancellation:** Soft-delete for bank reconciliation without affecting future installments.
- **Access Control:** `ALLOWED_CHAT_IDS` whitelist via `security_check` decorator on all handlers.
- **Cloud-Native:** Railway PaaS with `ThreadedConnectionPool`.

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

**Prerequisites:** Python 3.10+, Docker, Groq API key ([console.groq.com](https://console.groq.com)).

1. **Clone:** `git clone https://github.com/prBento/finance-ai-app.git && cd finance-ai-app`

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
   > **Tip:** Send any message to your bot and check terminal logs to find your `chat_id`.

3. **Start DB:** `docker-compose up -d`

4. **Install & run:**
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt && python bot.py
   ```

---

### 🗂️ Project Structure

```
finance-ai-app/
├── bot.py              # Handlers, State Machine, queue worker, AI pipeline, UI rendering
├── database.py         # All DB functions, connection pool, CTE queries, table creation
├── Procfile            # Railway process definition
├── docker-compose.yml  # Local PostgreSQL setup
├── requirements.txt    # Python dependencies
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
- [x] Dual-agent parsing, Outbox Pattern with Backoff, NFC-e + PDF intelligence.
- [x] Custom installment engine, ThreadedConnectionPool, whitelist, DATE columns + indexes.

#### ✅ V1.5 — AP/AR Dashboard Overhaul
- [x] Grouped invoice view, group payment with proportional discount.
- [x] Isolated View, Fast-Forward, Return to Current Month, escape hatches.
- [x] Income/Expense visual differentiation throughout. Busy-state queue deferral.

#### ✅ V1.6 — Cash Flow & Financial Intelligence
- [x] `/extrato` command with monthly Cash Flow Statement.
- [x] Benefit Wallet (VA/VR) separation with independent balance.
- [x] Dynamic installment index (`8/10`) via CTE `ROW_NUMBER()`.
- [x] Cash Basis Accounting: `month` field updated on group invoice payment.
- [x] Hidden discount detector in post-LLM math validation.
- [x] Disambiguation ruleset in Agent 2 prompt.
- [x] Income support in `/contas` with adapted action texts.

#### 🚧 V2 — Scale & Visualization
- [ ] **Task 10 (Streamlit):** Real-time Financial Dashboard.
- [ ] **Task 11 (FastAPI):** Webhooks replacing Long Polling.
- [ ] **Task 12:** Structured logging with `logging` module.
- [ ] **DEBT-03:** `CREATE VIEW monthly_summary` for Streamlit.
- [ ] **BACK-01:** Multi-transaction support per LLM response.
- [ ] **BACK-03:** PDF password decryption mid-conversation.

---
---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto

**Zotto** é uma Aplicação de Dados Full-Stack que atua como um **ERP financeiro pessoal**. Usa LLMs para ingerir inputs caóticos do dia a dia e os transforma em um banco de dados PostgreSQL rigidamente governado, com rastreamento completo de Contas a Pagar/Receber e um Extrato de Fluxo de Caixa em tempo real.

🤝 **Colaboração IA:** Visão e decisões por mim. Código em pair-programming com **Gemini AI** e **Claude**.

---

### 🌟 Funcionalidades Principais

- **Ingestão Multimodal:** Texto livre, URLs NFC-e e PDFs em um único pipeline.
- **Pipeline Dual de Agentes:** Extração (`temperature=0.0`) + categorização (`temperature=0.1`) com regras de desambiguação (Total Pass → Academia, iFood → Alimentação, streaming → Assinaturas, etc.).
- **Detecção de Desconto Oculto:** Se a soma dos itens exceder o total da nota, a diferença é registrada automaticamente como desconto.
- **Fila Outbox Resiliente:** Backoff Exponencial, adiamento para 09:00 em limite TPD, proteção contra itens zumbi.
- **Dashboard AP/AR (`/contas`):** Faturas agrupadas, Receitas (🟢/🟡) vs Despesas (🔹/🔴), alertas, Modo Isolado, Fast-Forward, escape hatches.
- **Extrato de Fluxo de Caixa (`/extrato`):**
  - Saldo Atual e Projetado.
  - **Separação de Carteira Benefício** (VA/VR) com saldo independente.
  - Lista monoespaciada com índice dinâmico de parcela (`8/10`) e marcador `*` para pendências.
- **Regime de Caixa:** Campo `month` atualizado para o mês do pagamento real. O `/extrato` mostra quando o dinheiro se moveu; o `/contas` preserva as datas originais.
- **Pagamento em Grupo:** Fatura inteira com desconto distribuído proporcionalmente.
- **Cancelamento de Parcela:** Soft-delete para conciliação bancária.

---

### 🗺️ Roadmap

#### ✅ V1 — Fundação
#### ✅ V1.5 — Dashboard AP/AR
#### ✅ V1.6 — Fluxo de Caixa e Inteligência Financeira
- [x] `/extrato`, Carteira Benefício, índice `8/10`, Regime de Caixa, detector de desconto, desambiguação, suporte a Receitas.

#### 🚧 V2 — Streamlit, Webhooks, logging, múltiplas transações, PDF com senha.