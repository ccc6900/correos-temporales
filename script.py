name: Registro Automatizado

on:
  workflow_dispatch: # Permite ejecutar el script manualmente desde la pestaña Actions en GitHub

jobs:
  run-script:
    runs-on: ubuntu-latest

    steps:
      # 1. Descargar el código de tu repositorio
      - name: Checkout repositorio
        uses: actions/checkout@v4

      # 2. Configurar Python
      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      # 3. Instalar dependencias (Playwright y requests)
      - name: Instalar dependencias
        run: |
          python -m pip install --upgrade pip
          pip install playwright requests
          playwright install firefox
          playwright install-deps firefox

      # 4. Ejecutar el script pasando los secretos como variables de entorno
      - name: Ejecutar script.py
        env:
          TARGET_URL: ${{ secrets.TARGET_URL }}
          OUTLOOK_USER: ${{ secrets.OUTLOOK_USER }}
          OUTLOOK_PASS: ${{ secrets.OUTLOOK_PASS }}
        run: |
          python script.py
