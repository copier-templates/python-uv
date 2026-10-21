# Template Architecture

This document describes the structure and design of the Copier template.

## Overview

The template is built using [Copier](https://copier.readthedocs.io/), a project templating tool that uses Jinja2 for dynamic content generation.

## Configuration

### `copier.yaml`

The main template configuration file that defines:
- **Questions**: Interactive prompts for template variables
- **Exclusions**: Files/directories not copied to generated projects via `_exclude`
- **Jinja Extensions**: Custom Jinja filters and extensions
- **Tasks**: Post-generation operations (migrations, setup scripts)

## Template Structure

Copier renders only `templates/` (`_subdirectory: templates` in `copier.yaml`).
All `*.jinja` files live under `templates/`; verbatim payload files
(`prek.toml`, `.editorconfig`, `.github/workflows/*.yml`) live alongside them.
License partials under `templates/licenses/` are Jinja includes excluded from copy.

```
├── templates/                   # Copier payload (_subdirectory)
│   ├── src/{{module_name}}/     # Main source code directory (templated)
│   │   ├── __init__.py.jinja    # Package initialization
│   │   └── py.typed.jinja       # Typed-package marker (lib only)
│   ├── tests/                   # Test directory structure (templated)
│   │   ├── __init__.py.jinja
│   │   └── unit/
│   │       └── test_init.py.jinja
│   ├── .github/workflows/       # CI workflows (verbatim)
│   │   ├── test.yml
│   │   └── prek.yml
│   ├── licenses/                # License partials (included, excluded from copy)
│   ├── .editorconfig            # Editor config (verbatim)
│   ├── .gitattributes.jinja
│   ├── .gitignore.jinja
│   ├── pyproject.toml.jinja     # Project configuration (templated)
│   ├── README.md.jinja          # Project README (templated)
│   ├── mise.toml.jinja          # Task runner config (templated)
│   ├── main.py.jinja            # App entrypoint (app only)
│   ├── LICENSE.jinja            # License file (optional, includes licenses/*)
│   ├── prek.toml                # Git hooks (verbatim, keep in sync with root)
│   └── {{ _copier_conf.answers_file }}.jinja  # Answers file configuration
│
├── examples/                    # Example data files (outside templates/, not copied)
│   └── config-basic.yml         # Sample answers file
├── my_tests/                    # Test suite (outside templates/, not copied)
│   ├── conftest.py
│   ├── test_core_structure.py
│   ├── test_exclusions.py
│   └── test_conditional_sections.py
├── copier.yaml                  # Template configuration (_subdirectory: templates)
└── README.md                    # Template documentation
```

## Excluded Directories

Only `templates/` is copied to generated projects. Everything outside it —
`examples/`, `my_tests/`, `docs/`, `scripts/`, `copier.yaml` itself — is
template tooling and never lands in generated projects.

Within `templates/`, `licenses/` partials are excluded from copy via `_exclude`
(they are only used through `{% include %}` in `LICENSE.jinja`).

## Templating Conventions

### Variable Interpolation

Use double-brace syntax for Jinja2 variables:

```jinja
Project: {{ project_name }}
Author: {{ author_name }}
Python: {{ python_version }}
```

### Conditional Sections

Make files and directories conditional by templating their names with Jinja expressions. For example, generate a file only when `use_prek` is true:

```
{% if use_prek %}prek.toml{% endif %}.jinja
```

Important: keep the template suffix (by default `.jinja`) outside the Jinja expression. If the suffix is inside the condition the file won't be treated as a template and will be copied verbatim.

Concrete example:

```
{% if enable_feature %}optional_feature.py{% endif %}.jinja
```

See `my_tests/test_conditional_sections.py` for expected behavior and the official Copier docs ("Conditional files and directories") for more details.

### File Extensions

- `.jinja` - Files that require template rendering
- No extension - Static files copied as-is

Example:
```
templates/README.md.jinja       # Rendered with Jinja2
templates/prek.toml             # Copied without processing
```

## Testing

The template includes comprehensive tests in `my_tests/`:

| Test | Purpose |
|------|---------|
| `test_core_structure.py` | Validates project structure, required files, and directories |
| `test_exclusions.py` | Ensures excluded files aren't rendered in generated projects |
| `test_conditional_sections.py` | Tests conditional rendering based on configuration |

### Test Fixtures

Defined in `my_tests/conftest.py`:

- **Session-scoped fixtures**: Generate test projects once per session, reused across tests
- **Module-scoped wrappers**: Provide clean API with performance optimizations
- **Read-only operations**: All tests are non-mutating to enable fixture reuse

## Variable Types

Variables are defined in `copier.yaml` with type hints:

- **String**: Simple text values
- **Boolean**: Yes/No choices
- **Choice**: Dropdown selection from predefined options
- **Integer**: Numeric values
- **Float**: Decimal values

## Answer Files

### `.copier-answers.yml`

Auto-maintained file created in generated projects. Used for:
- Tracking user responses
- Enabling future template updates via `copier update`
- Never manually edited

### Sample Configuration

`examples/config-basic.yml` provides:
- Example variable values
- Used with `copier copy --data-file` for non-interactive generation
- Excluded from generated projects

## Best Practices

1. **Always use relative paths** in template files
2. **Keep templates DRY**: Use Jinja2 includes for shared content
3. **Test conditionals thoroughly**: Edge cases matter
4. **Document variables**: Include helpful descriptions in `copier.yaml`
5. **Version templates**: Use Git tags for reproducible generations
6. **Commit before testing**: Copier uses Git to detect files
7. **Keep exclusions updated**: Remove deprecated files from templates

## Common Tasks

### Add a New Template Variable

1. Add question in `copier.yaml`:
   ```yaml
   _questions:
     my_variable:
       type: str
       help: "Description of this variable"
   ```

2. Use in template files:
   ```jinja
   {{ my_variable }}
   ```

3. Add test case in `my_tests/`


### Update Generated Projects

Users can sync with template changes:
```bash
copier update --answers-file .copier-answers.yml
```

## References

- [Copier Documentation](https://copier.readthedocs.io/en/stable/)
- [Jinja2 Template Documentation](https://jinja.palletsprojects.com/)
- [Python Packaging Guide](https://packaging.python.org/)
