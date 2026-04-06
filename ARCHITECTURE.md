# 🏛️ Technical Specification & System Architecture
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

**Project:** Zotto — Finance AI Data App
**Role:** Full-Stack Data Engineer & Product Owner

---

### 1. Architecture Overview

This system is a **Full-Stack Data Application** built on a **Hybrid AI Architecture**. The core design philosophy is a strict separation of concerns between intelligence and determinism: LLMs are used exclusively for the problem they are best at — translating unstructured human language and chaotic documents into structured data — while Python handles all deterministic operations: financial mathematics, state management, and data governance rules.

The system is cloud-native by design, deployed on Railway PaaS, and built around an event-driven **Transactional Outbox Pattern** to ensure no user message is ever lost, regardless of API availability.

**Data Flow in a single sentence:** *User input (text, URL, PDF) → Telegram Bot → PostgreSQL Queue → Background Worker → Dual LLM Pipeline (Extract → Enrich) → Human Confirmation UI → Relational Database.*

---

### 2. Core Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | **Entry Interface** | `python-telegram-bot` | Async user touchpoint. State Machine + Inline UI. |
| 2 | **Outbox Queue** | PostgreSQL `process_queue` | Decouples ingestion from processing. Guarantees delivery. |
| 3 | **Document Intelligence** | `BeautifulSoup4`, `PyPDF` | Scrapes NFC-e URLs and extracts text from PDF utility bills. |
| 4 | **AI Engine — Agent 1** | Groq API (`llama-4-scout-17b`) | Extracts raw entities from unstructured input. `temperature=0.0`. |
| 5 | **AI Engine — Agent 2** | Groq API (`llama-4-scout-17b`) | Enriches and categorizes the structured JSON from Agent 1. `temperature=0.1`. |
| 6 | **Backend Engine** | Python | Math validation, installment calculation, duplicate detection. |
| 7 | **AP/AR Dashboard** | Telegram Inline UI | Grouped invoice view, isolated view, fast-forward navigation. |
| 8 | **Database** | PostgreSQL | Relational storage with AP/AR Ledger and SCD audit columns. |

---

### 3. Functional Requirements (FRs)

* **FR01 — Multimodal Ingestion:** The bot must accept and process three input types: free-text messages (informal expenses), HTML content via URLs (NFC-e electronic invoice scraping), and PDF documents (utility bills, bank statements).
* **FR02 — AI Extraction & Routing:** The system must use a dual LLM pipeline to extract entities (vendor, amount, date, items) and infer missing data (e.g., deduce vendor name from URL domain), then route the transaction into `RECEITA` (Income) or `DESPESA` (Expense) logic.
* **FR03 — Installment Calculation (AP/AR Ledger):** The system must split the total transaction amount across N installments, calculating the correct due date for each one based on user-defined credit card closing and due-day rules.
* **FR04 — Human-in-the-Loop Confirmation:** Before any database write, the bot must display a structured Markdown summary of the extracted transaction and require explicit user confirmation via an interactive keyboard.
* **FR05 — AP/AR Management Dashboard (`/contas`):** The `/contas` command must render an interactive inline panel that:
  - Groups installments from the same credit card under a consolidated "Fatura" (Invoice) header with total amount.
  - Marks overdue bills with a 🔴 indicator.
  - Displays a global warning banner when overdue bills exist in other months.
  - Supports month navigation with previous/next buttons.
  - Provides a Fast-Forward button (⏭️) to jump directly to the furthest future month with pending bills.
  - Returns to the current month with a dedicated button when the user is time-traveling.
  - Provides a Close Panel button as an escape hatch.
* **FR06 — Individual Bill Payment:** Allows the user to pay a single installment, optionally entering a discounted amount for early payment. The discount is reflected in the parent transaction's accounting balance.
* **FR07 — Group Invoice Payment:** Allows the user to pay all installments for a given credit card in one action, with optional discount distributed proportionally across all items.
* **FR08 — Installment Cancellation (Reconciliation):** Allows soft-deleting a specific installment (status → `CANCELED`) for bank reconciliation, leaving other installments of the same purchase untouched.
* **FR09 — Isolated View:** When navigating to the last installment of a purchase, the panel filters to show only that transaction's installments, hiding all others and providing a "Return to Overview" button.
* **FR10 — Duplicate Detection:** The system must prevent duplicate entries using two independent heuristics: (1) exact match on `invoice_number` for formal documents, and (2) fuzzy match on `(location ILIKE + amount + date)` for informal entries.
* **FR11 — Credit Card Management:** The bot must allow the user to register new credit cards mid-flow (bank name, variant, closing day, due day) and persist this configuration for automatic reuse.

