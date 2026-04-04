# 🏛️ Technical Specification & System Architecture
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

**Project:** Finance AI Data App
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
| 4 | **AI Engine — Agent 1** | Groq API (`llama-4-scout-17b`) | Extracts raw entities from unstructured input. |
| 5 | **AI Engine — Agent 2** | Groq API (`llama-4-scout-17b`) | Enriches and categorizes the structured JSON from Agent 1. |
| 6 | **Backend Engine** | Python | Math validation, installment calculation, duplicate detection. |
| 7 | **Database** | PostgreSQL | Relational storage with AP/AR Ledger and SCD audit columns. |

---

### 3. Functional Requirements (FRs)
*What the system is required to do.*

* **FR01 — Multimodal Ingestion:** The bot must accept and process three input types: free-text messages (informal expenses), HTML content via URLs (NFC-e electronic invoice scraping), and PDF documents (utility bills, bank statements).
* **FR02 — AI Extraction & Routing:** The system must use a dual LLM pipeline to extract entities (vendor, amount, date, items) and infer missing data (e.g., deduce vendor name from URL domain), then route the transaction into `RECEITA` (Income) or `DESPESA` (Expense) logic.
* **FR03 — Installment Calculation (AP/AR Ledger):** The system must split the total transaction amount across N installments, calculating the correct due date for each one based on user-defined credit card closing and due-day rules.
* **FR04 — Human-in-the-Loop Confirmation:** Before any database write, the bot must display a structured Markdown summary of the extracted transaction and require explicit user confirmation via an interactive keyboard.
* **FR05 — Interactive AP/AR Management:** The `/contas` command must query and display all `PENDING` installments for the current month, allowing the user to mark any of them as paid with a single tap and assign a retroactive payment date.
* **FR06 — Duplicate Detection:** The system must prevent duplicate entries using two independent heuristics: (1) exact match on `invoice_number` for formal documents, and (2) fuzzy match on `(location ILIKE + amount + date)` for informal entries without invoice numbers.
* **FR07 — Credit Card Management:** The bot must allow the user to register new credit cards mid-flow (bank name, variant, closing day, due day) and persist this configuration for automatic reuse in future transactions.

---

### 4. Non-Functional Requirements (NFRs)
*How the system must behave (Quality Attributes).*

* **NFR01 — Resilience (Outbox Pattern):** The system must queue all incoming messages immediately and process them asynchronously in background. No user message may be lost due to API unavailability.
* **NFR02 — Exponential Backoff:** Upon API failure or rate-limit (HTTP 429), the background worker must parse the retry delay from the error response and reschedule the item with a wait time bounded between `60s` and `3600s`. The user is notified only on the first failure; subsequent retries are silent.
* **NFR03 — Dead Item Prevention:** Items that fail beyond `max_attempts` (default: 5) must be marked as `DEAD` and the user notified, preventing zombie items from blocking the queue indefinitely.
* **NFR04 — Connection Pool (Cloud Performance):** All database access must route through a `ThreadedConnectionPool` (min: 1, max: 10) to prevent connection exhaustion on cloud-hosted PostgreSQL instances with connection limits.
* **NFR05 — Fault-Tolerant JSON Parsing:** The backend must strip LLM hallucinations from JSON output (inline comments, Python-style booleans, unescaped control characters) before parsing, using `json.loads(..., strict=False)` as a last resort.
* **NFR06 — Math Validation (Anti-Hallucination):** After LLM processing, the backend must independently recalculate `valor_total` from item-level data if the model returns zero, and validate individual `valor_unitario` values against the transaction total.
* **NFR07 — Access Control (Whitelist):** The bot must enforce an `ALLOWED_CHAT_IDS` whitelist loaded from environment variables, silently rejecting any interaction from unauthorized Telegram users.
* **NFR08 — Stateless & Ephemeral Security:** Sensitive credentials (API Keys, DB passwords) must never be hardcoded. All secrets are injected via environment variables, compatible with Railway's Variables panel and local `.env` files.
* **NFR09 — Auditability (SCD):** All relational tables must implement Slowly Changing Dimensions with `created_at` and `updated_at` timestamps. The `transactions.status` column must be kept in sync with the aggregate state of its child `installments`.

---

### 5. Architectural Decisions: The "Why?"

