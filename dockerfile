# Verwenden Sie das offizielle Python-Basisbild
FROM python:3-slim

# Setzen Sie das Arbeitsverzeichnis im Container
WORKDIR /app
COPY . /app

# Install Librarys needed for selenium
RUN apt-get update \
    && apt-get install -y chromium chromium-driver libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && pip install -r requirements.txt \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Setzen Sie die Umgebungsvariable für den Headless-Modus von Chrome
ENV DISPLAY=:99

# Starten Sie Ihre Anwendung
CMD ["python3", "sma_scraper.py"]
