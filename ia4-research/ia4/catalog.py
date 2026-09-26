"""
IA 4 — katalog sygnałów S1 (Etap 1a).

Wersja projektu: 0.27 (2026-09-26) — musi zgadzać się z IA4_INSTRUKCJA.md

Jedno miejsce, w którym zdefiniowany jest cały katalog S1 (D20). Z tych
definicji powstaje plik `s1/catalog.json`, a z niego arkusz S1 (Apps Script)
i — w Etapie 1b — silnik.

Zasady budowy:
- **Opis słowny powstaje z parametrów**, nie jest pisany osobno. Dzięki temu
  tekst w arkuszu i JSON, który czyta silnik, nie mogą się rozjechać.
- **Lustra powstają mechanicznie** z sygnałów bazowych (odbicie kierunku),
  więc S085–S168 zawsze odpowiadają S001–S084 jeden do jednego.
- **Katalog powstaje na ślepo (D21):** ten moduł nie czyta żadnych świec i nie
  liczy żadnego wyniku. Częstość sygnałów dopisuje dopiero Etap 1b.

Konwencje wspólne dla wszystkich definicji (instrukcja 1.3):
- t = świeca sygnału, już zamknięta. O/H/L/C/V — otwarcie, maksimum, minimum,
  zamknięcie, wolumen świecy. Indeks t−1 = poprzednia świeca w ciągłym
  szeregu (przez noce i weekendy).
- „Sesja” = świece jednego dnia handlowego; numer świecy w sesji 1–7.
  „Ostatnia świeca sesji” to ostatnia faktycznie istniejąca (dni skrócone!).
- Zdarzenie: nowe rodziny odpalają na świecy, w której warunek STAJE SIĘ
  prawdziwy. Sygnały bazowe zachowują swoją pierwotną postać (część jest
  poziomowa; pkt 8 kontraktu silnika ignoruje sygnały w trakcie pozycji).
- Progi procentowe są liczone względem ceny odniesienia: „spadek o ≥ x%”
  oznacza C[t] ≤ ref × (1 − x/100), „wzrost o ≥ x%” — C[t] ≥ ref × (1 + x/100).

Uruchomienie (z katalogu ia4-research, w klonie całego repozytorium):
    python -m ia4.catalog            # zapisuje ../s1/catalog.json
    python -m ia4.catalog --check    # tylko sprawdza, niczego nie zapisuje
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_VERSION = "0.27"
CATALOG_VERSION = "S1-szkic-1"     # zmienia się przy każdej zmianie definicji
MAX_SIGNALS = 300                   # D19
MAX_WINDOW_BARS = 350               # instrukcja 1.3: najdłuższe okno w S1
BARS_PER_SESSION = 7
# Rozgrzewka = okno + to, czego potrzeba „obok” okna: poprzednia świeca do
# wykrycia przecięcia albo bieżąca sesja przy oknach liczonych w sesjach.
MAX_WARMUP_BARS = MAX_WINDOW_BARS + BARS_PER_SESSION
RVOL_SESSIONS = 20                  # instrukcja 1.3: RVOL względem 20 sesji
RECURSIVE_LIVE_FACTOR = 3           # patrz _live_lookback

SL_TP_GRID = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5]   # D4
H_DEFAULT = [                                            # D5 — punkt wyjścia dla D10
    {"tp_max": 1.0, "bars": 14},
    {"tp_max": 2.5, "bars": 35},
    {"tp_max": 5.0, "bars": 70},
]
DIRECTIONS = ["L", "S"]            # D9

CATEGORIES = {
    "H1": "Powrót do średniej",
    "H2": "Trend: średnie kroczące, MACD, VWAP",
    "H3": "Wybicia",
    "H4": "Zmienność",
    "H5": "Oscylatory i dywergencje",
    "H6": "Sesja i kalendarz",
    "H7": "Kontekst rynku",
    "H8": "Wolumen",
}

# ---------------------------------------------------------------------------
#  Formatowanie
# ---------------------------------------------------------------------------
def num(x) -> str:
    """Liczba po polsku: 1.5 → '1,5', 2.0 → '2'."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return str(x).replace(".", ",")


