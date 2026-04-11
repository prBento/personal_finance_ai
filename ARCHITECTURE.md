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

**Dual-mode deployment:** In `prod`, FastAPI + Uvicorn serves a Telegram Webhook endpoint on the Railway-provisioned PORT. In `dev`, the same codebase falls back to Long Polling — no Ngrok required. Branch: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.

**Three-surface architecture:** Data enters through the Telegram Bot (operational), is stored in PostgreSQL, and is read by the Streamlit dashboard (analytical). Both surfaces share the same database and `database.py` connection pool — no ETL, no sync layer.

---

### 2. Core Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | **Entry Interface** | `python-telegram-bot` | Async handlers, State Machine, Inline UI |
| 2 | **Web Server (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Outbox Queue** | PostgreSQL `process_queue` | Decouples ingestion from processing. Guaranteed delivery. |
| 4 | **Document Intelligence** | `BeautifulSoup4`, `PyPDF` | NFC-e URL scraping and PDF text extraction |
| 5 | **AI Prompt Engine** | `prompts.py` | Centralized system instructions separating AI logic from backend code. |
| 6 | **AI Agent 1** | Groq `llama-4-scout-17b` | Raw entity extraction. `temperature=0.0`. Chain-of-Thought date parsing. |
| 7 | **AI Agent 2** | Groq `llama-4-scout-17b` | Categorization with disambiguation rules. `temperature=0.1`. |
| 8 | **AP/AR Dashboard** | Telegram Inline UI | Progressive disclosure UI, monospace summary, accordion invoice view, isolated view |
| 9 | **Cash Flow Statement** | Telegram Inline UI | `/extrato` with "Invisible Grid" UI, benefit wallet separation, and dynamic installment index |
| 10| **Payment Engine** | `database.py` | Anticipation logic, cash-basis reallocation, dynamic method override |
| 11| **BI Dashboard** | Streamlit + Plotly | 5-tab analytical surface with Blacklist filters, reading directly from PostgreSQL |
| 12| **Database** | PostgreSQL | Relational AP/AR ledger. SCD audit columns. CTE-powered queries. |

---

### 3. Functional Requirements (FRs)

* **FR01** — Multimodal ingestion: free-text, NFC-e URL, PDF.
* **FR02** — Dual LLM pipeline with disambiguation ruleset (NF-e → always DESPESA; Total Pass → Academia; iFood → Alimentação; streaming → Assinaturas).
* **FR03** — Hidden discount detection: `if sum(items) > invoice_total` → auto-register difference as discount.
* **FR04** — Custom installment engine with Brazilian credit card billing rules (fechamento/vencimento cycles).
* **FR05** — Human-in-the-Loop confirmation before every database write. Summary shows discount breakdown when applicable.
* **FR06** — AP/AR Dashboard (`/contas`): Progressive disclosure UI with monospace header, accordion credit card grouping, income vs expense visual differentiation, overdue alerts, isolated view, fast-forward navigation.
* **FR07** — Smart payment settlement: dynamic method override at pay time. Credit card anticipation moves installment to next invoice cycle (stays PENDING). Cash/Pix marks PAID and reallocates `month` field.
* **FR08** — Group invoice payment with proportional discount distribution across all items.
* **FR09** — Installment soft-delete (`CANCELED`) for bank reconciliation.
* **FR10** — Cash Flow Statement (`/extrato`): "Invisible Grid" design, Saldo Atual + Projetado, benefit wallet isolation, `[B]` tag, dynamic installment index (`8/10`), pending item `*` indicator.
* **FR11** — Interactive help system: inline button menu with topic-specific sub-pages and back navigation.
* **FR12** — Duplicate detection: exact `invoice_number` match + fuzzy `(location ILIKE + amount + date)`.
* **FR13** — Streamlit BI Dashboard: 5-tab financial intelligence surface with correct cash-basis KPIs, savings rate, benefit wallet isolation, historical trends, card participation, income commitment gauge, hierarchical item analysis, frequency vs ticket scatter, day-of-month heatmap.
* **FR14** — Global BI Filters: Date filtering and Blacklist-style location filter (starts empty, user selects what to hide) to prevent UI clutter.

---

### 4. Non-Functional Requirements (NFRs)

* **NFR01** — Resilience: Outbox Pattern + `FOR UPDATE SKIP LOCKED` for concurrent processing safety.
* **NFR02** — Exponential Backoff: standard errors 60s–3600s; TPD rate limit defers 90 minutes.
* **NFR03** — Dead item prevention: `max_attempts` (default 5) → status `DEAD`.
* **NFR04** — Busy-state deferral: `reschedule_queue_item_busy` defers without consuming a retry attempt.
* **NFR05** — Connection Pool: `ThreadedConnectionPool` (1–10), shared between bot and dashboard via `database.py`.
* **NFR06** — Fault-tolerant JSON: strips LLM hallucinations before `json.loads(..., strict=False)`.
* **NFR07** — Math validation: recalculates totals from items post-LLM; detects hidden discounts.
* **NFR08** — Access control: `ALLOWED_CHAT_IDS` via `security_check` decorator on all public handlers.
* **NFR09** — Cash Basis Accounting: paid installment `month` updated to payment month. `/extrato` and Streamlit use `paid_amount` for PAID items and `expected_amount` for PENDING. Never mix.
* **NFR10** — CTE installment indexing: `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)` survives `month` field updates.
* **NFR11** — Dual deployment: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.
* **NFR12** — Dashboard data freshness: `@st.cache_data(ttl=60)` on all query functions — at most 60 seconds stale, no manual refresh required.
* **NFR13** — Dashboard regime consistency: financial tabs use `month` (cash basis); operational tab (items) uses `transaction_date` (accrual). Each tab declares its regime in a visible caption.
* **NFR14** — Developer Experience (DevEx): Local environment can safely pull production data via a disposable Docker pipeline (`sync_db.ps1`) reading dynamic credentials from `.env` to prevent credential leaks.

---

### 5. Architectural Decisions: The "Why?"

#### 5.1. Dual-Agent LLM Pipeline & Prompts Isolation
Isolated failure modes and calibrated temperatures per task. Centralizing prompts in `prompts.py` ensures the `bot.py` file remains strictly focused on business logic and routing, while the LLM behavior can be versioned and tweaked independently. Chain-of-Thought date reasoning prevents the most common PDF extraction errors.

#### 5.2. Transactional Outbox Pattern
Instant UX (< 100ms "Received"). Guaranteed delivery. `FOR UPDATE SKIP LOCKED` prevents race conditions without distributed locks.

#### 5.3. Custom Installment Engine
Brazilian credit card billing (fechamento/vencimento) is not modeled by any standard financial library.

#### 5.4. Credit Card Anticipation vs. Cash Payment
Paying a credit card installment early recalculates the target invoice cycle and moves the debt there — stays PENDING. This models how credit cards actually work. All non-card payments mark PAID and reallocate `month` for cash-basis reporting.

#### 5.5. FastAPI + Long Polling Dual Mode
Webhook requires a public HTTPS URL that doesn't exist locally. The `if ENV == "prod"` branch keeps the same codebase working in both environments with zero extra tooling for local dev.

#### 5.6. `month` vs `due_date` — Two Date Fields by Design
`due_date` is immutable (original contractual date). Used by `/contas` for overdue calculation. `month` is mutable (updated to payment month for cash-basis). Used by `/extrato` and Streamlit for financial reporting. They intentionally diverge after payment.

#### 5.7. Benefit Wallet Separation
VA/VR/prepaid balances are not fungible with cash. Mixing them gives a misleading picture of available liquidity. Both `/extrato` and the Streamlit dashboard apply the same detection logic: `payment_method` keywords + `card_bank` name matching.

#### 5.8. CTE `ROW_NUMBER()` for Installment Index
The sequence must survive cash-basis `month` field updates. Computing from the immutable `id` column at query time always returns the correct "8 of 10".

#### 5.9. Streamlit as a Separate Railway Service
Streamlit's blocking server model is incompatible with FastAPI's async event loop. Running them as separate Railway services keeps both clean and independently restartable. They share the same PostgreSQL plugin via `DATABASE_URL`.

#### 5.10. `paid_amount` vs `expected_amount` in KPIs
Using `expected_amount` for all installments overestimates realized expenses when discounts were applied at settlement. The correct model: for PAID installments use `paid_amount`; for PENDING use `expected_amount`. This is encapsulated in the `real_amount` computed column.

#### 5.11. Two Analytical Regimes in the Same Dashboard
Financial tabs operate on `month` (cash basis) — reflecting when money moved. The Operational tab operates on `transaction_date` (accrual) — reflecting when the purchase happened. Mixing them in the same calculation is the bug to avoid.

#### 5.12. Progressive Disclosure & Invisible Grid (UI/UX)
Telegram messages have strict character and screen real-estate limits. 
- `/contas` uses Progressive Disclosure: a monospace header summarizes the macro view, and the user clicks to expand the operational accordion buttons.
- `/extrato` uses an "Invisible Grid" approach: replacing heavy line separators `----` with double spacing (`\n\n`) to let the interface breathe natively within the chat bubble.

#### 5.13. Secure Production DB Syncing (DevEx)
Local development requires real-world data to test edge cases. Instead of manual dumps, a PowerShell script (`sync_db.ps1`) dynamically parses the local `.env` file for credentials, pipes the Railway database directly into the local Docker container in RAM, and exits. Zero hardcoded passwords, zero dangling `.sql` files, and perfect UTF-8 preservation.

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

Indexes:
  idx_installments_month_status ON installments(month, payment_status)
  idx_queue_status_next         ON process_queue(status, next_attempt)
  idx_transactions_date_type    ON transactions(transaction_date, transaction_type)
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
│   ├── FastAPI binds to $PORT                              │
│   ├── GET  /health   → liveness probe                     │
│   └── POST /webhook  → telegram_app.process_update()      │
│       └── job_queue (10s) → queue_processor()             │
│                                                           │
└── Service 2: Dashboard                                    │
    ├── Start Command:                                      │
    │   streamlit run dashboard.py                          │
    │     --server.port $PORT                               │
    │     --server.address 0.0.0.0                          │
    ├── DATABASE_URL ──────────────────────────────────────►┘
    └── @st.cache_data(ttl=60) on all queries

Local (dev)
├── sync_db.ps1           → Copies Prod DB to Local RAM safely using .env
├── python bot.py         → run_polling()
└── streamlit run dashboard.py
```

---

### 8. Security Strategy

- **Secrets:** `.env` locally, Railway Variables panel per service in production.
- **Dynamic Local Sync:** `sync_db.ps1` dynamically parses `.env` without loading it globally, piping data directly via Docker to prevent credential leaks to GitHub.
- **Access control (bot):** `ALLOWED_CHAT_IDS` whitelist via `security_check` decorator on all public handlers.
- **Access control (dashboard):** No built-in auth in Streamlit. For personal use, keeping the Railway service URL private is sufficient.
- **Stateless bot:** PDFs deleted in `finally` blocks. No sensitive state written to disk.
- **SQL injection:** All queries use parameterized `%s` placeholders.
- **Webhook security:** `/webhook` endpoint only accepts updates routed from Telegram's registered URL.

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Zotto — Finance AI Data App

---

### 1. Visão Geral da Arquitetura

**Arquitetura de IA Híbrida** com separação estrita entre inteligência e determinismo. Os LLMs lidam exclusivamente com a tradução de dados não estruturados para estruturados. Os prompts da IA são isolados em um arquivo `prompts.py` dedicado. O Python processa toda a matemática financeira, o gerenciamento de estados e a governança no banco de dados.

**Deploy de modo duplo:** Em `prod`, o FastAPI + Uvicorn expõe um endpoint Webhook do Telegram na porta (`PORT`) provida pelo Railway. Em `dev`, o mesmo código recua automaticamente para Long Polling — sem necessidade de Ngrok. Gatilho: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.

**Arquitetura de três superfícies:** Os dados entram pelo Bot do Telegram (operacional), são armazenados no PostgreSQL, e lidos pelo dashboard Streamlit (analítico). Ambas as superfícies compartilham o mesmo banco de dados e o pool de conexões do `database.py` — sem necessidade de pipelines ETL ou camadas de sincronização.

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface de Entrada** | `python-telegram-bot` | Handlers assíncronos, Máquina de Estados, UI Inline |
| 2 | **Servidor Web (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Fila Outbox** | PostgreSQL `process_queue` | Desacopla a ingestão do processamento. Entrega garantida. |
| 4 | **Inteligência de Docs** | `BeautifulSoup4`, `PyPDF` | Web scraping de URLs de NFC-e e extração de texto de PDF |
| 5 | **Motor de Prompts IA**| `prompts.py` | Centraliza instruções do sistema, separando IA do back-end. |
| 6 | **IA Agente 1** | Groq `llama-4-scout-17b` | Extração bruta de entidades. `temperature=0.0`. Raciocínio Chain-of-Thought para datas. |
| 7 | **IA Agente 2** | Groq `llama-4-scout-17b` | Categorização com regras de desambiguação. `temperature=0.1`. |
| 8 | **Dashboard AP/AR** | Telegram Inline UI | Disclosure progressivo, header monospace, acordeons, modo isolado |
| 9 | **Extrato Financeiro** | Telegram Inline UI | `/extrato` com "Grid Invisível", carteira de benefício separada e índice dinâmico |
| 10| **Motor de Pagamento** | `database.py` | Lógica de antecipação, realocação em regime de caixa, sobrescrita de método |
| 11| **Dashboard BI** | Streamlit + Plotly | Superfície analítica de 5 abas com filtro Blacklist, lendo direto do PostgreSQL |
| 12| **Banco de Dados** | PostgreSQL | Livro Caixa AP/AR relacional. Colunas de auditoria SCD. Consultas CTE. |

---

### 3. Requisitos Funcionais (FRs)

* **FR01** — Ingestão multimodal: texto livre, URL de NFC-e, faturas em PDF.
* **FR02** — Pipeline de LLM duplo com regras de desambiguação (NF-e → sempre DESPESA; Total Pass → Academia; iFood → Alimentação; streaming → Assinaturas).
* **FR03** — Detecção de desconto oculto: `if sum(items) > invoice_total` → registra automaticamente a diferença como desconto.
* **FR04** — Motor próprio de parcelamento com regras bancárias de cartão de crédito no Brasil (fechamento/vencimento).
* **FR05** — Human-in-the-Loop (Confirmação humana) antes de cada gravação no banco de dados. O resumo mostra quebra de descontos, se aplicável.
* **FR06** — Dashboard AP/AR (`/contas`): UI com disclosure progressivo, cabeçalho de resumo monospace, agrupamento em acordeon por cartão de crédito, diferenciação visual de receita/despesa, alertas de vencimento, visão isolada, navegação "fast-forward".
* **FR07** — Baixa de pagamento inteligente: sobrescrita dinâmica de método na hora de pagar. Antecipação de cartão de crédito move a parcela para o próximo ciclo de fatura (continua PENDENTE). Pix/Dinheiro marca como PAGO e realoca a coluna `month` para o regime de caixa.
* **FR08** — Pagamento de fatura completa (em lote) com distribuição proporcional de descontos sobre os itens.
* **FR09** — Soft-delete (`CANCELED`) de parcelas para fins de conciliação bancária.
* **FR10** — Extrato Financeiro (`/extrato`): Design com "Grid Invisível", Saldo Atual + Projetado, isolamento da carteira de benefícios, tag `[B]`, índice dinâmico de parcelas (`8/10`), indicador de pendência `*`.
* **FR11** — Sistema de ajuda interativo (`/help`): menu de botões inline com sub-páginas temáticas e navegação de retorno.
* **FR12** — Detecção de duplicidade: match exato de `invoice_number` + match heurístico `(location ILIKE + amount + date)`.
* **FR13** — Dashboard BI Streamlit: Inteligência financeira em 5 abas com KPIs corretos em regime de caixa, taxa de poupança, isolamento de benefícios, histórico de tendências, uso de cartões, gauge de comprometimento, análise hierárquica de itens (treemap → sunburst → tabela), scatter ticket vs frequência, heatmap de dia do mês.
* **FR14** — Filtros Globais BI: Filtro de datas e filtro de locais em estilo "Blacklist" (começa vazio, usuário escolhe o que ocultar) para evitar poluição visual.

---

### 4. Requisitos Não Funcionais (NFRs)

* **NFR01** — Resiliência: Padrão Outbox + `FOR UPDATE SKIP LOCKED` para concorrência segura.
* **NFR02** — Backoff Exponencial: erros padrão aguardam 60s–3600s; rate limit TPD defere para 90 minutos.
* **NFR03** — Prevenção de item zumbi: limite `max_attempts` (padrão 5) → converte status para `DEAD`.
* **NFR04** — Adiamento por "Estado Ocupado": `reschedule_queue_item_busy` adia mensagens sem queimar a contagem de tentativas se o usuário estiver respondendo a um questionário.
* **NFR05** — Connection Pool: `ThreadedConnectionPool` (1–10 conexões), compartilhado entre bot e dashboard via `database.py`.
* **NFR06** — JSON Tolerante a Falhas: limpa alucinações (comentários) do LLM antes de usar `json.loads(..., strict=False)`.
* **NFR07** — Validação Matemática: recalcula totais usando os itens pós-LLM; detecta descontos escondidos.
* **NFR08** — Controle de Acesso: Whitelist `ALLOWED_CHAT_IDS` via decorator `security_check` em todos os comandos.
* **NFR09** — Contabilidade em Regime de Caixa: coluna `month` da parcela muda para o mês do pagamento. `/extrato` e Streamlit usam `paid_amount` para itens PAGOS e `expected_amount` para itens PENDENTES. Nunca os dois somados.
* **NFR10** — Indexação CTE: `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)` sobrevive a atualizações da coluna `month`.
* **NFR11** — Deploy Híbrido: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.
* **NFR12** — Frescor de Dados (Dashboard): `@st.cache_data(ttl=60)` em todas as funções de query — máximo de 60 segundos de atraso, sem necessidade de atualizar a página manualmente.
* **NFR13** — Consistência de Regimes (Dashboard): Abas financeiras usam `month` (regime de caixa); aba operacional usa `transaction_date` (regime de competência). Toda aba declara seu regime num caption visual.
* **NFR14** — Experiência do Desenvolvedor (DevEx): Ambiente local pode puxar dados reais de produção de forma segura via pipeline Docker descartável (`sync_db.ps1`), lendo credenciais dinamicamente do `.env` para evitar vazamentos.

---

### 5. Decisões Arquiteturais: O "Por quê?"

#### 5.1. Pipeline Duplo de IA e Isolamento de Prompts
Modos de falha isolados e temperaturas calibradas por tarefa. Centralizar prompts no arquivo `prompts.py` garante que o back-end foque apenas em roteamento, permitindo que a engenharia de prompt seja evoluída independentemente. Raciocínio de "Cadeia de Pensamento" (Chain-of-Thought) nas datas evita o erro número 1 em extrações de PDF.

#### 5.2. Padrão Outbox Transacional
UX instantânea para o usuário (< 100ms "Recebido"). Entrega garantida. O uso de `FOR UPDATE SKIP LOCKED` impede condições de corrida sem precisar de locks distribuídos (como Redis).

#### 5.3. Motor de Parcelamento Customizado
As regras de faturamento de cartão de crédito no Brasil (data de fechamento, melhor dia de compra) não são modeladas nativamente por bibliotecas financeiras comuns do mercado.

#### 5.4. Antecipação de Cartão vs. Pagamento à Vista
Pagar a fatura do cartão "antes" recalcula o alvo da fatura atual e move a dívida pra lá — permanecendo PENDENTE. Isso modela como os cartões realmente funcionam. Pagamentos em Pix/Débito marcam PAGO e realocam a coluna `month` para bater com o Extrato do banco do usuário (Regime de Caixa).

#### 5.5. Modo Duplo FastAPI + Long Polling
Webhooks exigem uma URL HTTPS pública, o que complica o desenvolvimento local. O controle `if ENV == "prod"` mantém o código idêntico rodando nos dois ambientes sem precisar abrir portas via Ngrok no dev local.

#### 5.6. `month` vs `due_date` — Dois Campos de Data por Design
`due_date` é imutável (data contratual de vencimento). Usado pela aba `/contas` para calcular atrasos. `month` é mutável (atualizado para o mês de pagamento real no regime de caixa). Usado pelo `/extrato` e pelo Streamlit para relatórios reais. Eles divergem intencionalmente.

#### 5.7. Separação da Carteira de Benefícios
Saldos de VA/VR (Caju, Alelo, Sodexo) não se misturam com o dinheiro em conta corrente. Somá-los cria a falsa ilusão de liquidez. Tanto o `/extrato` quanto o Dashboard aplicam a mesma lógica de separação, usando leitura de palavras-chave.

#### 5.8. Indexação `ROW_NUMBER()` via CTE
O número "X/Y" da parcela precisa sobreviver mesmo quando a coluna `month` muda de lugar. Computar isso na hora da leitura SQL com base na chave primária `id` garante o sequenciamento inviolável.

#### 5.9. Streamlit como Serviço Separado no Railway
A arquitetura síncrona/bloqueante do Streamlit mata a performance do event-loop assíncrono do FastAPI. Rodar os dois como microsserviços no Railway os mantém rápidos e com logs independentes. Compartilham o banco lendo o mesmo `DATABASE_URL`.

#### 5.10. `paid_amount` vs `expected_amount` nos KPIs
Usar apenas `expected_amount` (previsto) superestima os gastos quando a pessoa conseguiu negociar descontos ao pagar a vista. O modelo correto: se for PAGO, puxe o `paid_amount`; se for PENDENTE, puxe o `expected_amount`. A coluna computada virtual `real_amount` encapsula essa inteligência.

#### 5.11. Dois Regimes Analíticos no Mesmo Dashboard
As abas de Saúde Financeira, Tendência e Burn Rate operam sobre `month` (Caixa) — refletindo saídas efetivas de conta. A aba Operacional (itens, supermercado, marcas) opera em `transaction_date` (Competência) — focando em quando o consumo de fato aconteceu. Misturar as visões sem critério é um erro crasso de BI que evitamos.

#### 5.12. Disclosure Progressivo & Grid Invisível (UX)
O Telegram tem restrições brutais de tela.
- `/contas` usa Disclosure Progressivo: um cabeçalho monospace resume o mês; se o usuário quiser a visão tática, clica nos botões inline em formato acordeon.
- `/extrato` usa o conceito de "Grid Invisível": abandona linhas desenhadas `----` e aposta no respiro (espaço duplo `\n\n`) para separar os blocos visuais sem poluir a interface.

#### 5.13. Sincronização Segura do Banco de Produção (DevEx)
O desenvolvimento da UI local precisa de dados da vida real para testar quebras de layout. Em vez de lidar com backups SQL inseguros, o script `sync_db.ps1` faz o parse dinâmico da senha no arquivo `.env`, joga os dados direto do Railway para a memória RAM do Docker local e encerra. Sem senhas no código, sem arquivos zumbis no PC, 100% de integridade UTF-8.

---

### 6. Esquema do Banco de Dados

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
    month (MM/YYYY)  ← mutável: assume o mês real da liquidação (regime de caixa)
    due_date (DATE)  ← imutável: a data que veio na nota fiscal/contrato original
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount

Índices de Performance:
  idx_installments_month_status ON installments(month, payment_status)
  idx_queue_status_next         ON process_queue(status, next_attempt)
  idx_transactions_date_type    ON transactions(transaction_date, transaction_type)
```

