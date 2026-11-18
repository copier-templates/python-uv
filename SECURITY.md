# Security Policy

## Reporting a Vulnerability

Do not open a public issue. Report via [GitHub Security Advisories](https://github.com/patryk-gpl/copier-python-uv/security/advisories/new) with details and reproduction steps, and allow time for a fix before any public disclosure.

## Supported Versions

Only the latest release receives security fixes.

| Version | Status | Security Fixes |
|---------|--------|----------------|
| Latest  | Active | ✅ Yes |
| Older   | EOL    | ❌ No |

## Best Practices

- Use a supported Python (3.12+) and run `uv sync` regularly for patches.
- Never commit secrets (API keys, tokens); keep `.env` untracked.
- Review generated code for your use case; enable Dependabot on rendered projects.
