FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

USER node

RUN git config --global user.email "claude@container" && \
    git config --global user.name "Claude"

WORKDIR /workspace

ENTRYPOINT ["claude"]
