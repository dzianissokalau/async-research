# Coffee Pilot Deliverable Maturity Fixture

This fixture captures the dogfood scenario that motivated deliverable maturity:
an internal draft assembly task is accepted, but the paper is not automatically
working-paper-ready.

The accepted source task is `TASK-0015`. The deliverable is `DELIV-0015` with
`current_maturity=internal_draft` and `target_maturity=working_paper`.

Expected first check:

```bash
async-research deliverable check research_ops DELIV-0015
```

The check should fail because accepted task evidence does not satisfy missing
related-work synthesis, figure/table narration, formal citations, complete
bibliography, critic review, or required review independence.

To promote the fixture, close the missing manuscript gates, record an
independent critic review, create response-matrix rows for critic-required
revisions, close or human-waive all critical and major rows, and rerun
`async-research deliverable check research_ops DELIV-0015`.
