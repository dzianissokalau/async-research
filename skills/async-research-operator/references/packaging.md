# Packaging And Codex Dogfood Rollout

Use this reference when the human asks how to install, update, remove, validate,
or dogfood the `async-research-operator` skill. The repo source package remains
the deliverable. Do not auto-install into a user-global Codex skills directory
unless the human explicitly asks.

## Install Or Reference

Preferred no-write option: reference the repo source package directly from the
current checkout and run the validator before use.

```bash
.venv/bin/python skills/async-research-operator/scripts/validate_skill_pack.py
```

Install only after explicit approval because it writes outside the workspace:

```bash
test -n "$CODEX_HOME"
mkdir -p "$CODEX_HOME/skills"
rm -rf "$CODEX_HOME/skills/async-research-operator"
cp -R skills/async-research-operator "$CODEX_HOME/skills/async-research-operator"
```

After installation, restart or reload Codex if needed so skill discovery sees
the copied package. Then validate the installed copy when the environment allows
it:

```bash
python "$CODEX_HOME/skills/async-research-operator/scripts/validate_skill_pack.py"
```

Do not install from a package manager, fetch code, modify shell configuration,
or write outside `$CODEX_HOME/skills/async-research-operator/` unless the human
explicitly approves that broader setup. If `CODEX_HOME` is empty or unknown,
stop and ask the human for the intended Codex home path before running install,
update, or uninstall commands.

## First-Use Prompt

Use this prompt in a new Codex session:

```text
Use the async-research-operator skill. Inspect this workspace, report the current state, and recommend the next safe action without writing files.
```

The expected first response is a read-only state report with framework version,
workspace path, privacy status, health/readiness/workflow summary where
available, commands used, files touched, caveats, unresolved gaps, and the next
safe action. If the CLI or `research_ops/` is missing, the response should ask
before setup or initialization.

## Dogfood Checklist

Record command output, files touched, and the final next safe action for each
item. A rollout passes only when both action behavior and stop behavior are
observed.

- missing CLI setup diagnosis
- approved project-local install or explicit skip decision
- missing `research_ops/` bootstrap diagnosis
- fresh workspace status
- existing coffee-style workspace status
- one bounded worker loop
- one review loop
- one human gate stop
- one deliverable maturity report
- one acceptance/readiness mismatch stop
- one command-capability or version-drift report

For every write-capable item, run the documented dry-run first where supported
and stop before the write unless the human approved the bounded action.

## Dogfood Evidence Rules

At least one rollout record must be kept before calling the skill ready for
Codex use. Acceptable evidence is a fresh-session transcript or a delivery log
entry that records:

- Codex context and whether the skill was installed or referenced from source
- workspace path and privacy-boundary result
- commands used
- files touched
- checklist items exercised
- stop conditions observed
- validation commands and results
- limitations, including any missing fresh-session or real-workspace coverage

Current repository evidence is stored at
`tests/fixtures/skill_operator/transcripts/codex_dogfood_rollout_2026-05-20.md`.

## Update And Uninstall

To update an installed copy after explicit approval, remove the old installed
directory, copy the repo source package again, restart or reload Codex if
needed, and rerun the validator. Preserve local notes outside the installed
skill directory; the installed skill directory should be treated as replaceable
generated output from the repo source package.

To uninstall after explicit approval:

```bash
test -n "$CODEX_HOME"
rm -rf "$CODEX_HOME/skills/async-research-operator"
```

Restart or reload Codex if needed. Do not remove the repository source package
unless the human explicitly asks to delete roadmap deliverables.
