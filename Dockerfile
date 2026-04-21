FROM ghcr.io/astral-sh/uv:alpine3.23
ADD . /code
WORKDIR /code
ENV UV_NO_DEV=1
ENV UV_LOCKED=1
RUN uv sync
CMD ["uv", "run", "python", "serve_debug.py"]
