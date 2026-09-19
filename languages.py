"""Standard language definitions and mappings for ASR and AI models.

Covers the standard ISO-639-1 language catalog natively supported by Whisper
and modern LLMs.
"""

# Master mapping of ISO-639-1 two-letter (and three-letter where standard) codes to English names.
LANGUAGE_NAMES: dict[str, str] = {
    "af": "Afrikaans",
    "am": "Amharic",
    "ar": "Arabic",
    "as": "Assamese",
    "az": "Azerbaijani",
    "ba": "Bashkir",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bo": "Tibetan",
    "br": "Breton",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fo": "Faroese",
    "fr": "French",
    "gl": "Galician",
    "gu": "Gujarati",
    "ha": "Hausa",
    "haw": "Hawaiian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "ht": "Haitian Creole",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "jw": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "la": "Latin",
    "lb": "Luxembourgish",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Myanmar (Burmese)",
    "ne": "Nepali",
    "nl": "Dutch",
    "nn": "Norwegian Nynorsk",
    "no": "Norwegian",
    "oc": "Occitan",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tr": "Turkish",
    "tt": "Tatar",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "yue": "Cantonese",
    "zh": "Chinese",
}

# Quick-pick common languages pinned near the top of lists
_COMMON_POPULAR_CODES = [
    "es",
    "hi",
    "fr",
    "de",
    "ja",
    "zh",
    "pt",
    "ru",
    "ar",
    "it",
    "ko",
]


def get_language_name(code: str) -> str:
    """Returns the display name for a language code, or the code itself if unknown."""
    if code == "auto":
        return "Auto-detect"
    return LANGUAGE_NAMES.get(code, code)


def _build_primary_dictation_languages() -> list[tuple[str, str]]:
    """Builds the list of dictation language options for the UI dropdown.

    Pinned at the top:
    1. Auto-detect
    2. English (Recommended)
    3. Common popular languages
    Followed by the full alphabetical list of remaining languages.
    """
    pinned = [
        ("auto", "Auto-detect (multilingual)"),
        ("en", "English (en) — Recommended for best accuracy"),
    ]
    popular = [(c, f"{LANGUAGE_NAMES[c]} ({c})") for c in _COMMON_POPULAR_CODES if c in LANGUAGE_NAMES]

    exclude = {"en", *_COMMON_POPULAR_CODES}
    remaining = [
        (c, f"{name} ({c})")
        for c, name in sorted(LANGUAGE_NAMES.items(), key=lambda item: item[1])
        if c not in exclude
    ]

    return pinned + popular + remaining


def _build_translation_target_languages() -> list[tuple[str, str]]:
    """Builds the list of target languages for the Translation feature.

    English is pinned at the top, followed by common popular languages,
    then the remaining languages sorted alphabetically.
    """
    pinned = [("en", "English (en)")]
    popular = [(c, f"{LANGUAGE_NAMES[c]} ({c})") for c in _COMMON_POPULAR_CODES if c in LANGUAGE_NAMES]

    exclude = {"en", *_COMMON_POPULAR_CODES}
    remaining = [
        (c, f"{name} ({c})")
        for c, name in sorted(LANGUAGE_NAMES.items(), key=lambda item: item[1])
        if c not in exclude
    ]

    return pinned + popular + remaining


PRIMARY_DICTATION_LANGUAGES: list[tuple[str, str]] = _build_primary_dictation_languages()
TRANSLATION_TARGET_LANGUAGES: list[tuple[str, str]] = _build_translation_target_languages()
