---
name: Add a speech model
description: Add a new on-device speech recognition model to the Models tab.
---

# Add a speech model

Use this when adding a downloadable speech model, or changing which model ships bundled.

Read [`AGENTS.md`](../../AGENTS.md) first. Invariants 5 and 8 apply here.

## Before you start

Confirm three things, in this order:

1. **sherpa-onnx supports it.** Check the [sherpa-onnx
   changelog](https://github.com/k2-fsa/sherpa-onnx/blob/master/CHANGELOG.md). If it does not, this is
   not a model addition — it is a second inference runtime, which is a much larger decision and needs
   an ADR.
2. **An int8 export exists**, ideally under `csukuangfj` on Hugging Face. Exporting one yourself is a
   separate project.
3. **The licence permits commercial use, cleanly.** This is what ruled out Moonshine
   ([ADR-009](../../docs/DECISIONS.md#adr-009)) — a licence requiring registration or carrying revenue
   thresholds is not acceptable. The app redistributes nothing (users download from the original host),
   which lowers the bar, but does not remove it. Record the licence; attribution obligations belong in
   the About screen, not only in a markdown file.

Also ask whether a third model is warranted at all. Two well-chosen options that trade against each
other beat a menu the user has to research. A new model should displace one of the existing two or
cover something neither does — not simply sit between them.

## Steps

1. **Measure before integrating.** On 20 real dictation takes, record:
   - word error rate against a hand-checked reference;
   - wall-clock latency for a 10-second clip on a mid-range laptop CPU;
   - **whether it streams or batches**, and if it batches, how latency scales with take length — this
     is the property users feel most, and it must be stated on the model card in the UI
     ([ARCHITECTURE](../../docs/ARCHITECTURE.md#streaming-vs-batch-engines));
   - **whether it emits punctuation and casing** — if not, it needs a punctuation model appended, which
     changes its effective size;
   - **how many fillers survive** — this determines whether it can back Advanced mode's retention
     promise ([R11](../../docs/RISKS.md#r11--advanced-modes-filler-retention-fights-the-speech-model--h)).

   Put the numbers in [`docs/MODELS.md`](../../docs/MODELS.md). Numbers, not impressions.

2. **Add the model definition** — id, display name, download URL, SHA-256, size, languages, licence,
   and the measured WER and filler-retention rating.

3. **Wire it into the Models tab** per [`UI-SPEC.md`](../../docs/UI-SPEC.md#models). It downloads only
   on an explicit click, is resumable, is SHA-256 verified, and cannot be activated while partial.

4. **State the language limit honestly.** Name the actual coverage — "25 European languages", not
   "multilingual" — if it does not include Hindi, Chinese, Japanese, Korean or Arabic. A user who
   dictates Hindi into it and gets garbage has been misled by the label.

5. **If filler retention is good**, add it to the models the Advanced-mode inline note recommends
   ([MODES](../../docs/MODES.md#filler-retention-honesty-note)).

6. **Add it to the first-run chooser** only if it earns a slot there
   ([UI-SPEC](../../docs/UI-SPEC.md#first-run)). That screen presents a small number of peers with a
   clear trade between them; a third card makes the first-run decision harder for everyone.

7. **Verify in a packaged build.** Path resolution differs from `dev` and this is a known failure mode
   ([R10](../../docs/RISKS.md#r10--the-asr-runtime-inside-a-packaged-app--m)).

## Tests

- Unit: model registry parsing and SHA-256 verification, including a corrupted-download case.
- Manual: download, interrupt, resume, activate, delete.
- Manual: a partial download cannot be activated.
- Manual: nothing downloads without a click — the first-run chooser asks, it does not pre-fetch.
- Manual: latency measured at 10 s **and** 30 s takes, to confirm the streaming/batch claim on the card.
- **Packaged build**: the model loads from `%APPDATA%` after download.

## Update

- [`docs/MODELS.md`](../../docs/MODELS.md) — the table, and the licences section
- [`README.md`](../../README.md) — the speech models table
- About screen attributions, if the licence requires it
