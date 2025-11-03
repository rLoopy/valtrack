#!/bin/bash
# Script pour activer l'environnement virtuel et lancer le bot

cd "$(dirname "$0")"
source venv/bin/activate
python bot.py

