"""
IA 4 — wskaźniki (Etap 1b).
Wersja projektu: 0.37 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Każdy wskaźnik z instrukcji 1.3, policzony dokładnie tak samo, jak go tam
opisano — bo w Etapie 4 te same wzory liczy Apps Script (D2), a drobna różnica
(inny start EMA, inna definicja RVOL) dałaby inne sygnały na żywo niż
w backteście. Każda funkcja ma test na ręcznie policzonym przykładzie w
`tests/test_indicators.py`.

WEJŚCIE: jeden instrument naraz — `pandas.DataFrame` posortowany po (date, slot),
z kolumnami symbol, date, slot (1–7), o, h, l, c, v — dokładnie to, co zwraca
`ia4.data.load()`. Funkcje traktują wiersze jako CIĄGŁY SZEREG (kontrakt
silnika, S1_KATALOG_BAZOWY.md pkt 9): nie znają kalendarza sesji i nie widzą
przerw w danych. Wykrywanie prawdziwych dziur (brakująca świeca, niepełna
sesja) i odrzucanie sygnałów, których okno je obejmuje, to osobna warstwa —
`ia4.bars` / `ia4.signals` (D27, S1_KATALOG_BAZOWY.md pkt 13, od 0.36) — bo
wymaga kalendarza sesji NYSE (`ia4.nyse`), którego wskaźniki same z siebie nie mają.

ROZGRZEWKA: każda funkcja zwraca serię tej samej długości co wejście, z NaN
tam, gdzie wskaźnik nie ma jeszcze pełnej historii (instrukcja 1.3, „sygnał
jest ważny dopiero przy pełnej historii najdłuższego okna”). Nic nie jest
dociągane ani ekstrapolowane wstecz.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
#  Pomocnicze
# ---------------------------------------------------------------------------
def _as_series(x) -> pd.Series:
    return x if isinstance(x, pd.Series) else pd.Series(x)


def _wilder_smooth(values: pd.Series, n: int) -> pd.Series:
    """
    Metoda Wildera (α = 1/n), start od średniej prostej z pierwszych n wartości
    (instrukcja 1.3, RSI/ATR). `values` może mieć wiodące NaN (np. różnice
    cen zaczynają się od indeksu 1) — rozgrzewka liczy się od pierwszej
    dostępnej wartości, nie od początku serii.
    """
    values = _as_series(values)
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < n:
        return out
    idx = valid.index
    seed = valid.iloc[:n].mean()
    out.loc[idx[n - 1]] = seed
    prev = seed
    for i in range(n, len(valid)):
        prev = (prev * (n - 1) + valid.iloc[i]) / n
        out.loc[idx[i]] = prev
    return out


# ---------------------------------------------------------------------------
#  Średnie
# ---------------------------------------------------------------------------
def sma(close: pd.Series, n: int) -> pd.Series:
    """SMA(n) — średnia arytmetyczna n zamknięć."""
    return _as_series(close).rolling(n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """
    EMA(n) — α = 2/(n+1), start od SMA(n) z pierwszych n dostępnych wartości
    (instrukcja 1.3). Działa też na serii z wiodącymi NaN (np. EMA z MACD),
    o ile po pierwszej dostępnej wartości seria już nie ma dziur — dokładnie
    tak wygląda każda kompozycja wskaźników w tym module.
    """
    close = _as_series(close)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    valid = close.dropna()
    if len(valid) < n:
        return out
    alpha = 2.0 / (n + 1)
    idx = valid.index
    seed = valid.iloc[:n].mean()
    out.loc[idx[n - 1]] = seed
    prev = seed
    for i in range(n, len(valid)):
        prev = alpha * valid.iloc[i] + (1 - alpha) * prev
        out.loc[idx[i]] = prev
    return out


def vwma(tp_times_v: pd.Series, v: pd.Series, n: int) -> pd.Series:
    """VWMA(n) — jak VWAP, ale w kroczącym oknie n świec zamiast sesji."""
    tp_times_v, v = _as_series(tp_times_v), _as_series(v)
    num = tp_times_v.rolling(n).sum()
    den = v.rolling(n).sum()
    return num / den.replace(0, np.nan)


# ---------------------------------------------------------------------------
#  Oscylatory (metoda Wildera) i zmienność
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI(n), metoda Wildera."""
    close = _as_series(close)
    diff = close.diff()
    gain = diff.clip(lower=0)
    loss = -diff.clip(upper=0)
    avg_gain = _wilder_smooth(gain, n)
    avg_loss = _wilder_smooth(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    high, low, close = _as_series(high), _as_series(low), _as_series(close)
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """ATR(n), metoda Wildera."""
    return _wilder_smooth(true_range(high, low, close), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> dict[str, pd.Series]:
    """
    Wstęga Bollingera(n, k) — SMA(n) ± k × odchylenie standardowe POPULACYJNE
    (dzielone przez n, nie n-1). Szerokość = (górna − dolna) / SMA.
    """
    close = _as_series(close)
    mid = sma(close, n)
    std = close.rolling(n).std(ddof=0)
    upper, lower = mid + k * std, mid - k * std
    width = (upper - lower) / mid
    return {"mid": mid, "upper": upper, "lower": lower, "width": width}


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    """MACD(12,26,9) — EMA(fast) − EMA(slow); linia sygnału = EMA(signal) z MACD."""
    close = _as_series(close)
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return {"macd": line, "signal": sig, "hist": line - sig}


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               n: int = 14, smooth: int = 3, d: int = 3) -> dict[str, pd.Series]:
    """Stochastyk — %K(14) wygładzony SMA(3), %D = SMA(3) z %K."""
    high, low, close = _as_series(high), _as_series(low), _as_series(close)
    hh, ll = high.rolling(n).max(), low.rolling(n).min()
    raw_k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    k = raw_k.rolling(smooth).mean()
    d_line = k.rolling(d).mean()
    return {"k": k, "d": d_line}


# ---------------------------------------------------------------------------
#  Wolumen
# ---------------------------------------------------------------------------
def vwap_session(date: pd.Series, high: pd.Series, low: pd.Series,
                  close: pd.Series, v: pd.Series) -> pd.Series:
    """VWAP sesji — Σ(TP × v) / Σv od pierwszej świecy sesji; zeruje się co sesję."""
    date, high, low, close, v = (_as_series(date), _as_series(high),
                                  _as_series(low), _as_series(close), _as_series(v))
    tp = (high + low + close) / 3.0
    num = (tp * v).groupby(date).cumsum()
    den = v.groupby(date).cumsum()
    return num / den.replace(0, np.nan)


def typical_price_x_volume(high: pd.Series, low: pd.Series, close: pd.Series, v: pd.Series) -> pd.Series:
    """TP × v — potrzebne osobno jako wejście do vwma()."""
    high, low, close, v = _as_series(high), _as_series(low), _as_series(close), _as_series(v)
    return (high + low + close) / 3.0 * v


def obv(close: pd.Series, v: pd.Series) -> pd.Series:
    """OBV — suma narastająca: +v gdy zamknięcie wyższe, −v gdy niższe, bez zmian gdy równe."""
    close, v = _as_series(close), _as_series(v)
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * v).cumsum()


