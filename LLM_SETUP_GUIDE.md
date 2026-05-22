# Async Research LLM Setup Guide

This file is a copy-paste guide you can give to another LLM so it can help you
set up and operate `async-research` without assuming you are deeply technical.

The important idea: use the public `async-research` GitHub repository for the
tool code, but keep real research work in a private folder or private repo.

## Copy-Paste Prompt For The LLM

Use this prompt with Codex, ChatGPT, Claude, or another coding assistant:

```text
You are helping me set up and use async-research.

My technical level: beginner/nontechnical. Explain each step in plain English
before running commands. Prefer safe, reversible actions.

Goal:
Set up an async-research workspace in a private project folder, verify it works,
open or prepare the operator dashboard, and guide me through the first research
workflow steps.

Important safety rules:
- Do not put my real research_ops folder inside a public GitHub repository unless
  I explicitly confirm that the contents are safe to publish.
- Do not use --force unless I explicitly ask you to replace an existing folder.
- Run dry-run or read-only checks first when the command supports it.
- Do not delete, reset, or overwrite files without asking me first.
- If a command fails, explain the failure in plain English and suggest the next
  safest fix.

Known project/tool location:
The folder where I cloned the async-research GitHub repository:
https://github.com/dzianissokalau/async-research

Preferred private workspace location:
A separate private research project folder or private GitHub repository outside
the public async-research repo.

Please do the following:

1. Check whether async-research is available.
   - If we are inside the cloned async-research GitHub repo folder, activate
     `.venv` if it exists.
   - Run: async-research version
   - If the command is not available, help me install it from the cloned GitHub
     repo folder or directly from GitHub.

2. Create or use a private research project folder.
   - Preferred location:
     a separate private research project folder or private GitHub repository.
   - Explain whether this folder is private or part of a public GitHub repo.
   - If it is public, stop and ask me before continuing.

3. Initialize the async-research workspace.
   - In the private project folder, run:
     async-research init research_ops
   - Do not use --force unless I confirm.

4. Run the first checks.
   - Run:
     async-research mode show research_ops
     async-research mode validate research_ops
     async-research workflow check research_ops
     async-research surface update research_ops
     async-research surface validate research_ops
   - Explain the interaction mode and check results in plain English.
   - Before mutating workflow state, read the mode. New starter workspaces
     normally report `supervised`; older workspaces without
     `interaction_mode.json` use manual-compatible behavior until I explicitly
     choose a mode.

5. Show me the dashboard option.
   - If appropriate, run:
     async-research console research_ops
   - Tell me to open the dashboard URL printed by the command.

6. Help me create my first research idea.
   - Ask me for one small research question.
   - Add it to research_ops/discovery_inbox.md only after confirming the wording
     with me.
   - Keep it small enough to become one bounded task.

7. Guide the framework loop.
   - Explain the current stage:
     idea -> task -> worker output -> review -> accepted/rejected/revision/human decision
   - Use:
     async-research workflow next research_ops
     async-research queue list research_ops
   - Do not invent completed findings. All accepted findings must go through
     review.

At the end, give me a short daily routine with only the commands I actually need.
```

## What You Are Setting Up

`async-research` creates a file-backed research control folder called
`research_ops/`.

That folder stores things like:

- research ideas
- task queue
- worker outputs
- review notes
- human decisions
- accepted findings
- rejected findings
- cost and health checks

It is meant to make research durable and reviewable, instead of leaving all
important context trapped in chat history.

## Where To Put It

Recommended:

```text
async-research/
  The cloned public GitHub repo for the tool code.

private-research-project/
  Your separate private research project folder or private GitHub repo.

private-research-project/research_ops/
  Your actual async-research workspace.
```

Avoid this for real research:

```text
async-research/research_ops/
```

That puts your real research workspace inside the public tool repo folder, which
may later be pushed to GitHub.

## Beginner Setup Steps

### 1. Go To The GitHub Repo Folder

Open a terminal in the folder where the async-research GitHub repository was
cloned.