---

### 4. Non-Functional Requirements (NFRs)

* **NFR01 — Resilience (Outbox Pattern):** The system must queue all incoming messages immediately and process them asynchronously in background. No user message may be lost due to API unavailability.
* **NFR02 — Exponential Backoff:** Upon API failure or rate-limit (HTTP 429), the background worker must parse the retry delay from the error response and reschedule the item. Standard errors use exponential backoff (60s to 3600s). TPD (Tokens Per Day) limits defer to 09:00 AM next day.
* **NFR03 — Dead Item Prevention:** Items that fail beyond `max_attempts` (default: 5) must be marked as `DEAD` and the user notified, preventing zombie items from blocking the queue indefinitely.
* **NFR04 — Busy-State Queue Deferral:** When a user is actively in a conversation flow (answering a questionnaire), the queue worker must detect this and defer the item without consuming a retry attempt, using a dedicated `reschedule_queue_item_busy` function.
* **NFR05 — Connection Pool (Cloud Performance):** All database access must route through a `ThreadedConnectionPool` (min: 1, max: 10) to prevent connection exhaustion on Railway's PostgreSQL instance.
* **NFR06 — Fault-Tolerant JSON Parsing:** The backend must strip LLM hallucinations from JSON output (inline comments, Python-style booleans, unescaped control characters) before parsing.
* **NFR07 — Math Validation (Anti-Hallucination):** After LLM processing, the backend must independently recalculate `valor_total` from item-level data if the model returns zero, and validate `valor_unitario` values.
* **NFR08 — Access Control (Whitelist):** The bot must enforce an `ALLOWED_CHAT_IDS` environment variable whitelist, rejecting any interaction from unauthorized Telegram users via a `security_check` decorator.
* **NFR09 — Stateless & Ephemeral Security:** Sensitive credentials must never be hardcoded. All secrets are injected via environment variables.
* **NFR10 — Auditability (SCD):** All relational tables must implement Slowly Changing Dimensions with `created_at` and `updated_at` timestamps. `transactions.status` must stay synchronized with the aggregate state of its child `installments`.
* **NFR11 — Proportional Discount Distribution:** When a group invoice is paid with a discounted amount, the discount must be distributed proportionally across all installments and reflected in each parent transaction's `discount_applied` and `total_amount` fields.

---

### 5. Architectural Decisions: The "Why?"

#### 5.1. Why a Dual-Agent LLM Pipeline instead of a Single Prompt?
**Decision:** Use two sequential LLM calls — Agent 1 extracts raw data, Agent 2 enriches and categorizes.

**Justification:** *Separation of Cognitive Responsibility.* A single, monolithic prompt trying to simultaneously extract entities, infer missing data, validate a date parsing chain-of-thought, apply a category taxonomy, and format a complex nested JSON is a recipe for hallucinations. Each agent has a focused, auditable task. Agent 1 operates with `temperature=0.0` (maximum determinism). Agent 2 operates with `temperature=0.1` (minimal creativity for classification). Failures are isolated and diagnosable at the exact stage where they occur.

#### 5.2. Why the Transactional Outbox Pattern instead of direct LLM calls?
**Decision:** Insert every incoming message into a PostgreSQL queue before any LLM processing occurs.

**Justification:** *Guaranteed Delivery and User Experience.* A direct API call from the Telegram handler means a failure loses the user's data silently. The Outbox Pattern decouples receipt from processing: the bot always responds "Received" instantly (< 100ms), and the background worker handles the slow, failure-prone LLM call asynchronously. The `FOR UPDATE SKIP LOCKED` SQL construct ensures safe concurrent processing without distributed locks.

