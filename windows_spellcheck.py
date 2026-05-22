from __future__ import annotations

from dataclasses import dataclass
from ctypes import POINTER, c_int, c_ubyte, c_ulong, c_wchar_p
from ctypes.wintypes import BOOL, ULONG

from comtypes import CLSCTX_INPROC_SERVER, COMMETHOD, GUID, HRESULT, IUnknown, CoCreateInstance, CoInitialize, CoUninitialize


SPELL_CHECKER_FACTORY_CLSID = GUID("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}")
SPELL_CHECKER_FACTORY_IID = GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")
SPELL_CHECKER_IID = GUID("{B6FD0B71-E2BC-4653-8D05-F197E412770B}")
ENUM_SPELLING_ERROR_IID = GUID("{803E3BD4-2828-4410-8290-418D1D73C762}")
SPELLING_ERROR_IID = GUID("{B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3}")
ENUM_STRING_IID = GUID("{00000101-0000-0000-C000-000000000046}")


class IEnumString(IUnknown):
    _iid_ = ENUM_STRING_IID
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Next",
            (["in"], c_ulong, "celt"),
            (["out"], POINTER(c_wchar_p), "rgelt"),
            (["out"], POINTER(c_ulong), "pceltFetched"),
        ),
        COMMETHOD([], HRESULT, "Skip", (["in"], c_ulong, "celt")),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "Clone", (["out"], POINTER(POINTER(IUnknown)), "ppenum")),
    ]


class ISpellingError(IUnknown):
    _iid_ = SPELLING_ERROR_IID
    _methods_ = [
        COMMETHOD([], HRESULT, "get_StartIndex", (["out"], POINTER(ULONG), "value")),
        COMMETHOD([], HRESULT, "get_Length", (["out"], POINTER(ULONG), "value")),
        COMMETHOD([], HRESULT, "get_CorrectiveAction", (["out"], POINTER(c_int), "value")),
        COMMETHOD([], HRESULT, "get_Replacement", (["out"], POINTER(c_wchar_p), "value")),
    ]


class IEnumSpellingError(IUnknown):
    _iid_ = ENUM_SPELLING_ERROR_IID
    _methods_ = [
        COMMETHOD([], HRESULT, "Next", (["out"], POINTER(POINTER(ISpellingError)), "value")),
    ]


class ISpellChecker(IUnknown):
    _iid_ = SPELL_CHECKER_IID
    _methods_ = [
        COMMETHOD([], HRESULT, "get_LanguageTag", (["out"], POINTER(c_wchar_p), "value")),
        COMMETHOD(
            [],
            HRESULT,
            "Check",
            (["in"], c_wchar_p, "text"),
            (["out"], POINTER(POINTER(IEnumSpellingError)), "value"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "Suggest",
            (["in"], c_wchar_p, "word"),
            (["out"], POINTER(POINTER(IEnumString)), "value"),
        ),
        COMMETHOD([], HRESULT, "Add", (["in"], c_wchar_p, "word")),
        COMMETHOD([], HRESULT, "Ignore", (["in"], c_wchar_p, "word")),
        COMMETHOD([], HRESULT, "AutoCorrect", (["in"], c_wchar_p, "from_"), (["in"], c_wchar_p, "to")),
        COMMETHOD([], HRESULT, "GetOptionValue", (["in"], c_wchar_p, "optionId"), (["out"], POINTER(c_ubyte), "value")),
        COMMETHOD([], HRESULT, "get_OptionIds", (["out"], POINTER(POINTER(IEnumString)), "value")),
        COMMETHOD([], HRESULT, "get_Id", (["out"], POINTER(c_wchar_p), "value")),
        COMMETHOD([], HRESULT, "get_LocalizedName", (["out"], POINTER(c_wchar_p), "value")),
    ]


class ISpellCheckerFactory(IUnknown):
    _iid_ = SPELL_CHECKER_FACTORY_IID
    _methods_ = [
        COMMETHOD([], HRESULT, "get_SupportedLanguages", (["out"], POINTER(POINTER(IEnumString)), "value")),
        COMMETHOD([], HRESULT, "IsSupported", (["in"], c_wchar_p, "languageTag"), (["out"], POINTER(BOOL), "value")),
        COMMETHOD(
            [],
            HRESULT,
            "CreateSpellChecker",
            (["in"], c_wchar_p, "languageTag"),
            (["out"], POINTER(POINTER(ISpellChecker)), "value"),
        ),
    ]


@dataclass(frozen=True)
class SpellingIssue:
    start: int
    length: int
    word: str
    suggestions: tuple[str, ...]


class WindowsSpellChecker:
    def __init__(self, language_tag: str = "ru-RU", max_suggestions: int = 6) -> None:
        self.language_tag = language_tag
        self.max_suggestions = max_suggestions
        self._factory = CoCreateInstance(
            SPELL_CHECKER_FACTORY_CLSID,
            interface=ISpellCheckerFactory,
            clsctx=CLSCTX_INPROC_SERVER,
        )
        if not self._factory.IsSupported(language_tag):
            raise RuntimeError(f"Windows Spell Checking API не поддерживает язык {language_tag}.")
        self._checker = self._factory.CreateSpellChecker(language_tag)

    def check(self, text: str) -> list[SpellingIssue]:
        if not text.strip():
            return []

        issues: list[SpellingIssue] = []
        spelling_errors = self._checker.Check(text)
        while True:
            error = spelling_errors.Next()
            if not error:
                break

            start = int(error.get_StartIndex())
            length = int(error.get_Length())
            if length <= 0:
                continue

            word = text[start : start + length]
            issues.append(
                SpellingIssue(
                    start=start,
                    length=length,
                    word=word,
                    suggestions=tuple(self.suggest(word)),
                )
            )
        return issues

    def suggest(self, word: str) -> list[str]:
        suggestions: list[str] = []
        seen: set[str] = set()
        suggestion_enum = self._checker.Suggest(word)

        while len(suggestions) < self.max_suggestions:
            item = suggestion_enum.Next(1)
            if not item:
                break
            suggestion = item[0] if isinstance(item, tuple) else item
            if not suggestion or suggestion in seen:
                break
            suggestions.append(str(suggestion))
            seen.add(str(suggestion))

        return suggestions

    def add(self, word: str) -> None:
        clean_word = word.strip()
        if clean_word:
            self._checker.Add(clean_word)


def check_text(text: str, language_tag: str = "ru-RU") -> list[SpellingIssue]:
    CoInitialize()
    try:
        return WindowsSpellChecker(language_tag=language_tag).check(text)
    finally:
        CoUninitialize()


def add_word(word: str, language_tag: str = "ru-RU") -> None:
    CoInitialize()
    try:
        WindowsSpellChecker(language_tag=language_tag).add(word)
    finally:
        CoUninitialize()
