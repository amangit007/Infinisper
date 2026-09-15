import pytest
from PySide6.QtWidgets import QApplication

from ui.tabs.language_tab import LanguageTab


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(qt_app):
    widget = LanguageTab({"dictation_language": "en", "custom_words": ["Kubernetes", "OKR"]})
    yield widget
    widget.deleteLater()


def test_existing_terms_are_shown_one_per_line(tab):
    assert tab.dictionary_edit.toPlainText() == "Kubernetes\nOKR"


def test_a_tab_with_no_dictionary_starts_empty(qt_app):
    widget = LanguageTab({"dictation_language": "en"})
    assert widget.dictionary_edit.toPlainText() == ""
    assert widget._parsed_custom_words() == []


def test_blank_lines_and_stray_whitespace_are_dropped(tab):
    tab.dictionary_edit.setPlainText("  Kubernetes  \n\n\n   \nOKR\n")
    assert tab._parsed_custom_words() == ["Kubernetes", "OKR"]


def test_duplicates_are_removed_case_insensitively_keeping_the_first(tab):
    tab.dictionary_edit.setPlainText("Nemotron\nnemotron\nNEMOTRON\nWhisper")
    assert tab._parsed_custom_words() == ["Nemotron", "Whisper"]


def test_the_order_the_user_typed_is_preserved(tab):
    """The list reaches the model's prompt in this order, so it should stay put."""
    tab.dictionary_edit.setPlainText("zebra\nalpha\nmike")
    assert tab._parsed_custom_words() == ["zebra", "alpha", "mike"]


def test_editing_does_not_emit_until_typing_stops(tab):
    """Every other control on this tab saves immediately; a free-text field has to
    wait, or it would write to disk on every keystroke."""
    emitted = []
    tab.custom_words_changed.connect(emitted.append)

    tab.dictionary_edit.setPlainText("Kubernetes\nOKR\nNemotron")
    assert emitted == [], "should still be waiting for the typing pause"

    tab._dictionary_timer.stop()
    tab._emit_custom_words()
    assert emitted == [["Kubernetes", "OKR", "Nemotron"]]


def test_the_count_label_tracks_what_was_typed(tab):
    tab.dictionary_edit.setPlainText("one\ntwo\nthree")
    assert "3 terms" in tab.dictionary_count.text()

    tab.dictionary_edit.setPlainText("only")
    assert "1 term" in tab.dictionary_count.text()
    assert "1 terms" not in tab.dictionary_count.text()

    tab.dictionary_edit.setPlainText("")
    assert tab.dictionary_count.text() == "No terms yet."


def test_clearing_the_box_emits_an_empty_list(tab):
    emitted = []
    tab.custom_words_changed.connect(emitted.append)
    tab.dictionary_edit.setPlainText("")
    tab._emit_custom_words()
    assert emitted == [[]]
