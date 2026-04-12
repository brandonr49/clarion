# Model Experiments — Future

## Current Setup

- **Hardware**: Mac (no dedicated GPU), CPU-only inference via Ollama
- **Default model**: qwen3:8b — 100% benchmark pass rate, ~20-30s per note
- **Cloud fallback**: Claude Sonnet via API (tier 3)

## Planned Experiments

### External GPU (eGPU)

Try an eGPU enclosure with a dedicated GPU for faster local inference:
- Thunderbolt eGPU enclosure + NVIDIA GPU (RTX 3090/4090)
- Would enable running larger parameter models locally
- Target: sub-5s per note processing with a 32B+ model

### Larger Qwen Models

With eGPU or on the Fedora production server (which has a GPU):
- **qwen3:32b** — significantly more capable than 8b, may handle complex
  reorganization and nuanced intent interpretation without cloud escalation
- **qwen3:72b** — near cloud-model quality for most tasks, could eliminate
  the need for Claude API for all but the most complex operations
- Compare brain organization quality at different parameter counts
- Measure: does the dispatcher make better decisions with a larger fast model?

### Kimi Models

Kimi (Moonshot AI) models are reported to be strong at tool use:
- Try kimi models via Ollama when available
- Compare tool-use reliability against qwen3 at similar parameter counts
- Particularly interested in: dispatch classification accuracy,
  checklist JSON generation quality, multi-tool-call sequences

### Benchmark Protocol

For each new model, run:
1. `make benchmark` — 5 scenarios x model comparison
2. `tests/test_brain_lifecycle.py` — grocery lifecycle (add/remove/query cycle)
3. `tests/test_brain_lifecycle.py::test_multi_domain_brain` — 16 notes across 6 domains
4. Manual testing via Android app for subjective quality assessment

Record: pass rate, avg time per note, tool call count, brain organization quality,
query accuracy, JSON view generation reliability.

## Model Quality Observations So Far

| Model | Pass Rate | Avg Time | Tool Use | View JSON | Notes |
|-------|-----------|----------|----------|-----------|-------|
| qwen3:8b | 100% | ~25s | Reliable | Good | Default choice |
| qwen2.5:7b | 100% | ~10s | Reliable | OK | Faster but less precise |
| llama3.1:8b | 80% | ~10s | OK | Poor | Skips reads on queries |
| llama3.2:3b | 40% | ~5s | Poor | Poor | Too small |
| Claude Haiku | 100% | ~2s | Excellent | Good | Cloud, costs money |
