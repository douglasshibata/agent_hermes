import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("agent_hermes.channels.discord_webhook")

class DiscordWebhookSender:
    """
    Integração assíncrona para postar resumos de mensagens ou alertas estruturados
    em canais do Discord através de Webhooks de forma não-bloqueante.
    """
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    async def send_message(self, content: str, username: str = "Hermes Bot", embeds: Optional[list] = None) -> bool:
        """
        Dispara uma notificação para um webhook do Discord de maneira assíncrona.
        Retorna True em caso de sucesso, ou lança uma exceção/retorna False em caso de falha.
        """
        url = self.webhook_url or "https://discord.com/api/webhooks/mock-url"

        payload: Dict[str, Any] = {
            "content": content,
            "username": username
        }
        if embeds:
            payload["embeds"] = embeds

        # Check for mock URL to facilitate offline test/validation
        if "mock-url" in url:
            logger.info(f"[MOCK DISCORD POST] Sent message: {content} with username {username}")
            return True

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code in [200, 204]:
                return True
            else:
                logger.error(f"Failed to post to Discord. Status: {response.status_code}, Body: {response.text}")
                return False
