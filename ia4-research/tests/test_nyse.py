"""
Kalendarz NYSE w Pythonie = ten sam co w Apps Script (Etap 1b). Wersja projektu: 0.47 (2026-09-29).

Silnik rozpoznaje dziury w danych (D27) po kalendarzu. Gdyby lista świąt albo
sesji skróconych w Pythonie rozjechała się z Apps Script, audyt i silnik
widziałyby inne dziury — dokładnie typ błędu z L12. Ten test czyta oba
pliki .gs i porównuje.

    python tests/test_nyse.py
"""
from __future__ import annotations

import re

from _bars import run
from ia4 import nyse
from ia4.bars import REPO


def _keys(path, const):
    text = (REPO / path).read_text(encoding="utf-8")
    block = re.search(const + r"\s*=\s*\{(.*?)\};", text, re.S)
    assert block, f"nie znalazłem {const} w {path}"
    return set(re.findall(r"'(\d{4}-\d{2}-\d{2})'", block.group(1)))


def test_holidays_match_history_gs():
    gs = _keys("History.gs", "US_MARKET_HOLIDAYS")
    assert gs == nyse.HOLIDAYS, f"różnica: tylko .gs {sorted(gs - nyse.HOLIDAYS)}, tylko py {sorted(nyse.HOLIDAYS - gs)}"


def test_early_close_matches_project_gs():
    gs = _keys("Project.gs", "EARLY_CLOSE_DAYS")
    assert gs == nyse.EARLY_CLOSE, f"różnica: {sorted(gs ^ nyse.EARLY_CLOSE)}"


def test_calendar_basics():
    assert nyse.is_trading_day("2025-03-03") and not nyse.is_trading_day("2025-03-01")   # sobota
    assert not nyse.is_trading_day("2025-04-18")                                        # Wielki Piątek
    assert nyse.expected_bars("2025-11-28") == 4 and nyse.expected_bars("2025-11-26") == 7
    assert nyse.next_trading_day("2025-04-17") == "2025-04-21"
    assert nyse.is_last_of_month("2025-02-28") and not nyse.is_last_of_month("2025-02-27")
    assert nyse.is_last_of_week("2025-04-17")


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
