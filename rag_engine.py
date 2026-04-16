# -*- coding: utf-8 -*-
"""
rag_engine.py — Multi-Utility Hybrid Engine (Gas | Strom | Wasser)
Strictly Offline Version using Gemma 3 via Ollama.
"""

from __future__ import annotations

# --- NumPy 2.x compatibility shim ---
import numpy as _np
if not hasattr(_np, "float_"):   _np.float_ = _np.float64
if not hasattr(_np, "int_"):     _np.int_ = int
if not hasattr(_np, "bool_"):    _np.bool_ = bool
if not hasattr(_np, "object_"): _np.object_ = object
# ------------------------------------

import os
import re
import io
from typing import List, Dict, Any, Optional, Sequence, Set

import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import requests
import json
import docx

from geo_utils import load_excel, CSV_FILES, ALL_UTILITIES, MATERIAL_LIFESPAN, get_utility_df, get_unified_df

load_dotenv()

# ─────────────── Config ───────────────
OFFLINE: bool = os.getenv("OFFLINE_MODE", "false").lower() == "true"
PERSIST_DIR: str = "./chroma_db"
EMBED_MODEL_NAME: str = os.getenv(
    "EMBED_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
RETURN_ALL_MAX: int = 100_000

# ─────────────── Utilities ───────────────
def _safe(v: Any) -> str:
    return "" if pd.isna(v) else str(v)

def row_to_paragraph(row: Dict[str, Any], utility: str = "") -> str:
    general_keys = ["Gemeinde", "Postleitzahl", "Straße", "Hausnummer", "Zusatz", "Objekt-ID_Global"]
    util_specific = {k: v for k, v in row.items() if k not in general_keys and k != "Sparte"}
    parts = []
    if utility: parts.append(f"VERSORGUNGSART: {utility}")
    gen = [f"{k}: {_safe(row.get(k))}" for k in general_keys if row.get(k) and pd.notna(row.get(k))]
    if gen: parts.append("ALLGEMEINE OBJEKTDATEN: " + ", ".join(gen))
    spec = [f"{k}: {_safe(v)}" for k, v in util_specific.items() if pd.notna(v) and str(v).strip() not in ("", "nan")]
    if spec: parts.append(f"DATEN ZUM NETZANSCHLUSS {utility}: " + ", ".join(spec))
    return " | ".join(parts) + "."

# ─────────────── Vector Store ───────────────
class VectorStore:
    def __init__(self, persist_dir: str = PERSIST_DIR, name: str = "energy_kb", embed_model: str = EMBED_MODEL_NAME):
        self.client = chromadb.PersistentClient(path=persist_dir, settings=Settings(anonymized_telemetry=False))
        try:
            self.col = self.client.get_collection(name)
        except Exception:
            self.col = self.client.create_collection(name, metadata={"embed_model": embed_model})
        meta = self.col.metadata or {}
        if meta.get("embed_model") != embed_model:
            self.client.delete_collection(name)
            self.col = self.client.create_collection(name, metadata={"embed_model": embed_model})

    def reset(self, metadata: Optional[Dict[str, Any]] = None):
        name = self.col.name
        self.client.delete_collection(name)
        self.col = self.client.create_collection(name, metadata=metadata)

    def count(self) -> int:
        try: return self.col.count()
        except: return 0

    def add(self, ids, embeddings, metadatas, documents):
        self.col.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)

    def query(self, query_embeddings, top_k: int = 5):
        cnt = self.count()
        if cnt == 0: return {"metadatas": [[]], "documents": [[]], "distances": [[]]}
        return self.col.query(query_embeddings=query_embeddings, n_results=min(top_k, cnt))

