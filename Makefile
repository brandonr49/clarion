.PHONY: test test-unit test-e2e test-scale test-cloud lint run benchmark

# Run unit tests only (fast, no LLM needed)
test-unit:
	.venv/bin/python -m pytest tests/ -v --timeout=30 \
		--ignore=tests/test_e2e_ollama.py \
		--ignore=tests/test_scale.py \
		--ignore=tests/test_cloud_models.py \
		--ignore=tests/benchmark_models.py

# Run e2e tests (requires Ollama running with qwen3:8b)
test-e2e:
	.venv/bin/python -m pytest tests/test_e2e_ollama.py -v -s --timeout=120

# Run scale tests (requires Ollama, ~10-30 min)
test-scale:
	.venv/bin/python -m pytest tests/test_scale.py -v -s --timeout=1800

# Run cloud model tests (requires ANTHROPIC_API_KEY)
test-cloud:
	.venv/bin/python -m pytest tests/test_cloud_models.py -v -s --timeout=120

# Run all tests except scale (reasonable CI time)
test:
	.venv/bin/python -m pytest tests/ -v --timeout=120 \
		--ignore=tests/test_scale.py \
		--ignore=tests/benchmark_models.py

# Benchmark all local models
benchmark:
	.venv/bin/python tests/benchmark_models.py

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