#### 5.1. Why a Dual-Agent LLM Pipeline instead of a Single Prompt?
**Decision:** Use two sequential LLM calls — Agent 1 extracts raw data, Agent 2 enriches and categorizes.

**Justification:** *Separation of Cognitive Responsibility.* A single, monolithic prompt trying to simultaneously extract entities, infer missing data, validate a date parsing chain-of-thought, apply a category taxonomy, and format a complex nested JSON consistently is a recipe for hallucinations. By splitting the pipeline, each agent has a focused, auditable task. Agent 1 operates with `temperature=0.0` (maximum determinism for data extraction). Agent 2 operates with `temperature=0.1` (minimal creativity for classification). The output of Agent 1 is a structured Python dict before Agent 2 ever runs — this means failures are isolated and diagnosable.

#### 5.2. Why the Transactional Outbox Pattern instead of direct LLM calls?
**Decision:** Insert every incoming message into a PostgreSQL queue before any LLM processing occurs.

**Justification:** *Guaranteed Delivery and User Experience.* A direct API call from the Telegram handler means a failure loses the user's data silently. The Outbox Pattern decouples receipt from processing: the bot always responds "Received" instantly (< 100ms), and the background worker handles the slow, failure-prone LLM call asynchronously. The `FOR UPDATE SKIP LOCKED` SQL construct ensures safe concurrent processing without distributed locks. This also naturally provides retry logic, rate-limit handling, and an audit trail — all for free.

#### 5.3. Why Tabular Q-Table for Installments instead of a Date Formula Library?
**Decision:** Build a custom installment engine (`generate_installment_details`) using `relativedelta` arithmetic rather than relying on a financial library.

**Justification:** *Domain-specific rules cannot be abstracted.* Brazilian credit card billing has idiosyncratic rules: the "fechamento" (closing day) determines which invoice cycle a purchase falls into, and the "vencimento" (due day) may fall in a different month than the closing cycle if `due_day < closing_day`. Standard financial libraries do not model this. A custom engine built on `dateutil.relativedelta` gives exact control over the boundary conditions and is fully testable with unit inputs.

#### 5.4. Why inject Chain-of-Thought fields into the LLM prompt for date parsing?
**Decision:** The prompt for Agent 1 contains a `_raciocinio_vencimento` field that forces the model to reason step-by-step about due dates before committing a value.

**Justification:** *Forcing deliberate reasoning prevents the most common extraction error.* PDF utility bills (energy, water, gas) lose their tabular formatting when converted to plain text. The LLM's default behavior is to pick the first date it encounters — which is invariably the emission date near the "Protocolo" or "Série" fields, not the actual due date. By requiring the model to explicitly articulate its reasoning in a structured field that the next pipeline stage can inspect, we force it to *find* the correct date rather than *guess* the first one. This single prompt engineering decision reduced date extraction errors by the largest margin of any change in the project.

#### 5.5. Why PostgreSQL over a NoSQL store for a personal finance app?
**Decision:** Use a relational model with foreign key constraints and normalized tables.

**Justification:** *Financial data has inherent relational structure.* A transaction has many items. A transaction has many installments. A installment belongs to exactly one transaction. These are 1-to-N relationships with referential integrity requirements — exactly the problem relational databases solve. The `installments` table acting as an AP/AR ledger with `ON DELETE CASCADE` from its parent transaction is a pattern borrowed directly from accounting software. NoSQL's schema flexibility would be a liability here, not an asset: every analytics query on the Streamlit dashboard benefits from typed columns, indexed dates, and aggregatable decimals.

---

### 6. Database Schema (Entity Relationships)

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────┐
    id, transaction_type, invoice_number              │ FK
    transaction_date (DATE), location_name            │
    card_bank, card_variant, status                   │
    original_amount, discount_applied, total_amount   │
    macro_category, payment_method                    │
    is_installment, installment_count                 │
                                                      │
transaction_items  ──── transaction_id (FK) ──────────┤
    description, brand, unit_price, quantity          │
    cat_macro, cat_category, cat_subcategory          │
                                                      │
installments  ───────── transaction_id (FK) ──────────┘
    month (MM/YYYY), due_date (DATE)
    amount, payment_status, payment_date (DATE), paid_amount
