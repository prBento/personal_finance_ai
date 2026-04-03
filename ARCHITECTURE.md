# Architecture Document: AI Data App

## [PT-BR] Visão Geral
Este sistema é uma aplicação Full-Stack focada em dados (Data App) para controle financeiro pessoal. Ele utiliza modelos de Linguagem de Larga Escala (LLMs) para transformar mensagens caóticas do dia a dia (textos, links e PDFs) em uma base de dados relacional governada.

### Componentes Principais
1. **Interface de Entrada (Telegram Bot):** Ponto de contato assíncrono do usuário. Contém uma máquina de estados para coletar métodos de pagamento e cartões.
2. **Backend Engine (Python):** O cérebro da operação. Processa o polling do Telegram, executa scrapings (BeautifulSoup) e extração de documentos (PyPDF).
3. **Queue System (Transactional Outbox):** Fila de processamento embutida no PostgreSQL para garantir resiliência contra indisponibilidades e *Rate Limits* da API de IA.
4. **Motor de IA (Groq API):** Utiliza LLMs leves e rápidos (como `llama-4-scout-17b`) divididos em dois agentes: Agente de Extração e Agente de Classificação/Enriquecimento.
5. **Banco de Dados (PostgreSQL via Docker):** Armazenamento relacional que garante a integridade dos dados, possuindo validações heurísticas contra inserções duplicadas.
6. **Interface de Visualização (Streamlit - Em breve):** Dashboard interativo para visualização de métricas de fluxo de caixa e faturas a pagar.

### Fluxo de Dados Resiliente
1. `User` envia Mensagem -> `Bot` salva na Tabela de Fila (`PENDENTE`) -> Retorna "Recebido".
2. `Worker` (Rodando em background a cada 10s) lê a fila -> Envia para `Groq API`.
3. Em caso de *Rate Limit*, `Worker` reagenda para X segundos (Exponential Backoff).
4. `Groq` devolve JSON -> `Worker` formata regras (Maiúsculas, UUIDs, anti-parcelamento).
5. `Worker` invoca a UI do Telegram pedindo Confirmação Humana (Human-in-the-loop).
6. Após "Sim", salva nas tabelas normalizadas do `PostgreSQL` -> Disponível para `Streamlit`.