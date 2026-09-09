# Running Claude Code in a Sandbox

This guide explains how to run Claude Code with `--dangerously-skip-permissions` safely using DevContainers.

## Why Use a Sandbox?

The `--dangerously-skip-permissions` flag enables autonomous operation without permission prompts. This is useful
for long-running tasks, but running it directly on your host machine risks:

- Accidental file deletions outside the project
- Modifications to system configs
- Access to SSH keys, cloud credentials, etc.

The solution: run Claude inside an isolated DevContainer that only has access to what it needs.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
- [VS Code](https://code.visualstudio.com/) with
  the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- SSH agent running with your key loaded (for git operations)

### Setting Up SSH Agent

Before opening the DevContainer, ensure your SSH agent is running:

```bash
# Start agent (if not already running)
eval $(ssh-agent)

# Add your key
ssh-add ~/.ssh/id_ed25519  # or your key path

# Verify
ssh-add -l
```

On macOS, you can add to your `~/.ssh/config`:

```
Host *
  AddKeysToAgent yes
  UseKeychain yes
```

## Quick Start

1. Open the project in VS Code
2. Press `F1` → "Dev Containers: Reopen in Container"
3. Wait for the container to build (first time takes a few minutes)
4. Run Claude:

```bash
claude --dangerously-skip-permissions
```

## What's Accessible Inside the Container

| Resource | Access | Notes |
|----------|--------|-------|
| `~/.claude` | read-write | Claude Max credentials and logs |
| `~/.config/gh` | read-only | GitHub CLI authentication |
| `~/.gitconfig` | read-only | Git configuration |
| Docker socket | read-write | Run tests via docker-compose |
| SSH agent | forwarded | Keys stay on host, only socket shared |
| Project folder | read-write | Mounted at `/workspace` |

## What's Protected (Not Accessible)

- `~/.ssh` - Private keys (SSH agent forwarding is used instead)
- `~/.gnupg` - GPG keys
- `~/.aws` - AWS credentials
- `~/.kube` - Kubernetes configs
- Other projects on your machine
- System files (`/etc`, `/usr`, etc.)

## Running Tests

Tests work normally inside the container via the Docker socket:

```bash
./scripts/test_single_module.sh trn_vocabulary
```

The test script is designed for parallel execution:

- **Unique database names**: Each test run creates `test_<module>_<random>` database
- **Unique Docker project**: `COMPOSE_PROJECT_NAME` is based on directory path hash
- **No port binding**: Tests run with `--no-http`

## Parallel Sessions with Git Worktrees

Run multiple Claude agents on different tasks simultaneously:

```bash
# Create isolated worktrees (from main repo)
git worktree add ../project-task-1 -b claude/feature-auth
git worktree add ../project-task-2 -b claude/fix-validation

# Open each in VS Code
cd ../project-task-1 && code .
cd ../project-task-2 && code .

# In each VS Code window: F1 → "Reopen in Container"
# Then run Claude in each container independently
```

Each container gets:

- Separate filesystem
- Separate Docker project (no container/network conflicts)
- Separate git branch
- Independent Claude session

### Cleanup Worktrees

```bash
# When done with a task
git worktree remove ../project-task-1
git branch -d claude/feature-auth  # after merging
```

## Without VS Code

### Using DevContainer CLI

```bash
# Install CLI
npm install -g @devcontainers/cli

# Start container
devcontainer up --workspace-folder .

# Run Claude inside
devcontainer exec --workspace-folder . claude --dangerously-skip-permissions

# Or get a shell
devcontainer exec --workspace-folder . bash
```

### Using Docker Directly

```bash
# Build the image
docker build -t project-sandbox -f .devcontainer/Dockerfile .devcontainer/

# Run with necessary mounts
docker run -it --rm \
  -v $(pwd):/workspace \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v ~/.claude:/home/node/.claude \
  -v ~/.gitconfig:/home/node/.gitconfig:ro \
  -v ~/.config/gh:/home/node/.config/gh:ro \
  -v $SSH_AUTH_SOCK:/ssh-agent \
  -e SSH_AUTH_SOCK=/ssh-agent \
  -w /workspace \
  project-sandbox \
  claude --dangerously-skip-permissions
```

## Troubleshooting

### SSH not working

Check that your SSH agent is running and has keys:

```bash
# On host machine
ssh-add -l
```

If empty, add your key: `ssh-add ~/.ssh/id_ed25519`

### Docker commands fail

Ensure the Docker socket is accessible:

```bash
# Inside container
ls -la /var/run/docker.sock
docker ps
```

### Claude not authenticated

The `~/.claude` directory is mounted from your host. If you haven't authenticated Claude on your
host machine yet, run `claude` on the host first to complete authentication.

### Container build fails

Try rebuilding without cache:

```bash
# VS Code: F1 → "Dev Containers: Rebuild Container Without Cache"

# Or with CLI
devcontainer build --workspace-folder . --no-cache
```

## Security Considerations

This setup prioritizes convenience for open-source development while providing reasonable isolation:

**Trade-offs made:**

- Docker socket is accessible (needed for tests)
- Claude credentials are mounted read-write (needed for logs)
- SSH agent is forwarded (keys stay on host, but agent is usable)

**For stricter isolation**, consider:

- Network firewall (see [Anthropic's reference devcontainer](https://github.com/anthropics/claude-code/.devcontainer))
- VM-based isolation (Vagrant, etc.)
- Cloud dev environments (GitHub Codespaces, Gitpod)

## Related Resources

- [Anthropic Claude Code DevContainer Reference](https://github.com/anthropics/claude-code/.devcontainer)
- [VS Code DevContainers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [DevContainer CLI](https://github.com/devcontainers/cli)
