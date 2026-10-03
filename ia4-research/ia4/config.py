"""
IA 4 — konfiguracja kopii lokalnej.
Wersja projektu: 1.14 (2026-10-03) — musi zgadzać się z IA4_INSTRUKCJA.md

KLUCZ SERWISOWY nigdy nie leży w repozytorium (instrukcja, zasada 5).
Domyślna ścieżka to ~/.ia4/serviceAccount.json, poza folderem ia4-research/.
Można ją nadpisać zmienną IA4_FIREBASE_KEY. Listy instrumentów czytamy
z Firestore (system/universe, pisze je Code.gs), nie z kodu.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

FIREBASE_PROJECT_ID = "ia-4-ff7af"

# Kopia lokalna (parquet). Wewnątrz repo, ale wykluczona przez .gitignore —
# surowych danych nie trzymamy w gicie.
RESEARCH_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = RESEARCH_DIR / "data"
MANIFEST_PATH = CACHE_DIR / "_manifest.json"

DEFAULT_KEY_PATH = Path.home() / ".ia4" / "serviceAccount.json"

# doubleProof — kopia listy z Code.gs (CONFIG.DOUBLE_PROOF_SYMBOLS), używana tylko gdy
# Firestore jest niedostępny, żeby poszukiwanie nigdy nie wzięło tych spółek (instrukcja 6a).
DOUBLE_PROOF_FALLBACK = ("AMD", "INTC", "QCOM", "CSCO", "ADBE", "LRCX", "C", "MS", "SCHW", "COP",
                         "OXY", "SLB", "BA", "GE", "UBER", "F", "GM", "COST", "BMY", "CMCSA")


def key_path() -> Path:
    """Ścieżka do klucza serwisowego. Nigdy nie wskazuje do wnętrza repo."""
    p = Path(os.environ.get("IA4_FIREBASE_KEY", DEFAULT_KEY_PATH)).expanduser()
    if RESEARCH_DIR in p.resolve().parents:
        raise RuntimeError(
            f"Klucz serwisowy leży wewnątrz repozytorium ({p}).\n"
            "Przenieś go poza ia4-research/ — instrukcja, zasada 5."
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


@lru_cache(maxsize=1)
def universe() -> dict:
    """Listy instrumentów z system/universe (pisze je Code.gs przy „Konfiguruj”)."""
    doc = client().document("system/universe").get()
    if not doc.exists:
        raise RuntimeError(
            "Brak dokumentu system/universe w Firestore.\n"
            "Uruchom w Apps Script: IA 4 → Konfiguruj i włącz automat."
        )
    d = doc.to_dict()
    return {
        "main": list(d.get("live", [])),
        "proof": list(d.get("proof", [])),
        "context": list(d.get("context", [])),
        "doubleProof": list(d.get("doubleProof", [])),   # tylko do weryfikacji (instrukcja 6a)
    }


def all_symbols() -> list[str]:
    u = universe()
    return u["main"] + u["proof"] + u["context"] + u["doubleProof"]


def group_of(symbol: str) -> str:
    u = universe()
    if symbol in u["main"]:
        return "main"
    if symbol in u["context"]:
        return "context"
    if symbol in u["doubleProof"]:
        return "doubleProof"
    return "proof"


def fs_id(symbol: str) -> str:
    """Identyfikator w Firestore — bez „^", jak w fsId_ z Code.gs."""
    return symbol.lstrip("^")
