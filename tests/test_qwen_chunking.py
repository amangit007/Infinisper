import numpy as np

from asr import qwen_asr


def test_stitch_transcription_chunks_empty_and_single():
    assert qwen_asr.stitch_transcription_chunks([]) == ""
    assert qwen_asr.stitch_transcription_chunks([""]) == ""
    assert qwen_asr.stitch_transcription_chunks(["   "]) == ""
    assert qwen_asr.stitch_transcription_chunks(["hello world"]) == "hello world"
    assert qwen_asr.stitch_transcription_chunks(["  hello world  "]) == "hello world"


def test_stitch_transcription_chunks_casing_and_punctuation():
    # Terminal punctuation preserves subsequent capital letter
    assert (
        qwen_asr.stitch_transcription_chunks(["First sentence.", "Second sentence."])
        == "First sentence. Second sentence."
    )
    assert (
        qwen_asr.stitch_transcription_chunks(["Are you ready?", "Yes I am."])
        == "Are you ready? Yes I am."
    )
    assert (
        qwen_asr.stitch_transcription_chunks(["Watch out!", "Look here."])
        == "Watch out! Look here."
    )

    # Mid-sentence continuation lowercases capitalized start
    assert (
        qwen_asr.stitch_transcription_chunks(["In today's meeting,", "We discussed the budget."])
        == "In today's meeting, we discussed the budget."
    )
    assert (
        qwen_asr.stitch_transcription_chunks(["because the system was", "Down for maintenance."])
        == "because the system was down for maintenance."
    )

    # Acronyms and pronoun "I" preserve capitalization
    assert (
        qwen_asr.stitch_transcription_chunks(["We contacted", "NASA about the launch."])
        == "We contacted NASA about the launch."
    )
    assert (
        qwen_asr.stitch_transcription_chunks(["Then", "I decided to proceed."])
        == "Then I decided to proceed."
    )
    assert (
        qwen_asr.stitch_transcription_chunks(["She said", "I'm coming over."])
        == "She said I'm coming over."
    )


class FakeStreamResult:
    def __init__(self, text: str):
        self.text = text


class FakeStream:
    def __init__(self, text_to_return: str):
        self.text_to_return = text_to_return
        self.result = FakeStreamResult(text_to_return)
        self.waveforms = []

    def accept_waveform(self, sample_rate: int, chunk: np.ndarray):
        self.waveforms.append(chunk)


class FakeOfflineRecognizer:
    def __init__(self, texts_to_return: list[str]):
        self.texts_to_return = list(texts_to_return)
        self.call_count = 0

    def create_stream(self):
        text = self.texts_to_return[min(self.call_count, len(self.texts_to_return) - 1)]
        self.call_count += 1
        return FakeStream(text)

    def decode_stream(self, stream: FakeStream):
        pass


def test_qwen_transcribe_short_audio_single_pass(monkeypatch):
    engine = object.__new__(qwen_asr.Qwen3AsrEngine)
    fake_rec = FakeOfflineRecognizer(["Quick take."])
    engine._recognizer = fake_rec

    audio = np.zeros(16000 * 5, dtype=np.float32)  # 5s
    result = engine.transcribe(audio, 16000)

    assert result == "Quick take."
    assert fake_rec.call_count == 1


def test_qwen_transcribe_long_audio_chunks_and_stitches(monkeypatch):
    engine = object.__new__(qwen_asr.Qwen3AsrEngine)
    fake_rec = FakeOfflineRecognizer([
        "This is the first section,",
        "And this is the second section.",
    ])
    engine._recognizer = fake_rec

    # 30s audio triggers chunking
    audio = np.zeros(16000 * 30, dtype=np.float32)
    result = engine.transcribe(audio, 16000)

    assert fake_rec.call_count >= 2
    assert "first section, and this is the second section." in result


def test_qwen_transcribe_empty_audio():
    engine = object.__new__(qwen_asr.Qwen3AsrEngine)
    assert engine.transcribe(np.array([], dtype=np.float32), 16000) == ""
    assert engine.transcribe(None, 16000) == ""
