# 🏛️ Agente Hermes - Orquestrador Inteligente de Comunicação & Roteamento

O **Agente Hermes** é o mensageiro central inteligente da arquitetura corporativa, inspirado no deus grego mensageiro, da velocidade e das conexões. Ele atua como uma camada de alta performance (API Gateway / Message Broker inteligente) que recebe eventos de múltiplos canais de entrada, extrai e limpa seu conteúdo semântico, classifica a intenção de forma ultrarrápida usando LLMs rápidos ou heurísticas otimizadas e realiza o roteamento direcionado para sub-agentes, RAGs ou canais específicos, com total resiliência operacional (retentativas exponenciais e fila de mensagens não entregues - DLQ).

---

## 1. Arquitetura

O Agente Hermes é estruturado em torno de um modelo orientado a eventos (Event-Driven) e assíncrono para garantir baixa latência e alto throughput. Ele utiliza o **FastAPI** como barreira de entrada assíncrona (Ingress) e o **LangGraph** como máquina de estado inteligente para classificar intenções e determinar condicionalmente o destino de cada requisição.

### Fluxo de Dados Central (Diagrama ASCII)

```text
+-------------------------------------------------------------------------------------------------------+
|                                        Fluxo de Execução do Hermes                                    |
+-------------------------------------------------------------------------------------------------------+

 Múltiplos Canais de Entrada
 (Webhooks, E-mails Transacionais)
               |
               v
  +-------------------------+
  | Hermes Ingress (FastAPI)| <--- Recebimento Assíncrono com BackgroundTasks
  +-------------------------+
               |
               v
  +-------------------------+
  |  Intelligent Router     | <--- Orquestrador LangGraph (StateGraph Workflow)
  |       (State)           |
  +-------------------------+
               |
               +---> Node 1: [Classificação de Intenção (LLM / Heurísticas NLU)]
               |
               +---> Node 2: [Decisão de Roteamento Semântico Condicional]
               |
               v
  +-----------------------------------------------------------------------------------------+
  |                                     Motor de Despacho                                   |
  +-----------------------------------------------------------------------------------------+
         |                                           |                                |
         | (Sucesso)                                 | (Sucesso)                      | (Falha Persistente)
         v                                           v                                v
  +-------------------+                      +-----------------+             +------------------+
  |   Apache Agent    |                      |   WeKnora RAG   |             |   Dead Letter    |
  | (Alerta de Infra) |                      | (Dúvidas de RH) |             |   Queue (DLQ)    |
  +-------------------+                      +-----------------+             +------------------+
```

---

## 2. Estrutura de Diretórios

O mapeamento de arquivos do projeto segue um design modular Plug-and-Play para que novos canais de entrada/saída e novas rotas inteligentes possam ser adicionados sem alterar a infraestrutura central:

```text
agent_hermes/
├── README.md                   # Documentação mestre em Português (este arquivo)
├── main.py                     # Entrypoint FastAPI com Ingress de alta concorrência
├── core/
│   ├── __init__.py
│   ├── router.py               # Máquina de Estado LangGraph e Classificador NLU
│   └── reliability.py          # Políticas de Retry Exponencial e Dead Letter Queue (DLQ)
├── channels/
│   ├── __init__.py
│   ├── email_parser.py         # Módulo de limpeza HTML BeautifulSoup e extração semântica
│   └── discord_webhook.py      # Notificador e despachador assíncrono Discord Webhook
└── tests/
    ├── __init__.py
    └── test_hermes.py          # Conjunto de testes automatizados e de integração
```

---

## 3. Instalação

### Pré-requisitos
* Python 3.11 ou superior
* Gerenciador de pacotes `pip`

### Instalar dependências necessárias
Execute o comando a seguir na raiz do projeto para instalar as bibliotecas base:

```bash
pip install langgraph langchain-core pydantic fastapi uvicorn tenacity httpx beautifulsoup4 pytest pytest-asyncio
```

---

## 4. Configuração

O Hermes é projetado para operar de forma híbrida:
1. **Modo Heurístico Rápido (Local):** Ativado por padrão caso chaves de API não estejam configuradas. Utiliza regras semânticas altamente otimizadas que garantem latência inferior a 1ms.
2. **Modo LLM Inteligente (NLU Remoto):** Se chaves de API estiverem configuradas, executa chamadas em tempo real para modelos Llama 3 (via Groq API) ou GPT-4o-mini (via OpenAI).

### Variáveis de Ambiente Suportadas:
* `LLM_API_KEY`: Chave da API do provedor correspondente (Groq ou OpenAI).
* No código do roteador (`core/router.py`), é possível parametrizar se deseja habilitar LLM e qual provedor usar (`groq` ou `openai`).

