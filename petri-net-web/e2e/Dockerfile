FROM ubuntu:24.04

ENV PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /e2e
RUN pip install --no-cache-dir "playwright==1.49.1" pytest
RUN playwright install --with-deps chromium
