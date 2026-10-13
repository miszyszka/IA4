"""
IA 4 — ustawienia AI Investor: limity ryzyka, koszty, model (instrukcja, sekcje 11c.2, 11c.6–11c.7).
Wersja projektu: 1.37 (2026-10-13) — musi zgadzać się z IA4_INSTRUKCJA.md

DEFAULTS to wartości z instrukcji. Nadpisuje je `ai/config.json` na branchu `ai` (zmienia człowiek
z Claude, jak research/config.json) — nieznane klucze są ignorowane z ostrzeżeniem. Zmiana wartości
domyślnej = zmiana instrukcji.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULTS = {
    # --- portfel (11c.6)
    "capital": 100_000.0,                 # USD, od startedAt
    # --- ryzyko (11c.7)
    "risk_pct": 0.5,                      # % stanu konta ryzykowane na transakcję (strata na SL z kosztami)
    "risk_dial": 1.0,                     # 0,25–1,0; Manager (AI-4) może tylko zmniejszyć
    "max_positions": 12,                  # otwarte + oczekujące
    "max_value_pct": {"stock": 20.0, "crypto": 20.0, "fx": 50.0},   # wartość jednej pozycji, % stanu konta
    "gross_max_pct": 200.0,               # ekspozycja brutto, % stanu konta
    "budget_pct": 6.0,                    # łączne ryzyko otwartych i oczekujących (12 × 0,5%)
    "own_budget_pct": 0.6,                # łączne ryzyko własnych pomysłów
    "daily_stop_pct": 2.0,                # wynik doby UTC ≤ −2% → bez nowych wejść do końca doby
    "dd_half_pct": 10.0,                  # obsunięcie od szczytu ≥ 10% → risk_dial 0,5
    "dd_stop_pct": 20.0,                  # ≥ 20% → bez nowych wejść do decyzji człowieka (halt_ack)
    "halt_ack": None,                     # ISO czas: człowiek potwierdził wznowienie po zatrzymaniu
    # --- mnożniki ryzyka według podstawy wejścia (11c.8)
    "mult": {"bazowa_wybrana": 1.0, "bazowa": 0.5, "inkubacja": 0.25, "zatwierdzona": 1.0,
             "own": 0.25, "fx_prognoza": 0.5, "wycofana": 0.0},
    # --- koszty (11c.6)
    "cost_stock_pct": 0.005,              # % wartości przy wejściu i przy wyjściu
    "cost_crypto_pct": 0.05,
    "fx_spread_pips": {"EURUSD": 0.8, "USDJPY": 0.9, "GBPUSD": 1.2, "AUDUSD": 1.0, "USDCAD": 1.5, "USDCHF": 1.5,
                       "NZDUSD": 1.6, "EURJPY": 1.6, "GBPJPY": 2.5, "EURGBP": 1.2},   # na transakcję: ½ wejście, ½ wyjście
    # --- własny pomysł (11c.6)
    "own_rr_min": 1 / 3, "own_rr_max": 3.0,   # TP/SL od 1:3 do 3:1
    "own_min_sl_atr": 1.0,                # SL ≥ 1 × ATR14 instrumentu
    "own_max_bars": 120,
    "own_per_round": 1,                   # najwyżej tyle własnych pomysłów w jednej rundzie
    # --- prognoza FX jako podstawa wejścia (tylko z udowodnioną przewagą kierunku)
    "fx_forecast_limit": 48,
    # --- runda
    "max_candidates": 12,
    "note_max": 600,
    "lessons_max": 50,
    # --- model (11c.2)
    "model": "qwen2.5:14b",
    "num_ctx": 8192,
    "temperature_investor": 0.2,
    "llm_retries": 2,
    "llm_timeout_sec": 600,
    # --- pliki
    "xlsx_path": "~/Desktop/IA4/AI-INVESTOR.xlsx",
    "playbook_refresh_hours": 6,
}


def merged(over: dict | None, log=print) -> dict:
    """DEFAULTS + nadpisania (słowniki — scalane o jeden poziom)."""
    cfg = copy.deepcopy(DEFAULTS)
    for k, v in (over or {}).items():
        if k.startswith("_"):
            continue
        if k not in DEFAULTS:
            log(f"  ! ai/config.json: nieznany klucz „{k}” — pomijam")
            continue
        if isinstance(DEFAULTS[k], dict) and isinstance(v, dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    cfg["risk_dial"] = min(1.0, max(0.25, float(cfg["risk_dial"])))
    return cfg


def load(path: Path | None, log=print) -> dict:
    over = {}
    if path is not None and path.exists():
        try:
            over = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log(f"  ! ai/config.json nieczytelny ({e}) — wartości domyślne")
    return merged(over, log)


def xlsx_path(cfg: dict) -> Path:
    return Path(cfg["xlsx_path"]).expanduser()
