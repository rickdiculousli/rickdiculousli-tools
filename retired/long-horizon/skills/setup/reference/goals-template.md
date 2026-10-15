# Goals template

Copy the block with project-specific criteria. IDs are stable; criteria are owned
policy. Checks are all required, including named tokens in Done when.

```markdown
# Goal: Tiny project — current
ID: tiny
Done when: validator:integration proves the full calling context.
Checks: ["validator:integration", "observation:review"]

## 1. Build evidence — current
Done when: validator:unit passes against the agreed fixtures.
- [ ] [1.1] Establish the fixture oracle. (any)
- [ ] [1.2] Implement the bounded behavior. (fixtures)

## 2. Integrate
Done when: validator:integration passes in the full calling context.
- [ ] [2.1] Refine integration work at this milestone boundary. (native)

## Parked
```

Adjacent citations: `Evidence: 1.1=<evidence-id-or-ancestor-commit>`.
Sign-off after actual approval: `Signed-off: user, 2026-10-11`.
Archive: `Archive: docs/goals-archive/2026-10-11-tiny-project.md`.
Shelve/drop adds `Reason:` and an archive preserving the original roadmap.
