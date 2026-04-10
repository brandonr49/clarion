.PHONY: test test-unit test-e2e lint run

# Run unit tests only (fast, no LLM needed)
test-unit:
	.venv/bin/python -m pytest tests/ -v --ignore=tests/test_e2e_ollama.py

# Run e2e tests (requires Ollama running with llama3.2:3b)
test-e2e:
	.venv/bin/python -m pytest tests/test_e2e_ollama.py -v -s

# Run all tests
test: test-unit test-e2e

# Lint
lint:
	.venv/bin/ruff check clarion/ tests/

# Run the server
run:
	.venv/bin/python -m clarion.app

# Install dependencies
install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
