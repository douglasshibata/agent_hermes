import re
from typing import Dict, Any
from bs4 import BeautifulSoup

class EmailParser:
    """
    Módulo para receber e-mails transacionais, limpar o HTML usando BeautifulSoup,
    e extrair o texto principal para análise semântica.
    """
    @staticmethod
    def parse_and_clean(html_content: str) -> str:
        if not html_content:
            return ""

        # Use BeautifulSoup to parse HTML and strip tags
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        text = soup.get_text()

        # Break into lines and remove leading/trailing whitespace
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        clean_text = "\n".join(chunk for chunk in chunks if chunk)

        # Normalize continuous spaces and multiple newlines
        clean_text = re.sub(r'\n+', '\n', clean_text)
        clean_text = re.sub(r' +', ' ', clean_text)

        return clean_text.strip()

    @staticmethod
    def extract_metadata_and_body(email_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses an incoming raw transactional email payload,
        cleans up any HTML inside, and returns clean structured fields.
        """
        sender = email_payload.get("from", "unknown@sender.com")
        subject = email_payload.get("subject", "")
        html_body = email_payload.get("html", "")
        text_body = email_payload.get("text", "")

        # If html is present, clean it, else use plain text body
        if html_body:
            cleaned_text = EmailParser.parse_and_clean(html_body)
        else:
            cleaned_text = text_body.strip()

        return {
            "from": sender,
            "subject": subject,
            "cleaned_body": f"Subject: {subject}\n\n{cleaned_text}"
        }