---

## 5. Execução & Uso

### Iniciar o Servidor FastAPI localmente
Inicie o servidor de alta performance usando o Uvicorn:

```bash
PYTHONPATH=. uvicorn agent_hermes.main:app --host 0.0.0.0 --port 8000 --reload
```

### Exemplos de Chamadas de Entrada (Ingress Webhook)

**1. Alerta de Infraestrutura (Direciona para o Apache Agent)**
```bash
curl -X POST "http://localhost:8000/ingress/webhook" \
     -H "Content-Type: application/json" \
     -d '{
       "source": "monitoring_service",
       "message": "URGENTE: O banco de dados de producao atingiu 99% de uso de CPU!",
       "metadata": {"server_id": "srv-prod-db-01"}
     }'
```

**2. Dúvida de RH / Suporte Geral (Direciona para o WeKnora RAG)**
```bash
curl -X POST "http://localhost:8000/ingress/webhook" \
     -H "Content-Type: application/json" \
     -d '{
       "source": "slack_integration",
       "message": "Ola Hermes, como faco para cadastrar meus dependentes no plano de saude?",
       "metadata": {"user": "colaborador_xyz"}
     }'
```

---

## 6. Testes

O projeto vem acompanhado de uma suite de testes unitários e de integração de cobertura completa que valida todos os nós da máquina de estado do LangGraph, limpeza de HTML por BeautifulSoup, envio de mensagens e tratamento de erros com retentativas e fila DLQ.

Execute os testes com o comando abaixo a partir da raiz do repositório:

```bash
PYTHONPATH=. pytest agent_hermes/tests/ -v
```

---

## 7. Segurança

1. **Camada Ingress Desacoplada:** O FastAPI recebe o payload de forma não-bloqueante e despacha para threads de background (`BackgroundTasks`), mitigando vetores de ataque por Denial of Service (DoS) em canais síncronos de comunicação externa.
2. **Sanitização contra Injeções de Código:** O `EmailParser` remove tags de script e folhas de estilo perigosas de e-mails recebidos para evitar ataques de Cross-Site Scripting (XSS) ou HTML injections que possam contaminar a memória dos agentes.
3. **Resiliência e Isolação de Falhas:** Caso um destino caia ou um payload malicioso cause falha persistente de entrega, o sistema não entra em travamento (crash loop). O erro é capturado e enviado para o `DeadLetterQueue` seguro para auditoria.

---

## 8. Troubleshooting

* **Erro de Import no Python (`ModuleNotFoundError`):** Garanta que você está executando comandos com a variável de ambiente `PYTHONPATH=.` configurada para que o interpretador identifique o pacote `agent_hermes`.
* **Chamadas para a API de LLM falhando por Timeout:** O Hermes possui fallback automático para heurísticas locais inteligentes em caso de indisponibilidade de rede ou expiração de token das APIs de IA, garantindo que o tempo de resposta permaneça estável e contínuo.

---

## 🧠 CONCEITO CORPORATIVO: PERSPECTIVA ESTRATÉGICA

### Pergunta:
> *O conceito do Hermes costuma variar dependendo do escopo do projeto corporativo. Você imagina esse agente atuando mais como um classificador inteligente de suporte (roteando dúvidas para equipes) ou como um orquestrador de eventos técnicos de infraestrutura?*

### Resposta:
A beleza arquitetural do **Agente Hermes** reside exatamente no fato de ele não ser exclusivo a nenhum dos dois domínios, mas sim a **ponte de tradução e roteamento inteligente** entre eles.

Em uma infraestrutura empresarial madura, o Hermes atua como um **Orquestrador de Fluxo Unificado de Eventos Corporativos**:
1. **De um lado (Suporte / Negócios):** Ele simplifica a barreira de entrada dos usuários (que enviam e-mails, mensagens no Slack ou formulários desestruturados) limpando os ruídos desses canais de comunicação informal e transformando-os em intenções estruturadas para plataformas de inteligência como RAGs (ex: WeKnora RAG).
2. **De outro lado (Operações / Infraestrutura técnica):** Ele intercepta sinais e telemetria gerados por ferramentas automáticas de monitoramento de infraestrutura (Zabbix, Prometheus, CloudWatch) e de segurança. Ele traduz alertas de telemetria frios e os encaminha para os respectivos agentes reativos ou plataformas (ex: Apache Agent ou equipes de SRE via alertas estruturados).

Portanto, o Hermes não deve ser visto apenas como uma das duas coisas isoladamente, mas sim como a **camada inteligente de roteamento unificada (NLU Router Gateway)** que permite que canais humanos e automações técnicas de computadores coexistam na mesma infraestrutura orientada a eventos.
