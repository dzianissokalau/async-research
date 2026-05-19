# Provider Notes

The v0.1 target is Codex with repository file access and terminal access.

## Codex

Codex can inspect files, run public CLI commands, and report concrete validation
results. The repo source package is the deliverable. Do not auto-install this
skill into `$CODEX_HOME/skills` unless the human explicitly asks.

## Web-Only Chat Clients

Web-only clients may review copied artifacts or advise from pasted command
output, but they are not operator targets because they cannot verify local repo
state or run the framework commands.

## Future Ports

Claude Code, API-agent workflows, and remote command gateways are deferred until
after Codex dogfood. Remote/API write gateways require a separate safety design.