#### 5.3. Why a custom Installment Engine instead of a financial library?
**Decision:** Build `generate_installment_details` using `dateutil.relativedelta` arithmetic.

**Justification:** *Domain-specific rules cannot be abstracted.* Brazilian credit card billing has idiosyncratic rules: the `fechamento` (closing day) determines which invoice cycle a purchase falls into, and the `vencimento` (due day) may fall in a different month. Standard financial libraries do not model this. The custom engine gives exact control over all boundary conditions.

#### 5.4. Why inject Chain-of-Thought fields into the prompt for date parsing?
**Decision:** The prompt for Agent 1 contains a `_raciocinio_vencimento` field that forces the model to reason step-by-step before committing a date value.

**Justification:** *Forcing deliberate reasoning prevents the most common extraction error.* PDF utility bills lose their tabular formatting when converted to plain text. The LLM's default behavior is to pick the first date it encounters — invariably the emission date near `Protocolo` or `Série` fields, not the actual due date. The Chain-of-Thought field forces the model to find the correct date rather than guess the first one.

#### 5.5. Why group credit card installments under a "Fatura" header in the UI?
**Decision:** The `/contas` panel detects installments sharing the same `card_bank`/`card_variant` and groups them under a consolidated parent button with the total amount.

**Justification:** *Matching the mental model of how people actually pay bills.* In practice, users don't pay each purchase individually — they pay their entire credit card invoice. A flat list of 12 individual installments from 4 different purchases obscures this. The grouped view (with individual items expandable beneath the header) reflects real-world bank behavior: you see the card name and total due, and can drill down to individual purchases if needed.

#### 5.6. Why proportional discount distribution for group payments?
**Decision:** When the user pays a group invoice with a discounted amount, the discount is split across each installment proportionally (by its percentage of the total), and each parent transaction's `total_amount` and `discount_applied` are updated accordingly.

**Justification:** *Accounting integrity must hold at every level.* A flat discount applied to only one installment would skew category totals in the future Streamlit dashboard. By distributing proportionally, the discount is correctly attributed to each purchase's cost center — a R$10 discount on a R$200 grouped invoice containing a R$150 and a R$50 purchase applies R$7.50 to the first and R$2.50 to the second.

#### 5.7. Why PostgreSQL over a NoSQL store?
**Decision:** Use a relational model with foreign key constraints and normalized tables.

**Justification:** *Financial data has inherent relational structure.* One transaction → many items. One transaction → many installments. These are 1-to-N relationships with referential integrity requirements. The `installments` table acting as an AP/AR ledger with `ON DELETE CASCADE` is a pattern borrowed from accounting software. NoSQL's schema flexibility would be a liability here, not an asset.

---

### 6. Database Schema (Entity Relationships)

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────────────┐
    id, transaction_type, invoice_number                      │ FK
    transaction_date (DATE), location_name                    │
    card_bank, card_variant, status [Ativa | PAID]            │
    original_amount, discount_applied, total_amount           │
    macro_category, payment_method                            │
    is_installment, installment_count                         │
                                                              │
transaction_items  ──── transaction_id (FK) ──────────────────┤
    description, brand, unit_price, quantity                  │
    cat_macro, cat_category, cat_subcategory                  │
                                                              │
installments  ───────── transaction_id (FK) ──────────────────┘
    month (MM/YYYY), due_date (DATE)
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount
```

**Installment Status Lifecycle:**
```
PENDING ──(user pays full amount)──► PAID
PENDING ──(user cancels/reconcile)──► CANCELED
PENDING ──(automatic, if last one)──► triggers transactions.status = 'PAID'
```

---

### 7. AP/AR Dashboard — Navigation State Machine

```
/contas
  └─► show_bills_month (current month)
        ├─► [💳 Fatura Card X - R$ total]  ──► fatgroup_ handler
        │     └─► [💸 Pagar Fatura Fechada] ──► paygroup_ ──► WAITING_FOR_PAYMENT_DATE
        │                                                         └─► WAITING_FOR_PAYMENT_AMOUNT
        │                                                               └─► pay_grouped_card_bills_in_db()
        │
        ├─► [🔹 Individual Bill]  ──► fatura_ handler
        │     ├─► [💸 Pagar / Antecipar]  ──► pagar_ ──► WAITING_FOR_PAYMENT_DATE
        │     │                                               └─► WAITING_FOR_PAYMENT_AMOUNT
        │     │                                                     └─► pay_bill_in_db()
        │     ├─► [🗑️ Cancelar Parcela]  ──► cancel_installment()
        │     └─► [⏭️ Pular para Última Parcela]  ──► mes_ + tx_ (Isolated View)
        │
        ├─► [⬅️ prev_month] / [next_month ➡️]  ──► show_bills_month(new_month)
        ├─► [⏭️ Pular para Último Mês]  ──► get_max_pending_month() ──► show_bills_month()
        ├─► [📅 Voltar para Mês Atual]  ──► show_bills_month(current_month)
        └─► [❌ Fechar Painel]  ──► close_panel (clears state)
