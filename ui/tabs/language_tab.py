from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

# Typing pause after which the dictionary is saved. Every other control on this tab
# saves the moment it changes; a free-text field needs to wait for the user to stop.
_DICTIONARY_SAVE_DELAY_MS = 600

LANGUAGES = [
    ("en", "English (en) — Recommended for best accuracy"),
    ("auto", "Auto-detect (multilingual)"),
    ("hi", "Hindi (hi)"),
    ("es", "Spanish (es)"),
    ("fr", "French (fr)"),
    ("de", "German (de)"),
    ("ja", "Japanese (ja)"),
    ("zh", "Chinese (zh)"),
]


class LanguageTab(QWidget):
    settings_changed = Signal(bool)  # force_english_transliteration
    language_changed = Signal(str)  # dictation_language
    custom_words_changed = Signal(list)  # custom_words

    def __init__(self, current_config: dict, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        content = QWidget()
        content.setObjectName("DashboardScrollContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 20, 26, 26)
        content_layout.setSpacing(16)
        content_layout.addWidget(self._build_lang_picker(current_config))
        content_layout.addWidget(self._build_row(current_config))
        content_layout.addWidget(self._build_dictionary(current_config))
        content_layout.addStretch()
        outer.addWidget(content, 1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("DashboardHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 0, 26, 0)
        layout.setSpacing(14)

        title = QLabel("Language")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        hint = QLabel("How dictated speech gets recognized and formatted.")
        hint.setObjectName("PageHint")
        layout.addWidget(hint)
        layout.addStretch()
        return header

    def _build_lang_picker(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("FallbackRow")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("Primary Dictation Language")
        title.setObjectName("FallbackText")
        text_col.addWidget(title)
        hint = QLabel(
            "Locks speech recognition to your chosen language. Setting this to English prevents "
            "slow or quiet speech from being misidentified."
        )
        hint.setObjectName("FallbackHint")
        hint.setWordWrap(True)
        text_col.addWidget(hint)
        header_layout.addLayout(text_col, 1)

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LanguageComboBox")
        current_lang = current_config.get("dictation_language", "en")
        selected_idx = 0
        for i, (code, label) in enumerate(LANGUAGES):
            self.lang_combo.addItem(label, code)
            if code == current_lang:
                selected_idx = i
        self.lang_combo.setCurrentIndex(selected_idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        header_layout.addWidget(self.lang_combo)

        layout.addLayout(header_layout)
        return card

    def _on_language_changed(self, index: int):
        code = self.lang_combo.itemData(index)
        if code:
            self.language_changed.emit(str(code))

    def _build_row(self, current_config: dict) -> QWidget:
        row = QWidget()
        row.setObjectName("FallbackRow")
        row.setAttribute(Qt.WA_StyledBackground, True)
        row.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(current_config.get("force_english_transliteration", False))
        self.checkbox.toggled.connect(self.settings_changed.emit)
        layout.addWidget(self.checkbox)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text = QLabel("Force English transliteration (Hinglish)")
        text.setObjectName("FallbackText")
        text.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(text)
        hint = QLabel(
            "Romanizes non-English speech into English alphabet instead of native script "
            "(e.g. Hindi speech appears as “mujhe yeh chahiye” rather than Devanagari). "
            "Applies when multimodal refinement is active."
        )
        hint.setObjectName("FallbackHint")
        hint.setWordWrap(True)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(hint)
        layout.addLayout(text_col, 1)

        row.mousePressEvent = lambda event: self._toggle(event, row)
        return row

    def _toggle(self, event, row):
        if event.button() == Qt.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        QWidget.mousePressEvent(row, event)

    def _build_dictionary(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("FallbackRow")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        title = QLabel("Custom dictionary")
        title.setObjectName("FallbackText")
        layout.addWidget(title)

        hint = QLabel(
            "Names, acronyms and jargon a general speech model tends to mishear — one per "
            "line. These are the words it cannot guess from context, so telling it they "
            "exist is the single biggest accuracy win available. Applies to Whisper and to "
            "multimodal refinement; Qwen3-ASR and Nemotron cannot be biased this way."
        )
        hint.setObjectName("FallbackHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.dictionary_edit = QPlainTextEdit()
        self.dictionary_edit.setObjectName("DictionaryEdit")
        self.dictionary_edit.setPlaceholderText("Kubernetes\nInfinisper\nOKR")
        self.dictionary_edit.setFixedHeight(120)
        self.dictionary_edit.setPlainText("\n".join(current_config.get("custom_words", []) or []))
        layout.addWidget(self.dictionary_edit)

        self.dictionary_count = QLabel()
        self.dictionary_count.setObjectName("FallbackHint")
        layout.addWidget(self.dictionary_count)

        self._dictionary_timer = QTimer(self)
        self._dictionary_timer.setSingleShot(True)
        self._dictionary_timer.setInterval(_DICTIONARY_SAVE_DELAY_MS)
        self._dictionary_timer.timeout.connect(self._emit_custom_words)
        self.dictionary_edit.textChanged.connect(self._on_dictionary_edited)

        self._refresh_dictionary_count()
        return card

    def _parsed_custom_words(self) -> list[str]:
        """One term per line, blanks dropped, duplicates removed but order kept -- the
        order reaches the model's prompt, so it should stay the order the user typed."""
        seen, words = set(), []
        for line in self.dictionary_edit.toPlainText().splitlines():
            word = line.strip()
            if word and word.lower() not in seen:
                seen.add(word.lower())
                words.append(word)
        return words

    def _on_dictionary_edited(self):
        self._refresh_dictionary_count()
        self._dictionary_timer.start()

    def _refresh_dictionary_count(self):
        count = len(self._parsed_custom_words())
        self.dictionary_count.setText(
            "No terms yet." if count == 0 else f"{count} term{'s' if count != 1 else ''} saved."
        )

    def _emit_custom_words(self):
        self.custom_words_changed.emit(self._parsed_custom_words())
