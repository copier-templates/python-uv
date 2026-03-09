# Internal template development Makefile (NOT copied to generated projects)
# Provides conveniences for running the template validation tests.

PYTHON ?= uv run

.PHONY: help clean check install test

CLEAN_ROOT_DIRS := build/ dist/ .pytest_cache .ruff_cache htmlcov .coverage
CLEAN_DIRS := __pycache__ *.egg-info
CLEAN_FILES := *.pyc

help: ## Display available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

check:
	@for tools in "uv"; do \
		if ! command -v $$tools >/dev/null 2>&1; then \
			echo "Error: '$$tools' is not installed. Please install it first." >&2; \
			exit 1; \
		fi; \
	done

install: check ## Install development dependencies (copier, pytest)
	@uv sync --all-extras
	@pre-commit install

# Run internal validation tests, use environment variable EXTRA_PYTEST_ARGS to pass additional args.
test: clean install ## Run internal template validation tests
	@$(PYTHON) pytest my_tests $$EXTRA_PYTEST_ARGS || (echo "\nHint: run 'make install' first to install copier & pytest" >&2; exit 1)

clean: ## Clean build and cache artifacts
	@rm -rf $(CLEAN_ROOT_DIRS)
	@for dir in $(CLEAN_DIRS); do find . -type d -name "$$dir" -exec rm -rf {} +; done
	@for file in $(CLEAN_FILES); do find . -type f -name "$$file" -delete; done
