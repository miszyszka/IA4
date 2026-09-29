"""
Sprawdzian przebiegu 4 na poletku (D35). Wersja projektu: 0.47 (2026-09-29).

Wyłącznie sztuczne świece. Najważniejszy test: `test_rating_B_nie_zalezy_od_poletka` —
zmiana wyłącznie danych poletka nie może zmienić ratingu, którym wersja B ocenia
transakcje. Gdyby zmieniała, „sprawdzian" znałby odpowiedź.

    python tests/test_poletko4.py
"""
from __future__ import annotations

import json

import numpy as np

from _bars import frame, run
from ia4 import backtest as BT
from ia4 import poletko4 as P
from ia4 import przebieg4 as P4
from ia4.bars import REPO


def _iid(n, seed, mu=0.0):
    """Spacer losowy bez pamięci: żadnych fal trendu, stała zmienność."""
    rng = np.random.default_rng(seed)
    rows, p = [], 100.0
    for _ in range(n):
        o = p
        c = max(1.0, p * (1 + rng.normal(mu, 0.006)))
        rows.append((o, max(o, c) * (1 + abs(rng.normal(0, 0.002))),
                     min(o, c) * (1 - abs(rng.normal(0, 0.002))), c, int(rng.integers(1000, 3000))))
        p = c
    return rows


def _mini(n_sig=2, n_sym=4, n=700, seed0=200):
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    akt = [s for s in cat["signals"] if s["status"] in ("aktywny", "kontrolny")]
    mini = {"meta": dict(cat["meta"]), "signals": akt[:n_sig]}
    syms = [f"S{i:02d}" for i in range(n_sym)]
    frames = {s: frame(_iid(n, seed0 + i), symbol=s) for i, s in enumerate(syms)}
    frames["SPY"] = frame(_iid(n, 77), symbol="SPY")
    daty = sorted(set(frames[syms[0]]["date"]))
    return mini, frames, syms, daty


def test_kolumny_i_podsumowanie():
    mini, frames, syms, daty = _mini()
    df, meta = P.run(mini, frames, frames["SPY"], syms, daty[len(daty) // 2], progress=lambda *_: None)
    assert list(df.columns) == P.COLUMNS
    d = df[df.B_transakcji > 0]
    assert len(d) > 0
    # A, B, C liczone na poletku: B i C to dokładnie połowa transakcji z A
    assert (d.B_transakcji == np.maximum(1, d.A_transakcji // 2)).all()
    assert (d.C_transakcji == d.B_transakcji).all()
    assert (d.U_transakcji > 0).all()
    s = meta["podsumowanie"]
    assert s["z_transakcjami_na_poletku"] == len(d)
    assert "purging" in meta and meta["decyzja"] == "D35"


def test_purging_odcina_transakcje_z_wyjsciem_na_poletku():
    mini, frames, syms, daty = _mini()
    df, _ = P.run(mini, frames, frames["SPY"], syms, daty[len(daty) // 2], progress=lambda *_: None)
    d = df[df.B_transakcji > 0]
    # rating uczony na mniejszej liczbie niż wszystkie transakcje z odkrywania
    assert (d.B_uczonych_na <= d.U_transakcji).all()
    assert (d.B_uczonych_na > 0).all()


def test_rating_B_nie_zalezy_od_poletka():
    """Podmiana danych SAMEGO poletka nie zmienia ratingu użytego w wersji B ani wyników U."""
    mini, frames, syms, daty = _mini(n_sig=2, n_sym=4)
    split = daty[len(daty) // 2]
    inne = {}
    for s, df0 in frames.items():
        d2 = df0.copy()
        m = d2["date"].to_numpy() >= split
        rng = np.random.default_rng(999)
        czyn = 1 + rng.normal(0, 0.05, m.sum())          # inne ceny tylko na poletku
        for col in ("o", "h", "l", "c"):
            d2.loc[m, col] = d2.loc[m, col].to_numpy() * czyn
        inne[s] = d2
    a, _ = P.run(mini, frames, frames["SPY"], syms, split, progress=lambda *_: None)
    b, _ = P.run(mini, inne, inne["SPY"], syms, split, progress=lambda *_: None)
    a, b = a.set_index("id"), b.set_index("id")
    for col in ("U_transakcji", "U_skutecznosc", "U_ekspektancja", "B_uczonych_na",
                "ok_mocnych_odkrywanie", "ok_najlepsza_odkrywanie", "ok_najlepsza_rating"):
        x, y = a[col], b.loc[a.index, col]
        assert x.equals(y), f"{col}: zmiana danych poletka wpłynęła na to, co policzono z odkrywania"
    assert not a["B_skutecznosc"].equals(b.loc[a.index, "B_skutecznosc"]), "poletko w ogóle nie wpłynęło na B"


def test_U_zgodne_z_przebiegiem_4():
    """Gdy poletko jest puste, wersja U musi dać to samo co kolumny b_* z przebiegu 4."""
    mini, frames, syms, daty = _mini(n_sig=1, n_sym=3)
    df, _ = P.run(mini, frames, frames["SPY"], syms, "2999-01-01", progress=lambda *_: None)
    ref, _, _ = P4.run(mini, frames, frames["SPY"], {"main": syms[:1], "control": syms[1:]},
                    boot=99, progress=lambda *_: None)
    a, r = df.set_index("id"), ref.set_index("id")
    assert (a["U_transakcji"] == r.loc[a.index, "b_transakcji"]).all()
    assert np.allclose(a["U_ekspektancja"].astype(float), r.loc[a.index, "b_ekspektancja"].astype(float),
                       equal_nan=True)
    assert (a["A_transakcji"] == 0).all() and a["B_skutecznosc"].isna().all()


def test_iluzja_wieksza_niz_sprawdzian():
    """
    Na danych bez pamięci (spacer losowy) filtr uczony na TYCH SAMYCH transakcjach
    (C) poprawia wynik mocno, a filtr uczony na innym okresie (B) — prawie wcale.
    To jest podziałka do czytania prawdziwego przebiegu: L38.

    Pojedyncza strategia może mieć C nieco gorsze od A, bo rating maksymalizuje udział
    TP, a skuteczność mierzy zysk — przy SL większym od TP wyjście z limitu czasu też
    bywa zyskowne. Dlatego patrzymy na średnią, nie na każdy wiersz.
    """
    mini, frames, syms, daty = _mini()
    df, _ = P.run(mini, frames, frames["SPY"], syms, daty[len(daty) // 2], progress=lambda *_: None)
    d = df[df.B_transakcji > 0]
    assert d.zysk_filtra_C.mean() > 5.0, "filtr w próbie powinien dawać wyraźną (pozorną) poprawę"
    assert d.zysk_filtra_C.mean() > d.zysk_filtra_B.mean() + 4.0, "iluzja musi być wyraźnie większa"
    assert abs(d.zysk_filtra_B.mean()) < 3.0, "na danych bez pamięci sprawdzian powinien wyjść około zera"
    assert (d.zysk_filtra_C < 0).mean() < 0.2


def test_stawki_w_zakresie():
    mini, frames, syms, daty = _mini()
    df, _ = P.run(mini, frames, frames["SPY"], syms, daty[len(daty) // 2], progress=lambda *_: None)
    d = df[df.B_transakcji > 0]
    for col in ("B_srednia_stawka", "C_srednia_stawka"):
        assert (d[col] >= P4.STAWKA_MIN - 1e-9).all() and (d[col] <= P4.STAWKA_MAX + 1e-9).all()
    assert (d.U_srednia_stawka == 10.0).all() and (d.A_srednia_stawka == 10.0).all()


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
