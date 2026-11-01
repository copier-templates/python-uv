# Security Policy

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in this project, please report it responsibly by following these steps:

### Do Not
- ❌ Do not open a public GitHub issue for security vulnerabilities
- ❌ Do not disclose the vulnerability publicly before we've had time to address it

### Please Do
- ✅ Report vulnerabilities using GitHub's [Security Advisory](https://github.com/patryk-gpl/copier-python-uv/security/advisories/new) feature
- ✅ Include detailed information about the vulnerability and steps to reproduce it
- ✅ Allow us reasonable time to develop and release a fix

## Security Advisory Process

1. **Report**: Submit your finding via [GitHub Security Advisories](https://github.com/patryk-gpl/copier-python-uv/security/advisories/new)
2. **Acknowledge**: We will acknowledge receipt of your report within 48 hours
3. **Investigate**: Our team will investigate and develop a fix
4. **Coordinate**: We'll work with you on timing for public disclosure
5. **Release**: A security patch will be released and announced

## Supported Versions

Security updates are provided for:
- The latest major version
- The previous major version (if recently released)

| Version | Status | Security Fixes |
|---------|--------|-----------------|
| Latest  | Active | ✅ Yes |
| N-1     | Active | ✅ Yes (if recently released) |
| Older   | EOL | ❌ No |

## Dependencies and Supply Chain Security

This project relies on several key dependencies:
- **copier**: Python project template tool
- **uv**: Fast Python package installer and resolver
- **pytest**: Testing framework
- **ruff**: Python linter and formatter
- **mutmut**: Mutation testing tool

We regularly update dependencies to address known vulnerabilities. Dependencies are pinned in `pyproject.toml` and updated through pull requests with automated testing.

## Security Best Practices

When using this project template:

- **Keep Python Updated**: Use a supported Python version (3.11+)
- **Update Dependencies**: Regularly run `uv sync` to get the latest security patches
- **Review Generated Code**: Always review code generated from templates for your use case
- **Secrets Management**: Never commit API keys, tokens, or other secrets to the repository
- **Dependency Scanning**: Enable GitHub's Dependabot for your generated projects

## Contact

For security-related questions or concerns, please use the [GitHub Security Advisory](https://github.com/patryk-gpl/copier-python-uv/security/advisories/new) feature rather than public issues or email.

## Acknowledgments

We appreciate the security research community's efforts to keep our project secure. Responsible disclosure helps us maintain a safe environment for all users.
