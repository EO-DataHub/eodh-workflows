FROM ubuntu:22.04

# Setup environment to match variables set by repo2docker as much as possible
# Tell apt-get to not block installs by asking for interactive human input
ENV DEBIAN_FRONTEND=noninteractive \
    # Use /bin/bash as shell, not the default /bin/sh (arrow keys, etc don't work then)
    SHELL=/bin/bash \
    # Setup locale to be UTF-8, avoiding gnarly hard to debug encoding errors
    LANG=C.UTF-8  \
    LC_ALL=C.UTF-8

# Home directory with our code
ENV HOME=/app

# Install basic apt packages
RUN echo "Installing Apt-get packages..." \
    && apt-get update --fix-missing > /dev/null \
    && apt-get install -y build-essential apt-utils wget gdal-bin libgdal-dev python3-gdal zip tzdata > /dev/null \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add TZ configuration - https://github.com/PrefectHQ/prefect/issues/3061
ENV TZ=UTC

# Get uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create home and give permissions to all
RUN mkdir -p ${HOME}

# Set working directory
WORKDIR ${HOME}

# Copy repo
COPY pyproject.toml ${HOME}
COPY uv.lock ${HOME}
COPY src ${HOME}

# Sync dependencies from lock-file
RUN uv sync --frozen --no-cache
