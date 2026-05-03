# Sources

Checked: 2026-05-01

## OpenAI And ChatGPT

- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540)
  - Used for Codex availability across ChatGPT plans, data controls, and Codex usage-limit framing.
- [Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)
  - Used for the April 2026 token-based Codex pricing/rate-card change.
- [About ChatGPT Pro tiers](https://help.openai.com/en/articles/9793128-about-chatgpt-pro-plans)
  - Used for Plus, Pro $100, and Pro $200 positioning and relative Codex allowance.
- [ChatGPT agent](https://help.openai.com/en/articles/11752874-chatgpt-codex)
  - Used for agent task duration, scheduled agent tasks, usage limits, and safety/privacy cautions.
- [ChatGPT Capabilities Overview](https://help.openai.com/en/articles/9260256-chatgpt-capabilities-overview)
  - Used for scheduled tasks, projects, deep research, and tool capability framing.
- [OpenAI API pricing](https://platform.openai.com/docs/pricing)
  - Used for API model, web search, code interpreter, embeddings, and tool cost anchors.
- [OpenAI Batch API](https://platform.openai.com/docs/guides/batch)
  - Used for asynchronous batch processing, 50 percent lower cost, 24-hour turnaround, and batch use cases.
- [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
  - Used for prompt caching requirements and prompt-structuring cost controls.
- [OpenAI Codex GitHub repository](https://github.com/openai/codex)
  - Used for Codex CLI installation, local/CLI framing, and GitHub-hosted source.

## Local Codex CLI Check

Commands run locally:

```text
command -v codex
codex --help
codex exec --help
```

Relevant local findings:

- Codex CLI is available at `/Applications/Codex.app/Contents/Resources/codex`.
- `codex exec` supports non-interactive operation.
- Relevant flags include `--cd`, `--sandbox`, `--ask-for-approval`, `--json`, `--output-last-message`, `--output-schema`, `--oss`, and `--local-provider`.

## GitHub Actions

- [Workflow syntax for GitHub Actions](https://docs.github.com/actions/learn-github-actions/workflow-syntax-for-github-actions)
  - Used for workflow structure, permissions, jobs, and concurrency.
- [Events that trigger workflows](https://docs.github.com/actions/reference/events-that-trigger-workflows)
  - Used for scheduled workflow behavior, cron, default-branch behavior, and inactivity note.
- [Control concurrency of workflows and jobs](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs)
  - Used for avoiding overlapping worker runs.

## Anthropic Comparison

- [Claude Code GitHub Actions](https://docs.anthropic.com/en/docs/claude-code/github-actions)
  - Used for comparison with GitHub-native coding-agent automation.
- [Claude Code routines](https://code.claude.com/docs/en/web-scheduled-tasks)
  - Used for comparison with scheduled/API/GitHub-triggered cloud routines. Note: source says routines are in research preview.
- [Anthropic Message Batches API](https://docs.anthropic.com/en/api/creating-message-batches)
  - Used for comparison with batch-style asynchronous processing.

## Scientific Discovery And Idea Generation

- [The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery](https://arxiv.org/abs/2408.06292)
  - Used for end-to-end idea generation, code, experiment execution, paper writing, and simulated review loop.
- [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)
  - Used for generate/debate/evolve hypothesis generation, asynchronous task execution, tournament evolution, and scientist-in-the-loop framing.
- [Robin: A multi-agent system for automating scientific discovery](https://arxiv.org/abs/2505.13400)
  - Used for iterative literature search, hypothesis generation, experiment proposal, data analysis, interpretation, and updated hypotheses.

## Multi-Reviewer And Evaluation Research

- [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171)
  - Used for the principle that diverse independent reasoning paths can improve final answer selection.
- [Improving Factuality and Reasoning in Language Models through Multiagent Debate](https://arxiv.org/abs/2305.14325)
  - Used for the evidence that multi-agent debate can improve reasoning and factuality in some settings.
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
  - Used for LLM-as-judge utility and limitations, including position, verbosity, self-enhancement, and limited-reasoning biases.
- [G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634)
  - Used for structured form-filling evaluation and the caution that LLM-based evaluators can bias toward LLM-generated texts.
- [ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate](https://arxiv.org/abs/2308.07201)
  - Used for the idea that multi-agent evaluator teams can mimic multi-annotator human evaluation processes.

## Design Notes

This workflow intentionally avoids depending on one vendor-specific scheduler. The durable core is:

```text
repo files + status.json + bounded worker prompt + reviewer gate + human approval
```

Schedulers can be swapped without changing the research state model.
