"""
IA 4 — silnik portfela AI Investor: wielkość pozycji, limity, koszty, rozliczanie świeca po świecy
(instrukcja, sekcje 11c.6–11c.7; kolejność zdarzeń jak 8.6).
Wersja projektu: 1.35 (2026-10-12) — musi zgadzać się z IA4_INSTRUKCJA.md

Każda liczba portfela powstaje tutaj — model językowy tylko wybiera (zasada 16).

Pozycja: oczekuje (decyzja na świecy t) → wejście po open pierwszej świecy instrumentu po t →
w każdej kolejnej świecy j: [luka SL/TP na otwarciu, j > e] → [FC albo zamknięcie decyzją — po open]
→ [SL w trakcie] → [TP w trakcie; SL i TP w jednej świecy — zawsze SL] → [limit czasu na zamknięciu]
→ [FC na zamknięciu — wyjście po open następnej świecy]. SL wolno tylko zacieśniać. Wynik zawsze netto
(koszty 11c.6), w USD (waluta kwotowana przeliczana kursem z chwili wejścia i z zamknięcia świecy wyjścia).

Dwie księgi: `main` (Agent-Investor, wszystkie limity) i `shadow` (każdy kandydat, bez limitów —
punkt odniesienia „wszyscy kandydaci” i wynik pominiętych sygnałów, 11c.9–11c.10).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .market import Prices, iso, pl

REASONS = ("TP", "SL", "FC", "LIMIT", "CLOSE")


@dataclass
class Pos:
    id: int
    book: str                         # main | shadow
    round_id: str
    inst: str
    kind: str                         # stock | fx | crypto
    side: int                         # +1 long, −1 short
    basis: str                        # S-… | own | fx-prognoza
    basis_kind: str                   # bazowa_wybrana | bazowa | own | fx_prognoza | …
    decided_k: int                    # świeca decyzji (sygnału)
    decided_at: float
    sl_pct: float                     # od ceny wejścia
    tp_pct: float
    max_bars: int | None
    has_fc: bool
    qty: float
    ref_px: float                     # zamknięcie świecy decyzji
    risk_usd: float                   # ryzyko planowane przy decyzji (strata na SL z kosztami)
    mult: float
    confidence: int | None = None
    note_in: str = ""
    status: str = "pending"           # pending | open | closed
    entry_k: int | None = None
    entry_t: float | None = None
    entry_px: float | None = None
    sl_px: float | None = None
    tp_px: float | None = None
    conv_in: float | None = None
    value_usd: float | None = None
    cost_in_usd: float = 0.0
    bars: int = 0
    last_k: int | None = None
    fc_k: int | None = None           # świeca, na której zamknięciu zachodzi FC (liczy wywołujący)
    fc_flag: bool = False
    close_req: bool = False
    note_out: str = ""
    sl_moves: list = field(default_factory=list)
    exit_k: int | None = None
    exit_t: float | None = None
    exit_px: float | None = None
    reason: str | None = None
    gap: bool = False
    conv_out: float | None = None
    cost_out_usd: float = 0.0
    pnl_gross_usd: float = 0.0
    pnl_net_usd: float = 0.0
    ret_net_pct: float = 0.0
    r_mult: float = 0.0
    mark_px: float | None = None
    mark_t: float | None = None

    @property
    def direction(self) -> str:
        return "long" if self.side > 0 else "short"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Pos":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


# ===========================================================================
#  Koszty i jednostki
# ===========================================================================
def cost_side(cfg: dict, prices: Prices, inst: str, qty: float, px: float, conv: float) -> float:
    """Koszt jednej strony transakcji w USD (11c.6)."""
    kind = prices.kind(inst)
    if kind == "stock":
        return abs(qty) * px * cfg["cost_stock_pct"] / 100.0
    if kind == "crypto":
        return abs(qty) * px * cfg["cost_crypto_pct"] / 100.0
    spread = float(cfg["fx_spread_pips"].get(inst, 2.0))
    return abs(qty) * spread * prices.pip(inst) / 2.0 * conv


def unit_loss(cfg, prices, inst, px, sl_pct, conv) -> float:
    """Strata na jednostkę przy wyjściu na SL, z kosztem wejścia i wyjścia (USD)."""
    sl_px = px * (1 - sl_pct / 100.0)
    return px * sl_pct / 100.0 * conv + cost_side(cfg, prices, inst, 1.0, px, conv) + cost_side(cfg, prices, inst, 1.0, sl_px, conv)


def round_px(prices: Prices, inst: str, x: float) -> float:
    return round(float(x), max(prices.digits(inst), 4) if prices.kind(inst) != "stock" else 4)


# ===========================================================================
#  Księga
# ===========================================================================
class Book:
    def __init__(self, cfg: dict, name: str = "main", positions: list[Pos] | None = None, next_id: int = 1):
        self.cfg, self.name = cfg, name
        self.pos: list[Pos] = list(positions or [])
        self.next_id = max([next_id] + [p.id + 1 for p in self.pos])

    # ------------------------------------------------------------ widoki
    def active(self) -> list[Pos]:
        return [p for p in self.pos if p.status in ("pending", "open")]

    def closed(self) -> list[Pos]:
        return [p for p in self.pos if p.status == "closed"]

    def holding(self, inst: str) -> Pos | None:
        return next((p for p in self.active() if p.inst == inst), None)

    # ------------------------------------------------------------ wycena
    def mark(self, p: Pos, prices: Prices) -> dict:
        """Wynik pozycji otwartej po ostatnim zamknięciu (netto, z szacowanym kosztem wyjścia)."""
        last = prices.last(p.inst)
        if p.status != "open" or last is None:
            return {"px": p.mark_px, "pnl": 0.0, "pct": 0.0, "R": 0.0, "value": p.value_usd or 0.0}
        _, px, t = last
        conv = prices.conv(p.inst, t) or p.conv_in or 1.0
        gross = p.side * p.qty * (px - p.entry_px) * conv
        out = cost_side(self.cfg, prices, p.inst, p.qty, px, conv)
        net = gross - p.cost_in_usd - out
        p.mark_px, p.mark_t = px, t
        return {"px": px, "pnl": net, "pct": 100.0 * net / p.value_usd if p.value_usd else 0.0,
                "R": net / p.risk_usd if p.risk_usd else 0.0, "value": p.qty * px * conv}

    def risk_now(self, p: Pos, prices: Prices) -> float:
        """Ryzyko pozycji: strata do bieżącego SL (po zacieśnieniu może być 0) + koszty; oczekująca — planowane."""
        if p.status == "pending":
            return p.risk_usd
        conv = p.conv_in or 1.0
        loss = max(0.0, p.side * (p.entry_px - p.sl_px)) * p.qty * conv
        return loss + p.cost_in_usd + cost_side(self.cfg, prices, p.inst, p.qty, p.sl_px, conv)

    def snapshot(self, prices: Prices, now: float, capital: float) -> dict:
        realized = sum(p.pnl_net_usd for p in self.closed())
        unreal, gross, risk, own_risk = 0.0, 0.0, 0.0, 0.0
        for p in self.active():
            m = self.mark(p, prices)
            if p.status == "open":
                unreal += m["pnl"]
                gross += m["value"]
            else:
                gross += p.qty * p.ref_px * (prices.conv(p.inst, now) or 1.0)
            r = self.risk_now(p, prices)
            risk += r
            if p.basis == "own":
                own_risk += r
        eq = capital + realized + unreal
        return {"equity": eq, "realized": realized, "unrealized": unreal, "gross": gross, "risk": risk,
                "ownRisk": own_risk, "positions": len(self.active()),
                "open": sum(1 for p in self.active() if p.status == "open"),
                "pending": sum(1 for p in self.active() if p.status == "pending")}

    # ------------------------------------------------------------ wielkość i limity
    def plan(self, prices: Prices, inst: str, side: int, sl_pct: float, mult: float, equity: float, dial: float,
             now: float, own: bool = False, snap: dict | None = None, limits: bool = True) -> tuple[float, float, str | None]:
        """(liczba jednostek, ryzyko $, powód odrzucenia albo None)."""
        cfg = self.cfg
        last = prices.last(inst)
        if last is None:
            return 0.0, 0.0, "brak danych instrumentu"
        _, px, t = last
        conv = prices.conv(inst, t)
        if conv is None:
            return 0.0, 0.0, "brak kursu przeliczenia na USD"
        if not (0 < sl_pct < 50):
            return 0.0, 0.0, f"SL {sl_pct:.2f}% poza zakresem"
        risk = equity * cfg["risk_pct"] / 100.0 * dial * mult
        qty = risk / unit_loss(cfg, prices, inst, px, sl_pct, conv)
        if not limits:
            return qty, risk, None
        cap = cfg["max_value_pct"].get(prices.kind(inst), 20.0) / 100.0 * equity
        if qty * px * conv > cap:                                   # przycięcie do limitu wartości
            qty = cap / (px * conv)
            risk = qty * unit_loss(cfg, prices, inst, px, sl_pct, conv)
        s = snap or self.snapshot(prices, now, cfg["capital"])
        if self.holding(inst):
            return 0.0, 0.0, "jest już pozycja na tym instrumencie"
        if s["positions"] >= cfg["max_positions"]:
            return 0.0, 0.0, f"limit pozycji ({cfg['max_positions']})"
        if s["gross"] + qty * px * conv > cfg["gross_max_pct"] / 100.0 * equity:
            return 0.0, 0.0, f"limit ekspozycji brutto ({cfg['gross_max_pct']:.0f}%)"
        if s["risk"] + risk > cfg["budget_pct"] / 100.0 * equity + 1e-9:
            return 0.0, 0.0, f"budżet ryzyka ({cfg['budget_pct']:.1f}%) wyczerpany"
        if own and s["ownRisk"] + risk > cfg["own_budget_pct"] / 100.0 * equity + 1e-9:
            return 0.0, 0.0, f"budżet własnych pomysłów ({cfg['own_budget_pct']:.1f}%) wyczerpany"
        return qty, risk, None

    def add(self, prices: Prices, *, round_id: str, inst: str, side: int, basis: str, basis_kind: str, decided_k: int,
            now: float, sl_pct: float, tp_pct: float, max_bars, has_fc: bool, qty: float, risk: float, mult: float,
            confidence=None, note: str = "") -> Pos:
        last = prices.last(inst)
        p = Pos(id=self.next_id, book=self.name, round_id=round_id, inst=inst, kind=prices.kind(inst), side=int(side),
                basis=basis, basis_kind=basis_kind, decided_k=int(decided_k), decided_at=now, sl_pct=float(sl_pct),
                tp_pct=float(tp_pct), max_bars=int(max_bars) if max_bars else None, has_fc=bool(has_fc), qty=float(qty),
                ref_px=float(last[1]), risk_usd=float(risk), mult=float(mult), confidence=confidence, note_in=note,
                last_k=int(decided_k))
        self.next_id += 1
        self.pos.append(p)
        return p

    # ------------------------------------------------------------ decyzje o pozycjach
    def request_close(self, p: Pos, note: str) -> str | None:
        if p.status != "open":
            return "pozycja jeszcze nie otwarta" if p.status == "pending" else "pozycja zamknięta"
        p.close_req, p.note_out = True, note
        return None

    def tighten(self, p: Pos, new_sl: float, prices: Prices, note: str, now: float) -> str | None:
        """SL tylko w stronę zysku i po właściwej stronie ostatniej ceny."""
        if p.status != "open":
            return "pozycja jeszcze nie otwarta"
        last = prices.last(p.inst)
        px = last[1] if last else p.entry_px
        if not math.isfinite(new_sl) or new_sl <= 0:
            return "nowy SL nieprawidłowy"
        if p.side * (new_sl - p.sl_px) <= 0:
            return f"SL można tylko zacieśniać (teraz {p.sl_px:g})"
        if p.side * (px - new_sl) <= 0:
            return f"nowy SL po złej stronie ceny ({px:g})"
        p.sl_moves.append({"at": iso(now), "from": p.sl_px, "to": float(new_sl), "note": note})
        p.sl_px = float(new_sl)
        return None

    # ------------------------------------------------------------ rozliczanie
    def settle(self, prices: Prices) -> list[dict]:
        """Wszystkie nowe świece każdej aktywnej pozycji. Zwraca zdarzenia (wejścia, wyjścia)."""
        ev = []
        for p in self.active():
            S = prices.S.get(p.inst)
            if S is None:
                continue
            for i in S.after(p.last_k if p.last_k is not None else p.decided_k):
                if prices.t_max is not None and S.tc[i] > prices.t_max:
                    break
                e = self._candle(p, S, i, prices)
                if e:
                    ev.extend(e)
                if p.status == "closed":
                    break
        return ev

    def _candle(self, p: Pos, S, i: int, prices: Prices) -> list[dict]:
        cfg = self.cfg
        k, tc, o, h, l, c = int(S.k[i]), float(S.tc[i]), float(S.o[i]), float(S.h[i]), float(S.l[i]), float(S.c[i])
        t_open = float(S.to[i])
        ev = []
        first = False
        if p.status == "pending":
            first = True
            conv = prices.conv(p.inst, t_open) or prices.conv(p.inst, tc) or 1.0
            p.status, p.entry_k, p.entry_t, p.entry_px, p.conv_in = "open", k, t_open, o, conv
            p.sl_px = o * (1 - p.side * p.sl_pct / 100.0)          # bez zaokrągleń — jak 8.6 p. 2 (zgodność z backtestem)
            p.tp_px = o * (1 + p.side * p.tp_pct / 100.0)
            p.value_usd = p.qty * o * conv
            p.cost_in_usd = cost_side(cfg, prices, p.inst, p.qty, o, conv)
            p.risk_usd = self.risk_now(p, prices)
            ev.append({"kind": "entry", "pos": p})
        p.last_k = k
        hit = None
        if not first:
            if p.side * (o - p.sl_px) <= 0:
                hit = ("SL", o, t_open, True)
            elif p.side * (o - p.tp_px) >= 0:
                hit = ("TP", p.tp_px, t_open, True)
            elif p.fc_flag:
                hit = ("FC", o, t_open, False)
            elif p.close_req:
                hit = ("CLOSE", o, t_open, False)
        if hit is None:
            if (p.side > 0 and l <= p.sl_px) or (p.side < 0 and h >= p.sl_px):
                hit = ("SL", p.sl_px, tc, False)
            elif (p.side > 0 and h >= p.tp_px) or (p.side < 0 and l <= p.tp_px):
                hit = ("TP", p.tp_px, tc, False)
        p.bars += 1
        if hit is None and p.max_bars and p.bars >= p.max_bars:
            hit = ("LIMIT", c, tc, False)
        if hit is None:
            if p.has_fc and p.fc_k is not None and k >= p.fc_k:
                p.fc_flag = True
            return ev
        reason, px, t, gap = hit
        self._exit(p, k, t, px, reason, gap, prices, tc)
        ev.append({"kind": "exit", "pos": p})
        return ev

    def _exit(self, p: Pos, k: int, t: float, px: float, reason: str, gap: bool, prices: Prices, tc: float) -> None:
        conv = prices.conv(p.inst, tc) or p.conv_in or 1.0
        p.status, p.exit_k, p.exit_t, p.exit_px, p.reason, p.gap, p.conv_out = "closed", k, t, float(px), reason, gap, conv
        p.cost_out_usd = cost_side(self.cfg, prices, p.inst, p.qty, px, conv)
        p.pnl_gross_usd = p.side * p.qty * (px - p.entry_px) * conv
        p.pnl_net_usd = p.pnl_gross_usd - p.cost_in_usd - p.cost_out_usd
        p.ret_net_pct = 100.0 * p.pnl_net_usd / p.value_usd if p.value_usd else 0.0
        p.r_mult = p.pnl_net_usd / p.risk_usd if p.risk_usd else 0.0
        p.mark_px, p.mark_t = float(px), tc


def ret_gross_pct(p: Pos) -> float:
    """Zwrot ceny w kierunku pozycji, % (jak 8.6 p. 6) — do porównania z backtestem."""
    if p.entry_px is None or p.exit_px is None:
        return 0.0
    return (p.exit_px / p.entry_px - 1.0) * 100.0 if p.side > 0 else (p.entry_px - p.exit_px) / p.entry_px * 100.0


def utc_day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def describe(p: Pos, prices: Prices) -> str:
    if p.status == "closed":
        usd = f"{p.pnl_net_usd:+,.2f}".replace(",", " ")
        return (f"#{p.id} {p.inst} {p.direction} {p.reason}{' (luka)' if p.gap else ''} · wejście {p.entry_px:g} → "
                f"wyjście {p.exit_px:g} · {usd} $ ({p.ret_net_pct:+.2f}%, {p.r_mult:+.2f}R) · świec {p.bars}")
    if p.status == "open":
        return f"#{p.id} {p.inst} {p.direction} otwarta po {p.entry_px:g} ({pl(p.entry_t)}) · SL {p.sl_px:g} / TP {p.tp_px:g}"
    return f"#{p.id} {p.inst} {p.direction} oczekuje na open następnej świecy"