def rvol(slot: pd.Series, v: pd.Series, lookback_sessions: int = 20) -> pd.Series:
    """
    RVOL (wolumen względny) — wolumen świecy / średni wolumen TEJ SAMEJ ŚWIECY
    DNIA (ten sam numer 1–7) z `lookback_sessions` poprzednich sesji.

    NIGDY przez średnią z ostatnich N świec: wolumen w ciągu dnia ma kształt
    litery U, więc zwykła średnia oznaczałaby każde otwarcie jako "powyżej
    normy" (instrukcja 1.3). Implementacja: dla każdego numeru świecy osobno,
    rolling mean przesunięty o 1 (nie licząc bieżącej), po czym wynik wraca
    na oryginalne pozycje.
    """
    slot, v = _as_series(slot), _as_series(v)
    avg = pd.Series(np.nan, index=v.index, dtype=float)
    for s in slot.unique():
        mask = slot == s
        sub = v[mask]
        avg.loc[mask] = sub.shift(1).rolling(lookback_sessions).mean()
    return v / avg.replace(0, np.nan)


# ---------------------------------------------------------------------------
#  Przecięcia
# ---------------------------------------------------------------------------
def cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    """A przecina B w górę na świecy t: A[t] > B[t] i A[t-1] <= B[t-1]."""
    a, b = _as_series(a), _as_series(b)
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_down(a: pd.Series, b: pd.Series) -> pd.Series:
    """A przecina B w dół na świecy t: A[t] < B[t] i A[t-1] >= B[t-1]."""
    a, b = _as_series(a), _as_series(b)
    return (a < b) & (a.shift(1) >= b.shift(1))
