ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY . /app

WORKDIR /app

ARG UID=10001
RUN adduser --disabled-password -gecos "" --home "/nonexistent" --shell "/sbin/nologin" --no-create-home --uid "${UID}" appuser

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

USER appuser

CMD ["python", "main.py"]