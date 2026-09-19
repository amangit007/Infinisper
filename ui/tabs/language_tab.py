from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from languages import (
    PRIMARY_DICTATION_LANGUAGES,
    TRANSLATION_TARGET_LANGUAGES,
)

from ui.widgets.info_button import InfoButton

# Backward compatibility alias
LANGUAGES = PRIMARY_DICTATION_LANGUAGES

# Typing pause after which the dictionary is saved. Every other control on this tab
# saves the moment it changes; a free-text field needs to wait for the user to stop.
_DICTIONARY_SAVE_DELAY_MS = 600


class LanguageTab(QWidget):
    transformation_changed = Signal(str, str)  # output_mode, target_language
    settings_changed = Signal(bool)  # legacy force_english_transliteration
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
        content_layout.addWidget(self._build_transformation_card(current_config))
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
        text_col.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("Primary Dictation Language")
        title.setObjectName("FallbackText")
        title_row.addWidget(title)

        badge = QLabel("Whisper & AI cleanup")
        badge.setObjectName("WarnBadge")
        title_row.addWidget(badge)
        title_row.addWidget(InfoButton(
            "<b>How each part uses this</b><br>"
            "Whisper: forced into this language, so slow or quiet speech isn't mistaken for another.<br>"
            "AI cleanup: told to transcribe and tidy strictly in this language.<br>"
            "Qwen3-ASR and Nemotron: detect the language themselves; only the AI cleanup step "
            "follows this setting."
        ))
        title_row.addStretch()
        text_col.addLayout(title_row)

        hint = QLabel("The language you mostly dictate in. Setting it stops speech being mistaken for another language.")
        hint.setObjectName("FallbackHint")
        hint.setWordWrap(True)
        text_col.addWidget(hint)
        header_layout.addLayout(text_col, 1)

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LanguageComboBox")
        current_lang = current_config.get("dictation_language", "en")
        selected_idx = 0
        for i, (code, label) in enumerate(PRIMARY_DICTATION_LANGUAGES):
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

    def _build_transformation_card(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("FallbackRow")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("Language transformation")
        title.setObjectName("FallbackText")
        title_row.addWidget(title)

        badge = QLabel("Requires AI cleanup")
        badge.setObjectName("WarnBadge")
        title_row.addWidget(badge)
        title_row.addWidget(InfoButton(
            "Speech engines always write what you said, in the language you said it. "
            "Turning it into Latin script or another language is done by the AI cleanup step, "
            "so AI cleanup must be switched on."
        ))
        title_row.addStretch()
        title_col.addLayout(title_row)

        hint = QLabel("Keep the original language, write it in Latin script, or translate it.")
        hint.setObjectName("FallbackHint")
        hint.setWordWrap(True)
        title_col.addWidget(hint)
        layout.addLayout(title_col)

        # Determine initial mode from config
        saved_mode = current_config.get("cleanup_output_mode")
        if not saved_mode:
            if current_config.get("force_english_transliteration", False):
                saved_mode = "transliterate"
            else:
                saved_mode = "original"

        self.btn_group = QButtonGroup(self)

        # 1. Original
        self.radio_original = QRadioButton()
        self.btn_group.addButton(self.radio_original)
        row_orig = self._make_radio_row(
            self.radio_original,
            "Original Language (Native script)",
            "Keep transcribed speech in its spoken language using its standard native script.",
        )
        layout.addWidget(row_orig)

        # 2. Transliteration
        self.radio_transliterate = QRadioButton()
        self.checkbox = self.radio_transliterate  # backward compatibility reference
        self.btn_group.addButton(self.radio_transliterate)
        row_translit = self._make_radio_row(
            self.radio_transliterate,
            "Force English transliteration (Hinglish / Latin script)",
            "Romanizes non-English speech into English alphabet instead of native script "
            "(e.g. Hindi speech appears as “mujhe yeh chahiye” rather than Devanagari).",
        )
        layout.addWidget(row_translit)

        # 3. Translation
        self.radio_translate = QRadioButton()
        self.btn_group.addButton(self.radio_translate)
        row_trans = self._make_radio_row(
            self.radio_translate,
            "Translate to another language",
            "Automatically translate dictated speech into your chosen target language.",
        )
        layout.addWidget(row_trans)

        # Target language selector indented under Translation
        target_row = QHBoxLayout()
        target_row.setContentsMargins(36, 2, 0, 0)
        target_row.setSpacing(12)
        self.target_label = QLabel("Target Language:")
        self.target_label.setObjectName("FallbackText")
        target_row.addWidget(self.target_label)

        self.target_combo = QComboBox()
        self.target_combo.setObjectName("TargetLanguageComboBox")
        target_lang = current_config.get("translation_target_language", "en")
        selected_target_idx = 0
        for i, (code, label) in enumerate(TRANSLATION_TARGET_LANGUAGES):
            self.target_combo.addItem(label, code)
            if code == target_lang:
                selected_target_idx = i
        self.target_combo.setCurrentIndex(selected_target_idx)
        target_row.addWidget(self.target_combo)
        target_row.addStretch()
        layout.addLayout(target_row)

        # Set active radio button
        if saved_mode == "translate":
            self.radio_translate.setChecked(True)
        elif saved_mode == "transliterate":
            self.radio_transliterate.setChecked(True)
        else:
            self.radio_original.setChecked(True)

        self._update_target_combo_state()

        # Connect signals
        self.radio_original.toggled.connect(self._on_transformation_changed)
        self.radio_transliterate.toggled.connect(self._on_transformation_changed)
        self.radio_translate.toggled.connect(self._on_transformation_changed)
        self.target_combo.currentIndexChanged.connect(self._on_transformation_changed)

        return card

    def _make_radio_row(self, radio: QRadioButton, title: str, hint: str) -> QWidget:
        row = QWidget()
        row.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)
        layout.addWidget(radio)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        lbl = QLabel(title)
        lbl.setObjectName("FallbackText")
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(lbl)

        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("FallbackHint")
        hint_lbl.setWordWrap(True)
        hint_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(hint_lbl)

        layout.addLayout(text_col, 1)

        def on_press(event):
            if event.button() == Qt.LeftButton:
                radio.setChecked(True)
            QWidget.mousePressEvent(row, event)

        row.mousePressEvent = on_press
        return row

    def _update_target_combo_state(self):
        is_translate = self.radio_translate.isChecked()
        self.target_label.setEnabled(is_translate)
        self.target_combo.setEnabled(is_translate)

    def _on_transformation_changed(self):
        self._update_target_combo_state()
        if self.radio_translate.isChecked():
            mode = "translate"
        elif self.radio_transliterate.isChecked():
            mode = "transliterate"
        else:
            mode = "original"

        target_lang = str(self.target_combo.currentData() or "en")
        self.transformation_changed.emit(mode, target_lang)

    def _build_dictionary(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("FallbackRow")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Custom dictionary")
        title.setObjectName("FallbackText")
        title_row.addWidget(title)
        title_row.addWidget(InfoButton(
            "Words a general speech model can't guess from context. Telling it they exist is "
            "the biggest single accuracy win available.<br><br>"
            "Used by Whisper and by AI cleanup. Qwen3-ASR and Nemotron can't be biased this way."
        ))
        title_row.addStretch()
        layout.addLayout(title_row)

        hint = QLabel("Names, acronyms and jargon that get misheard, one per line.")
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