def code_num(x) -> str:
    """Liczba w kodzie sygnału (kropka, jak w katalogu bazowym)."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return str(x)


def sesje(n_bars: int) -> str:
    """„1 sesja”, „3 sesje”, „5 sesji”, „≈ 2,9 sesji” — ile sesji to n świec."""
    s = n_bars / BARS_PER_SESSION
    if not s.is_integer():
        return f"≈ {num(round(s, 1))} sesji"
    s = int(s)
    if s == 1:
        return "1 sesja"
    if s % 10 in (2, 3, 4) and s % 100 not in (12, 13, 14):
        return f"{s} sesje"
    return f"{s} sesji"


# ---------------------------------------------------------------------------
#  Katalog bazowy (S001–S084) — kody i parametry z S1_KATALOG_BAZOWY.md.
#  Test tests/test_catalog.py pilnuje, żeby ta lista była identyczna z plikiem.
# ---------------------------------------------------------------------------
BASE = [
    ('DROP_N2_X1.5', {"type":"DROP","n":2,"pct":1.5}),
    ('DROP_N2_X2.5', {"type":"DROP","n":2,"pct":2.5}),
    ('DROP_N2_X4', {"type":"DROP","n":2,"pct":4}),
    ('DROP_N3_X2', {"type":"DROP","n":3,"pct":2}),
    ('DROP_N3_X3', {"type":"DROP","n":3,"pct":3}),
    ('DROP_N3_X5', {"type":"DROP","n":3,"pct":5}),
    ('DROP_N5_X2.5', {"type":"DROP","n":5,"pct":2.5}),
    ('DROP_N5_X4', {"type":"DROP","n":5,"pct":4}),
    ('DROP_N5_X6', {"type":"DROP","n":5,"pct":6}),
    ('DROP_N7_X3', {"type":"DROP","n":7,"pct":3}),
    ('DROP_N7_X5', {"type":"DROP","n":7,"pct":5}),
    ('DROP_N7_X8', {"type":"DROP","n":7,"pct":8}),
    ('DROP_N14_X5', {"type":"DROP","n":14,"pct":5}),
    ('DROP_N14_X8', {"type":"DROP","n":14,"pct":8}),
    ('DROP_N14_X12', {"type":"DROP","n":14,"pct":12}),
    ('RED_K3_X1', {"type":"RED","k":3,"pct":1}),
    ('RED_K3_X2', {"type":"RED","k":3,"pct":2}),
    ('RED_K3_X3', {"type":"RED","k":3,"pct":3}),
    ('RED_K4_X1.5', {"type":"RED","k":4,"pct":1.5}),
    ('RED_K4_X2.5', {"type":"RED","k":4,"pct":2.5}),
    ('RED_K4_X4', {"type":"RED","k":4,"pct":4}),
    ('RED_K5_X2', {"type":"RED","k":5,"pct":2}),
    ('RED_K5_X3', {"type":"RED","k":5,"pct":3}),
    ('RED_K5_X5', {"type":"RED","k":5,"pct":5}),
    ('RED_K6_X2.5', {"type":"RED","k":6,"pct":2.5}),
    ('RED_K6_X4', {"type":"RED","k":6,"pct":4}),
    ('RED_K6_X6', {"type":"RED","k":6,"pct":6}),
    ('MADEV_SMA7_X1.5', {"type":"MADEV","sma":7,"pct":1.5}),
    ('MADEV_SMA7_X3', {"type":"MADEV","sma":7,"pct":3}),
    ('MADEV_SMA20_X2', {"type":"MADEV","sma":20,"pct":2}),
    ('MADEV_SMA20_X4', {"type":"MADEV","sma":20,"pct":4}),
    ('MADEV_SMA50_X3', {"type":"MADEV","sma":50,"pct":3}),
    ('MADEV_SMA50_X6', {"type":"MADEV","sma":50,"pct":6}),
    ('MADEV_SMA140_X5', {"type":"MADEV","sma":140,"pct":5}),
    ('MADEV_SMA140_X10', {"type":"MADEV","sma":140,"pct":10}),
    ('RSI14_LT30', {"type":"RSI","len":14,"below":30}),
    ('RSI14_LT25', {"type":"RSI","len":14,"below":25}),
    ('RSI14_LT20', {"type":"RSI","len":14,"below":20}),
    ('RSI7_LT20', {"type":"RSI","len":7,"below":20}),
    ('RSI2_LT10', {"type":"RSI","len":2,"below":10}),
    ('RSI2_LT5', {"type":"RSI","len":2,"below":5}),
    ('BB20_K2', {"type":"BB","len":20,"k":2}),
    ('BB20_K2.5', {"type":"BB","len":20,"k":2.5}),
    ('BB20_K3', {"type":"BB","len":20,"k":3}),
    ('GAP_X1', {"type":"GAP","pct":1,"entry":"SESSION_OPEN"}),
    ('GAP_X2', {"type":"GAP","pct":2,"entry":"SESSION_OPEN"}),
    ('GAP_X3', {"type":"GAP","pct":3,"entry":"SESSION_OPEN"}),
    ('GAP_X5', {"type":"GAP","pct":5,"entry":"SESSION_OPEN"}),
    ('GAPRED_X1', {"type":"GAPRED","pct":1}),
    ('GAPRED_X2', {"type":"GAPRED","pct":2}),
    ('SODD_X1.5', {"type":"SODD","pct":1.5}),
    ('SODD_X2.5', {"type":"SODD","pct":2.5}),
    ('SODD_X4', {"type":"SODD","pct":4}),
    ('SODD_X6', {"type":"SODD","pct":6}),
    ('HHDD_L35_X5', {"type":"HHDD","lookback":35,"pct":5}),
    ('HHDD_L35_X8', {"type":"HHDD","lookback":35,"pct":8}),
    ('HHDD_L35_X12', {"type":"HHDD","lookback":35,"pct":12}),
    ('HHDD_L140_X12', {"type":"HHDD","lookback":140,"pct":12}),
    ('HHDD_L140_X20', {"type":"HHDD","lookback":140,"pct":20}),
    ('BIGRED_X1.5', {"type":"BIGRED","pct":1.5}),
    ('BIGRED_X2.5', {"type":"BIGRED","pct":2.5}),
    ('BIGRED_X4', {"type":"BIGRED","pct":4}),
    ('HAMMER_D2', {"type":"HAMMER","priorBars":5,"priorPct":2}),
    ('HAMMER_D4', {"type":"HAMMER","priorBars":5,"priorPct":4}),
    ('ENGULF_D2', {"type":"ENGULF","minRed":3,"priorPct":2}),
    ('ENGULF_D4', {"type":"ENGULF","minRed":3,"priorPct":4}),
    ('REVCONF_D3', {"type":"REVCONF","priorBars":5,"priorPct":3}),
    ('REVCONF_D5', {"type":"REVCONF","priorBars":5,"priorPct":5}),
    ('ATRDROP_N3_K2', {"type":"ATRDROP","n":3,"k":2,"atr":14}),
    ('ATRDROP_N3_K3', {"type":"ATRDROP","n":3,"k":3,"atr":14}),
    ('ATRDROP_N7_K3', {"type":"ATRDROP","n":7,"k":3,"atr":14}),
    ('ATRDROP_N7_K4', {"type":"ATRDROP","n":7,"k":4,"atr":14}),
    ('ATRDROP_N14_K4', {"type":"ATRDROP","n":14,"k":4,"atr":14}),
    ('ATRDROP_N14_K6', {"type":"ATRDROP","n":14,"k":6,"atr":14}),
    ('DDAYS_K3', {"type":"DDAYS","k":3}),
    ('DDAYS_K4', {"type":"DDAYS","k":4}),
    ('DROP_N3_X3@TREND140', {"type":"DROP","n":3,"pct":3,"filter":"TREND140"}),
    ('RED_K4_X2.5@TREND140', {"type":"RED","k":4,"pct":2.5,"filter":"TREND140"}),
    ('MADEV_SMA20_X2@TREND140', {"type":"MADEV","sma":20,"pct":2,"filter":"TREND140"}),
    ('RSI2_LT10@TREND140', {"type":"RSI","len":2,"below":10,"filter":"TREND140"}),
    ('BB20_K2@TREND140', {"type":"BB","len":20,"k":2,"filter":"TREND140"}),
    ('DROP_N7_X5@TREND140', {"type":"DROP","n":7,"pct":5,"filter":"TREND140"}),
    ('DROP_N7_X3@LASTBAR', {"type":"DROP","n":7,"pct":3,"filter":"LASTBAR"}),
    ('RSI14_LT30@FIRSTBAR', {"type":"RSI","len":14,"below":30,"filter":"FIRSTBAR"}),
]

BASE_FAMILY = {
    "DROP": "Spadek w N świecach",
    "RED": "Czerwone świece z rzędu",
    "MADEV": "Odchylenie od średniej kroczącej",
    "RSI": "Wyprzedanie RSI",
    "BB": "Wstęga Bollingera",
    "GAP": "Luka spadkowa na otwarciu",
    "GAPRED": "Luka spadkowa na otwarciu",
    "SODD": "Spadek od otwarcia sesji",
    "HHDD": "Spadek od szczytu",
    "BIGRED": "Duża czerwona świeca",
    "HAMMER": "Formacje świecowe odwrócenia",
    "ENGULF": "Formacje świecowe odwrócenia",
    "REVCONF": "Formacje świecowe odwrócenia",
    "ATRDROP": "Spadek względem zmienności (ATR)",
    "DDAYS": "Spadkowe sesje z rzędu",
}

# Odbicie typu bazowego w lustro wzrostowe (instrukcja 1.4, H1).
MIRROR_TYPE = {
    "DROP": "RISE", "RED": "GREEN", "MADEV": "MAUP", "RSI": "RSI", "BB": "BBU",
    "GAP": "GAPUP", "GAPRED": "GAPGREEN", "SODD": "SORU", "HHDD": "LLRU",
    "BIGRED": "BIGGREEN", "HAMMER": "STAR", "ENGULF": "ENGULFDN",
    "REVCONF": "REVDN", "ATRDROP": "ATRRISE", "DDAYS": "UDAYS",
}
MIRROR_FAMILY = {
    "RISE": "Wzrost w N świecach",
    "GREEN": "Zielone świece z rzędu",
    "MAUP": "Odchylenie w górę od średniej kroczącej",
    "RSI": "Wykupienie RSI",
    "BBU": "Wstęga Bollingera (górna)",
    "GAPUP": "Luka wzrostowa na otwarciu",
    "GAPGREEN": "Luka wzrostowa na otwarciu",
    "SORU": "Wzrost od otwarcia sesji",
    "LLRU": "Wzrost od dołka",
    "BIGGREEN": "Duża zielona świeca",
    "STAR": "Formacje świecowe odwrócenia w dół",
    "ENGULFDN": "Formacje świecowe odwrócenia w dół",
    "REVDN": "Formacje świecowe odwrócenia w dół",
    "ATRRISE": "Wzrost względem zmienności (ATR)",
    "UDAYS": "Wzrostowe sesje z rzędu",
}
MIRROR_FILTER = {"TREND140": "DOWN140", "LASTBAR": "LASTBAR", "FIRSTBAR": "FIRSTBAR"}


def mirror_params(p: dict) -> dict:
    """Lustro wzrostowe sygnału bazowego — te same liczby, odwrócony kierunek."""
    q = dict(p)
    q["type"] = MIRROR_TYPE[p["type"]]
    if p["type"] == "RSI":
        q.pop("below")
        q["above"] = 100 - p["below"]
    if p["type"] == "ENGULF":
        q["minGreen"] = q.pop("minRed")
    if "filter" in p:
        q["filter"] = MIRROR_FILTER[p["filter"]]
    return q


def mirror_code(code: str, p: dict) -> str:
    q = mirror_params(p)
    t = q["type"]
    body, _, flt = code.partition("@")
    if flt:
        flt = "@" + MIRROR_FILTER[flt]
    if p["type"] == "RSI":
        return f"RSI{p['len']}_GT{code_num(q['above'])}{flt}"
    prefix_map = {
        "DROP": "RISE", "RED": "GREEN", "MADEV": "MAUP", "BB": "BBU", "GAP": "GAPUP",
        "GAPRED": "GAPGREEN", "SODD": "SORU", "HHDD": "LLRU", "BIGRED": "BIGGREEN",
        "HAMMER": "STAR", "ENGULF": "ENGULFDN", "REVCONF": "REVDN", "ATRDROP": "ATRRISE",
        "DDAYS": "UDAYS",
    }
    old = p["type"]
    rest = body[len(old):]
    # Formacje: przyrostek _D (drop) → _U (up), tak jak „po spadku” → „po wzroście”.
    if old in ("HAMMER", "ENGULF", "REVCONF"):
        rest = rest.replace("_D", "_U", 1)
    return f"{prefix_map[old]}{rest}{flt}"


# ---------------------------------------------------------------------------
#  Opisy słowne — z parametrów
# ---------------------------------------------------------------------------
FILTER_TEXT = {
    "TREND140": "tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji",
    "DOWN140": "tylko w trendzie spadkowym: zamknięcie poniżej SMA(140) ≈ 20 sesji",
    "LASTBAR": "tylko gdy sygnał wypada na ostatniej świecy sesji (pozycja przez noc)",
    "FIRSTBAR": "tylko gdy sygnał wypada na pierwszej świecy sesji",
}


def _h1_text(p: dict) -> str:
    t = p["type"]
    up = t in MIRROR_FAMILY and t not in BASE_FAMILY or (t == "RSI" and "above" in p)
    word = "wyższe" if up else "niższe"
    if t in ("DROP", "RISE"):
        s = (f"Zamknięcie {word} o co najmniej {num(p['pct'])}% od zamknięcia sprzed "
             f"{p['n']} świec ({sesje(p['n'])}): C[t] {'≥' if up else '≤'} C[t−{p['n']}] × "
             f"(1 {'+' if up else '−'} {num(p['pct'])}%)")
    elif t in ("RED", "GREEN"):
        kol, kier = ("zielonych", "wzrost") if up else ("czerwonych", "spadek")
        s = (f"Ostatnie {p['k']} świec {kol} (zamknięcie {'>' if up else '<'} otwarcie), a łączny {kier} "
             f"od otwarcia pierwszej z nich do bieżącego zamknięcia wynosi co najmniej {num(p['pct'])}%")
    elif t in ("MADEV", "MAUP"):
        s = (f"Zamknięcie co najmniej {num(p['pct'])}% {'powyżej' if up else 'poniżej'} SMA({p['sma']}) "
             f"z zamknięć ({sesje(p['sma'])})")
    elif t == "RSI":
        if up:
            s = f"RSI({p['len']}) metodą Wildera przecina w górę poziom {num(p['above'])} (RSI[t] > {num(p['above'])} ≥ RSI[t−1])"
        else:
            s = f"RSI({p['len']}) metodą Wildera przecina w dół poziom {num(p['below'])} (RSI[t] < {num(p['below'])} ≤ RSI[t−1])"
    elif t in ("BB", "BBU"):
        znak = "+" if up else "−"
        s = (f"Zamknięcie {'powyżej górnej' if up else 'poniżej dolnej'} wstęgi Bollingera: "
             f"SMA({p['len']}) {znak} {num(p['k'])} × odchylenie standardowe populacyjne z {p['len']} zamknięć")
    elif t in ("GAP", "GAPUP"):
        s = (f"Otwarcie pierwszej świecy sesji {word} o co najmniej {num(p['pct'])}% od ostatniego zamknięcia "
             f"poprzedniej sesji. Wejście od razu po cenie tego otwarcia (SESSION_OPEN), bo luka jest znana "
             f"w chwili otwarcia")
    elif t in ("GAPRED", "GAPGREEN"):
        s = (f"Luka {'wzrostowa' if up else 'spadkowa'} ≥ {num(p['pct'])}% i pierwsza świeca sesji "
             f"{'zielona' if up else 'czerwona'} (luka się pogłębiła). Sygnał na zamknięciu pierwszej świecy, "
             f"wejście na otwarciu drugiej")
    elif t in ("SODD", "SORU"):
        s = (f"Zamknięcie świecy co najmniej {num(p['pct'])}% {'powyżej' if up else 'poniżej'} ceny otwarcia "
             f"bieżącej sesji. Liczy się tylko pierwszy taki sygnał w sesji")
    elif t in ("HHDD", "LLRU"):
        if up:
            s = (f"Zamknięcie co najmniej {num(p['pct'])}% powyżej najniższego low z ostatnich {p['lookback']} "
                 f"świec, łącznie z bieżącą ({sesje(p['lookback'])})")
        else:
            s = (f"Zamknięcie co najmniej {num(p['pct'])}% poniżej najwyższego high z ostatnich {p['lookback']} "
                 f"świec, łącznie z bieżącą ({sesje(p['lookback'])})")
    elif t in ("BIGRED", "BIGGREEN"):
        s = (f"Jedna {'zielona' if up else 'czerwona'} świeca z korpusem {'wzrostowym' if up else 'spadkowym'} "
             f"o co najmniej {num(p['pct'])}% (od otwarcia do zamknięcia tej świecy)")
    elif t == "HAMMER":
        s = (f"Młot po spadku: C[t−1] ≤ C[t−{p['priorBars'] + 1}] × (1 − {num(p['priorPct'])}%) "
             f"({p['priorBars']} poprzednich świec spadło łącznie o ≥ {num(p['priorPct'])}%); bieżąca świeca ma "
             f"dolny cień ≥ 2 × korpus, górny cień ≤ korpus i zamyka się w górnej 1/3 swojego zakresu")
    elif t == "STAR":
        s = (f"Spadająca gwiazda po wzroście: C[t−1] ≥ C[t−{p['priorBars'] + 1}] × (1 + {num(p['priorPct'])}%) "
             f"({p['priorBars']} poprzednich świec wzrosło łącznie o ≥ {num(p['priorPct'])}%); bieżąca świeca ma "
             f"górny cień ≥ 2 × korpus, dolny cień ≤ korpus i zamyka się w dolnej 1/3 swojego zakresu")
    elif t == "ENGULF":
        s = (f"Objęcie wzrostowe: co najmniej {p['minRed']} czerwone świece bezpośrednio przed bieżącą, "
             f"o łącznym spadku ≥ {num(p['priorPct'])}% (od otwarcia pierwszej do zamknięcia ostatniej); "
             f"bieżąca świeca zielona, otwarta ≤ poprzedniemu zamknięciu i zamknięta ≥ poprzedniemu otwarciu")
    elif t == "ENGULFDN":
        s = (f"Objęcie spadkowe: co najmniej {p['minGreen']} zielone świece bezpośrednio przed bieżącą, "
             f"o łącznym wzroście ≥ {num(p['priorPct'])}% (od otwarcia pierwszej do zamknięcia ostatniej); "
             f"bieżąca świeca czerwona, otwarta ≥ poprzedniemu zamknięciu i zamknięta ≤ poprzedniemu otwarciu")
    elif t == "REVCONF":
        s = (f"Potwierdzone odbicie: C[t−1] ≤ C[t−{p['priorBars'] + 1}] × (1 − {num(p['priorPct'])}%) "
             f"(spadek ≥ {num(p['priorPct'])}% w {p['priorBars']} świecach przed bieżącą), potem zielona świeca "
             f"zamykająca się powyżej high poprzedniej świecy")
    elif t == "REVDN":
        s = (f"Potwierdzone odwrócenie w dół: C[t−1] ≥ C[t−{p['priorBars'] + 1}] × (1 + {num(p['priorPct'])}%) "
             f"(wzrost ≥ {num(p['priorPct'])}% w {p['priorBars']} świecach przed bieżącą), potem czerwona świeca "
             f"zamykająca się poniżej low poprzedniej świecy")
    elif t in ("ATRDROP", "ATRRISE"):
        s = (f"{'Wzrost' if up else 'Spadek'} zamknięcia w {p['n']} świecach ≥ {num(p['k'])} × ATR({p['atr']}): "
             f"{'C[t] − C[t−' + str(p['n']) + ']' if up else 'C[t−' + str(p['n']) + '] − C[t]'} ≥ {num(p['k'])} × ATR[t]. Próg zależy od "
             f"zmienności spółki, więc spokojne i nerwowe spółki są oceniane tą samą miarą")
    elif t in ("DDAYS", "UDAYS"):
        s = (f"{p['k']} sesje z rzędu zamknięte {'wyżej' if up else 'niżej'} niż poprzednia sesja. Sygnał na ostatniej świecy sesji, "
             f"wejście na otwarciu kolejnej")
    else:
        raise KeyError(t)
    if "filter" in p:
        s += ", " + FILTER_TEXT[p["filter"]]
    return s + "."


# ---------------------------------------------------------------------------
#  Rozgrzewka i długość historii dla Apps Script
# ---------------------------------------------------------------------------
def _warmup(p: dict) -> int:
    """
    Ile świec historii potrzeba, żeby sygnał był ważny (kontrakt silnika, pkt 10).
    Dla EMA / metody Wildera to okno wskaźnika — startują od średniej prostej.
    """
    t = p["type"]
    S = BARS_PER_SESSION
    rv = RVOL_SESSIONS * S + S
    w = {
        "DROP": lambda: p["n"] + 1, "RISE": lambda: p["n"] + 1,
        "RED": lambda: p["k"], "GREEN": lambda: p["k"],
        "MADEV": lambda: p["sma"], "MAUP": lambda: p["sma"],
        "RSI": lambda: p["len"] + 2, "BB": lambda: p["len"], "BBU": lambda: p["len"],
        "GAP": lambda: S + 1, "GAPUP": lambda: S + 1, "GAPRED": lambda: S + 1, "GAPGREEN": lambda: S + 1,
        "SODD": lambda: S, "SORU": lambda: S,
        "HHDD": lambda: p["lookback"], "LLRU": lambda: p["lookback"],
        "BIGRED": lambda: 1, "BIGGREEN": lambda: 1,
        "HAMMER": lambda: p["priorBars"] + 2, "STAR": lambda: p["priorBars"] + 2,
        "ENGULF": lambda: p["minRed"] + 1, "ENGULFDN": lambda: p["minGreen"] + 1,
        "REVCONF": lambda: p["priorBars"] + 2, "REVDN": lambda: p["priorBars"] + 2,
        "ATRDROP": lambda: max(p["n"] + 1, p["atr"] + 1), "ATRRISE": lambda: max(p["n"] + 1, p["atr"] + 1),
        "DDAYS": lambda: (p["k"] + 1) * S, "UDAYS": lambda: (p["k"] + 1) * S,
        "MAX": lambda: p["slow"] + 1,
        "PXMA": lambda: p["n"] + 1,
        "PULLMA": lambda: max(p["n"], p["trend"]["slow"], p["trend"].get("lag", 0) + p["n"]) + 1,
        "MASLOPE": lambda: p["n"] + p["k"] + 1,
        "RIBBON": lambda: max(n for _, n in p["mas"]) + 1,
        "MACD": lambda: p["slow"] + p["signal"] + 1,
        "VWAPX": lambda: S, "VWAPDEV": lambda: S, "VWMAX": lambda: p["n"] + 1,
        "DONCH": lambda: p["n"] + 2,
        "NSES": lambda: (p["n"] + 1) * S,
        "PDHL": lambda: 2 * S, "ORB": lambda: S, "INSIDE": lambda: 3 * S,
        "SQZ": lambda: p["len"] + p["lookback"] + p["recent"],
        "NR": lambda: (p["n"] + 1) * (S if p["unit"] == "session" else 1) + 1,
        "WRB": lambda: p["atr"] + 2,
        "STOCH": lambda: p["k"] + p["smooth"] + p["d"] + 1,
        "RSIX": lambda: p["len"] + 2,
        "RSIDIV": lambda: p["len"] + 2 * p["lookback"],
        "IBS": lambda: S, "FHR": lambda: 2, "CAL": lambda: S, "BASE": lambda: S,
        "IDIO": lambda: p["n"] + 2, "MKT": lambda: p["n"] + 2, "RSX": lambda: p["n"] + 2,
        "CAP": lambda: max(_warmup(p["base"]), rv),
        "CLX": lambda: max(p["n"] + 1, rv),
        "VBRK": lambda: max(p["n"] + 2, rv),
        "VMAX": lambda: max(p["slow"] + 1, rv),
        "DRY": lambda: max(_warmup(p["pull"]), rv),
        "OBVD": lambda: 2 * p["lookback"] + 1,
        "GAPV": lambda: max(S + 1, rv),
        "ACC": lambda: p["n"] + 1,
    }[t]()
    if "filter" in p and p["filter"] in ("TREND140", "DOWN140"):
        w = max(w, 140)
    return w


def _recursive_lengths(p: dict) -> list[int]:
    """Okna wskaźników rekurencyjnych (EMA, Wilder), które sygnał używa."""
    t = p["type"]
    out: list[int] = []
    if t == "RSI" or t in ("RSIX", "RSIDIV"):
        out.append(p["len"])
    if t in ("ATRDROP", "ATRRISE", "WRB"):
        out.append(p["atr"])
    if t in ("MAX", "VMAX") and p["ma"] == "EMA":
        out.append(p["slow"])
    if t == "PULLMA":
        if p["ma"] == "EMA":
            out.append(p["n"])
        if p["trend"]["type"] == "EMA_GT":
            out.append(p["trend"]["slow"])
    if t == "RIBBON":
        out += [n for kind, n in p["mas"] if kind == "EMA"]
    if t == "MACD":
        out.append(p["slow"] + p["signal"])
    if t == "CAP":
        out += _recursive_lengths(p["base"])
    if t == "DRY":
        out += _recursive_lengths(p["pull"])
    return out


def _live_lookback(p: dict) -> int:
    """
    Ile świec wstecz musi znać Apps Script, żeby na żywo (Etap 4, D2) policzyć
    ten sam sygnał co Python w backteście.

    Średnia prosta zależy tylko od swojego okna. EMA i metoda Wildera pamiętają
    całą przeszłość — wpływ punktu startu maleje jak (1 − α)^k. Po 3 × n
    świecach różnica jest już znikoma (dla EMA ok. e^−6 ≈ 0,25% początkowej
    rozbieżności), więc Apps Script musi znać co najmniej tyle historii albo
    przechowywać stan wskaźnika między świecami.
    """
    rec = _recursive_lengths(p)
    return max([_warmup(p)] + [RECURSIVE_LIVE_FACTOR * n for n in rec])


# ---------------------------------------------------------------------------
#  Nowe rodziny (H2–H8) — kolejność = kolejność tabel w instrukcji 1.4
# ---------------------------------------------------------------------------
UP, DN = "up", "down"
EV = {UP: "wzrostowe", DN: "spadkowe"}
SUF = {UP: "UP", DN: "DN"}


def _lower_first(t: str) -> str:
    return t[:1].lower() + t[1:]


def _ma(kind: str, n: int) -> str:
    return f"{kind}({n})"


def _new_signals() -> list[dict]:
    S: list[dict] = []

    def add(cat, fam, code, params, text, event, volume=False, market=False,
            entry="NEXT_OPEN", paired=None, status="aktywny"):
        S.append(dict(category=cat, family=fam, code=code, params=params,
                      definition=text, event=event, volume=volume, market=market,
                      entry=entry, paired_with=paired, status=status))

    # ===================== H2 — trend =====================
    for kind, fast, slow in [("EMA", 7, 21), ("EMA", 14, 35), ("EMA", 50, 200),
                             ("SMA", 35, 140), ("SMA", 70, 350)]:
        for d in (UP, DN):
            add("H2", "Przecięcie średnich", f"MAX_{kind}{fast}_{slow}_{SUF[d]}",
                {"type": "MAX", "ma": kind, "fast": fast, "slow": slow, "dir": d},
                f"{_ma(kind, fast)} przecina {_ma(kind, slow)} {'w górę' if d == UP else 'w dół'}: "
                f"szybka {'>' if d == UP else '<'} wolna na świecy t, a na t−1 było odwrotnie albo równo "
                f"({sesje(fast)} / {sesje(slow)}).", EV[d])
    for n in (20, 50, 140, 350):
        for d in (UP, DN):
            add("H2", "Cena przecina średnią", f"PXMA_SMA{n}_{SUF[d]}",
                {"type": "PXMA", "ma": "SMA", "n": n, "dir": d},
                f"Zamknięcie przecina SMA({n}) {'w górę' if d == UP else 'w dół'}: C[t] "
                f"{'>' if d == UP else '<'} SMA[t] i C[t−1] {'≤' if d == UP else '≥'} SMA[t−1] ({sesje(n)}).",
                EV[d])
    pulls = [
        ("EMA20", {"ma": "EMA", "n": 20, "trend": {"type": "EMA_GT", "fast": 20, "slow": 50}},
         "EMA(20) > EMA(50)", "EMA(20) < EMA(50)"),
        ("EMA50", {"ma": "EMA", "n": 50, "trend": {"type": "EMA_GT", "fast": 50, "slow": 200}},
         "EMA(50) > EMA(200)", "EMA(50) < EMA(200)"),
        ("SMA140", {"ma": "SMA", "n": 140, "trend": {"type": "SLOPE", "slow": 140, "lag": 7}},
         "SMA(140) wyższa niż 7 świec temu", "SMA(140) niższa niż 7 świec temu"),
    ]
    for tag, base, tr_up, tr_dn in pulls:
        for d in (UP, DN):
            ma = _ma(base["ma"], base["n"])
            if d == UP:
                txt = (f"Cofnięcie do średniej w trendzie wzrostowym ({tr_up}): low świecy dotyka {ma} "
                       f"(L[t] ≤ {ma}[t] < C[t]), a poprzednia świeca jej nie dotykała (L[t−1] > {ma}[t−1]).")
            else:
                txt = (f"Cofnięcie do średniej w trendzie spadkowym ({tr_dn}): high świecy dotyka {ma} "
                       f"(H[t] ≥ {ma}[t] > C[t]), a poprzednia świeca jej nie dotykała (H[t−1] < {ma}[t−1]).")
            add("H2", "Cofnięcie do średniej w trendzie", f"PULLMA_{tag}_{SUF[d]}",
                {"type": "PULLMA", **base, "dir": d}, txt, EV[d])
    for n in (35, 140):
        for d in (UP, DN):
            add("H2", "Zmiana nachylenia średniej", f"MASLOPE_SMA{n}_{SUF[d]}",
                {"type": "MASLOPE", "ma": "SMA", "n": n, "k": 7, "dir": d},
                f"SMA({n}) zaczyna {'rosnąć' if d == UP else 'spadać'}: SMA[t] {'>' if d == UP else '<'} SMA[t−1], "
                f"a w każdej z 7 poprzednich świec średnia {'spadała' if d == UP else 'rosła'} "
                f"({'SMA[i] < SMA[i−1]' if d == UP else 'SMA[i] > SMA[i−1]'} dla i = t−7…t−1).", EV[d])
    for d in (UP, DN):
        rel = ">" if d == UP else "<"
        add("H2", "Ułożenie średnich", f"RIBBON_{SUF[d]}",
            {"type": "RIBBON", "mas": [["EMA", 7], ["EMA", 21], ["EMA", 50], ["SMA", 140]], "dir": d},
            f"Pierwsza świeca, w której średnie ułożyły się w trend {'wzrostowy' if d == UP else 'spadkowy'}: "
            f"EMA(7) {rel} EMA(21) {rel} EMA(50) {rel} SMA(140) na t, a na t−1 ten warunek nie był spełniony.",
            EV[d])
    macd = [
        ("SIG", UP, "linia MACD przecina linię sygnału w górę"),
        ("SIG", DN, "linia MACD przecina linię sygnału w dół"),
        ("ZERO", UP, "linia MACD przecina zero w górę"),
        ("ZERO", DN, "linia MACD przecina zero w dół"),
        ("SIGB0", UP, "linia MACD przecina linię sygnału w górę, będąc poniżej zera (MACD[t] < 0)"),
        ("SIGA0", DN, "linia MACD przecina linię sygnału w dół, będąc powyżej zera (MACD[t] > 0)"),
    ]
    for tag, d, what in macd:
        cross = "signal" if tag.startswith("SIG") else "zero"
        zone = {"SIGB0": "below0", "SIGA0": "above0"}.get(tag)
        params = {"type": "MACD", "fast": 12, "slow": 26, "signal": 9, "cross": cross, "dir": d}
        if zone:
            params["zone"] = zone
        add("H2", "MACD", f"MACD_{tag}_{SUF[d]}", params,
            f"MACD(12, 26, 9): {what}. Przecięcie jak w 1.3 (stan na t przeciwny niż na t−1).", EV[d])
    for d in (UP, DN):
        add("H2", "VWAP", f"VWAP_X_{SUF[d]}", {"type": "VWAPX", "dir": d},
            f"Zamknięcie przecina VWAP sesji {'w górę' if d == UP else 'w dół'} (C[t] {'>' if d == UP else '<'} VWAP[t], "
            f"C[t−1] {'≤' if d == UP else '≥'} VWAP[t−1]); tylko od 2. świecy sesji, żeby t−1 było w tej samej sesji.",
            EV[d], volume=True)
    for side, d in (("below", DN), ("above", UP)):
        for pct in (1, 2):
            word = "poniżej" if side == "below" else "powyżej"
            add("H2", "VWAP", f"VWAP_DEV{pct}_{side.upper()}", {"type": "VWAPDEV", "pct": pct, "side": side},
                f"Pierwsze w sesji zamknięcie co najmniej {pct}% {word} VWAP sesji "
                f"(C[t] {'≤' if side == 'below' else '≥'} VWAP[t] × (1 {'−' if side == 'below' else '+'} {pct}%)).",
                EV[d], volume=True)
    for d in (UP, DN):
        add("H2", "VWAP", f"VWMA35_X_{SUF[d]}", {"type": "VWMAX", "n": 35, "dir": d},
            f"Zamknięcie przecina VWMA(35) {'w górę' if d == UP else 'w dół'} — średnią ważoną wolumenem "
            f"z 35 świec (1 tydzień).", EV[d], volume=True)

    # ===================== H3 — wybicia =====================
    for n in (35, 140):
        for d in (UP, DN):
            if d == UP:
                txt = (f"Zamknięcie powyżej najwyższego high z {n} poprzednich świec (bez bieżącej): "
                       f"C[t] > max(H[t−{n}…t−1]), a na t−1 tego wybicia jeszcze nie było ({sesje(n)}).")
            else:
                txt = (f"Zamknięcie poniżej najniższego low z {n} poprzednich świec (bez bieżącej): "
                       f"C[t] < min(L[t−{n}…t−1]), a na t−1 tego wybicia jeszcze nie było ({sesje(n)}).")
            add("H3", "Kanał Donchiana", f"DONCH{n}_{SUF[d]}", {"type": "DONCH", "n": n, "dir": d}, txt, EV[d])
    for n in (20, 50):
        for d in (UP, DN):
            add("H3", "Nowe maksimum / minimum sesji", f"NSES{n}_{SUF[d]}", {"type": "NSES", "n": n, "dir": d},
                f"Sesja zamyka się {'najwyżej' if d == UP else 'najniżej'} od {n} sesji: zamknięcie sesji "
                f"{'>' if d == UP else '<'} {'max' if d == UP else 'min'} z zamknięć {n} poprzednich sesji. "
                f"Sygnał na ostatniej świecy sesji, wejście na otwarciu kolejnej.", EV[d])
    for d in (UP, DN):
        add("H3", "Przebicie poprzedniej sesji", f"PDHL_{SUF[d]}", {"type": "PDHL", "dir": d},
            f"Pierwsze w sesji zamknięcie {'powyżej high' if d == UP else 'poniżej low'} poprzedniej sesji.", EV[d])
    for bars in (1, 2):
        for d in (UP, DN):
            first, last = bars + 1, 5
            add("H3", "Wybicie z zakresu otwarcia", f"ORB{bars}_{SUF[d]}",
                {"type": "ORB", "bars": bars, "fromSlot": first, "toSlot": last, "dir": d},
                f"Zakres otwarcia = high i low {'pierwszej świecy' if bars == 1 else 'dwóch pierwszych świec'} sesji. "
                f"Pierwsze zamknięcie świecy nr {first}–{last} {'powyżej high' if d == UP else 'poniżej low'} "
                f"tego zakresu.", EV[d])
    for d in (UP, DN):
        add("H3", "Sesja wewnętrzna", f"INSIDE_{SUF[d]}", {"type": "INSIDE", "dir": d},
            f"Poprzednia sesja w całości w zakresie sesji ją poprzedzającej (high ≤, low ≥); w bieżącej sesji "
            f"pierwsze zamknięcie {'powyżej high' if d == UP else 'poniżej low'} tej poprzedniej (wewnętrznej) sesji.",
            EV[d])

    # ===================== H4 — zmienność =====================
    for lb in (70, 140):
        for d in (UP, DN):
            add("H4", "Ściśnięcie wstęgi", f"SQZ{lb}_{SUF[d]}",
                {"type": "SQZ", "len": 20, "k": 2, "lookback": lb, "recent": 7, "dir": d},
                f"Ściśnięcie i wybicie: w ciągu ostatnich 7 świec szerokość wstęgi Bollingera(20, 2) była najniższa "
                f"od {lb} świec; teraz zamknięcie {'powyżej górnej' if d == UP else 'poniżej dolnej'} wstęgi, "
                f"a na t−1 jeszcze nie.", EV[d])
    for d in (UP, DN):
        add("H4", "Najwęższy zakres", f"NR7S_{SUF[d]}", {"type": "NR", "unit": "session", "n": 7, "dir": d},
            f"Poprzednia sesja miała najwęższy zakres (high − low) z ostatnich 7 sesji (NR7); w bieżącej "
            f"pierwsze zamknięcie {'powyżej jej high' if d == UP else 'poniżej jej low'}.", EV[d])
    for d in (UP, DN):
        add("H4", "Najwęższy zakres", f"NR14B_{SUF[d]}", {"type": "NR", "unit": "bar", "n": 14, "dir": d},
            f"Świeca t−1 miała najwęższy zakres z ostatnich 14 świec; świeca t zamyka się "
            f"{'powyżej jej high' if d == UP else 'poniżej jej low'}.", EV[d])
    for k in (2, 3):
        for d in (UP, DN):
            add("H4", "Bardzo szeroka świeca", f"WRB_K{k}_{SUF[d]}", {"type": "WRB", "k": k, "atr": 14, "dir": d},
                f"Zakres świecy H − L ≥ {k} × ATR(14) z poprzedniej świecy (ATR[t−1], żeby świeca nie mierzyła "
                f"się sama sobą), zamknięcie w {'górnej' if d == UP else 'dolnej'} ćwiartce zakresu.", EV[d])

    # ===================== H5 — oscylatory =====================
    for d in (UP, DN):
        lvl = 20 if d == UP else 80
        add("H5", "Stochastyk", f"STOCH_{SUF[d]}",
            {"type": "STOCH", "k": 14, "smooth": 3, "d": 3, "level": lvl, "dir": d},
            f"Stochastyk (%K(14) wygładzony SMA(3), %D = SMA(3) z %K): %K przecina %D "
            f"{'w górę' if d == UP else 'w dół'}, a %K[t−1] {'<' if d == UP else '>'} {lvl}.", EV[d])
    for d, lvl in ((UP, 30), (DN, 70)):
        add("H5", "Wyjście RSI ze strefy", f"RSIX_{lvl}_{SUF[d]}", {"type": "RSIX", "len": 14, "level": lvl, "dir": d},
            f"RSI(14) wraca {'ponad' if d == UP else 'pod'} {lvl}: RSI[t] {'>' if d == UP else '<'} {lvl} "
            f"{'≥' if d == UP else '≤'} RSI[t−1]. Potwierdzenie wyjścia ze strefy, w odróżnieniu od bazowego "
            f"RSI, które odpala przy wejściu w nią.", EV[d])
    for d in (UP, DN):
        if d == UP:
            txt = ("Dywergencja wzrostowa: zamknięcie jest najniższe z 35 świec, ale RSI(14) jest wyżej niż przy "
                   "poprzednim takim minimum. Poprzednie minimum = najbliższa świeca j z przedziału t−35…t−5, "
                   "której zamknięcie było wtedy najniższe z 35 świec; warunek: RSI[t] > RSI[j]. Brak j — brak sygnału.")
        else:
            txt = ("Dywergencja spadkowa: zamknięcie jest najwyższe z 35 świec, ale RSI(14) jest niżej niż przy "
                   "poprzednim takim maksimum (j z przedziału t−35…t−5, jak w wersji wzrostowej); RSI[t] < RSI[j].")
        add("H5", "Dywergencja RSI", f"RSIDIV_{SUF[d]}",
            {"type": "RSIDIV", "len": 14, "lookback": 35, "minGap": 5, "dir": d}, txt, EV[d])

    # ===================== H6 — sesja i kalendarz =====================
    for side, d in (("low", DN), ("high", UP)):
        add("H6", "Zamknięcie przy krańcu sesji (IBS)", f"IBS_{side.upper()}",
            {"type": "IBS", "level": 0.1, "side": side},
            f"Na ostatniej świecy sesji: (zamknięcie sesji − low sesji) / (high sesji − low sesji) "
            f"{'≤ 0,1' if side == 'low' else '≥ 0,9'} — sesja zamyka się w {'dolnych' if side == 'low' else 'górnych'} "
            f"10% swojego zakresu. Wejście na otwarciu kolejnej sesji.", EV[d])
    for d in (UP, DN):
        if d == UP:
            txt = ("Odwrócenie pierwszej godziny w górę: świeca 1 sesji spada o ≥ 1% (C ≤ O × 0,99), świeca 2 "
                   "zamyka się powyżej połowy świecy 1 ((H1 + L1) / 2). Sygnał na zamknięciu świecy 2.")
        else:
            txt = ("Odwrócenie pierwszej godziny w dół: świeca 1 sesji rośnie o ≥ 1% (C ≥ O × 1,01), świeca 2 "
                   "zamyka się poniżej połowy świecy 1. Sygnał na zamknięciu świecy 2.")
        add("H6", "Odwrócenie pierwszej godziny", f"FHR_{SUF[d]}", {"type": "FHR", "pct": 1, "dir": d}, txt, EV[d])
    add("H6", "Kalendarz", "CAL_MONTH", {"type": "CAL", "when": "month_end"},
        "Ostatnia sesja miesiąca: sygnał na jej ostatniej świecy, wejście na otwarciu pierwszej sesji nowego "
        "miesiąca (efekt przełomu miesiąca).", "neutralne")
    add("H6", "Kalendarz", "CAL_WEEK", {"type": "CAL", "when": "week_end"},
        "Ostatnia sesja tygodnia: sygnał na jej ostatniej świecy, wejście na otwarciu pierwszej sesji kolejnego "
        "tygodnia (efekt weekendu).", "neutralne")
    add("H6", "Kontrolne: pora dnia", "BASE_OPEN", {"type": "BASE", "when": "session_open"},
        "KONTROLNY, nie kandydat do S2: sygnał na ostatniej świecy każdej sesji, wejście na otwarciu kolejnej. "
        "Mierzy czysty efekt „wejścia na otwarciu” — punkt odniesienia dla reszty H6.", "neutralne",
        status="kontrolny")
    add("H6", "Kontrolne: pora dnia", "BASE_CLOSE", {"type": "BASE", "when": "session_close"},
        "KONTROLNY, nie kandydat do S2: sygnał na przedostatniej świecy każdej sesji, wejście na otwarciu "
        "ostatniej. Mierzy czysty efekt „wejścia przed zamknięciem”.", "neutralne", status="kontrolny")

    # ===================== H7 — kontekst rynku =====================
    for pct in (2, 3):
        for d in (DN, UP):
            if d == DN:
                txt = (f"Ruch własny w dół: spółka spadła o ≥ {pct}% w 7 świecach (C[t] ≤ C[t−7] × (1 − {pct}%)), "
                       f"a SPY w tych samych godzinach nie spadł o więcej niż 0,3%. Pierwsza świeca, w której "
                       f"warunek jest spełniony.")
            else:
                txt = (f"Ruch własny w górę: spółka wzrosła o ≥ {pct}% w 7 świecach, a SPY w tych samych godzinach "
                       f"nie wzrósł o więcej niż 0,3%. Pierwsza świeca, w której warunek jest spełniony.")
            add("H7", "Ruch własny spółki", f"IDIO_X{pct}_{SUF[d]}",
                {"type": "IDIO", "n": 7, "pct": pct, "mkt": "SPY", "mktMax": 0.3, "dir": d},
                txt, EV[d], market=True)
    for d in (DN, UP):
        add("H7", "Ruch całego rynku", f"MKT_{SUF[d]}",
            {"type": "MKT", "n": 7, "mkt": "SPY", "mktPct": 1, "pct": 1.5, "dir": d},
            f"Ruch całego rynku {'w dół' if d == DN else 'w górę'}: SPY {'spadł' if d == DN else 'wzrósł'} o ≥ 1% "
            f"w 7 świecach i spółka {'spadła' if d == DN else 'wzrosła'} o ≥ 1,5%. Pierwsza świeca, w której "
            f"oba warunki są spełnione.", EV[d], market=True)
    for d in (UP, DN):
        add("H7", "Siła względna", f"RSX_{SUF[d]}", {"type": "RSX", "n": 35, "mkt": "SPY", "dir": d},
            f"Siła względna: stosunek C spółki do C SPY {'najwyższy' if d == UP else 'najniższy'} z 35 świec "
            f"(nowe {'maksimum' if d == UP else 'minimum'}, którego na t−1 nie było), a SPY nie jest na swoim "
            f"{'maksimum' if d == UP else 'minimum'} z 35 świec.", EV[d], market=True)

    # ===================== H8 — wolumen =====================
    caps = [
        ({"type": "DROP", "n": 3, "pct": 2}, "DROP_N3_X2", 2),
        ({"type": "DROP", "n": 3, "pct": 2}, "DROP_N3_X2", 3),
        ({"type": "BIGRED", "pct": 1.5}, "BIGRED_X1.5", 2),
    ]
    for base, bcode, rv in caps:
        for d in (DN, UP):
            b = base if d == DN else mirror_params(base)
            bc = bcode if d == DN else mirror_code(bcode, base)
            add("H8", "Kapitulacja / wykupienie na wolumenie", f"CAP_{bc}_R{rv}",
                {"type": "CAP", "base": b, "rvol": rv, "dir": d},
                f"{'Kapitulacja' if d == DN else 'Wykupienie'}: warunek {bc} "
                f"({_lower_first(_h1_text(b)[:-1])}) i RVOL[t] ≥ {rv}.", EV[d], volume=True, paired=bc)
    for d in (DN, UP):
        if d == DN:
            txt = ("Kulminacja podaży: RVOL[t] ≥ 3, low świecy najniższe z 35 świec (L[t] ≤ min(L[t−35…t−1])), "
                   "zamknięcie w górnej połowie świecy (C ≥ (H + L) / 2) — niższe ceny zostały odrzucone.")
        else:
            txt = ("Kulminacja popytu: RVOL[t] ≥ 3, high świecy najwyższe z 35 świec, zamknięcie w dolnej połowie "
                   "świecy — wyższe ceny zostały odrzucone.")
        add("H8", "Kulminacja wolumenu", f"CLX_{SUF[d]}", {"type": "CLX", "rvol": 3, "n": 35, "dir": d},
            txt, EV[d], volume=True)
    for d in (UP, DN):
        dc = f"DONCH35_{SUF[d]}"
        add("H8", "Wybicie a wolumen", f"VBRK35_RMIN1.5_{SUF[d]}",
            {"type": "VBRK", "n": 35, "rvolMin": 1.5, "dir": d},
            f"Wybicie {dc} potwierdzone wolumenem: RVOL[t] ≥ 1,5.", EV[d], volume=True, paired=dc)
        add("H8", "Wybicie a wolumen", f"VBRK35_RMAX0.8_{SUF[d]}",
            {"type": "VBRK", "n": 35, "rvolMax": 0.8, "dir": d},
            f"Wybicie {dc} bez wolumenu: RVOL[t] < 0,8 — kandydat na fałszywe wybicie (sprawdzany "
            f"kierunkiem przeciwnym).", EV[d], volume=True, paired=dc)
    for d in (UP, DN):
        mc = f"MAX_EMA14_35_{SUF[d]}"
        add("H8", "Przecięcie średnich z wolumenem", f"VMAX_EMA14_35_{SUF[d]}",
            {"type": "VMAX", "ma": "EMA", "fast": 14, "slow": 35, "rvol": 1.5, "dir": d},
            f"Przecięcie {mc} i RVOL[t] ≥ 1,5.", EV[d], volume=True, paired=mc)
    for d in (UP, DN):
        pc = f"PULLMA_EMA20_{SUF[d]}"
        pull = {"type": "PULLMA", "ma": "EMA", "n": 20,
                "trend": {"type": "EMA_GT", "fast": 20, "slow": 50}, "dir": d}
        add("H8", "Wysychanie wolumenu", f"DRY_EMA20_{SUF[d]}",
            {"type": "DRY", "pull": pull, "rvolAvg": 0.7, "bars": 3, "dir": d},
            f"Cofnięcie {pc} przy wysychającym wolumenie: średni RVOL świec t−2, t−1, t ≤ 0,7 "
            f"(cofnięcie {'„bez podaży”' if d == UP else '„bez popytu”'}).", EV[d], volume=True, paired=pc)
    for d in (UP, DN):
        if d == UP:
            txt = ("Dywergencja OBV: zamknięcie najniższe z 35 świec, a OBV wyższe niż przy poprzednim takim minimum "
                   "(j jak w RSIDIV: najbliższa świeca z t−35…t−5, która była wtedy minimum z 35) — ktoś kupuje spadek.")
        else:
            txt = ("Dywergencja OBV w dół: zamknięcie najwyższe z 35 świec, a OBV niższe niż przy poprzednim takim "
                   "maksimum — wzrost bez kupujących.")
        add("H8", "Dywergencja OBV", f"OBVD_{SUF[d]}", {"type": "OBVD", "lookback": 35, "minGap": 5, "dir": d},
            txt, EV[d], volume=True)
    for d in (DN, UP):
        for key, val, word in (("rvolMin", 2, "≥ 2 (luka na wolumenie)"), ("rvolMax", 1, "< 1 (luka bez wolumenu)")):
            gc = f"GAP{'' if d == DN else 'UP'}_X2"
            add("H8", "Luka z wolumenem",
                f"GAPV_X2_{'RMIN2' if key == 'rvolMin' else 'RMAX1'}_{SUF[d]}",
                {"type": "GAPV", "pct": 2, key: val, "dir": d},
                f"Luka {'spadkowa' if d == DN else 'wzrostowa'} ≥ 2% i RVOL pierwszej świecy {word}. Sygnał na "
                f"zamknięciu pierwszej świecy, wejście na otwarciu drugiej — wolumen pierwszej świecy znamy dopiero "
                f"po jej zamknięciu (5.2).", EV[d], volume=True, paired=gc)
    for side, ratio, d in (("acc", 2, UP), ("dist", 0.5, DN)):
        add("H8", "Akumulacja / dystrybucja", "ACC" if side == "acc" else "DIST",
            {"type": "ACC", "n": 35, "ratio": ratio, "flat": 2, "side": side},
            f"{'Akumulacja' if side == 'acc' else 'Dystrybucja'}: suma wolumenu świec wzrostowych / suma wolumenu "
            f"świec spadkowych z 35 świec {'≥ 2' if side == 'acc' else '≤ 0,5'}, przy zmianie ceny z 35 świec "
            f"poniżej 2% co do wartości. Pierwsza świeca, w której warunek jest spełniony.", EV[d], volume=True)
    return S


# ---------------------------------------------------------------------------
#  Złożenie katalogu
# ---------------------------------------------------------------------------
def _uses_volume(p: dict) -> bool:
    return p["type"] in ("VWAPX", "VWAPDEV", "VWMAX", "CAP", "CLX", "VBRK", "VMAX", "DRY", "OBVD", "GAPV", "ACC")


def build() -> dict:
    signals: list[dict] = []

    def entry_of(p):
        return "SESSION_OPEN" if p["type"] in ("GAP", "GAPUP") else "NEXT_OPEN"

    for i, (code, p) in enumerate(BASE, start=1):
        signals.append(dict(
            id=f"S{i:03d}", code=code, category="H1", family=BASE_FAMILY[p["type"]], event="spadkowe",
            definition=_h1_text(p), params=p, volume=False, market=False, entry=entry_of(p),
            origin="bazowy", paired_with=None, status="aktywny"))
    for i, (code, p) in enumerate(BASE, start=1):
        q = mirror_params(p)
        signals.append(dict(
            id=f"S{i + len(BASE):03d}", code=mirror_code(code, p), category="H1",
            family=MIRROR_FAMILY[q["type"]], event="wzrostowe", definition=_h1_text(q), params=q,
            volume=False, market=False, entry=entry_of(q), origin=f"lustro S{i:03d}",
            paired_with=code, status="aktywny"))
    for s in _new_signals():
        s["id"] = f"S{len(signals) + 1:03d}"
        s["origin"] = "nowy"
        signals.append(s)

    for s in signals:
        s["warmup_bars"] = _warmup(s["params"])
        s["live_lookback_bars"] = _live_lookback(s["params"])
        s["strategies"] = len(DIRECTIONS) * len(SL_TP_GRID) ** 2

    key_order = ["id", "code", "category", "family", "event", "definition", "params", "volume",
                 "market", "warmup_bars", "live_lookback_bars", "entry", "origin", "paired_with",
                 "status", "strategies"]
    signals = [{k: s[k] for k in key_order} for s in signals]

    by_cat = {c: sum(1 for s in signals if s["category"] == c) for c in CATEGORIES}
    body = {
        "signals": signals,
        "exits": {
            "sl_pct": SL_TP_GRID, "tp_pct": SL_TP_GRID, "directions": DIRECTIONS,
            "h_default": H_DEFAULT,
            "h_rule": "D10: H nie jest przeszukiwany; po backteście H = 90. percentyl czasu do TP, "
                      "strategia liczona ponownie z tą jedną wartością.",
        },
    }
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    meta = {
        "catalog_version": CATALOG_VERSION,
        "project_version": PROJECT_VERSION,
        "status": "szkic — niezamrożony (D21: zamrożenie na końcu Etapu 1)",
        "content_hash": digest,
        "signals": len(signals),
        "signals_active": sum(1 for s in signals if s["status"] == "aktywny"),
        "signals_control": sum(1 for s in signals if s["status"] == "kontrolny"),
        "strategies": sum(s["strategies"] for s in signals),
        "by_category": by_cat,
        "categories": CATEGORIES,
        "max_warmup_bars": max(s["warmup_bars"] for s in signals),
        "max_live_lookback_bars": max(s["live_lookback_bars"] for s in signals),
        "conventions": {
            "bar": "świeca 1h; sesja = 7 świec (nr 1–7, świeca 7 trwa 30 min); szereg ciągły przez noce",
            "sma": "średnia arytmetyczna n zamknięć",
            "ema": "alfa = 2/(n+1), start od SMA(n) z pierwszych n zamknięć",
            "wilder": "RSI, ATR: alfa = 1/n, start od średniej prostej z pierwszych n wartości",
            "bollinger": "SMA(n) ± k × odchylenie standardowe populacyjne (dzielone przez n)",
            "macd": "EMA(12) − EMA(26); sygnał = EMA(9) z MACD",
            "stochastic": "%K(14) wygładzony SMA(3); %D = SMA(3) z %K",
            "vwap": "sesyjny: suma(TP × v) / suma(v) od 1. świecy sesji, TP = (H + L + C) / 3",
            "obv": "suma narastająca: +v, gdy C > C[t−1]; −v, gdy C < C[t−1]",
            "rvol": f"v[t] / średni v tej samej świecy dnia (nr 1–7) z {RVOL_SESSIONS} poprzednich sesji",
            "cross_up": "A[t] > B[t] i A[t−1] ≤ B[t−1]",
            "splits": "D11: sygnał nie odpala, jeśli jego okno obejmuje sesję ze splitem",
            "volume": "D12: sygnały z volume=true wymagają v > 0 w całym oknie",
            "entry": "NEXT_OPEN = otwarcie świecy t+1; SESSION_OPEN = otwarcie świecy sygnału (tylko luki)",
            "live_lookback": f"ile świec historii potrzebuje Apps Script na żywo; EMA/Wilder: "
                             f"{RECURSIVE_LIVE_FACTOR} × okno (albo przechowywany stan wskaźnika)",
        },
    }
    return {"meta": meta, **body}


def validate(cat: dict) -> list[str]:
    """Twarde sprawdzenia katalogu. Pusta lista = wszystko w porządku."""
    err: list[str] = []
    sig = cat["signals"]
    ids = [s["id"] for s in sig]
    codes = [s["code"] for s in sig]
    if ids != [f"S{i:03d}" for i in range(1, len(sig) + 1)]:
        err.append("identyfikatory nie są ciągłe S001…")
    dup = {c for c in codes if codes.count(c) > 1}
    if dup:
        err.append(f"powtórzone kody: {sorted(dup)}")
    if len(sig) > MAX_SIGNALS:
        err.append(f"{len(sig)} sygnałów > limit {MAX_SIGNALS} (D19)")
    for s in sig:
        if s["warmup_bars"] > MAX_WARMUP_BARS:
            err.append(f"{s['id']} {s['code']}: rozgrzewka {s['warmup_bars']} > {MAX_WARMUP_BARS} świec "
                       f"(okno {MAX_WINDOW_BARS} z 1.3 + jedna sesja)")
        if s["volume"] != _uses_volume(s["params"]):
            err.append(f"{s['id']}: niezgodna flaga volume")
        if not s["definition"].endswith("."):
            err.append(f"{s['id']}: definicja bez kropki")
        if s["paired_with"] and s["paired_with"] not in codes:
            err.append(f"{s['id']}: paired_with {s['paired_with']} nie istnieje w katalogu")
    return err


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generuje s1/catalog.json (katalog S1).")
    ap.add_argument("--out", type=Path, default=None, help="ścieżka pliku (domyślnie <repo>/s1/catalog.json)")
    ap.add_argument("--check", action="store_true", help="tylko sprawdź, nic nie zapisuj")
    a = ap.parse_args(argv)
    cat = build()
    errors = validate(cat)
    m = cat["meta"]
    print(f"Katalog {m['catalog_version']}: {m['signals']} sygnałów ({m['signals_active']} aktywnych, "
          f"{m['signals_control']} kontrolnych), {m['strategies']} strategii, hash {m['content_hash']}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in m["by_category"].items()))
    print(f"  najdłuższa rozgrzewka: {m['max_warmup_bars']} świec; na żywo: {m['max_live_lookback_bars']} świec")
    if errors:
        print("BŁĘDY:\n  " + "\n  ".join(errors))
        return 1
    if a.check:
        return 0
    out = a.out or repo_root() / "s1" / "catalog.json"
    if a.out is None and not (repo_root() / "IA4_INSTRUKCJA.md").exists():
        print("To nie jest klon całego repozytorium — podaj --out albo uruchom w klonie IA4.")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Zapisano {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
