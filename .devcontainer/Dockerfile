# Odoo 19 DevContainer for safe Claude Code usage
# Provides filesystem isolation while allowing full Docker and network access
#
# What's protected:
# - Your home directory (~/.ssh, ~/.gnupg, etc.)
# - Other projects on your machine
# - System files
#
# What's allowed:
# - Full network access (no firewall)
# - Docker operations via socket (for running tests)
# - Project files in /workspace

FROM node:20

# Keep latest to always get newest Claude Code features
# Pin to specific version if reproducibility is needed: e.g., 1.0.0
ARG CLAUDE_CODE_VERSION=latest

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    ripgrep \
    fzf \
    zsh \
    nano \
    vim \
    sudo \
    ca-certificates \
    gnupg \
    # PostgreSQL client (for debugging)
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Docker CLI with compose plugin from official Docker repo
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Allow node user to run sudo chmod without password (for postStartCommand)
RUN echo "node ALL=(root) NOPASSWD: /usr/bin/chmod" > /etc/sudoers.d/docker-socket && \
    chmod 0440 /etc/sudoers.d/docker-socket

# Ensure node user has access to npm global directory only
RUN mkdir -p /usr/local/share/npm-global && \
    chown -R node:node /usr/local/share/npm-global

# Create workspace directory
RUN mkdir -p /workspace /home/node/.claude && \
    chown -R node:node /workspace /home/node/.claude

WORKDIR /workspace

# Set up non-root user
USER node

ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin
ENV SHELL=/bin/zsh
ENV DEVCONTAINER=true

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Install oh-my-zsh (download first, then execute for security)
RUN curl -fsSL -o /tmp/install-ohmyzsh.sh https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh && \
    sh /tmp/install-ohmyzsh.sh --unattended && \
    rm /tmp/install-ohmyzsh.sh
