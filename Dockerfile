FROM python:3.10-slim

WORKDIR /opt/ai-ticket

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml setup.cfg setup.py ./
COPY ./src/ ./src/

WORKDIR /opt/ai-ticket/src/ai_ticket/ui
RUN npm install \
    && npm run build \
    && npm cache clean --force \
    && rm -rf node_modules

WORKDIR /opt/ai-ticket
RUN pip install .

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD curl -f http://localhost:5000/health || exit 1
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "src.ai_ticket.server:app"]