# Architecture Document: AI Data App (Roadmap 2)

## [PT-BR] Visão Geral
Este sistema é uma aplicação Full-Stack focada em dados (Data App) para controle financeiro pessoal, utilizando Processamento de Linguagem Natural (NLP) para extração de dados não estruturados (textos e links de notas fiscais).

### Componentes Principais
1. **Interface de Entrada (Telegram Bot):** Ponto de contato do usuário. Recebe áudios, textos livres ou URLs de notas fiscais (NFC-e).
2. **Backend (FastAPI):** O cérebro da operação. Gerencia os webhooks do Telegram, orquestra as chamadas de IA e processa as regras de negócio.
3. **Motor de IA (Groq API):** Utiliza LLMs open-source (ex: Llama 3) para extrair entidades das mensagens e devolver um payload JSON estruturado (Item, Valor, Categoria, Data).
4. **Banco de Dados (PostgreSQL via Docker):** Armazenamento relacional e transacional dos gastos.
5. **Interface de Visualização (Streamlit):** Dashboard interativo em Python para visualização de métricas, evolução de gastos e edição manual de registros.

### Fluxo de Dados
User -> Telegram -> FastAPI -> Groq (LLM Parsing) -> FastAPI -> PostgreSQL -> Streamlit -> User

---

## [EN-US] Overview
This system is a Full-Stack Data App for personal finance management, leveraging Natural Language Processing (NLP) to extract unstructured data (free text and invoice links).

### Core Components
1. **Input Interface (Telegram Bot):** The user's touchpoint. It receives audio, free text, or invoice URLs (NFC-e).
2. **Backend (FastAPI):** The brain of the operation. It manages Telegram webhooks, orchestrates AI calls, and processes business rules.
3. **AI Engine (Groq API):** Uses open-source LLMs (e.g., Llama 3) to extract entities from messages and return a structured JSON payload (Item, Value, Category, Date).
4. **Database (PostgreSQL via Docker):** Relational and transactional storage for expenses.
5. **Visualization Interface (Streamlit):** Interactive Python dashboard for viewing metrics, expense trends, and manual record editing.

### Data Flow
User -> Telegram -> FastAPI -> Groq (LLM Parsing) -> FastAPI -> PostgreSQL -> Streamlit -> User