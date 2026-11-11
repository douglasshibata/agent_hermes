import pytest
from unittest import mock
import httpx

from agent_hermes.core.router import IntentClassifier, hermes_routing_agent, MessageState
from agent_hermes.channels.email_parser import EmailParser
from agent_hermes.channels.discord_webhook import DiscordWebhookSender
from agent_hermes.core.reliability import DeadLetterQueue, ExponentialRetryPolicy, dlq_instance
from agent_hermes.main import dispatch_to_destination, process_orchestrated_message

@pytest.mark.asyncio
async def test_intent_classifier():
    classifier = IntentClassifier(use_llm=False)

    # 1. Test infra alert
    res_infra = await classifier.classify("O servidor de banco de dados CPU atingiu 98% de uso!")
    assert res_infra["intent"] == "infrastructure_alert"
    assert res_infra["confidence"] > 0.5

    # 2. Test support query
    res_support = await classifier.classify("Preciso de ajuda com o RH para solicitar minhas ferias acumuladas.")
    assert res_support["intent"] == "support_query"
    assert res_support["confidence"] > 0.5

    # 3. Test unknown
    res_unknown = await classifier.classify("Oi tudo bem?")
    assert res_unknown["intent"] == "unknown"


@pytest.mark.asyncio
async def test_langgraph_routing_agent():
    state: MessageState = {
        "id": "123",
        "source": "slack",
        "payload": {},
        "cleaned_content": "Alerta de infraestrutura: O disco do servidor está cheio!",
        "intent": None,
        "confidence": 0.0,
        "target_destination": None,
        "routed_successfully": False,
        "error": None
    }

    result = await hermes_routing_agent.ainvoke(state)
    assert result["intent"] == "infrastructure_alert"
    assert result["target_destination"] == "apache_agent"


def test_email_parser_html_cleanup():
    html = """
    <html>
        <head><style>body { color: #333; }</style></head>
        <body>
            <h1>Novo alerta de infraestrutura</h1>
            <p>O <strong>servidor de producao</strong> caiu.</p>
            <script>console.log("ignore me");</script>
        </body>
    </html>
    """
    cleaned = EmailParser.parse_and_clean(html)
    assert "ignore me" not in cleaned
    assert "Novo alerta de infraestrutura" in cleaned
    assert "servidor de producao" in cleaned


@pytest.mark.asyncio
async def test_discord_webhook_sender():
    sender = DiscordWebhookSender(webhook_url="https://discord.com/api/webhooks/mock-url")
    success = await sender.send_message(content="Test notification", username="Test Herm")
    assert success is True


@pytest.mark.asyncio
async def test_exponential_retry_policy_failures():
    # Count how many times the function was called
    call_count = 0

    @ExponentialRetryPolicy.get_retry_decorator(max_attempts=3, min_wait=0.01, max_wait=0.05)
    async def transient_error_func():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Transient network failure")

    with pytest.raises(ConnectionError):
        await transient_error_func()

    assert call_count == 3


@pytest.mark.asyncio
async def test_dlq_push_and_clear():
    dlq = DeadLetterQueue()
    assert len(dlq.get_all()) == 0

    dlq.push({"id": "err_1", "text": "failed"}, reason="Network Timeout")
    assert len(dlq.get_all()) == 1
    assert dlq.get_all()[0]["reason"] == "Network Timeout"

    dlq.clear()
    assert len(dlq.get_all()) == 0


@pytest.mark.asyncio
async def test_background_process_orchestrated_message_failures():
    dlq_instance.clear()

    state: MessageState = {
        "id": "err-state-id",
        "source": "webhook",
        "payload": {},
        "cleaned_content": "simulate-failure: Alerta de infraestrutura grave!",
        "intent": None,
        "confidence": 0.0,
        "target_destination": None,
        "routed_successfully": False,
        "error": None
    }

    await process_orchestrated_message(state)

    # Since it contains "simulate-failure", dispatch_to_destination raises ConnectionError.
    # It will be retried 3 times, fail, and then pushed to DLQ.
    records = dlq_instance.get_all()
    assert len(records) >= 1
    assert "Delivery failure" in records[0]["reason"]
