FROM ghcr.io/astral-sh/uv:alpine3.23
ADD . /code
WORKDIR /code
RUN uv sync --locked --no-dev
CMD ["uv", "run", "python", "serve_debug.py"]
