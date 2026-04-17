FROM python:3.12-slim

# Arbeitsverzeichnis
WORKDIR /app

# Abhängigkeiten zuerst (für besseres Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bot-Dateien kopieren
COPY . .

# Daten-Verzeichnis für die Datenbank
RUN mkdir -p /app/data

# Port für Web-Dashboard
EXPOSE 5000

CMD ["python", "bot.py"]
