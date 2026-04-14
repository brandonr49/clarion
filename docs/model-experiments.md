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

## Benchmark Results (April 2026)

5 scenarios tested: bootstrap, two-note update, different topics, query, priming.
All local models on Mac with 48GB RAM (Apple Silicon). Times include LLM thinking.

| Model | Size | Pass Rate | Avg Time | Cost | Notes |
|-------|------|-----------|----------|------|-------|
| **gemma4** | 9.6 GB | **100%** | **55.6s** | Free | Excellent. Best speed/quality ratio for local. |
| **qwen2.5:7b** | 4.7 GB | **100%** | **29.6s** | Free | Fastest 100% model. Good for fast-path dispatch. |
| **qwen3:8b** | 5.2 GB | **100%** | 133.7s | Free | Current default. Reliable but slow (thinks hard). |
| **qwen3:14b** | 9.3 GB | **100%** | 130.3s | Free | Same speed as 8b, equally reliable. |
| qwen3:32b | 20 GB | 80% | 264.0s | Free | Slower, failed 1 scenario. Not worth the RAM cost. |
| gemma3:12b | 8.1 GB | 20% | 3.5s | Free | Tool-use format incompatible with Ollama. Don't use. |
| llama3.2:3b | 2.0 GB | 40% | 12.4s | Free | Too small for reliable tool use. |
| Claude Haiku | Cloud | 100% | ~2s | $$ | Cloud. Fastest overall. Costs per token. |
| Claude Sonnet | Cloud | 100%* | ~3s | $$$ | Cloud. Best quality for complex reasoning. |

*Sonnet tested on individual scenarios, not full benchmark.

### Key Findings

1. **gemma4 is a strong contender** — 100% pass rate at 55.6s avg, significantly
   faster than qwen3:8b (133.7s). Consider as default or tier1 fast model.
2. **qwen2.5:7b is the speed champion** — 100% at 29.6s. Great for dispatch and
   fast paths where speed matters more than depth.
3. **qwen3:8b is reliable but slow** — extensive chain-of-thought thinking makes
   it thorough but 2-4x slower than alternatives.
4. **Bigger isn't always better** — qwen3:32b (80%) performed worse than qwen3:8b (100%)
   while being 2x slower. May need different prompt tuning for larger models.
5. **gemma3 doesn't work** — tool-use format incompatible with current Ollama version.
6. **Cloud models are fast but cost money** — Claude Haiku at ~2s is unbeatable for
   speed when cost isn't a concern.
