# Glossary

Domain terms for this Copier template. Use them as written.

Implementation details live in `docs/architecture.md`; decisions live in `docs/adr/`.

## Language

### Template and payload

**Template repository**:
The repository that develops the Copier template and its history.
_Avoid_: template (alone)

**Generated project**:
A project Copier produces from the payload and answers.
_Avoid_: output, scaffold (noun)

**Payload**:
The files that ship into every generated project.
_Avoid_: template files

**Verbatim payload**:
Payload files copied without Jinja rendering.
_Avoid_: static files

**Symlink**:
A root tooling file that points into the payload as its single source of truth.
_Avoid_: link

**Mirror**:
A root file kept byte-identical to its payload counterpart.
_Avoid_: byte copy, copy

**Root tooling**:
Files at the repository root that develop or release the template and never ship unless also in the payload.
_Avoid_: root files

**Template tooling**:
All non-shipping development files outside the payload.
_Avoid_: tooling

**Maintainer tooling**:
Root-only automation that never ships to generated projects.
_Avoid_: scripts (alone)

**Template contract**:
The task names every generated project must expose.
_Avoid_: mise contract

### Answers and rendering

**Answer**:
A value given for a template question.
_Avoid_: input, option

**Answers file**:
The record of answers kept in each generated project for future updates.
_Avoid_: answers (alone)

**Render fact**:
A value derived from answers and re-derived on every render, never stored.
_Avoid_: computed fact, derived answer

**Render**:
Copier producing a project from the payload and answers.
_Avoid_: generate, scaffold (verb)

**Update**:
Replaying a generated project against a newer template version.
_Avoid_: upgrade, sync (verb)

**Project type**:
Whether a generated project is an application, a packaged application, or a library.
_Avoid_: project kind

**Variant**:
A named set of answers used to render a test project.
_Avoid_: fixture, example

**Task variant**:
A variant rendered with post-copy tasks enabled.
_Avoid_: full render

### Validation

**Validation suite**:
The tests that validate the template by rendering projects.
_Avoid_: test suite, unit tests (alone)

**Payload tests**:
The tests that ship inside generated projects.
_Avoid_: template tests, generated tests

**Lifecycle script**:
The post-copy script that initializes Git and verifies the new project.
_Avoid_: post-copy hook, git script

**Gate**:
The pre-push check that must stay green before delivery.
_Avoid_: CI (alone), checks

**Delivery gate**:
Green Gate plus reviewer sign-off required before delivery.
_Avoid_: gate (for the full process), approval

### Release

**Release**:
A versioned bump with changelog, commit amend, and tag, without pushing.
_Avoid_: version bump, tag (verb)

**Auto-release**:
The CI job that releases a Release PR after green checks.
_Avoid_: automatic release, bot release

**Release PR**:
A pull request carrying exactly one release label, the only kind CI will release.
_Avoid_: version PR

**Release label**:
The label that decides the version bump kind.
_Avoid_: bump label, version label

**Orphan tag**:
A release tag left behind by a PR closed without merging.
_Avoid_: stale tag, dangling tag

### Agent workflow

**Role**:
A named agent responsibility with its own rules.
_Avoid_: agent, persona

**Orchestrator**:
The role that plans, dispatches workers, and integrates their commits without editing files directly.
_Avoid_: lead, coordinator

**Worker**:
A role that works alone on an isolated branch or worktree and hands off to the orchestrator.
_Avoid_: subagent, helper
