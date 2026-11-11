import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from .core.router import hermes_routing_agent, MessageState
from .core.reliability import dlq_instance, ExponentialRetryPolicy
from .channels.email_parser import EmailParser
from .channels.discord_webhook import DiscordWebhookSender

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_hermes")

app = FastAPI(
    title="Agent Hermes",
    description="Hermes Communication & Intelligent Routing Agent - Event-Driven and Resilient",
    version="1.0.0"
)

# Pydantic Schemas
class WebhookPayload(BaseModel):
    source: str
    message: str
    metadata: Optional[Dict[str, Any]] = None

class EmailPayload(BaseModel):
    from_address: str
    subject: str
    html_body: Optional[str] = None
    text_body: Optional[str] = None


# Destination Simulator/Mocks
# In a full ecosystem, these would trigger network calls to other microservices.
# We wrap them in dynamic exponential retries for robustness!
@ExponentialRetryPolicy.get_retry_decorator(max_attempts=3)
async def dispatch_to_destination(destination: str, state_id: str, content: str):
    logger.info(f"Dispatching state {state_id} to destination {destination}...")

    # Simulate potential temporary network/API failures
    if "simulate-failure" in content:
        raise ConnectionError("Simulated network drop to destination!")

    # Trigger Discord webhook post as an egress notification channel
    discord_sender = DiscordWebhookSender()
    discord_summary = f"**[Hermes Dispatcher]** Routed message to **{destination}**\nContent snippet: *{content[:100]}*"
    await discord_sender.send_message(content=discord_summary, username="Hermes Routing System")

    return True


async def process_orchestrated_message(state: MessageState):
    """
    Background Task: Runs the compiled LangGraph routing agent on the MessageState,
    decides target, and attempts delivery with retries. If failures persist, pushes to DLQ.
    """
    try:
        # Run through LangGraph compiler
        output_state = await hermes_routing_agent.ainvoke(state)

        target = output_state.get("target_destination")
        cleaned_content = output_state.get("cleaned_content", "")

        if target in ["apache_agent", "weknora_rag"]:
            # Attempt resilient dispatch with retries
            try:
                await dispatch_to_destination(target, output_state["id"], cleaned_content)
                output_state["routed_successfully"] = True
            except Exception as e:
                logger.error(f"Failed to deliver message {output_state['id']} after maximum retries. Routing to DLQ.")
                output_state["routed_successfully"] = False
                output_state["error"] = str(e)
                dlq_instance.push(output_state, reason=f"Delivery failure: {str(e)}")
        else:
            # Undefined intent/unknown route -> Route to DLQ directly
            output_state["routed_successfully"] = False
            output_state["error"] = "Unknown destination route"
            dlq_instance.push(output_state, reason="Unclassified/Unknown Intent destination")

    except Exception as e:
        logger.error(f"Critical error during LangGraph state workflow: {e}")
        state["routed_successfully"] = False
        state["error"] = f"Workflow Exception: {str(e)}"
        dlq_instance.push(state, reason=f"Workflow crash: {str(e)}")


# 1. Webhook Ingress Endpoint
@app.post("/ingress/webhook", status_code=202)
async def webhook_ingress(payload: WebhookPayload, background_tasks: BackgroundTasks):
    message_id = str(uuid.uuid4())

    state: MessageState = {
        "id": message_id,
        "source": payload.source,
        "payload": payload.metadata or {},
        "cleaned_content": payload.message,
        "intent": None,
        "confidence": 0.0,
        "target_destination": None,
        "routed_successfully": False,
        "error": None
    }

    background_tasks.add_task(process_orchestrated_message, state)
    return {"status": "accepted", "message_id": message_id}


# 2. Transactional Email Ingress Endpoint
@app.post("/ingress/email", status_code=202)
async def email_ingress(payload: EmailPayload, background_tasks: BackgroundTasks):
    message_id = str(uuid.uuid4())

    # Use the BeautifulSoup EmailParser to parse & clean html
    email_dict = {
        "from": payload.from_address,
        "subject": payload.subject,
        "html": payload.html_body,
        "text": payload.text_body or ""
    }
    parsed = EmailParser.extract_metadata_and_body(email_dict)

    state: MessageState = {
        "id": message_id,
        "source": "email",
        "payload": {"from": payload.from_address, "subject": payload.subject},
        "cleaned_content": parsed["cleaned_body"],
        "intent": None,
        "confidence": 0.0,
        "target_destination": None,
        "routed_successfully": False,
        "error": None
    }

    background_tasks.add_task(process_orchestrated_message, state)
    return {"status": "accepted", "message_id": message_id}


# 3. DLQ Admin/Monitoring Endpoint
@app.get("/admin/dlq")
async def get_dlq():
    return {
        "dlq_size": len(dlq_instance.get_all()),
        "records": dlq_instance.get_all()
    }
