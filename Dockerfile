FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 1000 appuser
COPY requirements.lock.txt ./requirements.lock.txt
RUN pip install -r requirements.lock.txt
COPY --chown=appuser:appuser . .
RUN mkdir -p /app/.cache && chown -R appuser:appuser /app
USER appuser
# Bake public embedding and reranking weights into the image; no API key is used.
RUN python -m scripts.build_index
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.getenv('PORT', '7860') + '/health')" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
