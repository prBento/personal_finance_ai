# 🤖 Finance AI Data App: LLM-Powered Personal ERP
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Autor
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

## 🇺🇸 English Version

### 🎯 About the Project
This is an advanced Full-Stack Data Application designed to act as a personal financial ERP. It leverages Large Language Models (LLMs) to ingest chaotic, unstructured daily inputs (free-text messages, website URLs, and complex PDFs) and transform them into a strictly governed, relational database. 

🤝 **AI Mentorship & Collaboration Note:** While the product vision, business rules, and architectural ideas were driven by me, the actual code development, refactoring, and technical structuring were achieved through an active pair-programming and mentoring collaboration with Google's **Gemini AI**.

### 📋 System Requirements

#### Functional Requirements (FR)
- **Multimodal Ingestion:** The bot must accept and process free-text messages, HTML via URLs (NFC-e scraping), and PDF documents (Utility bills).
- **AI Extraction & Routing:** The system must use LLMs to extract entities, infer missing data (e.g., extracting vendors from URLs), and route transactions into 'Income' or 'Expense' logic.
- **AP/AR Ledger Management:** The system must track the payment status of transactions (PENDING vs. PAID) and allow retroactive payment date assignments.
- **Card Statement Math:** The system must calculate future invoice dates and split values accurately based on user-defined credit card closing/due dates.
- **Human-in-the-Loop UI:** The bot must display a summarized breakdown and require explicit user confirmation via an interactive Telegram keyboard before database insertion.
- **Interactive Checkboxes:** The bot must provide an inline menu to query pending bills for the current month and mark them as paid with a single click.

#### Non-Functional Requirements (NFR)
- **Resilience (Outbox Pattern):** The system must queue incoming messages and apply an Exponential Backoff algorithm (60s to 3600s) if the LLM API is unavailable or rate-limited.
- **Fault-Tolerant JSON Parsing:** The backend must handle LLM hallucinations, stripping out invalid control characters and comments (`strict=False`) to prevent decoding crashes.
- **Data Governance:** The database must prevent duplicate entries via exact ID matches and fuzzy logic heuristics (Location + Amount + Date). 
- **Auditability:** All relational tables must implement Slowly Changing Dimensions (SCD) with `criado_em` and `atualizado_em` timestamps managed directly by the SQL queries.
- **Stateless Security:** Sensitive credentials (API Keys, DB Passwords) must never be hardcoded, relying strictly on environment variables (`.env`) for safe cloud deployment.

### 🛠️ Tech Stack
* **Language:** Python 3.10+
* **Conversational Interface:** `python-telegram-bot` (State Machine & Inline UI)
* **AI Engine:** Groq API (`meta-llama/llama-4-scout-17b-16e-instruct`)
* **Database:** PostgreSQL (via Docker) with `psycopg2`
* **Scraping & Parsing:** `BeautifulSoup4`, `PyPDF`

### 🚀 How to Run Locally

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/prBento/finance-ai-app.git](https://github.com/prBento/finance-ai-app.git)
   cd finance-ai-app
   ```
2. **Set up the Environment Variables:**
   Create a `.env` file in the root directory (do not commit this file):
   ```env
   # API Keys
   TELEGRAM_TOKEN=your_telegram_bot_token
   GROQ_API_KEY=your_groq_api_key
   
   # Database Secrets
   DB_USER=your_secure_user
   DB_PASSWORD=your_secure_password
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
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

---

## 🇧🇷 Versão em Português Brasileiro

### 🎯 Sobre o Projeto
Esta é uma Aplicação de Dados Full-Stack avançada, projetada para atuar como um ERP financeiro pessoal. O sistema utiliza Modelos de Linguagem de Larga Escala (LLMs) para ingerir entradas caóticas e não estruturadas do dia a dia (mensagens de texto livre, URLs de sites e PDFs complexos) e transformá-las em um banco de dados relacional e rigidamente governado.

🤝 **Nota de Mentoria e Colaboração com IA:** Embora a visão do produto, as decisões de regras de negócio e as ideias de arquitetura tenham sido direcionadas por mim, todo o desenvolvimento do código, refatoração e estruturação técnica foram construídos através de uma colaboração ativa de *pair-programming* (programação em par) e mentoria com a Inteligência Artificial **Gemini** (Google).

### 📋 Requisitos do Sistema

#### Requisitos Funcionais (RF)
- **Ingestão Multimodal:** O bot deve aceitar e processar texto livre, HTML via URLs (*scraping* de NFC-e) e documentos PDF (Faturas).
- **Extração e Roteamento por IA:** O sistema deve usar LLMs para extrair entidades, deduzir dados ausentes (ex: extrair empresa da URL) e classificar a transação como 'Receita' ou 'Despesa'.
- **Gestão de Livro Caixa (AP/AR):** O sistema deve rastrear o status de pagamento (PENDENTE vs PAGO) e permitir a atribuição retroativa de datas de pagamento.
- **Matemática de Faturas:** O sistema deve calcular o vencimento de faturas futuras e dividir os valores de parcelas com base nas datas de corte/vencimento de cartões definidos pelo usuário.
- **UI Human-in-the-Loop:** O bot deve exibir um resumo formatado e exigir confirmação explícita via teclado interativo antes de inserir dados no banco.
- **Checkboxes Interativos:** O bot deve fornecer um menu *inline* para consultar contas pendentes do mês e permitir dar baixa com um único clique.

#### Requisitos Não-Funcionais (RNF)
- **Resiliência (Padrão Outbox):** O sistema deve enfileirar mensagens e aplicar um algoritmo de Espera Exponencial (60s a 3600s) caso a API da IA falhe ou atinja limite de requisições.
- **Parsing Tolerante a Falhas:** O backend deve tratar alucinações do LLM, limpando caracteres de controle inválidos e comentários soltos (`strict=False`) para evitar quebra no JSON.
- **Governança de Dados:** O banco deve barrar inserções duplicadas via validação exata de ID e heurísticas de similaridade (Local + Valor + Data).
- **Auditabilidade:** Todas as tabelas relacionais devem implementar Slowly Changing Dimensions (SCD), com carimbos de `criado_em` e `atualizado_em` regidos pelo SQL.
- **Segurança Stateless:** Credenciais sensíveis nunca devem estar em *hardcode*, dependendo inteiramente de variáveis de ambiente (`.env`) para garantir um deploy seguro na nuvem.

### 🛠️ Stack Tecnológico
* **Linguagem:** Python 3.10+
* **Interface Conversacional:** `python-telegram-bot` (Máquina de Estados e UI Inline)
* **Motor de IA:** API da Groq (`meta-llama/llama-4-scout-17b-16e-instruct`)
* **Banco de Dados:** PostgreSQL (via Docker) com `psycopg2`
* **Scraping e Parsing:** `BeautifulSoup4`, `PyPDF`

### 🚀 Como Rodar Localmente

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/prBento/finance-ai-app.git](https://github.com/prBento/finance-ai-app.git)
   cd finance-ai-app
   ```
2. **Configure as Variáveis de Ambiente:**
   Crie um arquivo `.env` na raiz do projeto (não suba este arquivo para o Git):
   ```env
   # Chaves de API
   TELEGRAM_TOKEN=seu_token_do_telegram
   GROQ_API_KEY=sua_chave_da_groq
   
   # Credenciais do Banco de Dados
   DB_USER=seu_usuario_seguro
   DB_PASSWORD=sua_senha_segura
   DB_NAME=db_finance
   DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
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