# playwright-god — common dev tasks
# Usage: `make <target>`. Run `make help` to see all targets.

.PHONY: help install install-dev hooks scan-secrets scan-secrets-history test test-unit test-integration coverage clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	pip install -e .

install-dev: ## Install dev dependencies + pre-commit hooks
	pip install -e ".[dev]"
	pip install pre-commit
	pre-commit install

hooks: ## Run all pre-commit hooks against every file
	pre-commit run --all-files

scan-secrets: ## Scan working tree for leaked secrets (gitleaks)
	@command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks not installed. See https://github.com/gitleaks/gitleaks#installing"; exit 1; }
	gitleaks detect --source . --no-git --config .gitleaks.toml --redact --verbose

scan-secrets-history: ## Scan full git history for leaked secrets (gitleaks)
	@command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks not installed. See https://github.com/gitleaks/gitleaks#installing"; exit 1; }
	gitleaks detect --source . --config .gitleaks.toml --redact --verbose

test: ## Run unit + integration tests
	pytest tests/unit tests/integration -q

test-unit: ## Run unit tests only
	pytest tests/unit -q

test-integration: ## Run integration tests only
	pytest tests/integration -q

coverage: ## Run tests with coverage
	pytest --cov=playwright_god --cov-report=term-missing

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info playwright_god.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/
