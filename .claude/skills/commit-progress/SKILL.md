---
name: commit-progress
description: Commit conventions for this repository (Conventional Commits, one commit per plan step, no squash or force-push, docs/ never committed). Use whenever committing.
---
# Committing progress

- Conventional Commits: `feat(<context>): ...`, `fix`, `test`, `docs`, `chore`, `build`, `ci`, `refactor`.
- One logical step per commit; the history must tell how the project was built (evaluated by Artefact).
- Before committing: `make lint` and `make test-unit` green; `git status` shows no `.env` and no `docs/`.
- Never `--amend` pushed commits, never force-push, never squash.
- End the message with the `Co-Authored-By` trailer for the AI assistant.
