# Python-uv Template

Domain terms for this Copier template. Use them as written.

## Language

**Payload**
: The contents of `templates/`, the only part Copier copies into rendered projects.

**Verbatim payload**
: Payload files copied without Jinja rendering.

**Root tooling**
: Files at the repo root that develop or release this template. Never shipped unless they are also in the payload.

**Symlink**
: A root tooling file that points into `templates/`, the single source of truth.

**Mirror**
: A byte-identical root copy of a payload file, used only for `.github/workflows/*.yml`.
_Avoid_: Byte copy.

**Question**
: An interactive prompt in `copier.yaml` that collects a value used during rendering.

**Answer**
: A value given for a question. Recorded in the answers file unless the question is a render fact.

**Render fact**
: A hidden question (`when: false`) whose value is computed from answers instead of prompted: `is_app`, `is_lib`, `is_package`, `module_name`, and `license_spdx`. Re-derived on every render and omitted from the answers file.

**Render**
: Copier producing a project from `templates/` and the answers.

**Rendered project**
: A project Copier produced from the templates and answers.
_Avoid_: Generated project, consumer project.

**Template source**
: The directory containing `copier.yaml` and `templates/` that Copier renders from.

**Variant**
: A named set of answers used for test renders.

**Task variant**
: A variant that also runs the template `_tasks` during rendering.

**Lifecycle script**
: The post-copy and post-update step that commits the rendered project to Git, then installs and verifies it.

**Task contract**
: The mise task names that both the template root and rendered projects expose.

**Shared refs**
: The per-category pinned releases of `shared-dev-tooling` used by the
`mise.toml` task includes and mirrored by `tests/_projects.py`. The newest ref
supplies the `prek.toml` shared hooks `rev`, while `[update.repos]` lists every
managed ref. Moved with `scripts/sync_shared_refs.py`, never by hand-editing
individual pins.

**Gate**
: The `mise run ci` check that must be green before delivery.
