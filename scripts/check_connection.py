"""Check credentials without printing secrets or raw provider errors."""
import sys

from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import get_settings

settings = get_settings()
if not settings.google_api_key.get_secret_value():
    print('GOOGLE_API_KEY is missing. Add it to .env.')
    sys.exit(1)
try:
    model = ChatGoogleGenerativeAI(model=settings.gemini_model,
                                  google_api_key=settings.google_api_key.get_secret_value(),
                                  timeout=30, max_retries=0, thinking_budget=0)
    reply = model.invoke('Reply with the word READY only.')
    print('Gemini connection successful:', settings.gemini_model, bool(reply.content))
except Exception as exc:
    print('Gemini connection failed:', type(exc).__name__)
    # Sanitized status helps distinguish quota and invalid keys without leaking request URLs.
    status = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    print('Status:', status if isinstance(status, (int, str)) else 'unavailable')
    sys.exit(1)
