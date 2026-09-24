# IA 4 — katalog bazowy sygnałów (84)

**Wersja projektu: 0.11 (2026-09-24) — musi zgadzać się z `IA4_INSTRUKCJA.md`

Katalog przeniesiony z arkusza `STRATEGIE_LEGENDA` starego projektu. To **punkt
wyjścia dla Etapu 1**, a nie gotowy katalog S1: wszystkie 84 sygnały są wyłącznie
LONG i wszystkie opisują jedną hipotezę — „spadło, więc odbije". S1 ma je objąć
razem z wariantami SHORT i nowymi rodzinami (decyzja D9).

Arkusz `STRATEGIE` starego projektu zawierał 1008 wierszy = 84 sygnały × 12 profili
wyjścia. W Etapie 1 profile zastępuje pełna siatka 10×10 (decyzja D4), więc stare
profile podaję tutaj tylko jako zapis tego, co było liczone wcześniej.


## Kontrakt silnika (zasady wspólne)

1. Wszystkie strategie otwierają wyłącznie pozycje LONG. Każda jest testowana osobno dla AAPL, TSLA i NVDA.

2. Sygnał jest liczony na zamkniętej świecy t. Wejście następuje po cenie otwarcia świecy t+1 (NEXT_OPEN), więc nie ma zaglądania w przyszłość.

3. Wyjątek: sygnały GAP_X wchodzą po cenie otwarcia pierwszej świecy sesji (SESSION_OPEN), bo luka jest znana w chwili otwarcia.

4. SL i TP liczone są od ceny wejścia, sprawdzane na każdej świecy od świecy wejścia włącznie, po jej high i low.

5. Jeśli w jednej świecy osiągalny jest i SL, i TP, przyjmujemy SL (wariant ostrożny).

6. Jeśli świeca otwiera się za poziomem SL lub TP (luka), wyjście następuje po cenie otwarcia tej świecy.

7. Limit czasu: brak SL/TP po H świecach od wejścia oznacza wyjście po zamknięciu H-tej świecy. 7 świec = 1 sesja.

8. Jedna pozycja naraz na strategię i spółkę. Sygnały pojawiające się w trakcie pozycji są ignorowane.

9. Świece liczone są jako ciągły szereg (przez noce i weekendy). Wszystkie wskaźniki liczymy z zamknięć świec 1h.

10. Sygnał jest ważny dopiero, gdy wskaźnik ma pełną historię (np. SMA(140) wymaga 140 świec).

11. Świeca 21:30–22:00 (ostatnie 30 min sesji) jest traktowana jak każda inna świeca.

12. Koszty transakcyjne i poślizg to parametry silnika (proponowane 0,05% na stronę transakcji).


## Stare profile wyjścia (12) — zastąpione siatką 10×10 w Etapie 1

| ID | SL | TP | Limit świec | Limit sesji | Charakter |
|---|---|---|---|---|---|
| X01 | −1% | +1% | 7 | 1 | Scalp 1:1, najwyżej 1 sesja |
| X02 | −1% | +2% | 14 | 2 | Ciasny stop, zysk 2:1 |
| X03 | −2% | +1% | 14 | 2 | Szybkie odbicie, szeroki stop (wysoka skuteczność) |
| X04 | −2% | +2% | 14 | 2 | Symetryczny 2% |
| X05 | −2% | +4% | 35 | 5 | Odbicie 2:1, do 5 sesji |
| X06 | −3% | +3% | 35 | 5 | Symetryczny 3% |
| X07 | −4% | +2% | 35 | 5 | Szeroki stop, mały zysk |
| X08 | −5% | +3% | 35 | 5 | Bardzo szeroki stop, średni zysk |
| X09 | −4% | +8% | 70 | 10 | Swing 2:1, do 10 sesji |
| X10 | −5% | +10% | 105 | 15 | Swing 2:1, do 15 sesji |
| X11 | −8% | +4% | 70 | 10 | Głęboki stop, przeczekanie paniki |
| X12 | −10% | +15% | 140 | 20 | Pozycja wielotygodniowa, do 20 sesji |

## Filtry

