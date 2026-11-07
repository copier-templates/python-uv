# 0003. CI auto-release from Release PRs

Status: Accepted

## Context

Releases cut a version bump, changelog, amend, and tag. Local releases stay human-run, but waiting on a human to push tags after every green PR is slow, and letting agents bump, tag, or push is unsafe. Version intent also needs a signal that survives review and cannot be guessed.

## Decision

- A PR carrying exactly one `release:patch`, `release:minor`, or `release:major` label is a Release PR, the only kind the release workflow acts on. The label alone decides the bump kind.
- The release job fires when the Test workflow succeeds on a pull request event. It resolves the bump from the label, previews the version, checks out the PR head, cuts the release, validates the amended tree with the Gate, then pushes the commit and tag and merges the PR.
- A manual `workflow_dispatch` input selects one PR for piloting. Closing a PR without merging deletes its orphan tag.
- `@releaser` only opens the labeled PR and never bumps, tags, pushes, or merges.

## Consequences

- CI owns bump, tag, push, and merge; humans and agents never do them from automation. Local `mise run release` remains for human-run releases.
- Multiple or unknown release labels fail instead of guessing; an already-released version skips.
- Red CI never releases, because the job requires a successful Test run.
