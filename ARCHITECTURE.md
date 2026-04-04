# 🏗️ Architecture Document: AI Data App
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Autor
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### 🧩 System Design Philosophy
This system is a Full-Stack Data Application transitioning towards a cloud-native, event-driven model. It employs a **Hybrid Architecture**: LLMs are used strictly for unstructured-to-structured translation (NLP), while Python handles deterministic mathematics, state management, and data governance.

### 🏗️ Core Components
1. **Entry Interface (Telegram Bot):** The asynchronous user touchpoint. Features a state machine for interactive entity resolution and an Inline UI for the Accounts Payable module.
2. **Backend Engine (Python):** Orchestrates web scraping (`BeautifulSoup`), PDF extraction (`PyPDF` with password handling), and mathematically validates LLM outputs.
3. **Queue System (Transactional Outbox):** A resilient background worker querying a `PENDING` PostgreSQL table. It handles API rate limits using an **Exponential Backoff** algorithm.
4. **AI Engine (Groq API):** Uses `llama-4-scout-17b` with injected "Chain of Thought" fields to force logical extraction from unformatted documents.
5. **Database (PostgreSQL):** Relational storage featuring the `parcelas` table acting as a full AP/AR (Accounts Payable/Receivable) ledger with SCD (Slowly Changing Dimensions) audit columns.

### 🛡️ Security Strategy
- **Decoupled Secrets:** Sensitive data (API Keys, DB Credentials) are injected via Environment Variables.
- **Stateless Design:** Prepared for containerized deployment where the file system is ephemeral.

---

## 🇧🇷 Versão em Português Brasileiro

### 🧩 Filosofia de Design do Sistema
Este sistema é uma Aplicação de Dados Full-Stack em transição para um modelo nativo em nuvem e orientado a eventos. Emprega uma **Arquitetura Híbrida**: LLMs são usados estritamente para tradução de dados não-estruturados (NLP), enquanto o Python lida com matemática determinística, gerenciamento de estados e governança.

### 🏗️ Componentes Principais
1. **Interface de Entrada (Telegram Bot):** Ponto de contato assíncrono. Possui uma máquina de estados para resolução de entidades e uma UI Inline para o módulo de Contas a Pagar.
2. **Backend Engine (Python):** Orquestra *scraping* (`BeautifulSoup`), extração de PDFs (`PyPDF` com tratamento de senhas) e blinda matematicamente as alucinações do LLM.
3. **Queue System (Transactional Outbox):** *Worker* resiliente em *background* que lê filas no PostgreSQL. Lida com instabilidades da IA aplicando algoritmos de **Exponential Backoff**.
4. **Motor de IA (Groq API):** Usa LLMs rápidos com engenharia de *prompt* avançada, incluindo injeção de "Cadeia de Pensamento" para forçar extrações lógicas.
5. **Banco de Dados (PostgreSQL):** Armazenamento relacional onde a tabela `parcelas` atua como um Livro Caixa oficial (Contas a Pagar/Receber), possuindo rastreamento de status e colunas de auditoria.

### 🛡️ Estratégia de Segurança
- **Segredos Desacoplados:** Dados sensíveis (Chaves de API, Credenciais de Banco) são injetados via Variáveis de Ambiente.
- **Design Stateless:** Preparado para deploy em containers onde o sistema de arquivos é efêmero.