class Embedder:
    def __init__(self, model_name: str = EMBED_MODEL_NAME):
        import os
        os.environ["TQDM_DISABLE"] = "1"
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        self.model = SentenceTransformer(model_name)
    def embed(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        return self.model.encode(texts, batch_size=batch_size, show_progress_bar=False).tolist()

# ─────────────── Main Engine ───────────────
class EnergyRAG:
    def __init__(self, persist_dir: str = PERSIST_DIR, embed_model: str = EMBED_MODEL_NAME):
        self.vs = VectorStore(persist_dir, "energy_kb_multi", embed_model)
        self.embedder = Embedder(embed_model)
        
        # --- Provider-Agnostic LLM Configuration ---
        self.llm_api_key = os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY"))
        self.llm_model = os.getenv("LLM_MODEL_NAME", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        # Base URL for OpenAI-compatible APIs (default to Groq if not specified)
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        
        self.unified_df = get_unified_df()
        self.reference_manual = self._load_reference_manual()

    def _load_reference_manual(self) -> str:
        """Loads the Word reference manual for system prompt context."""
        doc_path = os.path.join("excel_data", "Hausanschluss_KI_Referenzhandbuch.docx")
        if not os.path.exists(doc_path):
            return "Reference Manual not found."
        try:
            doc = docx.Document(doc_path)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except:
            return "Error loading Reference Manual."

    def check_llm_status(self) -> Dict[str, Any]:
        if not self.llm_api_key:
            return {"ok": False, "msg": "API Key fehlt."}
        try:
            # Simple check call to models list (OpenAI-compatible)
            headers = {"Authorization": f"Bearer {self.llm_api_key}"}
            resp = requests.get(f"{self.llm_base_url}/models", headers=headers, timeout=5)
            if resp.status_code == 200:
                provider_name = "Online" if "groq" in self.llm_base_url else "Custom Provider"
                return {"ok": True, "msg": f"{provider_name}: {self.llm_model}"}
            return {"ok": False, "msg": f"LLM Error: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"Verbindungsfehler: {str(e)[:50]}"}

    def init_or_refresh_kb(self, utility: Optional[str] = None, reset: bool = False) -> int:
        utils = [utility] if utility else ALL_UTILITIES
        if reset: 
            # Preserve metadata during reset to avoid startup deletion loop
            old_meta = self.vs.col.metadata
            self.vs.reset(metadata=old_meta)
        total = 0
        for util in utils:
            df = get_utility_df(util)
            if df.empty: continue
            docs, ids, metas = [], [], []
            for i, row in df.iterrows():
                row_id = f"{util}_{row.get('Datensatz', i)}"
                para = row_to_paragraph(row.to_dict(), utility=util)
                if not para: continue
                docs.append(para)
                ids.append(row_id)
                metas.append({
                    "utility": util, 
                    "id": str(row.get("Kundennummer", "")),
                    "name": str(row.get("Kundenname", ""))
                })
            if docs:
                embeddings = self.embedder.embed(docs)
                self.vs.add(ids=ids, embeddings=embeddings, metadatas=metas, documents=docs)
                total += len(docs)
        self.unified_df = get_unified_df()
        return total

    def transcribe_audio(self, audio_bytes: bytes) -> Dict[str, Any]:
        if not self.llm_api_key: return {"ok": False, "text": "API Key fehlt."}
        if not audio_bytes or len(audio_bytes) < 100:
            return {"ok": False, "text": "Audio-Daten zu kurz oder leer."}
            
        try:
            headers = {"Authorization": f"Bearer {self.llm_api_key}"}
            files = {
                "file": ("audio.webm", io.BytesIO(audio_bytes), "audio/webm"),
                "model": (None, os.getenv("WHISPER_MODEL", "whisper-large-v3")),
            }
            # Whisper endpoint is usually /audio/transcriptions
            resp = requests.post(f"{self.llm_base_url}/audio/transcriptions", headers=headers, files=files, timeout=30)
            if resp.status_code == 200:
                t = resp.json().get("text", "")
                return {"ok": True, "text": t}
            return {"ok": False, "text": f"LLM Error: {resp.status_code} - {resp.text}"}
        except Exception as e:
            return {"ok": False, "text": f"Verbindungsfehler: {str(e)}"}

    def _try_dataframe_answer(self, question: str) -> Optional[Dict[str, Any]]:
        ql = (question or "").lower()
        
        # 0. STRICT BYPASS: If this is an update command, we MUST use the Agentic Engine
        update_keywords = ["update", "ändern", "setze", "change", "aktualisier", "korrigier", "fix", "put", "schreib"]
        if any(x in ql for x in update_keywords):
            return None

        if self.unified_df.empty: self.unified_df = get_unified_df()
        
        # 1. Direct ID Lookup (Prioritized for Queries only)
        id_match = re.search(r'(\d+)', ql)
        if id_match and not any(x in ql for x in ["älter", "jahre", "vor", "nach", "count", "anzahl", "old", "older", "years", "more", "over", "über", "list", "table", "tabelle", "alle", "all"]):
            sid = id_match.group(1)
            search_df = self.unified_df.copy()
            
            # Smart Sparten Filter (Optional)
            target_sparte = None
            if "gas" in ql: target_sparte = "Gas"
            elif "wasser" in ql: target_sparte = "Wasser"
            
            if target_sparte:
                search_df = search_df[search_df["Sparte"] == target_sparte]
            
            # Find the ID
            matches = pd.DataFrame()
            for col in ["Kundennummer", "Objekt-ID", "Objekt-ID_Global"]:
                if col in search_df.columns:
                    mask = search_df[col].astype(str).str.contains(rf'\b{sid}\b', regex=True, na=False)
                    if mask.any():
                        matches = search_df[mask]
                        break
            
            if not matches.empty:
                res = matches.iloc[0]
                lines = [f"✅ **Datensatz gefunden: {res.get('Sparte', '')} - {res.get('Kundennummer', sid)}**", ""]
                
                # Check specifics
                if any(x in ql for x in ["material", "werkstoff", "type", "art"]):
                    lines.append(f"🏗️ **Material:** {res.get('Werkstoff', 'n/a')} ({res.get('Dimension', '')})")
                
                if any(x in ql for x in ["strasse", "straße", "hausnummer", "address", "location"]):
                    lines.append(f"📍 **Adresse:** {res.get('Straße', 'n/a')} {res.get('Hausnummer', '')}")
                    lines.append(f"🏙️ **Ort:** {res.get('Postleitzahl', '')} {res.get('Gemeinde', '')}")

                if any(x in ql for x in ["alter", "age", "year", "einbau"]):
                    lines.append(f"⏳ **Alter:** {int(res.get('Alter', 0))} Jahre (Einbau: {res.get('Einbaujahr', 'unbekannt')})")

                if len(lines) <= 2: # Show all if vague
                    lines.append(f"📍 **Adresse:** {res.get('Straße', 'n/a')} {res.get('Hausnummer', '')}")
                    lines.append(f"🏗️ **Material:** {res.get('Werkstoff', 'n/a')}")
                    lines.append(f"⚠️ **Risiko:** {res.get('Risiko', 'n/a')}")
                
                if any(x in ql for x in ["karte", "map", "zeige", "view", "show"]):
                    if pd.notna(res.get("lat")) and pd.notna(res.get("lon")):
                        return {
                            "answer": f"📍 **Navigation zur Karte gestartet...**\nIch zeige Ihnen den Anschluss `{res.get('Kundennummer', sid)}` ({res.get('Sparte', '')}) in der `{res.get('Straße', '')} {res.get('Hausnummer', '')}` auf der Karte.",
                            "hits": [],
                            "model_used": "Navigation-Engine-v1",
                            "switched": True,
                            "pending_action": {
                                "type": "navigate_map",
                                "args": {
                                    "customer_id": str(res.get("Kundennummer", sid)),
                                    "lat": float(res["lat"]),
                                    "lon": float(res["lon"])
                                }
                            }
                        }
                    else:
                        return {"answer": f"⚠️ Der Kunde `{sid}` wurde gefunden, hat aber leider keine Koordinaten für die Karte.", "hits": [], "model_used": "Navigation-Engine-v1", "switched": True}

                # ── Only attach download_data if specifically requested (Strict Keywords) ──
                dl_requested = any(x in ql for x in ["excel", "csv", "tabelle", "table", "format", "tabular"])
                resp = {"answer": "\n".join(lines), "hits": [], "model_used": "Direct-ID-Engine-v2", "switched": True}
                if dl_requested:
                    resp["download_data"] = matches.to_csv(index=False).encode('utf-8-sig')
                return resp

        # 2. Greetings (Fixed for False Positives like "whicH I...")
        if ql.strip() in ["hi", "hallo", "hello", "guten tag", "hey"]:
            return {"answer": "Guten Tag! Ich bin das ESC Infrastructure Intelligence System. Wie kann ich Ihnen heute bei der Analyse Ihrer Gas- oder Wasser-Anschlussdaten helfen?", "hits": [], "model_used": "System", "switched": False}

        # 3. Analytical Trends (Materials over time)
        if any(x in ql for x in ["material", "werkstoff", "anschlussart"]) and any(x in ql for x in ["wann", "verbaut", "historisch", "zeitraum"]):
            try:
                target_sparte = None
                if "gas" in ql: target_sparte = "Gas"
                elif "wasser" in ql: target_sparte = "Wasser"

                df = self.unified_df.copy()
                if target_sparte:
                    df = df[df["Sparte"].astype(str).str.contains(target_sparte, case=False, na=False)]

                df["Dekade"] = (df["Einbaujahr"] // 10) * 10
                summary = df.groupby(["Dekade", "Werkstoff"]).size().unstack(fill_value=0)
                sparte_text = f" ({target_sparte})" if target_sparte else ""
                lines = [f"📜 **Historische Analyse: Materialverwendung{sparte_text}**", ""]
                for decade in sorted(summary.index.dropna()):
                    if decade < 1920: continue
                    mats = summary.loc[decade]
                    top = mats[mats > 0].sort_values(ascending=False)
                    mat_str = ", ".join([f"{m} ({q})" for m, q in top.items()])
                    lines.append(f"- **{int(decade)}er Jahre**: {mat_str}")
                return {"answer": "\n\n".join(lines), "hits": [], "model_used": "History-Engine", "switched": True, "download_data": summary.to_csv().encode('utf-8-sig')}
            except: pass

        # 4. Numeric Age Filters
        age_match = re.search(r'(älter|older|>|über|over|more\s*than)\s*(?:als\s*|than\s*)?(\d+)', ql)
        if age_match:
            try:
                threshold = int(age_match.group(2))
                
                target_sparte = None
                if "gas" in ql: target_sparte = "Gas"
                elif "wasser" in ql: target_sparte = "Wasser"
                
                search_df = self.unified_df
                if target_sparte:
                    search_df = search_df[search_df["Sparte"].astype(str).str.contains(target_sparte, case=False, na=False)]

                matches = search_df[search_df["Alter"] > threshold].sort_values("Alter", ascending=False)
                if not matches.empty:
                    sparte_text = f" {target_sparte}-" if target_sparte else " "
                    answer_header = f"📊 **Analyse: {len(matches)}{sparte_text}Objekte > {threshold} Jahre**"
                    exact_count_msg = f"Es wurden insgesamt **{len(matches)}{sparte_text}Hausanschlüsse** gefunden, die älter als {threshold} Jahre sind."
                    lines = [answer_header, exact_count_msg, "Hier sind die Top-Treffer:", ""]
                    for _, r in matches.head(5).iterrows():
                        lines.append(f"- {r['Sparte']} ({r['Kundennummer']}): {r['Straße']} | **{int(r['Alter'])} J.**")
                    
                    return {
                        "answer": "\n\n".join(lines), 
                        "hits": [], 
                        "model_used": "Age-Filter-Engine", 
                        "switched": True,
                        "download_data": matches.to_csv(index=False).encode('utf-8-sig')
                    }
            except: pass

        # 5. Risk & Criticality Filters
        if any(re.search(rf'\b{x}\b', ql) for x in ["risiko", "risk", "risikoreich", "kritisch", "kritisches", "kritische", "critical", "hoch", "hohes", "hohe", "hoher", "hohem", "high", "low", "niedrig", "niedriges", "niedrige", "niedrigen", "mittel", "mittleres", "mittlere", "mittleren", "medium"]):
            try:
                target_sparte = None
                if "gas" in ql: target_sparte = "Gas"
                elif "wasser" in ql: target_sparte = "Wasser"
                
                search_df = self.unified_df
                if target_sparte:
                    search_df = search_df[search_df["Sparte"].astype(str).str.contains(target_sparte, case=False, na=False)]

                if any(re.search(rf'\b{x}\b', ql) for x in ["kein", "keine", "no", "niedrig", "niedriges", "niedrige", "niedrigen", "low", "lowest", "unbedenklich","safe"]):
                    matches = search_df[search_df["Risiko"] == "Niedrig"]
                    status_text = "mit geringem oder keinem Risiko"
                    emoji = "✅"
                elif any(re.search(rf'\b{x}\b', ql) for x in ["mittel", "mittleres", "mittlere", "mittleren", "medium"]):
                    matches = search_df[search_df["Risiko"] == "Mittel"]
                    status_text = "mit mittlerem Risiko"
                    emoji = "⚠️"
                elif any(re.search(rf'\b{x}\b', ql) for x in ["hoch", "hohes", "hohe", "hoher", "hohem", "high", "highest", "kritisch", "kritisches", "kritische", "critical"]):
                    matches = search_df[search_df["Risiko"] == "Hoch"]
                    status_text = "hochrisikig / kritisch"
                    emoji = "🚨"
                else:
                    matches = search_df[search_df["Risiko"].isin(["Hoch", "Mittel"])]
                    status_text = "mit erhöhtem Risiko"
                    emoji = "🚨"
                    
                if not matches.empty:
                    sparte_text = f" {target_sparte}-" if target_sparte else " "
                    answer_header = f"{emoji} **Risiko-Analyse: {len(matches)}{sparte_text}Objekte gefunden**"
                    exact_count_msg = f"Es wurden insgesamt **{len(matches)}{sparte_text}Hausanschlüsse** als **{status_text}** eingestuft."
                    lines = [answer_header, exact_count_msg, "Hier sind die obersten Treffer:", ""]
                    for _, r in matches.head(5).iterrows():
                        lines.append(f"- {r['Sparte']} ({r['Kundennummer']}): {r['Straße']} | **Risiko: {r['Risiko']}**")
                    
                    return {
                        "answer": "\n\n".join(lines), 
                        "hits": [], 
                        "model_used": "Risk-Engine", 
                        "switched": True,
                        "download_data": matches.to_csv(index=False).encode('utf-8-sig')
                    }
            except: pass

        # 6. Full Table / Listing
        table_keywords = ["liste", "tabelle", "alle", "list", "table", "all", "übersicht", "total", "excel", "csv", "daten", "format"]
        if any(x in ql for x in table_keywords):
            target_sparte = None
            if "gas" in ql: target_sparte = "Gas"
            elif "wasser" in ql: target_sparte = "Wasser"
            
            df = self.unified_df.copy()
            if target_sparte:
                df = df[df["Sparte"].astype(str).str.contains(target_sparte, case=False, na=False)]
            
            if any(x in ql for x in ["high risk", "hohes risiko", "risiko hoch", "hoch"]):
                df = df[df["Risiko"] == "Hoch"]
            elif any(x in ql for x in ["medium", "mittel", "mittleres risiko"]):
                df = df[df["Risiko"] == "Mittel"]
            elif any(x in ql for x in ["low", "niedrig", "gering"]):
                df = df[df["Risiko"] == "Niedrig"]
                
            unique_streets = [str(s) for s in df["Straße"].dropna().unique() if len(str(s)) > 3]
            matched_streets = [s for s in unique_streets if s.lower() in ql]
            if matched_streets:
                best_street = max(matched_streets, key=lambda x: len(x))
                df = df[df["Straße"] == best_street]
                hn_match = re.search(r'\b\d{1,4}[a-zA-Z]?\b', ql.replace(best_street.lower(), ''))
                if hn_match:
                    num = hn_match.group()
                    df = df[df["Hausnummer"].astype(str).str.lower() == num.lower()]

            if target_sparte:
                answer = f"✅ **{target_sparte}-Übersicht**: Ich habe {len(df)} Anschlüsse gefunden."
            else:
                answer = f"✅ **Gesamtübersicht**: Ich habe {len(df)} Anschlüsse gefunden."
            
            if not df.empty:
                cols = ["Kundenname", "Kundennummer", "Sparte", "Straße", "Hausnummer", "Risiko", "Alter"]
                available_cols = [c for c in cols if c in df.columns]
                preview_df = df[available_cols].head(15)
                table_md = preview_df.to_markdown(index=False)
                
                return {
                    "answer": f"{answer}\n\n{table_md}\n\n*(Oben sehen Sie die ersten 15 Zeilen. Nutzen Sie den Button unten für den vollständigen Export als CSV)*",
                    "hits": [],
                    "model_used": "Full-Table-Engine",
                    "switched": True,
                    "download_data": df.to_csv(index=False).encode('utf-8-sig')
                }
            else:
                return {
                    "answer": f"📊 **Tabelle**: Ich konnte leider keine Daten für '{target_sparte or 'Gesamt'}' finden, die Ihrer Anfrage entsprechen.",
                    "hits": [],
                    "model_used": "Full-Table-Engine",
                    "switched": True
                }

        # 6. General Map Navigation (Only triggers if NO table keywords are present)
        map_keywords = ["karte", "map", "landkarte", "netz-karte", "zeige", "view", "show", "öffne", "open"]
        if any(x in ql for x in map_keywords) and not id_match and not any(x in ql for x in table_keywords):
             return {
                "answer": "🗺️ **Ich erstelle die Netz-Karte direkt hier im Chat...**",
                "hits": [],
                "model_used": "Navigation-Engine-v1",
                "switched": True,
                "pending_action": {"type": "navigate_map_general", "args": {"filter": target_sparte or "All"}}
             }

        return None

    def answer_question(self, question: str, utility: Optional[str] = None, history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        ql = (question or "").lower()
        
        # 0. SKIP FAST ENGINE FOR UPDATES (Force Agentic Tool Mode)
        update_keywords = ["update", "ändern", "setze", "change", "aktualisier", "korrigier", "fix", "put", "schreib"]
        is_update = any(x in ql for x in update_keywords)
        
        search_query = question
        if history:
            history_to_use = history[:-1] if history and history[-1].get("content", "") == question else history
            last_user_msg = next((h["content"] for h in reversed(history_to_use) if h["role"] == "user"), "")
            
            # If current question is a follow up (short or lacks numbers), conditionally prepend the previous context
            if last_user_msg and len(question.split()) < 10 and not re.search(r'\d+', question):
                risk_keys = ["risiko", "risk", "kritisch", "kritisches", "critical", "hoch", "high", "low", "niedrig", "mittel", "medium", "mittleres"]
                age_keys = ["älter", "older", "jahre", "years", "alter", "age", "more"]
                map_keys = ["karte", "map", "landkarte", "netz-karte", "view", "show", "öffne", "open"]
                table_keys = ["liste", "tabelle", "alle", "list", "table", "all", "übersicht", "total"]
                
                ql_curr = question.lower()
                has_new_intent = any(k in ql_curr for k in risk_keys + age_keys + map_keys + table_keys)
                is_context_id = bool(re.search(r'\d{4,}', last_user_msg)) # IDs are typically 4+ digits
                
                # Prepend context if it contains a clear ID marker, or if the current question lacks a strong new intent
                if is_context_id or not has_new_intent:
                    search_query = f"{last_user_msg}. {question}"
                
        # For the fast lookup dataframe engine, use context-aware query if safely built
        if not is_update:
            df_res = self._try_dataframe_answer(search_query)  # Use the context-aware query here too!
            if df_res: 
                return df_res

        status = self.check_llm_status()
        if not status["ok"]:
            return {"answer": f"⚠️ **Service-Status**: {status['msg']}", "hits": [], "model_used": "Status-Check", "switched": False}

        hits = []
        try:
            results = self.vs.query(query_embeddings=self.embedder.embed([search_query]), top_k=4)
            hits = [{"meta": m, "doc": d, "score": 1-dist} for m, d, dist in zip(results["metadatas"][0], results["documents"][0], results["distances"][0])]
            
            ctx = "\n---\n".join([h["doc"] for h in hits])
            
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }

            if is_update:
                # --- AGENTIC MODE: send tools for write operations ---
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "update_asset",
                            "description": "Updates any field of a utility asset in the database. Call this when the user asks to change, set, or update any value.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "customer_id": {"type": "string", "description": "Customer ID, e.g. '3' or 'Kunde 3'."},
                                    "field_name": {"type": "string", "description": "Column to update, e.g. Hausnummer, Schutzrohr, Werkstoff, Installateur Name, Gemeinde, Gestattungsvertrag, etc."},
                                    "new_value": {"type": "string", "description": "New value to write."},
                                    "utility": {"type": "string", "enum": ["Gas", "Wasser", "Gemeinsam"], "description": "Utility sector. Use Gemeinsam for shared fields."}
                                },
                                "required": ["customer_id", "field_name", "new_value", "utility"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "navigate_to_map",
                            "description": "Navigates to the map view for a specific customer or the general map. Call this when the user asks to see a customer, an address, or simply 'the map'.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "customer_id": {"type": "string", "description": "Optional Customer ID to show on map. If omitted, shows general map."}
                                }
                            }
                        }
                    }
                ]
                payload = {
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": (
                            "You are the ESC Agentic Assistant. You have tools to update the database and navigate the map. "
                            "1. If the user asks to change/update a value, use 'update_asset'. "
                            "2. If the user asks to see a customer or address on the map OR simply requests the map view, use 'navigate_to_map'. "
                            "3. If the user says 'Yes', 'Ja', 'Gerne' or similar after you offered to show the map, use 'navigate_to_map'. "
                            "CRITICAL: If the user wants to see the map, ONLY call the tool. Do NOT provide coordinates in text. "
                            "CRITICAL MAP INSTRUCTION: ONLY use the 'navigate_to_map' tool IF the user EXPLICITLY asks to view a map, or confirms they want to see the map (e.g. 'Yes', 'Show me'). "
                            "NEVER use the map tool as a fallback or for answering questions like 'how old is it' or 'what is the material'. "
                            "Be proactive. In the same language as the question."
                        )}
                    ],
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.0,
                    "max_tokens": 300
                }
                # Add history if available (map 'bot' to 'assistant')
                if history:
                    history_to_use = history[:-1] if history[-1].get("content", "") == question else history
                    for h in history_to_use[-6:]:
                        role = "assistant" if h["role"] == "bot" else h["role"]
                        payload["messages"].append({"role": role, "content": h["content"]})
                
                payload["messages"].append({"role": "user", "content": f"Question: {question}"})
            else:
                # --- FAST READ MODE WITHOUT TOOLS ---
                # We disable tools for read mode completely to prevent hallucination, rely on fast-engine for map nav.
                payload = {
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": (
                            "You are an infrastructure data expert. "
                            "Answer questions accurately based on the provided Data. Keep it concise, friendly, and in the language of the user."
                            f"Context: {self.reference_manual[:300]}"
                        )}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600
                }
                if history:
                    history_to_use = history[:-1] if history[-1].get("content", "") == question else history
                    for h in history_to_use[-6:]:
                        role = "assistant" if h["role"] == "bot" else h["role"]
                        payload["messages"].append({"role": role, "content": h["content"]})
                
                payload["messages"].append({"role": "user", "content": f"Data:\n{ctx}\n\nQuestion: {question}"})

            resp = requests.post(f"{self.llm_base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                choice = resp.json()["choices"][0]
                msg = choice["message"]
                
                # Check for tool calls
                if "tool_calls" in msg and msg["tool_calls"]:
                    tc = msg["tool_calls"][0]["function"]
                    args = json.loads(tc["arguments"])
                    
                    if tc["name"] == "update_asset":
                        return {
                            "answer": f"🤖 Update erkannt:\n- **Kunde:** `{args.get('customer_id')}`\n- **Feld:** `{args.get('field_name')}`\n- **Neuer Wert:** `{args.get('new_value')}`\n- **Sparte:** `{args.get('utility')}`",
                            "hits": hits,
                            "model_used": self.llm_model,
                            "pending_action": {"type": "update_asset", "args": args}
                        }
                    
                    if tc["name"] == "navigate_to_map":
                        # Try to find the customer in unified_df to get coordinates
                        sid = args.get("customer_id")
                        if not sid:
                            return {
                                "answer": "🗺️ **Ich öffne die Netz-Karte für Sie...**",
                                "hits": hits,
                                "model_used": self.llm_model,
                                "pending_action": {"type": "navigate_map_general", "args": {}}
                            }

                        if self.unified_df.empty: self.unified_df = get_unified_df()
                        # Find the ID (fuzzy)
                        matches = pd.DataFrame()
                        for col in ["Kundennummer", "Objekt-ID", "Objekt-ID_Global"]:
                            if col in self.unified_df.columns:
                                mask = self.unified_df[col].astype(str).str.contains(rf'\b{sid}\b', regex=True, na=False)
                                if mask.any():
                                    matches = self.unified_df[mask]
                                    break
                                    
                        if not matches.empty:
                            res = matches.iloc[0]
                            if pd.notna(res.get("lat")) and pd.notna(res.get("lon")):
                                return {
                                    "answer": f"📍 **Navigation zur Karte...**\nIch zeige Ihnen den Anschluss `{res.get('Kundennummer')}` on the map.",
                                    "hits": hits,
                                    "model_used": self.llm_model,
                                    "pending_action": {
                                        "type": "navigate_map", 
                                        "args": {
                                            "customer_id": str(res.get("Kundennummer")),
                                            "lat": float(res["lat"]),
                                            "lon": float(res["lon"])
                                        }
                                    }
                                }
                        
                        # General map navigation if no specific match or no coordinates
                        return {
                            "answer": "🗺️ **Ich öffne die Netz-Karte für Sie...**",
                            "hits": hits,
                            "model_used": self.llm_model,
                            "pending_action": {"type": "navigate_map_general", "args": {}}
                        }

                answer = msg.get("content", "")
                return {"answer": answer, "hits": hits, "model_used": self.llm_model, "switched": False}
        except: pass

        if hits:
            fallback = "⏱️ **Zeitüberschreitung**: Relevantes aus der Datenbank:\n\n" + "\n".join([f"- {h['doc']}" for h in hits[:2]])
            return {"answer": fallback, "hits": hits, "model_used": "Timeout-Fallback", "switched": False}
        
        return {"answer": "Keine Antwort gefunden.", "hits": [], "model_used": "Error", "switched": False}

    def chat_general(self, user_message: str, history: List[Dict]) -> Dict[str, Any]:
        return self.answer_question(user_message, history=history)