```

---

### 8. Security Strategy

* **Decoupled Secrets:** API Keys and DB credentials are injected via Environment Variables. Local development uses `.env` (git-ignored). Production uses Railway's Variables panel.
* **Access Control:** An `ALLOWED_CHAT_IDS` whitelist loaded at startup blocks all unauthorized Telegram users at the handler level via a `security_check` decorator applied to every public handler.
* **Stateless Design:** The application is designed for containerized deployment where the file system is ephemeral. PDFs are processed in-memory and deleted in a `finally` block.
* **SQL Injection Prevention:** All database queries use parameterized statements (`%s` placeholders) — never f-string interpolation.

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Zotto — Finance AI Data App
**Papel:** Engenheiro de Dados Full-Stack & Dono do Produto

---

### 1. Visão Geral da Arquitetura

Este sistema é uma **Aplicação de Dados Full-Stack** construída sobre uma **Arquitetura de IA Híbrida**. A filosofia central de design é a separação estrita entre inteligência e determinismo: LLMs são usados exclusivamente para o problema em que são melhores — traduzir linguagem humana desestruturada e documentos caóticos em dados estruturados — enquanto o Python lida com todas as operações determinísticas: matemática financeira, gerenciamento de estado e regras de governança.

O sistema é nativo em nuvem por design, deployado no Railway PaaS, e construído em torno de um **Padrão de Outbox Transacional** orientado a eventos para garantir que nenhuma mensagem do usuário seja perdida.

**Fluxo de dados em uma frase:** *Input do usuário (texto, URL, PDF) → Telegram Bot → Fila PostgreSQL → Worker em Background → Pipeline Dual LLM (Extrair → Enriquecer) → UI de Confirmação Humana → Banco de Dados Relacional.*

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface de Entrada** | `python-telegram-bot` | Ponto de contato assíncrono. Máquina de estados + UI inline. |
| 2 | **Fila Outbox** | PostgreSQL `process_queue` | Desacopla ingestão do processamento. Garante entrega. |
| 3 | **Inteligência de Documentos** | `BeautifulSoup4`, `PyPDF` | Scraping de URLs de NFC-e e extração de texto de PDFs. |
| 4 | **Motor de IA — Agente 1** | Groq API (`llama-4-scout-17b`) | Extrai entidades brutas do input não estruturado. `temperature=0.0`. |
| 5 | **Motor de IA — Agente 2** | Groq API (`llama-4-scout-17b`) | Enriquece e categoriza o JSON estruturado do Agente 1. `temperature=0.1`. |
| 6 | **Backend Engine** | Python | Validação matemática, cálculo de parcelas, detecção de duplicatas. |
| 7 | **Dashboard AP/AR** | Telegram Inline UI | Visão de fatura agrupada, modo isolado, navegação temporal inteligente. |
| 8 | **Banco de Dados** | PostgreSQL | Armazenamento relacional com Livro Caixa AP/AR e colunas de auditoria SCD. |

---

### 3. Requisitos Funcionais (RFs)

* **RF01 — Ingestão Multimodal:** O bot deve aceitar e processar três tipos de entrada: mensagens de texto livre, HTML via URLs (scraping de NFC-e) e documentos PDF (faturas bancárias, contas de consumo).
* **RF02 — Extração por IA e Roteamento:** O sistema deve usar um pipeline dual de LLM para extrair entidades e deduzir dados ausentes, roteando a transação para lógica de `RECEITA` ou `DESPESA`.
* **RF03 — Cálculo de Parcelas (Livro Caixa AP/AR):** O sistema deve dividir o valor total da transação em N parcelas, calculando a data de vencimento correta com base nas regras de fechamento/vencimento dos cartões.
* **RF04 — Confirmação Human-in-the-Loop:** Antes de qualquer escrita no banco, o bot deve exibir um resumo estruturado e exigir confirmação explícita via teclado interativo.
* **RF05 — Dashboard de Gestão de Contas (`/contas`):** O comando `/contas` deve renderizar um painel inline que:
  - Agrupa parcelas do mesmo cartão de crédito sob um header "Fatura" com total consolidado.
  - Marca contas vencidas com indicador 🔴.
  - Exibe banner de alerta global quando há contas vencidas em outros meses.
  - Suporta navegação entre meses com botões anterior/próximo.
  - Fornece botão Fast-Forward (⏭️) para pular ao mês mais distante com pendências.
  - Retorna ao mês atual com botão dedicado quando o usuário está navegando.
  - Fornece botão "Fechar Painel" como escape.
* **RF06 — Pagamento Individual de Parcela:** Permite pagar uma parcela avulsa, informando opcionalmente um valor com desconto por antecipação.
* **RF07 — Pagamento em Grupo de Fatura:** Permite pagar todas as parcelas de um cartão em um mês com um único clique, com desconto opcional distribuído proporcionalmente entre os itens.
* **RF08 — Cancelamento de Parcela (Conciliação):** Permite soft-delete de uma parcela específica (`CANCELED`) para conciliação bancária, sem afetar outras parcelas da mesma compra.
* **RF09 — Modo Isolado:** Ao navegar para a última parcela de uma compra, o painel filtra para exibir apenas as parcelas daquela transação, fornecendo botão de retorno à visão geral.
* **RF10 — Detecção de Duplicatas:** O sistema deve prevenir lançamentos duplicados via match exato de `invoice_number` e match fuzzy em `(local ILIKE + valor + data)`.
* **RF11 — Gestão de Cartões de Crédito:** O bot deve permitir cadastrar novos cartões de crédito durante o fluxo e persistir a configuração para reuso automático.

---

### 4. Requisitos Não Funcionais (RNFs)

* **RNF01 — Resiliência (Padrão Outbox):** O sistema deve enfileirar todas as mensagens recebidas imediatamente e processá-las de forma assíncrona. Nenhuma mensagem pode ser perdida.
* **RNF02 — Backoff Exponencial:** Erros genéricos usam backoff exponencial (60s a 3600s). Limites TPD (Tokens Per Day) adiam para as 09:00 do dia seguinte.
* **RNF03 — Prevenção de Itens Zumbi:** Itens que falham além de `max_attempts` (padrão: 5) são marcados como `DEAD` e o usuário notificado.
* **RNF04 — Adiamento por Estado Ocupado:** Quando um usuário está em um fluxo ativo, o worker detecta isso e adia o item sem consumir tentativa, usando `reschedule_queue_item_busy`.
* **RNF05 — Pool de Conexões:** Todo acesso ao banco deve passar por um `ThreadedConnectionPool` (mín: 1, máx: 10).
* **RNF06 — Parsing de JSON Tolerante a Falhas:** O backend deve limpar alucinações do LLM (comentários inline, booleanos Python, caracteres de controle) antes do parsing.
* **RNF07 — Validação Matemática:** Após o LLM, o backend recalcula `valor_total` a partir dos itens se o modelo retornar zero.
* **RNF08 — Controle de Acesso (Whitelist):** A whitelist `ALLOWED_CHAT_IDS` rejeita qualquer interação de usuários não autorizados via decorator `security_check`.
* **RNF09 — Segurança Stateless:** Credenciais nunca são hardcoded. Todos os segredos são injetados via variáveis de ambiente.
* **RNF10 — Auditabilidade (SCD):** Todas as tabelas implementam `created_at` e `updated_at`. `transactions.status` é mantido em sincronia com o estado agregado das `installments` filhas.
* **RNF11 — Distribuição Proporcional de Desconto:** Em pagamentos em grupo com desconto, o desconto é distribuído proporcionalmente entre as parcelas e refletido em cada transação pai.

---

### 5. Decisões Arquiteturais: O "Por Quê?"

#### 5.1. Por que um Pipeline Dual de LLM?
**Decisão:** Duas chamadas LLM sequenciais — Agente 1 extrai, Agente 2 enriquece.
**Justificativa:** *Separação de Responsabilidade Cognitiva.* Falhas são isoladas e diagnosticáveis. Cada agente tem uma temperatura calibrada para sua tarefa específica.

#### 5.2. Por que o Padrão Outbox Transacional?
**Decisão:** Inserir toda mensagem em uma fila PostgreSQL antes de qualquer processamento LLM.
**Justificativa:** *Entrega Garantida.* O bot responde "Recebido" em < 100ms. O worker lida assincronamente com a chamada lenta. `FOR UPDATE SKIP LOCKED` evita processamento duplicado.

#### 5.3. Por que um Motor de Parcelas Customizado?
**Decisão:** `generate_installment_details` com `dateutil.relativedelta`.
**Justificativa:** *Regras de domínio específicas.* O faturamento de cartão de crédito brasileiro (fechamento/vencimento) não é modelado por bibliotecas financeiras padrão.

#### 5.4. Por que Chain-of-Thought para datas?
**Decisão:** Campo `_raciocinio_vencimento` no prompt do Agente 1.
**Justificativa:** *Forçar raciocínio deliberado.* PDFs perdem formatação tabular. O CoT força o modelo a encontrar a data correta em vez de pegar a primeira que aparece.

#### 5.5. Por que agrupar parcelas por cartão na UI?
**Decisão:** Parcelas do mesmo `card_bank`/`card_variant` são agrupadas sob um header "Fatura" consolidado.
**Justificativa:** *Modelo mental do usuário.* As pessoas pagam faturas, não compras individuais. A visão agrupada espelha o comportamento real dos bancos — você vê o total da fatura e pode expandir para ver os itens.

#### 5.6. Por que distribuição proporcional de desconto?
**Decisão:** Desconto em pagamento de grupo é distribuído proporcionalmente por parcela.
**Justificativa:** *Integridade contábil em todos os níveis.* Um desconto flat em apenas uma parcela distorceria os totais por categoria no dashboard Streamlit futuro.

#### 5.7. Por que PostgreSQL?
**Decisão:** Modelo relacional com constraints de chave estrangeira e tabelas normalizadas.
**Justificativa:** *Dados financeiros têm estrutura relacional inerente.* 1 transação → N itens → N parcelas. A flexibilidade de schema do NoSQL seria um passivo aqui.

---

### 6. Schema do Banco de Dados

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────────────┐
    id, transaction_type, invoice_number                      │ FK
    transaction_date (DATE), location_name                    │
    card_bank, card_variant, status [Ativa | PAID]            │
    original_amount, discount_applied, total_amount           │
    macro_category, payment_method                            │
    is_installment, installment_count                         │
                                                              │
transaction_items  ──── transaction_id (FK) ──────────────────┤
    description, brand, unit_price, quantity                  │
    cat_macro, cat_category, cat_subcategory                  │
                                                              │
installments  ───────── transaction_id (FK) ──────────────────┘
    month (MM/AAAA), due_date (DATE)
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount
```

---

### 7. Estratégia de Segurança

* **Segredos Desacoplados:** Chaves de API e credenciais do banco são injetadas via Variáveis de Ambiente. Desenvolvimento local usa `.env` (ignorado pelo git). Produção usa o painel de Variables do Railway.
* **Controle de Acesso:** Whitelist `ALLOWED_CHAT_IDS` bloqueia todos os usuários não autorizados via decorator `security_check` aplicado a todos os handlers públicos.
* **Design Stateless:** A aplicação é projetada para deploy em containers efêmeros. PDFs são processados em memória e deletados em bloco `finally`.
* **Prevenção de SQL Injection:** Todas as queries usam statements parametrizados (`%s`) — nunca interpolação com f-strings.