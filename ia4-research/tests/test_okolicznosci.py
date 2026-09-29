"""
Katalog okoliczności towarzyszących (D34). Wersja projektu: 0.46 (2026-09-29).

Wyłącznie sztuczne świece. Najważniejszy jest test „nie zagląda w przyszłość":
okoliczność policzona na świecy t musi mieć tę samą wartość, gdy obetniemy
dane zaraz za t. Bez tego cały rating byłby liczony z wiedzą o przyszłości.

    python tests/test_okolicznosci.py
"""
from __future__ import annotations

import json

import numpy as np

from _bars import frame, run
from ia4 import bars as BARS
from ia4 import okolicznosci as OK
from ia4.bars import REPO


def _rows(n, seed=7):
    """Sztuczna spółka: zmienność jak na prawdziwej świecy 1h, luki na otwarciu sesji,
    skoki wolumenu i zmienne fale trendu — żeby wszystkie okoliczności miały szansę odpalić."""
    rng = np.random.default_rng(seed)
    rows, p = [], 100.0
    for i in range(n):
        if i % 7 == 0 and i:                                   # otwarcie sesji: luka
            p *= 1 + rng.normal(0, 0.012)
        fala = 0.004 * np.sin(i / 55.0)                        # wolne fale trendu
        step = rng.normal(fala, 0.009 if (i // 140) % 2 else 0.004)
        o = p
        c = max(1.0, p * (1 + step))
        hi = max(o, c) * (1 + abs(rng.normal(0, 0.003)))
        lo = min(o, c) * (1 - abs(rng.normal(0, 0.003)))
        v = int(rng.integers(500, 5000) * (6 if rng.random() < 0.04 else 1))   # sporadyczne skoki
        rows.append((o, hi, lo, c, v))
        p = c
    return rows


def _bars(n=420, seed=7, market=True):
    df = frame(_rows(n, seed), symbol="X1")
    mkt = frame(_rows(n, seed + 1), symbol="SPY") if market else None
    return BARS.prepare(df, splits=[], market=mkt)


def test_katalog_spojny():
    doc = json.loads((REPO / "s1" / "okolicznosci.json").read_text(encoding="utf-8"))
    ids = [o["id"] for o in doc["okolicznosci"]]
    assert ids == OK.IDS, "s1/okolicznosci.json nie zgadza się z kodem — uruchom python3 -m ia4.okolicznosci"
    assert len(ids) == len(set(ids)) == doc["meta"]["liczba"] == len(OK.DEFS)
    assert 180 <= len(ids) <= 260                       # „około 200" (D34)
    assert all(o["grupa"] in OK.GRUPY for o in doc["okolicznosci"])
    assert all(len(o["opis"]) > 20 for o in doc["okolicznosci"]), "każda okoliczność musi mieć czytelny opis"


def test_ksztalt_i_typy():
    B = _bars()
    val, dfn = OK.evaluate(B)
    assert val.shape == dfn.shape == (B.n, len(OK.DEFS))
    assert val.dtype == bool and dfn.dtype == bool
    assert not np.any(val & ~dfn), "wartość TAK przy nie dającej się policzyć okoliczności"
    # na końcu serii (pełna historia) prawie wszystko musi być policzalne
    assert dfn[-1].mean() > 0.95


def test_nie_zaglada_w_przyszlosc():
    """Wartość na świecy t liczona z pełnej serii = wartość liczona z serii obciętej na t."""
    n = 420
    rows = _rows(n)
    mrows = _rows(n, 8)
    full = BARS.prepare(frame(rows, symbol="X1"), splits=[], market=frame(mrows, symbol="SPY"))
    v_full, d_full = OK.evaluate(full)
    for t in (300, 355, 419):
        cut = BARS.prepare(frame(rows[:t + 1], symbol="X1"), splits=[],
                           market=frame(mrows[:t + 1], symbol="SPY"))
        v_cut, d_cut = OK.evaluate(cut)
        bad = np.flatnonzero((v_full[t] != v_cut[-1]) | (d_full[t] != d_cut[-1]))
        assert not len(bad), f"świeca {t}: zagląda w przyszłość — {[OK.IDS[j] for j in bad[:5]]}"


def test_rozgrzewka_blokuje_poczatek():
    B = _bars(n=200)
    _, dfn = OK.evaluate(B)
    dlugie = [OK.IDS.index(x) for x in ("T_SMA140_ROSNIE", "P_POD_SZCZYTEM_140_5", "M_SPY_NAD_SMA140")]
    assert not dfn[0:140, dlugie].any(), "długie okna nie mogą być policzalne na początku historii"
    krotkie = OK.IDS.index("K_ZIELONA")
    assert dfn[5, krotkie]


def test_wartosci_recznie_policzone():
    """Rosnąca seria: świece zielone, cena nad średnimi, nowe szczyty."""
    rows, p = [], 100.0
    for _ in range(300):
        o, c = p, p * 1.003
        rows.append((o, c * 1.0005, o * 0.9995, c, 1000))
        p = c
    B = BARS.prepare(frame(rows, symbol="X1"), splits=[], market=None)
    val, dfn = OK.evaluate(B)
    i = 299
    for oid in ("K_ZIELONA", "T_SMA20_ROSNIE", "T_SMA20_CENA_POWYZEJ", "T_CENA_NAD_WSZYSTKIMI",
                "P_NOWY_SZCZYT_35", "R_WZROST_7_1", "T_WACHLARZ_WZROSTOWY"):
        j = OK.IDS.index(oid)
        assert dfn[i, j] and val[i, j], oid
    for oid in ("K_CZERWONA", "P_NOWY_DOLEK_35", "R_SPADEK_7_1", "T_CENA_POD_WSZYSTKIMI"):
        j = OK.IDS.index(oid)
        assert dfn[i, j] and not val[i, j], oid
    # bez SPY okoliczności rynkowe są nie do policzenia, nie „fałszywe"
    j = OK.IDS.index("M_SPY_NAD_SMA140")
    assert not dfn[i, j]


def test_dziura_wylacza_okno():
    """Po dziurze w danych (D27) okoliczności z długim oknem są nie do policzenia."""
    rows = _rows(300)
    df = frame(rows, symbol="X1")
    df = df.drop(df.index[150:157]).reset_index(drop=True)     # wycięta sesja
    B = BARS.prepare(df, splits=[], market=None)
    _, dfn = OK.evaluate(B)
    h = int(np.flatnonzero(B.hole_before)[0])
    j = OK.IDS.index("R_WZROST_35_1")
    assert not dfn[h, j] and not dfn[h + 10, j]
    assert dfn[h + 40, j]


def test_rozklad_nie_jest_zdegenerowany():
    """Żadna okoliczność nie może być stale TAK ani stale NIE na losowych danych — byłaby bezużyteczna."""
    B = _bars(n=1400, seed=11)
    val, dfn = OK.evaluate(B)
    martwe = []
    for j, oid in enumerate(OK.IDS):
        d = dfn[:, j]
        if d.sum() < 50:
            continue
        r = val[d, j].mean()
        if r == 0.0 or r == 1.0:
            martwe.append(oid)
    assert len(martwe) <= 12, f"stała wartość na losowych danych: {martwe[:15]}"


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
