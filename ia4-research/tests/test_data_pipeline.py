"""
Testy potoku danych Etapu 0B: sync.py, data.py, verify.py. Wersja projektu: 0.34 (2026-09-28).

Bez Firestore i bez sieci: klient Firestore jest podmieniony na atrapę w pamięci,
granice skarbca na stałe z instrukcji 5.1, katalog danych na folder tymczasowy.

Uruchomienie z katalogu ia4-research:
    python -m pytest tests               # jeśli jest pytest
    python tests/test_data_pipeline.py   # bez pytest
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from ia4 import config, data, sync  # noqa: E402
import verify  # noqa: E402

VAULT = config.Vault(
    research_end_exclusive="2026-03-23", discovery_end_exclusive="2025-10-01",
    plot_start="2025-10-01", plot_end="2026-03-22", vault_start="2026-03-23",
    vault_end="2026-09-22", live_from="2026-09-23", vault_opened=False, stage=0,
    instruction_version="0.30",
)


# ---------------------------------------------------------------------------
#  Atrapa Firestore: kolekcje dokumentów, where (obie składnie), order_by, stream
# ---------------------------------------------------------------------------
class FakeDoc:
    def __init__(self, id_, d):
        self.id, self._d = id_, d

    def to_dict(self):
        return dict(self._d)


class FakeQuery:
    def __init__(self, docs, reads):
        self.docs, self.reads = docs, reads

    def where(self, *args, filter=None):  # noqa: A002 — jak w kliencie Firestore
        f, op, val = (filter.field_path, filter.op_string, filter.value) if filter else args
        assert op == ">"
        return FakeQuery({k: d for k, d in self.docs.items() if f in d and d[f] > val}, self.reads)

    def order_by(self, field):
        return FakeQuery(dict(sorted(self.docs.items(), key=lambda kv: kv[1][field])), self.reads)

    def stream(self):
        for k, d in self.docs.items():
            self.reads[0] += 1
            yield FakeDoc(k, d)


class FakeClient:
    def __init__(self):
        self.colls: dict[str, dict] = {}
        self.reads = [0]

    def collection(self, path):
        return FakeQuery(self.colls.setdefault(path, {}), self.reads)


T0 = datetime(2026, 9, 20, tzinfo=timezone.utc)


def session_doc(date, closes, vol=None, updated=T0):
    n = len(closes)
    return {"date": date, "slots": list(range(1, n + 1)), "o": closes, "h": closes, "l": closes,
            "c": closes, "v": vol if vol is not None else [0] * n, "updatedAt": updated}


def setup(tmp: Path) -> FakeClient:
    fc = FakeClient()
    config.CACHE_DIR = tmp
    config.MANIFEST_PATH = tmp / "_manifest.json"
    config.client = lambda: fc
    config.vault = lambda: VAULT
    config.group_of = lambda s: "main" if s == "AAPL" else "proof"
    config.all_symbols = lambda: ["AAPL", "KO"]
    data.PLOT_LOG = tmp / "poletko_zajrzenia.jsonl"
    return fc


def fill(fc: FakeClient):
    # KO: 40 sesji w odkrywaniu (2025-01..), bez wolumenu; AAPL: po jednej świecy na sesję
    ko = fc.colls.setdefault("proof/KO/sessions", {})
    aapl = fc.colls.setdefault("stocks/AAPL/candles", {})
    day = datetime(2025, 1, 2)
    for i in range(40):
        d = (day + timedelta(days=i)).strftime("%Y-%m-%d")
        ko[d] = session_doc(d, [50.0 + i * 0.1] * 7)
        aapl[f"{d}_1"] = {"date": d, "slot": 1, "open": 100.0, "high": 101.0, "low": 99.0,
                          "close": 100.5, "volume": 0, "updatedAt": T0}
    for d in ("2025-12-01", "2026-04-01", "2026-09-24"):   # poletko, skarbiec, na żywo
        ko[d] = session_doc(d, [60.0] * 7, [10] * 7)


# ---------------------------------------------------------------------------
#  sync.py
# ---------------------------------------------------------------------------
def test_sync_catches_backward_rewrite():
    """Wolumen dopisany do sesji sprzed roku musi dotrzeć do kopii lokalnej (0.30)."""
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        m = sync.load_manifest()
        sync.sync_symbol("KO", m)                      # pierwsze: całość
        assert m["KO"]["full"] and m["KO"]["synced_at"]
        first_reads = fc.reads[0]

        later = datetime.now(timezone.utc) + timedelta(hours=1)
        old = "2025-01-05"                             # dużo dalej niż 14 dni wstecz
        fc.colls["proof/KO/sessions"][old] = session_doc(old, [50.3] * 7, [777] * 7, later)
        new_d = "2026-09-25"
        fc.colls["proof/KO/sessions"][new_d] = session_doc(new_d, [61.0] * 7, [5] * 7, later)

        fc.reads[0] = 0
        sync.sync_symbol("KO", m)
        assert not m["KO"]["full"], "druga synchronizacja powinna być przyrostowa"
        assert fc.reads[0] < first_reads / 3, f"przyrost czytał za dużo: {fc.reads[0]}"
        df = pd.read_parquet(sync.parquet_path("KO"))
        assert (df[df["date"] == old]["v"] == 777).all(), "przepisanie wstecz nie dotarło (stary błąd 0.22)"
        assert new_d in set(df["date"]), "nowa sesja nie dotarła"
        assert not df.duplicated(["date", "slot"]).any()


def test_sync_old_manifest_forces_full():
    """Manifest sprzed 0.30 (bez synced_at) → jednorazowo pełne pobranie."""
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        m = sync.load_manifest()
        sync.sync_symbol("AAPL", m)
        m["AAPL"].pop("synced_at")
        m["AAPL"]["last_date"] = "2026-09-24"
        fc.colls["stocks/AAPL/candles"]["2025-01-03_1"]["volume"] = 1234   # bez zmiany updatedAt
        sync.sync_symbol("AAPL", m)
        assert m["AAPL"]["full"]
        df = pd.read_parquet(sync.parquet_path("AAPL"))
        assert int(df[df["date"] == "2025-01-03"]["v"].iloc[0]) == 1234


# ---------------------------------------------------------------------------
#  data.py — skarbiec i poletko (5.1)
# ---------------------------------------------------------------------------
def test_default_is_discovery_only():
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        sync.sync_symbol("KO", sync.load_manifest())
        df = data.load("KO")
        assert df["date"].max() < VAULT.discovery_end_exclusive
        assert not data.PLOT_LOG.exists()


def test_research_period_counts_as_plot_peek():
    """period='research' zawiera poletko — bez powodu błąd, z powodem wpis w dzienniku."""
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        sync.sync_symbol("KO", sync.load_manifest())
        try:
            data.load("KO", period="research")
            raise AssertionError("research bez plot_reason przeszło — dziura w 5.1")
        except data.PlotError:
            pass
        df = data.load("KO", period="research", plot_reason="test")
        assert "2025-12-01" in set(df["date"]) and df["date"].max() < VAULT.vault_start
        assert data.PLOT_LOG.read_text(encoding="utf-8").count("[research] test") == 1


def test_vault_locked():
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        sync.sync_symbol("KO", sync.load_manifest())
        for period in ("vault", "all"):
            try:
                data.load("KO", period=period)
                raise AssertionError(f"{period} bez unlock_vault przeszło")
            except data.VaultError:
                pass


# ---------------------------------------------------------------------------
#  verify.py
# ---------------------------------------------------------------------------
def test_verify_volume_and_jumps():
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        ko = fc.colls["proof/KO/sessions"]
        for i, d in enumerate(sorted(k for k in ko if k < "2025-10-01")):
            if i >= 5 and d != "2025-01-20":          # 5 sesji na początku bez wolumenu + dziura 01-20
                ko[d]["v"] = [100] * 7
        ko["2025-01-25"]["o"] = [5.0] + ko["2025-01-25"]["o"][1:]   # skok −90% jak NFLX
        sync.sync_symbol("KO", sync.load_manifest())

        vol = verify.volume_report(["KO"], VAULT.vault_start).iloc[0]
        assert vol["bez_wol_pocz"] == 5
        assert vol["bez_wol_srod"] == 1 and vol["przyklad_dziury"] == "2025-01-20"

        j = verify.price_jumps(["KO"])
        assert len(j) >= 1 and (j["date"] == "2025-01-25").any()
        assert (j[j["date"] == "2025-01-25"]["pct"].abs() >= verify.SPLIT_LIKE_PCT).all()


def test_verify_telemetry_compare_only_audited_range():
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        sync.sync_symbol("KO", sync.load_manifest())
        df = pd.read_parquet(sync.parquet_path("KO"))
        seen = df[df["date"] <= "2025-12-01"]
        tel = {"data": {"instruments": {"countedAt": "x", "items": [
            {"symbol": "KO", "first": "2025-01-02", "last": "2025-12-01",
             "sessions": int(seen["date"].nunique()), "candles": int(len(seen))}]}}}
        diffs, _ = verify.compare_with_telemetry(["KO"], tel)
        assert diffs == [], diffs                       # sesje po audycie nie są rozbieżnością
        tel["data"]["instruments"]["items"][0]["candles"] += 1
        diffs, _ = verify.compare_with_telemetry(["KO"], tel)
        assert len(diffs) == 1


def test_preflight_freshness_flags_stale_and_zero_volume():
    """0.33 — L32: preflight_freshness nie woła Firestore (tylko manifest + telemetria)."""
    with tempfile.TemporaryDirectory() as t:
        fc = setup(Path(t))
        fill(fc)
        m = sync.load_manifest()
        sync.sync_symbol("KO", m)
        sync.save_manifest(m)
        reads_before = fc.reads[0]

        # Audyt "w przyszłości" względem synced_at lokalnego — kopia ma być stara.
        future_audit = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        tel_stale = {"data": {"audit": {"fullAt": future_audit, "nightlyAt": future_audit},
                               "gaps": {"total": 1, "new": 1, "byType": {"ZERO_WOLUMEN": 1}}}}
        out = verify.preflight_freshness(tel_stale)
        assert any("nowszy" in line or "Odśwież" in line for line in out)
        assert any("ZERO_WOLUMEN" in line for line in out)

        # Audyt "w przeszłości" — kopia lokalna ma być aktualna.
        past_audit = "2020-01-01T00:00:00Z"
        tel_fresh = {"data": {"audit": {"fullAt": past_audit, "nightlyAt": past_audit}, "gaps": {}}}
        out2 = verify.preflight_freshness(tel_fresh)
        assert any("aktualna" in line for line in out2)

        assert fc.reads[0] == reads_before   # żadnego dodatkowego odczytu Firestore


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} testów zaliczonych")
    sys.exit(1 if failed else 0)