```

---

### 7. Security Strategy

* **Decoupled Secrets:** API Keys and DB credentials are injected via Environment Variables. Local development uses `.env` (git-ignored). Production uses Railway's Variables panel.
* **Access Control:** An `ALLOWED_CHAT_IDS` whitelist loaded at startup blocks all unauthorized Telegram users at the handler level via a `security_check` decorator.
* **Stateless Design:** The application is designed for containerized deployment where the file system is ephemeral. No sensitive state is written to disk (PDFs are processed in-memory and deleted in a `finally` block).

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Finance AI Data App
**Papel:** Engenheiro de Dados Full-Stack & Dono do Produto

---

### 1. Visão Geral da Arquitetura

Este sistema é uma **Aplicação de Dados Full-Stack** construída sobre uma **Arquitetura de IA Híbrida**. A filosofia central de design é a separação estrita entre inteligência e determinismo: LLMs são usados exclusivamente para o problema em que são melhores — traduzir linguagem humana desestruturada e documentos caóticos em dados estruturados — enquanto o Python lida com todas as operações determinísticas: matemática financeira, gerenciamento de estado e regras de governança.

O sistema é nativo em nuvem por design, deployado no Railway PaaS, e construído em torno de um **Padrão de Outbox Transacional** orientado a eventos para garantir que nenhuma mensagem do usuário seja perdida, independentemente da disponibilidade da API.

**Fluxo de dados em uma frase:** *Input do usuário (texto, URL, PDF) → Telegram Bot → Fila PostgreSQL → Worker em Background → Pipeline Dual LLM (Extrair → Enriquecer) → UI de Confirmação Humana → Banco de Dados Relacional.*

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface de Entrada** | `python-telegram-bot` | Ponto de contato assíncrono. Máquina de estados + UI inline. |
| 2 | **Fila Outbox** | PostgreSQL `process_queue` | Desacopla ingestão do processamento. Garante entrega. |
| 3 | **Inteligência de Documentos** | `BeautifulSoup4`, `PyPDF` | Scraping de URLs de NFC-e e extração de texto de PDFs. |
| 4 | **Motor de IA — Agente 1** | Groq API (`llama-4-scout-17b`) | Extrai entidades brutas do input não estruturado. |
| 5 | **Motor de IA — Agente 2** | Groq API (`llama-4-scout-17b`) | Enriquece e categoriza o JSON estruturado do Agente 1. |
| 6 | **Backend Engine** | Python | Validação matemática, cálculo de parcelas, detecção de duplicatas. |
| 7 | **Banco de Dados** | PostgreSQL | Armazenamento relacional com Livro Caixa AP/AR e colunas de auditoria SCD. |

---

### 3. Requisitos Funcionais (RFs)
*O que o sistema é obrigado a fazer.*

* **RF01 — Ingestão Multimodal:** O bot deve aceitar e processar três tipos de entrada: mensagens de texto livre (despesas informais), conteúdo HTML via URLs (scraping de NFC-e), e documentos PDF (contas de consumo, faturas bancárias).
* **RF02 — Extração por IA e Roteamento:** O sistema deve usar um pipeline dual de LLM para extrair entidades (fornecedor, valor, data, itens) e deduzir dados ausentes (ex: nome do fornecedor a partir do domínio da URL), roteando a transação para a lógica de `RECEITA` ou `DESPESA`.
* **RF03 — Cálculo de Parcelas (Livro Caixa AP/AR):** O sistema deve dividir o valor total da transação em N parcelas, calculando a data de vencimento correta de cada uma com base nas regras de fechamento e vencimento dos cartões de crédito definidos pelo usuário.
* **RF04 — Confirmação Human-in-the-Loop:** Antes de qualquer escrita no banco, o bot deve exibir um resumo estruturado em Markdown da transação extraída e exigir confirmação explícita via teclado interativo.
* **RF05 — Gestão Interativa de Contas (AP/AR):** O comando `/contas` deve consultar e exibir todas as parcelas `PENDING` do mês atual, permitindo ao usuário marcar qualquer uma como paga com um único toque e atribuir uma data de pagamento retroativa.
* **RF06 — Detecção de Duplicatas:** O sistema deve prevenir lançamentos duplicados usando duas heurísticas independentes: (1) match exato no `numero_nota` para documentos formais, e (2) match fuzzy em `(local ILIKE + valor + data)` para entradas informais sem número de nota.
* **RF07 — Gestão de Cartões de Crédito:** O bot deve permitir ao usuário cadastrar novos cartões de crédito durante o fluxo (banco, variante, dia de fechamento, dia de vencimento) e persistir essa configuração para reuso automático.

---

### 4. Requisitos Não Funcionais (RNFs)
*Como o sistema deve se comportar (Atributos de Qualidade).*

* **RNF01 — Resiliência (Padrão Outbox):** O sistema deve enfileirar todas as mensagens recebidas imediatamente e processá-las de forma assíncrona em background. Nenhuma mensagem do usuário pode ser perdida por indisponibilidade da API.
* **RNF02 — Backoff Exponencial:** Em caso de falha na API ou rate-limit (HTTP 429), o worker em background deve extrair o tempo de espera da mensagem de erro e reagendar o item com espera entre `60s` e `3600s`. O usuário é notificado apenas na primeira falha; tentativas subsequentes são silenciosas.
* **RNF03 — Prevenção de Itens Zumbi:** Itens que falham além de `max_attempts` (padrão: 5) devem ser marcados como `DEAD` e o usuário notificado, prevenindo que itens irrecuperáveis bloqueiem a fila indefinidamente.
* **RNF04 — Pool de Conexões (Performance em Nuvem):** Todo acesso ao banco deve passar por um `ThreadedConnectionPool` (mín: 1, máx: 10) para prevenir esgotamento de conexões em instâncias PostgreSQL hospedadas na nuvem.
* **RNF05 — Parsing de JSON Tolerante a Falhas:** O backend deve limpar alucinações do LLM da saída JSON (comentários inline, booleanos estilo Python, caracteres de controle não escapados) antes do parsing, usando `json.loads(..., strict=False)` como último recurso.
* **RNF06 — Validação Matemática (Anti-Alucinação):** Após o processamento do LLM, o backend deve recalcular independentemente o `valor_total` a partir dos dados dos itens se o modelo retornar zero, e validar os valores de `valor_unitario` contra o total da transação.
* **RNF07 — Controle de Acesso (Whitelist):** O bot deve aplicar uma whitelist `ALLOWED_CHAT_IDS` carregada das variáveis de ambiente, rejeitando silenciosamente qualquer interação de usuários Telegram não autorizados.
* **RNF08 — Segurança Stateless e Efêmera:** Credenciais sensíveis nunca devem ser hardcoded. Todos os segredos são injetados via variáveis de ambiente, compatíveis com o painel de Variables do Railway e arquivos `.env` locais.
* **RNF09 — Auditabilidade (SCD):** Todas as tabelas relacionais devem implementar Slowly Changing Dimensions com timestamps `created_at` e `updated_at`. A coluna `transactions.status` deve ser mantida em sincronia com o estado agregado de seus `installments` filhos.

---

### 5. Decisões Arquiteturais: O "Por Quê?"

#### 5.1. Por que um Pipeline Dual de LLM em vez de um Único Prompt?
**Decisão:** Usar duas chamadas LLM sequenciais — Agente 1 extrai dados brutos, Agente 2 enriquece e categoriza.

**Justificativa:** *Separação de Responsabilidade Cognitiva.* Um prompt monolítico tentando simultaneamente extrair entidades, deduzir dados ausentes, validar uma cadeia de raciocínio sobre datas, aplicar uma taxonomia de categorias e formatar um JSON aninhado complexo de forma consistente é uma receita para alucinações. Ao dividir o pipeline, cada agente tem uma tarefa focada e auditável. O Agente 1 opera com `temperature=0.0` (determinismo máximo para extração). O Agente 2 opera com `temperature=0.1` (criatividade mínima para classificação). A saída do Agente 1 é um dicionário Python estruturado antes do Agente 2 executar — falhas são isoladas e diagnosticáveis.

#### 5.2. Por que o Padrão Outbox Transacional em vez de chamadas diretas ao LLM?
**Decisão:** Inserir toda mensagem recebida em uma fila PostgreSQL antes de qualquer processamento pelo LLM.

**Justificativa:** *Entrega Garantida e Experiência do Usuário.* Uma chamada direta à API no handler do Telegram significa que uma falha perde os dados do usuário silenciosamente. O Padrão Outbox desacopla o recebimento do processamento: o bot sempre responde "Recebido" instantaneamente (< 100ms), e o worker em background lida com a chamada lenta e suscetível a falhas de forma assíncrona. O construto SQL `FOR UPDATE SKIP LOCKED` garante processamento concorrente seguro sem locks distribuídos. Isso também fornece lógica de retry, tratamento de rate-limit e trilha de auditoria — tudo gratuitamente.

#### 5.3. Por que um motor de parcelas customizado em vez de uma biblioteca financeira?
**Decisão:** Construir um motor customizado de parcelas (`generate_installment_details`) usando aritmética com `relativedelta` em vez de uma biblioteca financeira.

**Justificativa:** *Regras de domínio específicas não podem ser abstraídas.* O faturamento de cartão de crédito brasileiro tem regras idiossincráticas: o dia de "fechamento" determina em qual ciclo de fatura uma compra cai, e o dia de "vencimento" pode estar em um mês diferente do ciclo de fechamento se `vencimento < fechamento`. Bibliotecas financeiras padrão não modelam isso. Um motor customizado construído sobre `dateutil.relativedelta` oferece controle exato sobre as condições de contorno e é totalmente testável.

#### 5.4. Por que injetar campos de Chain-of-Thought no prompt para análise de datas?
**Decisão:** O prompt do Agente 1 contém um campo `_raciocinio_vencimento` que força o modelo a raciocinar passo a passo sobre datas de vencimento antes de comprometer um valor.

**Justificativa:** *Forçar raciocínio deliberado previne o erro de extração mais comum.* PDFs de contas de consumo (energia, água, gás) perdem sua formatação tabular quando convertidos para texto plano. O comportamento padrão do LLM é pegar a primeira data que encontra — invariavelmente a data de emissão próxima aos campos "Protocolo" ou "Série", não a data de vencimento real. Ao exigir que o modelo articule explicitamente seu raciocínio em um campo estruturado, forçamos que ele *encontre* a data correta em vez de *adivinhar* a primeira. Esta decisão de engenharia de prompt reduziu os erros de extração de data pela maior margem de qualquer mudança no projeto.

#### 5.5. Por que PostgreSQL em vez de um armazenamento NoSQL para um app de finanças pessoais?
**Decisão:** Usar modelo relacional com constraints de chave estrangeira e tabelas normalizadas.

**Justificativa:** *Dados financeiros têm estrutura relacional inerente.* Uma transação tem muitos itens. Uma transação tem muitas parcelas. Uma parcela pertence a exatamente uma transação. Esses são relacionamentos 1-para-N com requisitos de integridade referencial — exatamente o problema que bancos de dados relacionais resolvem. A tabela `installments` atuando como um Livro Caixa AP/AR com `ON DELETE CASCADE` é um padrão emprestado diretamente de softwares contábeis. A flexibilidade de schema do NoSQL seria um passivo aqui, não um ativo: cada query analítica no dashboard Streamlit se beneficia de colunas tipadas, datas indexadas e decimais agregáveis.

---

### 6. Schema do Banco de Dados (Relacionamentos)

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────┐
    id, transaction_type, invoice_number              │ FK
    transaction_date (DATE), location_name            │
    card_bank, card_variant, status                   │
    original_amount, discount_applied, total_amount   │
    macro_category, payment_method                    │
    is_installment, installment_count                 │
                                                      │
transaction_items  ──── transaction_id (FK) ──────────┤
    description, brand, unit_price, quantity          │
    cat_macro, cat_category, cat_subcategory          │
                                                      │
installments  ───────── transaction_id (FK) ──────────┘
    month (MM/AAAA), due_date (DATE)
    amount, payment_status, payment_date (DATE), paid_amount
```

---

### 7. Estratégia de Segurança

* **Segredos Desacoplados:** Chaves de API e credenciais do banco são injetadas via Variáveis de Ambiente. Desenvolvimento local usa `.env` (ignorado pelo git). Produção usa o painel de Variables do Railway.
* **Controle de Acesso:** Uma whitelist `ALLOWED_CHAT_IDS` carregada na inicialização bloqueia todos os usuários Telegram não autorizados no nível do handler, via decorator `security_check`.
* **Design Stateless:** A aplicação é projetada para deploy em containers onde o sistema de arquivos é efêmero. Nenhum estado sensível é gravado em disco (PDFs são processados e deletados em um bloco `finally`).
