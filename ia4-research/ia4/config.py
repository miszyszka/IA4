"""
IA 4 — konfiguracja środowiska badawczego.
Wersja projektu: 0.14 (2026-09-24) — musi zgadzać się z IA4_INSTRUKCJA.md

Dwie rzeczy, które ten moduł załatwia raz dla całego projektu:

1. KLUCZ SERWISOWY nigdy nie leży w repozytorium (zasada 2.6 i 6.5).
   Domyślna ścieżka to ~/.ia4/serviceAccount.json, czyli poza folderem
   ia4-research/. Można ją nadpisać zmienną IA4_FIREBASE_KEY.

2. GRANICE SKARBCA czytamy z Firestore (system/project), nie z kodu
   (zasada 5.1). Dzięki temu Python i Apps Script zawsze używają tej samej
   daty — gdy granica zmieni się w Apps Script, Python dowie się o tym sam,
   bez edycji tego pliku.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FIREBASE_PROJECT_ID = "ia-4-ff7af"

# Katalog na dane lokalne (pamięć podręczna parquet). Wewnątrz repo, ale
# wykluczony przez .gitignore — surowych danych nie trzymamy w gicie.
RESEARCH_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = RESEARCH_DIR / "data"
MANIFEST_PATH = CACHE_DIR / "_manifest.json"

DEFAULT_KEY_PATH = Path.home() / ".ia4" / "serviceAccount.json"


def key_path() -> Path:
    """Ścieżka do klucza serwisowego. Nigdy nie wskazuje do wnętrza repo."""
    p = Path(os.environ.get("IA4_FIREBASE_KEY", DEFAULT_KEY_PATH)).expanduser()
    if RESEARCH_DIR in p.resolve().parents:
        raise RuntimeError(
            f"Klucz serwisowy leży wewnątrz repozytorium ({p}).\n"
            "Przenieś go poza ia4-research/ — zasada 2.6 i 6.5 instrukcji."
        )
    if not p.exists():
        raise FileNotFoundError(
            f"Nie znaleziono klucza serwisowego: {p}\n"
            "Pobierz go z konsoli Firebase (Ustawienia projektu → Konta usługi →\n"
            "Wygeneruj nowy klucz prywatny) i zapisz jako ~/.ia4/serviceAccount.json,\n"
            "albo wskaż inną ścieżkę zmienną IA4_FIREBASE_KEY."
        )
    return p


@lru_cache(maxsize=1)
def client():
    """Klient Firestore. Tworzony raz na proces."""
    from google.cloud import firestore  # import lokalny: szybszy start CLI
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(str(key_path()))
    return firestore.Client(project=FIREBASE_PROJECT_ID, credentials=creds)


@dataclass(frozen=True)
class Vault:
    """Granice okresów z system/project (zasada 5.1)."""

    research_end_exclusive: str  # okres badawczy: wszystko PRZED tą datą
    vault_start: str
    vault_end: str
    live_from: str
    vault_opened: bool
    stage: int
    instruction_version: str

    @property
    def research_end(self) -> str:
        """Ostatni dzień okresu badawczego (włącznie)."""
        from datetime import date, timedelta

        d = date.fromisoformat(self.research_end_exclusive) - timedelta(days=1)
        return d.isoformat()


@lru_cache(maxsize=1)
def vault() -> Vault:
    """Czyta granice skarbca z Firestore. Brak dokumentu = twardy błąd."""
    doc = client().document("system/project").get()
    if not doc.exists:
        raise RuntimeError(
            "Brak dokumentu system/project w Firestore.\n"
            "Uruchom w Apps Script: IA 4 → Projekt → Pokaż / odśwież stan projektu."
        )
    d = doc.to_dict()
    missing = [k for k in ("researchEndExclusive", "vaultStart", "vaultEnd", "liveFrom") if k not in d]
    if missing:
        raise RuntimeError(f"system/project nie ma pól: {', '.join(missing)}")
    return Vault(
        research_end_exclusive=d["researchEndExclusive"],
        vault_start=d["vaultStart"],
        vault_end=d["vaultEnd"],
        live_from=d["liveFrom"],
        vault_opened=bool(d.get("vaultOpened", False)),
        stage=int(d.get("stage", 0)),
        instruction_version=str(d.get("instructionVersion", "?")),
    )


@lru_cache(maxsize=1)
def universe() -> dict:
    """Listy instrumentów z system/universe (pisane przez Proof.gs)."""
    doc = client().document("system/universe").get()
    if not doc.exists:
        raise RuntimeError(
            "Brak dokumentu system/universe w Firestore.\n"
            "Uruchom w Apps Script: IA 4 → Spółki kontrolne → Pobierz historię."
        )
    d = doc.to_dict()
    return {
        "main": list(d.get("live", [])),
        "proof": list(d.get("proof", [])),
        "context": list(d.get("context", [])),
        "proof_ready": list(d.get("proofReady", [])),
        "context_ready": list(d.get("contextReady", [])),
        "proof_partial": list(d.get("proofPartial", [])),
        "proof_failed": list(d.get("proofFailed", [])),
    }


def all_symbols() -> list[str]:
    u = universe()
    return u["main"] + u["proof"] + u["context"]


def group_of(symbol: str) -> str:
    u = universe()
    if symbol in u["main"]:
        return "main"
    if symbol in u["context"]:
        return "context"
    return "proof"


def fs_id(symbol: str) -> str:
    """Identyfikator w Firestore — bez „^", jak w fsId_ z Code.gs."""
    return symbol.lstrip("^")
