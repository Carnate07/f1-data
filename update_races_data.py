
name: Aggiorna races-data.json

on:
  # Ogni lunedì alle 06:00 UTC (dopo il GP domenicale)
  schedule:
    - cron: '0 6 * * 1'
  # Permette di avviarlo manualmente dal tab Actions su GitHub
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Installa dipendenze
        run: pip install requests pytz

      - name: Esegui script aggiornamento
        run: python update_races_data.py

      - name: Commit e push se ci sono modifiche
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add races-data.json
          git diff --cached --quiet || git commit -m "Auto-update races-data.json [$(date -u '+%Y-%m-%d %H:%M UTC')]"
          git push