---

### 7. Arquitetura de Deploy

```text
Projeto Railway
├── Plugin: PostgreSQL ─────────────────────────────────────┐
│   └── DATABASE_URL (URL interna)                          │ partilhado
│                                                           │
├── Serviço 1: Bot (web)                                    │
│   ├── Procfile: "web: python bot.py"                      │
│   ├── FastAPI escuta no $PORT automático                  │
│   ├── GET  /health   → liveness probe                     │
│   └── POST /webhook  → telegram_app.process_update()      │
│       └── job_queue (10s) → queue_processor()             │
│                                                           │
└── Serviço 2: Dashboard                                    │
    ├── Start Command:                                      │
    │   streamlit run dashboard.py                          │
    │     --server.port $PORT                               │
    │     --server.address 0.0.0.0                          │
    ├── DATABASE_URL ──────────────────────────────────────►┘
    └── @st.cache_data(ttl=60) em queries nativas

Ambiente Local (dev)
├── sync_db.ps1           → Clona Prod -> Local de forma segura consumindo o .env
├── python bot.py         → run_polling()
└── streamlit run dashboard.py
```

---

### 8. Estratégia de Segurança

- **Segredos (Secrets):** Ficam no `.env` local ou no painel Variables do Railway. Nunca expostos (hardcoded) nos arquivos `.py`.
- **Sincronização Dinâmica:** O `sync_db.ps1` foi construído para parsear o `.env` de forma isolada e fazer pipes de dados sem salvar senhas nas variáveis globais do SO, blindando o repositório no GitHub.
- **Controle de Acesso (Bot):** Whitelist absoluta via `ALLOWED_CHAT_IDS` processada no decorator `security_check` — rejeita mensagens de curiosos silenciosamente.
- **Controle de Acesso (Painel):** Streamlit não possui Auth nativa. Para o escopo pessoal, manter a URL gerada pelo Railway privada supre a demanda.
- **Bot Stateless:** Nenhum estado sensível fica salvo no sistema de arquivos do Railway. PDFs e rascunhos são sumariamente deletados através de blocos `finally` do Python logo após extraídos.
- **Injeção de SQL:** Todas as inserções usam placeholders parametrizados (`%s`) na camada do `psycopg2`.
- **Proteção do Webhook:** O endpoint `/webhook` descarta qualquer tráfego que não venha serializado corretamente do ambiente oficial do Telegram, graças ao `Update.de_json`.