### 2. Activate The Existing Environment

```bash
. .venv/bin/activate
```

### 3. Confirm The Tool Works

```bash
async-research version
```

Expected result: JSON showing an `ok` value and a version such as `0.2.0a5`.

### 4. Create Or Open A Private Research Project Folder

Create or open a separate private project folder or private GitHub repository
for the actual research work.

### 5. Initialize The Workspace

```bash
async-research init research_ops
```

This creates:

```text
research_ops/
```

### 6. Run Safety Checks

```bash
async-research mode show research_ops
async-research mode validate research_ops
async-research workflow check research_ops
async-research surface update research_ops
async-research surface validate research_ops
```

If anything fails, stop and fix that before starting research work.

The `mode show` command tells the LLM operator how much authority the framework
has before it mutates task state. New starter workspaces should show
`supervised`, which lets the framework handle routine revisions and source
substitutions while still stopping for credentials, destructive actions, private
data, hard budget breaches, legal/policy-sensitive claims, and publication or
external-claim approval. Existing workspaces without `interaction_mode.json`
stay manual-compatible until you explicitly choose a mode with:

```bash
async-research mode set research_ops --mode supervised
```

### 7. Open The Dashboard

```bash
async-research console research_ops
```

Then open:

```text
the dashboard URL printed by the command
```

## The Framework In Plain English

The async-research loop is:

```text
Idea
  -> Task
  -> Worker output
  -> Review
  -> Accepted, rejected, revision, or human decision
```

### Stage 1: Idea

You start with a small research question.

Good example:

```text
Compare whether rental yield is more sensitive to school quality or transport
access in one London borough.
```

Too broad:

```text
Research the whole UK property market.
```

Put ideas in:

```text
research_ops/discovery_inbox.md
```

### Stage 2: Task

An idea becomes a bounded task. A task should have a clear output.

Example:

```text
Produce a short evidence memo comparing two drivers of rental yield in one
defined area, using named sources and listing uncertainty.
```

Tasks live in:

```text
research_ops/tasks/
```

### Stage 3: Worker Output

A worker, which can be you or an LLM, completes one task and writes the result.

The result should go into the task folder as:

```text
worker_output.md
```

### Stage 4: Review

A reviewer checks the worker output. The reviewer can accept it, reject it, ask
for revision, or send it to you for a human decision.

For a first run, the safest review route is usually `needs_human`, because it
proves the workflow without treating the result as accepted evidence too soon.

### Stage 5: Accepted Memory

Only reviewed and accepted results become reusable research memory.

Accepted outputs are tracked in:

```text
research_ops/accepted_outputs_index.md
research_ops/evidence_ledger.md
```

Rejected results are also valuable because they stop the system from repeating
bad ideas.

Rejected results are tracked in:

```text
research_ops/rejected_results.md
```

## Commands You Actually Need Most Days

Ask what to do next:

```bash
async-research workflow next research_ops
```

See the task board:

```bash
async-research queue list research_ops
```

Refresh human-readable status:

```bash
async-research surface update research_ops
async-research surface validate research_ops
```

Open the dashboard:

```bash
async-research console research_ops
```

Run a broader health check:

```bash
async-research workflow check research_ops
```

## First Conversation To Have With The LLM After Setup

Once `research_ops/` exists, paste this:

```text
I have initialized async-research in my private project folder.

Please help me start the first research loop.

1. Inspect research_ops/discovery_inbox.md, queue.md, daily_status.md, and
   human_review_queue.md.
2. Ask me for one small research idea.
3. Help me word it clearly.
4. Add it to discovery_inbox.md only after I approve the wording.
5. Tell me the next safe async-research command to run.

Keep the explanation beginner-friendly and do not skip review gates.
```

## Simple Rules To Remember

- Public repo for tool code is fine.
- Private repo or private folder for real research is safer.
- One small research question at a time.
- Do not treat LLM output as accepted evidence until it has been reviewed.
- Use `workflow next` whenever you feel unsure.
- Use the dashboard when command output feels too technical.
