FROM python:3.10-slim
WORKDIR /opt/ai-ticket
COPY requirements.txt /opt/ai-ticket/
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml setup.cfg setup.py /opt/ai-ticket/
COPY ./src/ /opt/ai-ticket/src/
RUN pip install .
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD curl -f http://localhost:5000/health || exit 1
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "src.ai_ticket.server:app"]