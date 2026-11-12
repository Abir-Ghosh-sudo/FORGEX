
# syntax=docker/dockerfile:1

# Build a portable wheel using FORGEX's pure-Python fallback.
# The native C++20 extension remains available for dedicated native builds.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY . .

# Install Python build dependencies, including Ninja.
RUN python -m pip install --upgrade pip scikit-build-core cmake ninja \
    && mkdir -p /wheels \
    && python -m pip wheel \
        --no-deps \
        --no-build-isolation \
        --config-settings=cmake.define.FORGEX_BUILD_PYTHON=OFF \
        --wheel-dir=/wheels \
        .


# Runtime image
# Run FORGEX as an unprivileged user.
FROM python:3.12-slim AS runtime

ARG FORGEX_UID=1000
ARG FORGEX_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/forgex/.cache/huggingface

# Install runtime dependencies and create an unprivileged user.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${FORGEX_GID}" forgex \
    && useradd \
        --uid "${FORGEX_UID}" \
        --gid forgex \
        --create-home \
        --shell /usr/sbin/nologin \
        forgex

# Install the wheel built in the builder stage.
COPY --from=builder /wheels /wheels

RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels

WORKDIR /workspace

USER forgex

ENTRYPOINT ["forgex"]

CMD ["chat", "--workspace", "/workspace"]
