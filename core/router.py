import os
import json
from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import httpx

# 1. State definition for the LangGraph orchestrator
class MessageState(TypedDict):
    id: str
    source: str          # e.g. "webhook", "email", "slack", "discord"
    payload: Dict[str, Any]
    cleaned_content: str
    intent: Optional[str] # "infrastructure_alert" or "support_query" or "unknown"
    confidence: float
    target_destination: Optional[str] # "apache_agent", "weknora_rag", "unknown_dlq"
    routed_successfully: bool
    error: Optional[str]

# 2. Intent Classifier Class using LLM or robust fallback rules
class IntentClassifier:
    """
    Classifies the intent of incoming messages using NLU or local fallback logic.
    Supports mock modes for offline testing and standard LLMs (Groq, OpenAI, etc.).
    """
    def __init__(self, use_llm: bool = False, api_key: Optional[str] = None, provider: str = "groq"):
        self.use_llm = use_llm
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.provider = provider.lower()

    async def classify(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()

        # Heuristics/Regex local classification (extremely reliable and fast fallback)
        infra_keywords = [
            "infra", "server", "banco de dados", "database", "cpu", "memoria", "memory",
            "alert", "alerta", "down", "off", "error", "falha", "timeout", "port", "disk", "disco"
        ]
        support_keywords = [
            "ajuda", "help", "duvida", "como fazer", "suporte", "rh", "contratacao",
            "ferias", "payment", "pagamento", "salario", "weknora", "rag"
        ]

        # Standard baseline prediction
        predicted_intent = "unknown"
        confidence = 0.5

        # Check heuristics
        infra_score = sum(1 for kw in infra_keywords if kw in text_lower)
        support_score = sum(1 for kw in support_keywords if kw in text_lower)

        if infra_score > support_score and infra_score > 0:
            predicted_intent = "infrastructure_alert"
            confidence = min(0.5 + (0.1 * infra_score), 0.95)
        elif support_score > infra_score and support_score > 0:
            predicted_intent = "support_query"
            confidence = min(0.5 + (0.1 * support_score), 0.95)

        # If LLM classification is requested and API key is present, attempt remote call
        if self.use_llm and self.api_key:
            try:
                system_prompt = (
                    "You are a fast NLU intent classifier. Classify the message into one of: "
                    "['infrastructure_alert', 'support_query']. Reply strictly in JSON format "
                    "with keys 'intent' and 'confidence'."
                )
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                if self.provider == "groq":
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    model = "llama3-8b-8192"
                else:
                    url = "https://api.openai.com/v1/chat/completions"
                    model = "gpt-4o-mini"

                payload = {
                    "model": model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Message: {text}"}
                    ],
                    "temperature": 0.0
                }

                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        if parsed.get("intent") in ["infrastructure_alert", "support_query"]:
                            return {
                                "intent": parsed["intent"],
                                "confidence": float(parsed.get("confidence", 0.9))
                            }
            except Exception as e:
                # Silently fallback to heuristic classification on API failure
                pass

        return {"intent": predicted_intent, "confidence": confidence}

# 3. Graph Nodes definition
async def classify_intent_node(state: MessageState) -> MessageState:
    classifier = IntentClassifier()
    result = await classifier.classify(state["cleaned_content"])
    state["intent"] = result["intent"]
    state["confidence"] = result["confidence"]
    return state

async def router_decision_node(state: MessageState) -> MessageState:
    intent = state.get("intent")
    if intent == "infrastructure_alert":
        state["target_destination"] = "apache_agent"
    elif intent == "support_query":
        state["target_destination"] = "weknora_rag"
    else:
        state["target_destination"] = "unknown_dlq"
    return state

# 4. Constructing the LangGraph Routing Workflow
workflow = StateGraph(MessageState)

# Add nodes to graph
workflow.add_node("classify", classify_intent_node)
workflow.add_node("route", router_decision_node)

# Set entry point
workflow.set_entry_point("classify")

# Add standard progression
workflow.add_edge("classify", "route")
workflow.add_edge("route", END)

# Compile LangGraph app
hermes_routing_agent = workflow.compile()
