FROM ubuntu:24.04

ENV PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /e2e
RUN pip install --no-cache-dir "playwright==1.49.1" pytest
RUN playwright install --with-deps chromium

RUN mkdir -p /opt/katex && cd /opt/katex \
    && npm init -y > /dev/null \
    && npm install --no-audit --no-fund katex@0.19.0

# Фаза 2.6: visual regression (Pillow pixel-diff) + axe-core (a11y-аудит).
RUN pip install --no-cache-dir "pillow==12.3.0"
RUN mkdir -p /opt/axe && cd /opt/axe \
    && npm init -y > /dev/null \
    && npm install --no-audit --no-fund "@axe-core/playwright@4.13.0" "axe-core@4.13.0"
