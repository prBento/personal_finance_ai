# 🤖 Finance AI Data App

Um assistente financeiro pessoal turbinado por Inteligência Artificial (LLMs). Este projeto ingere mensagens de texto livre, PDFs de notas fiscais ou URLs da Secretaria da Fazenda via Telegram, extrai as entidades usando a API da Groq (Llama Models) e armazena os dados estruturados em um banco relacional PostgreSQL.

## 🚀 Funcionalidades (Features)
* **Extração NLP:** Entende linguagem natural (ex: "Comprei um pão por 5 reais na padaria do zé").
* **Leitura Multimodal:** Faz scraping de URLs (NFC-e) via `BeautifulSoup` e lê faturas em PDF via `PyPDF`.
* **Resiliência Máxima (Fila Customizada):** Se a API da IA estiver fora do ar ou com *Rate Limit* estourado, o bot retém a transação numa fila no banco de dados e tenta novamente de forma autônoma.
* **Governança de Dados:** * Verificação de duplicidade de chaves de Notas Fiscais.
  * Heurística de similaridade de textos para alertar sobre compras repetidas.
  * Trava automática contra parcelamento em cartões pré-pagos/benefício.
* **Human-in-the-Loop:** Pede confirmação interativa antes de sujar o banco de dados.

## 🛠️ Stack Tecnológica
* **Linguagem:** Python 3.10+
* **Interface Conversacional:** `python-telegram-bot`
* **Inteligência Artificial:** API da Groq (`meta-llama/llama-4-scout-17b-16e-instruct`)
* **Banco de Dados:** PostgreSQL (via Docker) e `psycopg2`

## ⚙️ Como rodar localmente (Setup)

### 1. Pré-requisitos
* Docker e Docker Compose instalados na máquina.
* Python 3.10 ou superior.
* Um token de Bot do Telegram (Criado via [BotFather](https://t.me/botfather)).
* Uma API Key gratuita da [Groq Cloud](https://console.groq.com/).

### 2. Configurando o Ambiente
Clone o repositório e crie um arquivo `.env` na raiz do projeto contendo as suas chaves e a URL do banco local:

```env
TELEGRAM_TOKEN=seu_token_do_telegram_aqui
GROQ_API_KEY=sua_chave_da_groq_aqui
DATABASE_URL=postgresql://user_finance:password_finance@localhost:5432/db_finance
```

### 3. Subindo o Banco de Dados
Abra o terminal na pasta do projeto e inicie o contêiner do PostgreSQL em segundo plano:
```bash
docker-compose up -d
```

### 4. Instalando Dependências
Crie um ambiente virtual (VENV), ative-o e instale os pacotes:
```bash
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 5. Iniciando o Cérebro (O Bot)
Basta executar o script principal. Ele automaticamente criará as tabelas no PostgreSQL (caso não existam) e começará a ouvir as mensagens do Telegram e processar a fila em background.
```bash
python bot.py
```

Pronto! Agora é só mandar um "Oi" para o seu bot no Telegram e começar a enviar os seus gastos.