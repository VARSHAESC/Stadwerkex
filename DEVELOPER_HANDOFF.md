# 🛠️ Developer Handoff Guide: EnergyBot Platform

Welcome to the **STADTWERKE X Infrastructure Platform**. This project is a multi-utility intelligence system designed for gas, water, and electricity infrastructure analysis.

## 🏗️ Architecture Overview

The system is built on a modern "Local-First" AI stack:
1.  **Frontend/UI**: [Streamlit](https://streamlit.io/) (`app.py`) for a responsive, dashboard-centric interface.
2.  **AI Engine**: RAG (Retrieval-Augmented Generation) system (`rag_engine.py`) using:
    *   **Vector DB**: [ChromaDB](https://www.trychroma.com/) for document/record retrieval.
    *   **Embeddings**: `sentence-transformers` for multilingual semantic search.
    *   **LLM Orchestration**: OpenAI-compatible API layer (currently configured for Groq/Llama 3.3).
3.  **Geospatial Engine**: `geo_utils.py` handles Excel ingestion and coordinates.
4.  **Routing Backend**: [OSRM](http://project-osrm.org/) (Open Source Routing Machine) running in Docker for street-accurate mapping.

---

## 🚀 Quick Start (Docker - Recommended)

The professional deployment runs via Docker Compose. This ensures OSRM is active and the mapping is accurate.

1.  **Configure Environment**:
    *   Copy `.env.template` to `.env`.
    *   Add your `LLM_API_KEY` (Groq or Azure OpenAI).
2.  **Launch**:
    ```bash
    docker compose up --build -d
    ```
3.  **Access**:
    *   App: `http://localhost:8600`
    *   OSRM Backend: `http://localhost:5000`

---

## 📂 Core Modules

### `app.py`
The main entry point. It manages session state (navigation, auth, map focus) and coordinates tab rendering.
*   **KPI Logic**: Dynamically calculates infrastructure health metrics from cached dataframes.
*   **Map Logic**: Integrates `folium` with CSS-injected animations and custom marker clustering.

### `rag_engine.py`
The "brain" of the platform.
*   **Multi-Utility Loading**: Ingests multiple utilities into a single vector space.
*   **Agentic Search**: Includes a "Direct ID lookup" engine that bypasses the LLM for high-accuracy coordinate/record retrieval.

### `geo_utils.py`
Data processing and GIS utility layer.
*   **Excel Sanitization**: Normalizes varied naming conventions in input spreadsheets.
*   **Network Topology**: (Critical!) Implements a Minimum Spanning Tree (MST) and street-projection algorithm to reconstruct utility networks from point-data using OSRM.

---

## 🛠️ Maintenance & Updates

### Updating the Database
The app uses `excel_data/Hausanschluss_data.xlsx`.
1.  Replace the file with updated data (ensure column names remain consistent).
2.  In the Sidebar, click **"🔄 KI-Speicher aktualisieren"**. 
3.  The app will automatically:
    *   Wipe the ChromaDB collection.
    *   Re-index the new rows.
    *   Regenerate the `utility_networks.geojson` using the OSRM routing engine.

### Error Handling
*   **ArrowTypeError**: If you see serialization errors in Streamlit tables, ensure new columns are cast to strings in `geo_utils.py` before return.
*   **OSRM Fallback**: If OSRM is down, the code automatically falls back to straight-line mappings.

---

## ⚙️ CI/CD & Deployment
*   **GitHub**: Use the provided `github_push_guide.md` to deploy to a private repo and connect to **Streamlit Cloud** for a public URL.
*   **Secrets**: Use Streamlit Secrets (TOML) for cloud deployments to keep the `.env` secure.
