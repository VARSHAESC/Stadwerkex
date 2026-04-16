========================================
EnergyBot – Online Demo (Gemini-basiert)
========================================

Voraussetzungen
---------------
• Windows 10/11 oder Windows Server mit Docker Desktop
• Internetzugang (für Gemini API)
• Eigenen Gemini API Key

Ordnerstruktur
--------------
EnergyBot_Online/
  app.py, geo_utils.py, rag_engine.py
  requirements.txt, Dockerfile, compose.yaml, .dockerignore
  .env.example
  run_energybot_online.bat, stop_energybot_online.bat

WICHTIG (Datenschutz / GDPR)
----------------------------
• Bitte KEINE Excel-Dateien an uns senden.
• Legen Sie Ihre Excel-Daten nur lokal auf Ihrem Server ab (siehe Schritt 3).
• Alle Daten bleiben in Ihrem Netzwerk. In das Image werden KEINE Daten eingebunden.

Schritte (Erstinstallation)
---------------------------
1) Docker Desktop installieren und starten:
   https://www.docker.com/products/docker-desktop

2) .env anlegen:
   • Kopieren Sie .env.example -> .env
   • Tragen Sie Ihren GEMINI_API_KEY ein

3) Ordner für lokale Daten anlegen:
   • Erstellen Sie im Projektordner:
       excel_data\
       cache\
       chroma_db\
   • Legen Sie Ihre Exceldatei z.B. als:
       excel_data\kunden_anschluesse.xlsx

4) Anwendung starten:
   • Doppelklick: run_energybot_online.bat
   • Oder im Terminal:
       docker compose build
       docker compose up

5) Dashboard öffnen:
   • http://localhost:8501

6) Anwendung stoppen:
   • Doppelklick: stop_energybot_online.bat
   • Oder im Terminal:
       docker compose down

Hinweise
--------
• Port-Konflikt: Falls 8501 bereits belegt ist, ändern Sie in compose.yaml z.B. auf "8600:8501" und öffnen http://localhost:8600
• Wissenbasis (RAG): Klicken Sie im Sidebar auf "Build / Refresh Knowledge Base", wenn Sie die Excel aktualisieren.
• Geokodierung: Für große Datenmengen empfehlen wir vorhandene Koordinaten; ansonsten kann Adress-Geokodierung genutzt werden (Nominatim Rate Limits).
• Support: Für einen Offline-Modus (ohne Internet / ohne Gemini) kann später eine eigene Variante bereitgestellt werden.