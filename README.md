# 💰 Finance AI Data App: LLM-Powered Personal ERP
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white) ![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white) ![Railway](https://img.shields.io/badge/Railway-131415?style=for-the-badge&logo=railway&logoColor=white) ![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge&logo=groq&logoColor=white)

*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🎯 About the Project

This is an advanced Full-Stack Data Application designed to act as a **personal financial ERP**. The system uses Large Language Models (LLMs) to ingest chaotic, unstructured daily inputs — free-text messages, electronic invoice URLs, and complex PDF bills — and transforms them into a strictly governed, relational PostgreSQL database with full Accounts Payable/Receivable tracking.

The architecture is built around a **Transactional Outbox Pattern**: every input is persisted to a queue immediately, then processed asynchronously by a background worker with Exponential Backoff, meaning no transaction is ever lost even if the AI API is temporarily unavailable.

🤝 **AI Collaboration Note:** The product vision, business rules, and all architectural decisions were driven by me. Code development, refactoring, and technical structuring were built through an active pair-programming collaboration with **Gemini AI** (Google) and **Claude** (Anthropic).

---

### 🌟 Key Features

- **Multimodal Ingestion:** Accepts free-text messages, NFC-e electronic invoice URLs (web scraping), and PDF utility bills (text extraction) in a single unified pipeline.
- **Dual-Agent AI Pipeline:** Agent 1 extracts raw entities with `temperature=0.0`; Agent 2 enriches and categorizes with `temperature=0.1`. Separation of cognitive responsibility eliminates entire classes of LLM hallucination.
- **Resilient Outbox Queue:** All inputs are queued to PostgreSQL before any AI processing. A background worker retries failed items with Exponential Backoff (60s–3600s), with a `max_attempts` limit to prevent zombie queue items.
- **Human-in-the-Loop Confirmation:** Every transaction is presented as a structured Markdown summary and requires explicit user confirmation before any database write occurs.
- **AP/AR Ledger with Installment Engine:** A custom installment calculator handles Brazilian credit card billing rules (closing day + due day → correct invoice cycle), splitting transactions across multiple months in the `installments` table.
- **Interactive Accounts Payable (`/contas`):** Inline keyboard UI to browse pending bills for the current month and mark them as paid with a single tap and a retroactive date.
- **Access Control Whitelist:** An `ALLOWED_CHAT_IDS` environment variable blocks all unauthorized Telegram users at the handler level.
- **Cloud-Native Deployment:** Runs on Railway PaaS with a `ThreadedConnectionPool` to manage database connections efficiently within cloud-tier limits.

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

### 🤖 How to Create your Telegram Bot

Before running the application, you need to create a bot on Telegram to get your API Token.

1. Open Telegram and search for [@BotFather](https://t.me/botfather).
2. Send the command `/newbot` and follow the instructions to name your bot and choose a username.
3. Copy the **HTTP API Token** provided at the end. You will use this as your `TELEGRAM_TOKEN_DEV` and `TELEGRAM_TOKEN_PROD`.
4. To get your personal `ALLOWED_CHAT_IDS`, send a "Hello" to your newly created bot, then talk to [@userinfobot](https://t.me/userinfobot) to discover your unique Telegram account ID.

---

### 🚀 How to Run Locally

**Prerequisites:** Python 3.10+, Docker, and a Groq API key (free at [console.groq.com](https://console.groq.com)).

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/prBento/finance-ai-app.git](https://github.com/prBento/finance-ai-app.git)
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

### ☁️ Cloud Deployment (Railway)

This project is fully optimized for PaaS deployment, specifically [Railway](https://railway.app/).

1. Create a new project on Railway and provision a **PostgreSQL** database plugin.
2. Connect your GitHub repository to the project.
3. Railway's Nixpacks engine will automatically detect the `.python-version` file (forcing Python 3.12) and install dependencies from `requirements.txt`.
4. Go to the **"Variables"** tab of your app service and add all the production variables from your `.env` file:
   * `ENVIRONMENT=prod`
   * `TELEGRAM_TOKEN_PROD`
   * `GROQ_API_KEY_PROD`
   * `DATABASE_URL` (Use the internal connection string provided by your Railway Postgres plugin)
   * `ALLOWED_CHAT_IDS`
5. The deployment will trigger automatically. Once the green checkmark appears, your bot is live and waiting for your receipts!

---

### 🧠 AI Architecture: Why a Dual-Agent Pipeline?

For the extraction engine, we chose a **Two-Agent Sequential Pipeline** over a single monolithic prompt for the following reasons:

1. **Isolated Failure Modes:** If Agent 1 (Extractor) fails, Agent 2 (Enricher) never runs. Errors are diagnosed at the exact stage where they occur, not in a tangled single-prompt output.
2. **Calibrated Temperature per Task:** Data extraction requires determinism (`temperature=0.0`). Category classification tolerates minimal variation (`temperature=0.1`). A single prompt cannot have two temperatures.
3. **Chain-of-Thought Date Reasoning:** Agent 1 contains a `_raciocinio_vencimento` field that forces the model to reason step-by-step about due dates before committing a value — the single most effective technique to prevent the most common extraction error in PDF utility bills (confusing emission date with due date).
4. **Math Validation Post-LLM:** After both agents run, Python recalculates `total_amount` from item-level data and fills in missing `unit_price` values. The LLM extracts; Python validates. Neither is fully trusted to do the other's job.

---

### 🗂️ Project Structure

```
finance-ai-app/
├── bot.py              # Telegram handlers, State Machine, queue worker, AI pipeline
├── database.py         # All DB functions, connection pool, table creation
├── Procfile            # Railway process definition
├── docker-compose.yml  # Local PostgreSQL setup
├── requirements.txt    # Python dependencies
├── ARCHITECTURE.md     # Full technical specification (this document's companion)
├── BACKLOG.md          # Product backlog and roadmap
├── .python-version     # Enforces exact Python version in cloud buildpacks
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
- [x] Interactive AP/AR: Inline keyboard for pending bills + single-tap payment.
- [x] `ThreadedConnectionPool` for cloud-safe database connections.
- [x] `ALLOWED_CHAT_IDS` whitelist security.
- [x] DATE-typed columns for all date fields + SQL indexes.
- [x] `try/finally` safe PDF cleanup (no temp file leaks).
- [x] `transactions.status` sync when all installments are paid.

#### 🚧 V2 — Scale & Visualization (In Progress)
- [ ] **Task 10 (Streamlit):** Real-time Financial Dashboard for spend analysis, category breakdowns, and monthly cash flow.
- [ ] **Task 11 (FastAPI):** Transition from Long Polling to Webhooks for lower latency and resource usage.
- [ ] **Task 12 (Cloud):** Full cloud hardening with structured logging (`logging` module) and Railway deployment best practices.
- [ ] **Task 13 (Anticipation):** Commands for early installment payment with discount yield calculation.
- [ ] **Task 14 (UX/UI AP/AR):** Show card bank and variant next to each pending installment in `/contas`, allowing visual grouping by credit card invoice.
- [ ] **DEBT-03 (Analytics View):** `CREATE VIEW monthly_summary` in PostgreSQL to feed Streamlit aggregations without complex runtime joins.
- [ ] **BACK-01 (Multi-transaction):** Process arrays of multiple transactions from a single LLM response (e.g., multi-purchase PDFs).
- [ ] **BACK-03 (PDF Decrypt):** Request PDF password mid-conversation via State Machine and decrypt in-memory.

---
---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto

Esta é uma Aplicação de Dados Full-Stack avançada, projetada para atuar como um **ERP financeiro pessoal**. O sistema usa Modelos de Linguagem de Larga Escala (LLMs) para ingerir entradas caóticas e não estruturadas do dia a dia — mensagens de texto livre, URLs de notas fiscais eletrônicas e PDFs complexos de contas — e as transforma em um banco de dados PostgreSQL relacional e rigidamente governado, com rastreamento completo de Contas a Pagar e a Receber.

A arquitetura é construída em torno de um **Padrão de Outbox Transacional**: todo input é persistido em uma fila imediatamente, depois processado de forma assíncrona por um worker em background com Backoff Exponencial, o que significa que nenhuma transação é perdida mesmo que a API de IA esteja temporariamente indisponível.

🤝 **Nota de Colaboração com IA:** A visão do produto, as regras de negócio e todas as decisões arquiteturais foram direcionadas por mim. O desenvolvimento do código, refatoração e estruturação técnica foram construídos através de uma colaboração ativa de pair-programming com **Gemini AI** (Google) e **Claude** (Anthropic).

---

### 🌟 Funcionalidades Principais

- **Ingestão Multimodal:** Aceita mensagens de texto livre, URLs de NFC-e (web scraping), e PDFs de contas de consumo (extração de texto) em um único pipeline unificado.
- **Pipeline Dual de Agentes de IA:** Agente 1 extrai entidades brutas com `temperature=0.0`; Agente 2 enriquece e categoriza com `temperature=0.1`. A separação de responsabilidade cognitiva elimina classes inteiras de alucinação do LLM.
- **Fila Outbox Resiliente:** Todos os inputs são enfileirados no PostgreSQL antes de qualquer processamento pela IA. Um worker em background tenta novamente os itens falhos com Backoff Exponencial (60s–3600s), com limite de `max_attempts` para prevenir itens zumbi na fila.
- **Confirmação Human-in-the-Loop:** Toda transação é apresentada como um resumo estruturado em Markdown e requer confirmação explícita do usuário antes de qualquer escrita no banco.
- **Livro Caixa AP/AR com Motor de Parcelas:** Um calculador de parcelas customizado lida com as regras de faturamento de cartão de crédito brasileiro (dia de fechamento + dia de vencimento → ciclo correto da fatura), distribuindo as transações por múltiplos meses na tabela `installments`.
- **Contas a Pagar Interativo (`/contas`):** UI com teclado inline para navegar pelas contas pendentes do mês atual e marcá-las como pagas com um único toque e uma data retroativa.
- **Whitelist de Controle de Acesso:** Uma variável de ambiente `ALLOWED_CHAT_IDS` bloqueia todos os usuários Telegram não autorizados no nível do handler.
- **Deploy Cloud-Native:** Roda no Railway PaaS com um `ThreadedConnectionPool` para gerenciar conexões de banco de dados eficientemente dentro dos limites da nuvem.

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

### 🤖 Como Criar seu Bot no Telegram

Antes de rodar a aplicação, você precisa criar um bot no Telegram para obter o seu Token de API.

1. Abra o Telegram e busque por [@BotFather](https://t.me/botfather).
2. Envie o comando `/newbot` e siga as instruções para dar um nome e um "username" ao seu bot.
3. Copie o **HTTP API Token** gerado no final. Você usará isso como seu `TELEGRAM_TOKEN_DEV` e `TELEGRAM_TOKEN_PROD`.
4. Para pegar o seu `ALLOWED_CHAT_IDS`, envie um "Oi" para o seu novo bot e, em seguida, fale com o [@userinfobot](https://t.me/userinfobot) para descobrir o seu ID pessoal da conta do Telegram.

---

### 🚀 Como Rodar Localmente

**Pré-requisitos:** Python 3.10+, Docker, e uma chave de API da Groq (gratuita em [console.groq.com](https://console.groq.com)).

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/prBento/finance-ai-app.git](https://github.com/prBento/finance-ai-app.git)
   cd finance-ai-app
   ```

2. **Configure as Variáveis de Ambiente:**
   Crie um arquivo `.env` na raiz do projeto. **Nunca faça commit deste arquivo.**
   ```env
   # Ambiente
   ENVIRONMENT=dev

   # Tokens do Telegram (um por ambiente)
   TELEGRAM_TOKEN_DEV=seu_token_bot_dev
   TELEGRAM_TOKEN_PROD=seu_token_bot_prod

   # Chaves da Groq API
   GROQ_API_KEY_DEV=sua_chave_groq_dev
   GROQ_API_KEY_PROD=sua_chave_groq_prod

   # Banco de Dados
   DB_USER=seu_usuario
   DB_PASSWORD=sua_senha
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}

   # Whitelist de Segurança (IDs do Telegram separados por vírgula)
   ALLOWED_CHAT_IDS=seu_chat_id_do_telegram
   ```

3. **Suba o Banco de Dados:**
   ```bash
   docker-compose up -d
   ```

4. **Instale as Dependências e Inicie:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # No Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python bot.py
   ```
   Na inicialização, `create_tables()` roda automaticamente e cria todas as tabelas, índices e constraints caso não existam.

---

### ☁️ Deploy na Nuvem (Railway)

Este projeto é otimizado para deploy em PaaS, especificamente no [Railway](https://railway.app/).

1. Crie um novo projeto no Railway e adicione o plugin do **PostgreSQL**.
2. Conecte o seu repositório do GitHub ao projeto.
3. O motor Nixpacks do Railway vai detectar automaticamente o arquivo `.python-version` (forçando o Python 3.12) e instalar as dependências do `requirements.txt`.
4. Vá até a aba **"Variables"** do seu serviço e adicione todas as variáveis de produção do seu arquivo `.env`:
   * `ENVIRONMENT=prod`
   * `TELEGRAM_TOKEN_PROD`
   * `GROQ_API_KEY_PROD`
   * `DATABASE_URL` (Use a URL de conexão interna fornecida pelo próprio plugin do PostgreSQL do Railway)
   * `ALLOWED_CHAT_IDS`
5. O deploy será iniciado automaticamente. Assim que o ícone verde de sucesso aparecer, seu bot estará rodando na nuvem 24/7!

---

### 🧠 Arquitetura de IA: Por que um Pipeline Dual de Agentes?

Para o motor de extração, escolhemos um **Pipeline Sequencial de Dois Agentes** em vez de um único prompt monolítico pelos seguintes motivos:

1. **Modos de Falha Isolados:** Se o Agente 1 (Extrator) falhar, o Agente 2 (Enriquecedor) nunca executa. Erros são diagnosticados exatamente na etapa onde ocorrem, não em uma saída de prompt único entrelaçada.
2. **Temperature Calibrada por Tarefa:** Extração de dados requer determinismo (`temperature=0.0`). Classificação de categorias tolera variação mínima (`temperature=0.1`). Um único prompt não pode ter duas temperatures.
3. **Raciocínio de Datas via Chain-of-Thought:** O Agente 1 contém um campo `_raciocinio_vencimento` que força o modelo a raciocinar passo a passo sobre datas de vencimento antes de comprometer um valor — a técnica mais eficaz para prevenir o erro de extração mais comum em PDFs de contas (confundir data de emissão com data de vencimento).
4. **Validação Matemática Pós-LLM:** Após ambos os agentes executarem, o Python recalcula o `valor_total` a partir dos dados dos itens e preenche valores ausentes de `valor_unitario`. O LLM extrai; o Python valida. Nenhum dos dois é completamente confiado para fazer o trabalho do outro.

---

### 🗂️ Estrutura do Projeto

```
finance-ai-app/
├── bot.py              # Handlers do Telegram, Máquina de Estados, worker da fila, pipeline de IA
├── database.py         # Todas as funções de BD, pool de conexões, criação de tabelas
├── Procfile            # Definição de processo do Railway
├── docker-compose.yml  # Configuração local do PostgreSQL
├── requirements.txt    # Dependências Python
├── ARCHITECTURE.md     # Especificação técnica completa
├── BACKLOG.md          # Backlog do produto e roadmap
├── .python-version     # Força a versão exata do Python nos servidores cloud
└── .env                # Variáveis de ambiente (ignorado pelo git)
```

---

### 🚦 Padrões de Git e Commits

Este projeto segue a especificação **Conventional Commits**:

| Prefixo | Uso |
|---------|-----|
| `feat:` | Nova funcionalidade ou comportamento |
| `fix:` | Correção de bug |
| `refactor:` | Mudança de código sem alteração de comportamento |
| `docs:` | Documentação apenas |
| `chore:` | Build, configuração ou mudanças de dependências |

---

### 🗺️ Roadmap de Desenvolvimento

#### ✅ V1 — Fundação de Produção (Concluído)
- [x] Ingestão base: Telegram Bot + parsing dual-agente via Groq.
- [x] Padrão Outbox com Backoff Exponencial e proteção contra itens zumbi.
- [x] Inteligência de Documentos: scraper de URL NFC-e + extrator de texto de PDF.
- [x] Roteamento multi-agente para lógica de Receitas e Despesas.
- [x] Motor customizado de parcelas com regras de faturamento de cartão brasileiro.
- [x] AP/AR Interativo: teclado inline para contas pendentes + baixa com um toque.
- [x] `ThreadedConnectionPool` para conexões de banco seguras na nuvem.
- [x] Whitelist de segurança `ALLOWED_CHAT_IDS`.
- [x] Colunas tipadas `DATE` para todas as datas + índices SQL.
- [x] Limpeza segura de PDFs temporários com `try/finally` (sem vazamentos).
- [x] Sincronização de `transactions.status` quando todas as parcelas são pagas.

#### 🚧 V2 — Escala e Visualização (Em Progresso)
- [ ] **Task 10 (Streamlit):** Dashboard Financeiro em tempo real para análise de gastos, categorias e fluxo de caixa mensal.
- [ ] **Task 11 (FastAPI):** Transição de Long Polling para Webhooks para menor latência e uso de recursos.
- [ ] **Task 12 (Nuvem):** Hardening completo em nuvem com logging estruturado (módulo `logging`) e boas práticas de deploy no Railway.
- [ ] **Task 13 (Antecipação):** Comandos para pagamento antecipado de parcelas com cálculo de rendimento de desconto.
- [ ] **Task 14 (UX/UI Contas a Pagar):** Mostrar banco e variante do cartão ao lado de cada parcela pendente no `/contas`, permitindo agrupamento visual por fatura de cartão.
- [ ] **DEBT-03 (View Analítica):** `CREATE VIEW monthly_summary` no PostgreSQL para alimentar as agregações do Streamlit sem joins complexos em tempo de execução.
- [ ] **BACK-01 (Multi-transação):** Processar arrays de múltiplas transações de uma única resposta do LLM (ex: PDFs com múltiplas compras).
- [ ] **BACK-03 (PDF com Senha):** Solicitar senha do PDF durante a conversa via Máquina de Estados e descriptografar em memória.