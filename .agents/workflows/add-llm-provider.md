---
name: Add a refinement engine
description: Add a new LLM provider (refinement engine) to Advanced and Pro mode.
---

# Add a refinement engine

Use this when adding a new provider alongside `bundled`, `ollama` and `gemini` — another cloud API,
another local runtime, or a self-hosted gateway.

Read [`AGENTS.md`](../../AGENTS.md) first. Invariants 4, 6 and 7 all apply here.

## Before you start

**Does it need to be a provider at all?** LiteLLM already speaks to a very large number of backends,
so in most cases a new target is a model string and a base URL rather than a new class. A separate
`LlmProvider` implementation is warranted only when the auth model or the model-discovery mechanism
genuinely differs — as it does for Ollama, whose catalogue must be read live from the daemon.

## Steps

1. **Implement `LlmProvider`** in `freewisperr/llm/providers/<id>.py`. All four members are required:

   - `id` — added to the `Literal` union in the `LlmProvider` protocol.
   - `list_models()` — what is available **right now**. Query the service where possible. Only fall
     back to `model_registry.json` for providers whose catalogue cannot be discovered at runtime
     (cloud APIs). Never return a hardcoded list for something that can be asked.
   - `probe()` — must distinguish *unreachable* from *reachable but unconfigured* from *ready*. The UI
     renders these differently and "it doesn't work" is not an acceptable message when the app knows
     which one it hit.
   - `transform()` — takes the prompt and transcript, returns text. No retries beyond one; the 4 s
     budget is owned by `DictationSession`, not by you.

2. **Never mutate the user's environment.** No installing, no pulling, no downloading models on their
   behalf. If something is missing, `probe()` reports it and the UI explains it. This is
   [ADR-006](../../docs/DECISIONS.md#adr-006) generalised — it
   applies to every provider, not just Ollama.

3. **Register** the provider in `freewisperr/llm/__init__.py`.

4. **Add cloud model IDs to `model_registry.json`**, never to source. If the provider discovers its own
   models, it gets no registry entry at all.

5. **Add a Providers-tab card** per [`UI-SPEC.md`](../../docs/UI-SPEC.md#providers). It must show live
   `probe()` status, and a distinct state for each failure it can report.

6. **If it is a cloud provider:**
   - keys go through `keyring` into the Windows Credential Manager, write-only, never read back;
   - the chip shows the amber `cloud` badge during refinement;
   - selecting it the first time raises the one-time privacy confirmation;
   - the card carries a plain-language line saying what leaves the machine.

7. **Confirm the fallback path.** When this provider is unavailable, output degrades to **Basic**, and
   the chip says so. It must never fall through to a different engine — a user who chose a local
   provider for privacy must not have their words sent to a cloud they avoided
   ([R24](../../docs/RISKS.md#r24--silent-provider-substitution--h)).

## Tests

- Unit: `probe()` result mapping for every reachable/unreachable/unconfigured combination — pure, no
  network.
- Unit: `listModels()` parsing, including the empty-list case.
- Manual: kill the service mid-request and confirm the raw transcript is pasted within 4 s.
- Manual: run the prompt-injection cases from
  [`MODES.md`](../../docs/MODES.md#prompt-safety) — dictating a question must write the question down,
  not answer it.

## Update

- [`docs/MODELS.md`](../../docs/MODELS.md) — the refinement engines section
- [`docs/UI-SPEC.md`](../../docs/UI-SPEC.md) — the Providers tab
- [`README.md`](../../README.md) — the refinement engines table
- [`docs/DECISIONS.md`](../../docs/DECISIONS.md) — a new ADR if this changes the provider model
