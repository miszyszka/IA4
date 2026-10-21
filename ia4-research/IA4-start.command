#!/bin/zsh
# IA 4 — AI Investor: dwuklik uruchamia `ia4 start` (instrukcja, sekcja 11c.3). Wersja projektu: 1.56 (2026-10-21)
# Plik można skopiować na Pulpit. Folder projektu: $IA4_DIR (domyślnie ~/Desktop/IA4). Ctrl+C kończy.
IA4_DIR="${IA4_DIR:-$HOME/Desktop/IA4}"
cd "$IA4_DIR/ia4-research" || { echo "Brak folderu $IA4_DIR/ia4-research"; read "?Enter zamyka okno…"; exit 1; }
source .venv/bin/activate || { echo "Brak środowiska .venv — instalacja: ia4-research/README.md"; read "?Enter zamyka okno…"; exit 1; }
python -m ia4.ai "$@"
echo
read "?Program zakończony. Enter zamyka okno…"