| Kod | Znaczenie |
|---|---|
| `TREND140` | tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji |
| `LASTBAR` | tylko gdy sygnał wypada na ostatniej świecy sesji (pozycja przez noc) |
| `FIRSTBAR` | tylko gdy sygnał wypada na pierwszej świecy sesji (po porannej panice) |

## Sygnały (84)

| ID | Kod | Rodzina | Definicja | Parametry |
|---|---|---|---|---|
| S001 | `DROP_N2_X1.5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 1,5% od zamknięcia sprzed 2 świec. | `{"type":"DROP","n":2,"pct":1.5}` |
| S002 | `DROP_N2_X2.5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 2,5% od zamknięcia sprzed 2 świec. | `{"type":"DROP","n":2,"pct":2.5}` |
| S003 | `DROP_N2_X4` | Spadek w N świecach | Zamknięcie niższe o co najmniej 4% od zamknięcia sprzed 2 świec. | `{"type":"DROP","n":2,"pct":4}` |
| S004 | `DROP_N3_X2` | Spadek w N świecach | Zamknięcie niższe o co najmniej 2% od zamknięcia sprzed 3 świec. | `{"type":"DROP","n":3,"pct":2}` |
| S005 | `DROP_N3_X3` | Spadek w N świecach | Zamknięcie niższe o co najmniej 3% od zamknięcia sprzed 3 świec. | `{"type":"DROP","n":3,"pct":3}` |
| S006 | `DROP_N3_X5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 5% od zamknięcia sprzed 3 świec. | `{"type":"DROP","n":3,"pct":5}` |
| S007 | `DROP_N5_X2.5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 2,5% od zamknięcia sprzed 5 świec. | `{"type":"DROP","n":5,"pct":2.5}` |
| S008 | `DROP_N5_X4` | Spadek w N świecach | Zamknięcie niższe o co najmniej 4% od zamknięcia sprzed 5 świec. | `{"type":"DROP","n":5,"pct":4}` |
| S009 | `DROP_N5_X6` | Spadek w N świecach | Zamknięcie niższe o co najmniej 6% od zamknięcia sprzed 5 świec. | `{"type":"DROP","n":5,"pct":6}` |
| S010 | `DROP_N7_X3` | Spadek w N świecach | Zamknięcie niższe o co najmniej 3% od zamknięcia sprzed 7 świec (1 sesji). | `{"type":"DROP","n":7,"pct":3}` |
| S011 | `DROP_N7_X5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 5% od zamknięcia sprzed 7 świec (1 sesji). | `{"type":"DROP","n":7,"pct":5}` |
| S012 | `DROP_N7_X8` | Spadek w N świecach | Zamknięcie niższe o co najmniej 8% od zamknięcia sprzed 7 świec (1 sesji). | `{"type":"DROP","n":7,"pct":8}` |
| S013 | `DROP_N14_X5` | Spadek w N świecach | Zamknięcie niższe o co najmniej 5% od zamknięcia sprzed 14 świec (2 sesji). | `{"type":"DROP","n":14,"pct":5}` |
| S014 | `DROP_N14_X8` | Spadek w N świecach | Zamknięcie niższe o co najmniej 8% od zamknięcia sprzed 14 świec (2 sesji). | `{"type":"DROP","n":14,"pct":8}` |
| S015 | `DROP_N14_X12` | Spadek w N świecach | Zamknięcie niższe o co najmniej 12% od zamknięcia sprzed 14 świec (2 sesji). | `{"type":"DROP","n":14,"pct":12}` |
| S016 | `RED_K3_X1` | Czerwone świece z rzędu | Co najmniej 3 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 1%. | `{"type":"RED","k":3,"pct":1}` |
| S017 | `RED_K3_X2` | Czerwone świece z rzędu | Co najmniej 3 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 2%. | `{"type":"RED","k":3,"pct":2}` |
| S018 | `RED_K3_X3` | Czerwone świece z rzędu | Co najmniej 3 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 3%. | `{"type":"RED","k":3,"pct":3}` |
| S019 | `RED_K4_X1.5` | Czerwone świece z rzędu | Co najmniej 4 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 1,5%. | `{"type":"RED","k":4,"pct":1.5}` |
| S020 | `RED_K4_X2.5` | Czerwone świece z rzędu | Co najmniej 4 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 2,5%. | `{"type":"RED","k":4,"pct":2.5}` |
| S021 | `RED_K4_X4` | Czerwone świece z rzędu | Co najmniej 4 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 4%. | `{"type":"RED","k":4,"pct":4}` |
| S022 | `RED_K5_X2` | Czerwone świece z rzędu | Co najmniej 5 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 2%. | `{"type":"RED","k":5,"pct":2}` |
| S023 | `RED_K5_X3` | Czerwone świece z rzędu | Co najmniej 5 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 3%. | `{"type":"RED","k":5,"pct":3}` |
| S024 | `RED_K5_X5` | Czerwone świece z rzędu | Co najmniej 5 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 5%. | `{"type":"RED","k":5,"pct":5}` |
| S025 | `RED_K6_X2.5` | Czerwone świece z rzędu | Co najmniej 6 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 2,5%. | `{"type":"RED","k":6,"pct":2.5}` |
| S026 | `RED_K6_X4` | Czerwone świece z rzędu | Co najmniej 6 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 4%. | `{"type":"RED","k":6,"pct":4}` |
| S027 | `RED_K6_X6` | Czerwone świece z rzędu | Co najmniej 6 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 6%. | `{"type":"RED","k":6,"pct":6}` |
| S028 | `MADEV_SMA7_X1.5` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 1,5% poniżej SMA(7) z zamknięć (≈ 1 sesji). | `{"type":"MADEV","sma":7,"pct":1.5}` |
| S029 | `MADEV_SMA7_X3` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 3% poniżej SMA(7) z zamknięć (≈ 1 sesji). | `{"type":"MADEV","sma":7,"pct":3}` |
| S030 | `MADEV_SMA20_X2` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 2% poniżej SMA(20) z zamknięć (≈ 2,9 sesji). | `{"type":"MADEV","sma":20,"pct":2}` |
| S031 | `MADEV_SMA20_X4` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 4% poniżej SMA(20) z zamknięć (≈ 2,9 sesji). | `{"type":"MADEV","sma":20,"pct":4}` |
| S032 | `MADEV_SMA50_X3` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 3% poniżej SMA(50) z zamknięć (≈ 7,1 sesji). | `{"type":"MADEV","sma":50,"pct":3}` |
| S033 | `MADEV_SMA50_X6` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 6% poniżej SMA(50) z zamknięć (≈ 7,1 sesji). | `{"type":"MADEV","sma":50,"pct":6}` |
| S034 | `MADEV_SMA140_X5` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 5% poniżej SMA(140) z zamknięć (≈ 20 sesji). | `{"type":"MADEV","sma":140,"pct":5}` |
| S035 | `MADEV_SMA140_X10` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 10% poniżej SMA(140) z zamknięć (≈ 20 sesji). | `{"type":"MADEV","sma":140,"pct":10}` |
| S036 | `RSI14_LT30` | Wyprzedanie RSI | RSI(14) liczony metodą Wildera z zamknięć spada poniżej 30. | `{"type":"RSI","len":14,"below":30}` |
| S037 | `RSI14_LT25` | Wyprzedanie RSI | RSI(14) liczony metodą Wildera z zamknięć spada poniżej 25. | `{"type":"RSI","len":14,"below":25}` |
| S038 | `RSI14_LT20` | Wyprzedanie RSI | RSI(14) liczony metodą Wildera z zamknięć spada poniżej 20. | `{"type":"RSI","len":14,"below":20}` |
| S039 | `RSI7_LT20` | Wyprzedanie RSI | RSI(7) liczony metodą Wildera z zamknięć spada poniżej 20. | `{"type":"RSI","len":7,"below":20}` |
| S040 | `RSI2_LT10` | Wyprzedanie RSI | RSI(2) liczony metodą Wildera z zamknięć spada poniżej 10. | `{"type":"RSI","len":2,"below":10}` |
| S041 | `RSI2_LT5` | Wyprzedanie RSI | RSI(2) liczony metodą Wildera z zamknięć spada poniżej 5. | `{"type":"RSI","len":2,"below":5}` |
| S042 | `BB20_K2` | Wstęga Bollingera | Zamknięcie poniżej dolnej wstęgi Bollingera: SMA(20) − 2 × odchylenie standardowe z 20 zamknięć. | `{"type":"BB","len":20,"k":2}` |
| S043 | `BB20_K2.5` | Wstęga Bollingera | Zamknięcie poniżej dolnej wstęgi Bollingera: SMA(20) − 2,5 × odchylenie standardowe z 20 zamknięć. | `{"type":"BB","len":20,"k":2.5}` |
| S044 | `BB20_K3` | Wstęga Bollingera | Zamknięcie poniżej dolnej wstęgi Bollingera: SMA(20) − 3 × odchylenie standardowe z 20 zamknięć. | `{"type":"BB","len":20,"k":3}` |
| S045 | `GAP_X1` | Luka spadkowa na otwarciu | Otwarcie pierwszej świecy sesji niższe o ≥ 1% od zamknięcia poprzedniej sesji. Wejście od razu po cenie otwarcia sesji (gra na domknięcie luki). | `{"type":"GAP","pct":1,"entry":"SESSION_OPEN"}` |
| S046 | `GAP_X2` | Luka spadkowa na otwarciu | Otwarcie pierwszej świecy sesji niższe o ≥ 2% od zamknięcia poprzedniej sesji. Wejście od razu po cenie otwarcia sesji (gra na domknięcie luki). | `{"type":"GAP","pct":2,"entry":"SESSION_OPEN"}` |
| S047 | `GAP_X3` | Luka spadkowa na otwarciu | Otwarcie pierwszej świecy sesji niższe o ≥ 3% od zamknięcia poprzedniej sesji. Wejście od razu po cenie otwarcia sesji (gra na domknięcie luki). | `{"type":"GAP","pct":3,"entry":"SESSION_OPEN"}` |
| S048 | `GAP_X5` | Luka spadkowa na otwarciu | Otwarcie pierwszej świecy sesji niższe o ≥ 5% od zamknięcia poprzedniej sesji. Wejście od razu po cenie otwarcia sesji (gra na domknięcie luki). | `{"type":"GAP","pct":5,"entry":"SESSION_OPEN"}` |
| S049 | `GAPRED_X1` | Luka spadkowa na otwarciu | Luka spadkowa ≥ 1% i pierwsza świeca sesji czerwona (luka się pogłębiła). Wejście na otwarciu drugiej świecy. | `{"type":"GAPRED","pct":1}` |
| S050 | `GAPRED_X2` | Luka spadkowa na otwarciu | Luka spadkowa ≥ 2% i pierwsza świeca sesji czerwona (luka się pogłębiła). Wejście na otwarciu drugiej świecy. | `{"type":"GAPRED","pct":2}` |
| S051 | `SODD_X1.5` | Spadek od otwarcia sesji | Zamknięcie świecy co najmniej 1,5% poniżej ceny otwarcia bieżącej sesji. Liczy się tylko pierwszy taki sygnał w sesji. | `{"type":"SODD","pct":1.5}` |
| S052 | `SODD_X2.5` | Spadek od otwarcia sesji | Zamknięcie świecy co najmniej 2,5% poniżej ceny otwarcia bieżącej sesji. Liczy się tylko pierwszy taki sygnał w sesji. | `{"type":"SODD","pct":2.5}` |
| S053 | `SODD_X4` | Spadek od otwarcia sesji | Zamknięcie świecy co najmniej 4% poniżej ceny otwarcia bieżącej sesji. Liczy się tylko pierwszy taki sygnał w sesji. | `{"type":"SODD","pct":4}` |
| S054 | `SODD_X6` | Spadek od otwarcia sesji | Zamknięcie świecy co najmniej 6% poniżej ceny otwarcia bieżącej sesji. Liczy się tylko pierwszy taki sygnał w sesji. | `{"type":"SODD","pct":6}` |
| S055 | `HHDD_L35_X5` | Spadek od szczytu | Zamknięcie co najmniej 5% poniżej najwyższego high z ostatnich 35 świec (5 sesji). | `{"type":"HHDD","lookback":35,"pct":5}` |
| S056 | `HHDD_L35_X8` | Spadek od szczytu | Zamknięcie co najmniej 8% poniżej najwyższego high z ostatnich 35 świec (5 sesji). | `{"type":"HHDD","lookback":35,"pct":8}` |
| S057 | `HHDD_L35_X12` | Spadek od szczytu | Zamknięcie co najmniej 12% poniżej najwyższego high z ostatnich 35 świec (5 sesji). | `{"type":"HHDD","lookback":35,"pct":12}` |
| S058 | `HHDD_L140_X12` | Spadek od szczytu | Zamknięcie co najmniej 12% poniżej najwyższego high z ostatnich 140 świec (20 sesji). | `{"type":"HHDD","lookback":140,"pct":12}` |
| S059 | `HHDD_L140_X20` | Spadek od szczytu | Zamknięcie co najmniej 20% poniżej najwyższego high z ostatnich 140 świec (20 sesji). | `{"type":"HHDD","lookback":140,"pct":20}` |
| S060 | `BIGRED_X1.5` | Duża czerwona świeca | Jedna czerwona świeca z korpusem (otwarcie → zamknięcie) spadkowym o ≥ 1,5%. | `{"type":"BIGRED","pct":1.5}` |
| S061 | `BIGRED_X2.5` | Duża czerwona świeca | Jedna czerwona świeca z korpusem (otwarcie → zamknięcie) spadkowym o ≥ 2,5%. | `{"type":"BIGRED","pct":2.5}` |
| S062 | `BIGRED_X4` | Duża czerwona świeca | Jedna czerwona świeca z korpusem (otwarcie → zamknięcie) spadkowym o ≥ 4%. | `{"type":"BIGRED","pct":4}` |
| S063 | `HAMMER_D2` | Formacje świecowe odwrócenia | Młot po spadku: 5 poprzednich świec spadło łącznie o ≥ 2%, bieżąca świeca ma dolny cień ≥ 2× korpus, górny cień ≤ korpus i zamyka się w górnej 1/3 swojego zakresu. | `{"type":"HAMMER","priorBars":5,"priorPct":2}` |
| S064 | `HAMMER_D4` | Formacje świecowe odwrócenia | Młot po spadku: 5 poprzednich świec spadło łącznie o ≥ 4%, bieżąca świeca ma dolny cień ≥ 2× korpus, górny cień ≤ korpus i zamyka się w górnej 1/3 swojego zakresu. | `{"type":"HAMMER","priorBars":5,"priorPct":4}` |
| S065 | `ENGULF_D2` | Formacje świecowe odwrócenia | Objęcie wzrostowe: co najmniej 3 czerwone świece o łącznym spadku ≥ 2%, potem zielona świeca otwarta ≤ poprzedniemu zamknięciu i zamknięta ≥ poprzedniemu otwarciu. | `{"type":"ENGULF","minRed":3,"priorPct":2}` |
| S066 | `ENGULF_D4` | Formacje świecowe odwrócenia | Objęcie wzrostowe: co najmniej 3 czerwone świece o łącznym spadku ≥ 4%, potem zielona świeca otwarta ≤ poprzedniemu zamknięciu i zamknięta ≥ poprzedniemu otwarciu. | `{"type":"ENGULF","minRed":3,"priorPct":4}` |
| S067 | `REVCONF_D3` | Formacje świecowe odwrócenia | Potwierdzone odbicie: spadek ≥ 3% w 5 świecach, potem zielona świeca zamykająca się powyżej high poprzedniej świecy. | `{"type":"REVCONF","priorBars":5,"priorPct":3}` |
| S068 | `REVCONF_D5` | Formacje świecowe odwrócenia | Potwierdzone odbicie: spadek ≥ 5% w 5 świecach, potem zielona świeca zamykająca się powyżej high poprzedniej świecy. | `{"type":"REVCONF","priorBars":5,"priorPct":5}` |
| S069 | `ATRDROP_N3_K2` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 3 świecach ≥ 2 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":3,"k":2,"atr":14}` |
| S070 | `ATRDROP_N3_K3` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 3 świecach ≥ 3 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":3,"k":3,"atr":14}` |
| S071 | `ATRDROP_N7_K3` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 7 świecach ≥ 3 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":7,"k":3,"atr":14}` |
| S072 | `ATRDROP_N7_K4` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 7 świecach ≥ 4 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":7,"k":4,"atr":14}` |
| S073 | `ATRDROP_N14_K4` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 14 świecach ≥ 4 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":14,"k":4,"atr":14}` |
| S074 | `ATRDROP_N14_K6` | Spadek względem zmienności (ATR) | Spadek zamknięcia w 14 świecach ≥ 6 × ATR(14). Próg zależy od zmienności spółki, więc AAPL i TSLA są oceniane tą samą miarą. | `{"type":"ATRDROP","n":14,"k":6,"atr":14}` |
| S075 | `DDAYS_K3` | Spadkowe sesje z rzędu | 3 sesje z rzędu zamknięte niżej niż poprzednia sesja. Sygnał na ostatniej świecy sesji, wejście na otwarciu kolejnej. | `{"type":"DDAYS","k":3}` |
| S076 | `DDAYS_K4` | Spadkowe sesje z rzędu | 4 sesje z rzędu zamknięte niżej niż poprzednia sesja. Sygnał na ostatniej świecy sesji, wejście na otwarciu kolejnej. | `{"type":"DDAYS","k":4}` |
| S077 | `DROP_N3_X3@TREND140` | Spadek w N świecach | Zamknięcie niższe o co najmniej 3% od zamknięcia sprzed 3 świec, tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"DROP","n":3,"pct":3,"filter":"TREND140"}` |
| S078 | `RED_K4_X2.5@TREND140` | Czerwone świece z rzędu | Co najmniej 4 czerwone świece z rzędu (zamknięcie < otwarcie), łączny spadek od otwarcia pierwszej do zamknięcia ostatniej ≥ 2,5%, tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"RED","k":4,"pct":2.5,"filter":"TREND140"}` |
| S079 | `MADEV_SMA20_X2@TREND140` | Odchylenie od średniej kroczącej | Zamknięcie co najmniej 2% poniżej SMA(20) z zamknięć (≈ 2,9 sesji), tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"MADEV","sma":20,"pct":2,"filter":"TREND140"}` |
| S080 | `RSI2_LT10@TREND140` | Wyprzedanie RSI | RSI(2) liczony metodą Wildera z zamknięć spada poniżej 10, tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"RSI","len":2,"below":10,"filter":"TREND140"}` |
| S081 | `BB20_K2@TREND140` | Wstęga Bollingera | Zamknięcie poniżej dolnej wstęgi Bollingera: SMA(20) − 2 × odchylenie standardowe z 20 zamknięć, tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"BB","len":20,"k":2,"filter":"TREND140"}` |
| S082 | `DROP_N7_X5@TREND140` | Spadek w N świecach | Zamknięcie niższe o co najmniej 5% od zamknięcia sprzed 7 świec (1 sesji), tylko w trendzie wzrostowym: zamknięcie powyżej SMA(140) ≈ 20 sesji. | `{"type":"DROP","n":7,"pct":5,"filter":"TREND140"}` |
| S083 | `DROP_N7_X3@LASTBAR` | Spadek w N świecach | Zamknięcie niższe o co najmniej 3% od zamknięcia sprzed 7 świec (1 sesji), tylko gdy sygnał wypada na ostatniej świecy sesji (pozycja przez noc). | `{"type":"DROP","n":7,"pct":3,"filter":"LASTBAR"}` |
| S084 | `RSI14_LT30@FIRSTBAR` | Wyprzedanie RSI | RSI(14) liczony metodą Wildera z zamknięć spada poniżej 30, tylko gdy sygnał wypada na pierwszej świecy sesji (po porannej panice). | `{"type":"RSI","len":14,"below":30,"filter":"FIRSTBAR"}` |

## Rodziny — podsumowanie

| Rodzina | Sygnałów |
|---|---|
| Spadek w N świecach | 18 |
| Czerwone świece z rzędu | 13 |
| Odchylenie od średniej kroczącej | 9 |
| Wyprzedanie RSI | 8 |
| Luka spadkowa na otwarciu | 6 |
| Formacje świecowe odwrócenia | 6 |
| Spadek względem zmienności (ATR) | 6 |
| Spadek od szczytu | 5 |
| Wstęga Bollingera | 4 |
| Spadek od otwarcia sesji | 4 |
| Duża czerwona świeca | 3 |
| Spadkowe sesje z rzędu | 2 |
| **razem** | **84** |
