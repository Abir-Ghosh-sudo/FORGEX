# syntax=docker/dockerfile:1

# Build the wheel with the optional C++20 extension when a compiler is available.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . .

RUN python -m pip install --upgrade pip scikit-build-core pybind11 \
    && mkdir -p /wheels \
    && python -m pip wheel --no-deps --no-build-isolation --wheel-dir=/wheels .


# Keep the runtime image small and run FORGEX as an unprivileged user.
FROM python:3.12-slim AS runtime

ARG FORGEX_UID=1000
ARG FORGEX_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/forgex/.cache/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid ${FORGEX_GID} forgex \
    && useradd --uid ${FORGEX_UID} --gid forgex --create-home --shell /usr/sbin/nologin forgex

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels

WORKDIR /workspace
USER forgex

ENTRYPOINT ["forgex"]
CMD ["chat", "--workspace", "/workspace"]
