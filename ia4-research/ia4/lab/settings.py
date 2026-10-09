"""
IA 4 — ustawienia poszukiwania (domyślne). Wersja projektu: 1.24 (2026-10-09)

Wartości domyślne są tu. Claude (albo człowiek) nadpisuje je plikiem
research/config.json na branchu `research` — Python czyta go przy starcie
i co 30 minut, więc zmiana działa bez restartu i bez `git pull` na Macu.
Znaczenie progów: IA4_INSTRUKCJA.md, sekcja 9.
"""

from __future__ import annotations

import copy

MA_TYPES = ["SMA", "EMA", "WMA", "HMA", "DEMA", "TEMA", "KAMA", "VWMA", "ZLEMA"]

DEFAULTS = {
    # --- hipotezy wyjścia (zawsze wszystkie kombinacje) --------------------
    "sl_grid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "tp_grid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],

    # --- kryteria (sekcja 9.3) --------------------------------------------
    "min_trades_main": 30,        # grupa główna
    "min_trades_vault": 10,       # skarbiec
    "pf_min": 1.5,                # PF grupy głównej i PF łączny (główna + skarbiec)
    "pf_sltp_neighbors": 1.2,     # mediana PF sąsiednich SL/TP (±1 pkt proc.)
    "folds_min_ok": 3,            # z 4 okresów grupy głównej z PF > 1
    "pf_param_neighbors": 1.2,    # mediana PF strategii o sąsiednich parametrach
    "param_neighbors_share_ok": 0.6,   # udział sąsiadów z PF ≥ 1
    "max_param_neighbors": 12,
    # przewaga nad wejściem „na ślepo” (PF strategii / PF losowego wejścia z tym samym
    # wyjściem); 0 = bez odrzucania (sekcja 9.3)
    "pf_edge_min": 1.2,
    # duplikat: ten sam kierunek i ≥ tyle wspólnych świec wejścia (Jaccard) co strategia
    # już zapisana albo już odrzucona przez skarbiec
    "dup_jaccard": 0.5,
    "vault_pf_min": 1.2,          # PF samego skarbca (oprócz PF łącznego ≥ pf_min)
    "tp_sl_ratio": [0.3334, 3.0], # dozwolony stosunek TP/SL (od 1:3 do 3:1)
    "max_per_group": 5,           # najwyżej tyle aktywnych strategii w jednej grupie (sekcja 9.5)
    "max_time_share": 0.10,       # najwyżej tyle transakcji może się kończyć limitem czasu
    "min_tp_share": 0.0,          # najmniej tyle transakcji musi kończyć się na TP (0 = bez progu)

    # --- złożoność ---------------------------------------------------------
    "period_min": 5,
    "period_max": 150,
    "max_lines": 3,
    "max_filters": 2,

    # --- siatka (etap 1 poszukiwania) --------------------------------------
    "ma_types": MA_TYPES,
    "coarse_periods": [5, 7, 10, 13, 17, 21, 26, 32, 40, 50, 60, 75, 90, 110, 130, 150],
    "grid_max_bars": [None, 35],
    "grid_converge": [[3, 1], [3, 2], [5, 2]],
    "grid_revert_k": [1.0, 2.0],
    "grid_reexpand_n": 2,

    # --- adaptacja (etap 2 poszukiwania) -----------------------------------
    "max_bars_options": [None, 7, 14, 35, 70],
    "pool_size": 400,
    "pool_per_family": 25,
    "short_share": 0.5,           # udział rodziców z puli short w adaptacji
    "explore_share": 0.2,         # część zadań losowanych od zera z pełnej przestrzeni
    "batch": 0,                   # 0 = 24 × liczba procesów

    # --- praca -------------------------------------------------------------
    "log_every_min": 30,
    "dp_refresh_min": 60,         # co ile minut dociągać świece doubleProof i przeliczać weryfikację
    "workers": 0,                 # 0 = liczba rdzeni − 1
    "paused_kinds": [],           # np. ["revert"] — Claude może wyłączać rodzaje sygnałów
    # true = poszukiwanie zamknięte: python -m ia4.lab tylko synchronizuje, sprawdza bazę
    # i przelicza weryfikację doubleProof, nie szuka i nie zmienia strategii (sekcja 9.7)
    "search_closed": False,
}


def merged(overrides: dict | None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    for k, v in (overrides or {}).items():
        if k.startswith("_"):
            continue                       # komentarze w config.json
        if k in cfg:
            cfg[k] = v
    return cfg
