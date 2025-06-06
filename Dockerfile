FROM python:3.10-slim
WORKDIR /opt/ai-ticket
COPY pyproject.toml /opt/ai-ticket/
COPY setup.cfg /opt/ai-ticket/
COPY setup.py /opt/ai-ticket/
COPY requirements.txt /opt/ai-ticket/
COPY ./src/ /opt/ai-ticket/src/
RUN pip install .
