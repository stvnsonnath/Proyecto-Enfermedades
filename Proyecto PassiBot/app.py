from __future__ import annotations

import os
import socket
import sys

# Cache and original function for custom DNS resolution (Bypasses local DNS blocks for LLM API calls)
original_getaddrinfo = socket.getaddrinfo
dns_cache = {}

def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in dns_cache:
        return original_getaddrinfo(dns_cache[host], port, family, type, proto, flags)
    try:
        return original_getaddrinfo(host, port, family, type, proto, flags)
    except Exception:
        if host == "api-inference.huggingface.co":
            try:
                import urllib.request
                import json
                import ssl
                
                url = f"https://8.8.8.8/resolve?name={host}&type=A"
                req = urllib.request.Request(url, headers={"Host": "dns.google"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(req, context=ctx, timeout=3) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode())
                        if "Answer" in data:
                            for ans in data["Answer"]:
                                if ans["type"] == 1: # IPv4
                                    ip = ans["data"]
                                    dns_cache[host] = ip
                                    print(f"DNS resolved {host} -> {ip} via Google DoH", file=sys.stderr)
                                    return original_getaddrinfo(ip, port, family, type, proto, flags)
            except Exception as doh_err:
                print(f"Failed Google DoH: {doh_err}", file=sys.stderr)
        raise

# Configuración de DNS según el entorno
if os.environ.get("RENDER") == "true":
    # En Render, forzar resolución IPv4 para evitar fallos de DNS con IPv6
    def force_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:
            family = socket.AF_INET
        return original_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = force_ipv4_getaddrinfo
elif os.environ.get("USE_CUSTOM_DNS") == "true":
    socket.getaddrinfo = custom_getaddrinfo

import json
import re
import datetime
import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import faiss
import requests
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

# Bypass para Hugging Face ZeroGPU (requiere al menos una función decorada con @spaces.GPU)
try:
    import spaces
    HAS_SPACES = True
except ImportError:
    HAS_SPACES = False
    class spaces:
        @staticmethod
        def GPU(func):
            return func

@spaces.GPU
def dummy_gpu_function():
    return "ok"

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = BASE_DIR / "rag_artifacts"

load_dotenv(dotenv_path=BASE_DIR / ".env")
HF_TOKEN = os.getenv("HF_TOKEN")

@dataclass
class ChunkRecord:
    chunk_id: int
    source: str
    page_start: int
    page_end: int
    text: str

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"
GENERATION_MODEL = "Qwen/Qwen2.5-7B-Instruct"

faiss_path = ARTIFACT_DIR / "sources.faiss"
chunks_path = ARTIFACT_DIR / "chunks.json"

if not faiss_path.exists() or not chunks_path.exists():
    print("Error: No se encontraron los archivos del indice vectorial.")
    sys.exit(1)

# Cargar el modelo de embeddings local si está disponible y se solicita (pero NUNCA en Render)
embedding_model = None
if HAS_SENTENCE_TRANSFORMERS and os.environ.get("USE_LOCAL_EMBEDDINGS") == "true" and not os.environ.get("RENDER"):
    print("Cargando modelo de embeddings local (intfloat/multilingual-e5-base)...")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print("Modelo de embeddings cargado con éxito.")
else:
    print("Se utilizará la API de Hugging Face para generar embeddings de consulta (ahorro de RAM).")

index = faiss.read_index(str(faiss_path))
with chunks_path.open("r", encoding="utf-8") as f:
    chunks_raw = json.load(f)
chunks = [ChunkRecord(**c) for c in chunks_raw]

client = InferenceClient(api_key=HF_TOKEN)

app = FastAPI(title="PassiBot API")

class ChatRequest(BaseModel):
    question: str
    knowledge_level: str = "Técnico / Profesional"
    top_k: int = 4
    min_score: float = 0.70
    weights: dict[str, float] = None
    w_others: float = 1.0

class FeedbackRequest(BaseModel):
    message_text: str
    liked: bool

def citation_for(chunk: ChunkRecord) -> str:
    if chunk.page_start == chunk.page_end:
        return f"{chunk.source}, p. {chunk.page_start}"
    return f"{chunk.source}, pp. {chunk.page_start}-{chunk.page_end}"

def retrieve(question: str, top_k: int, weights: dict[str, float] = None, w_others: float = 1.0) -> list[dict]:
    try:
        query_text = f"query: {question}"
        if embedding_model is not None:
            query_embedding = embedding_model.encode([query_text], convert_to_numpy=True).astype("float32")
        else:
            # Generación vía API remota para ahorrar RAM (Render/Koyeb free)
            api_url = f"https://api-inference.huggingface.co/models/{EMBEDDING_MODEL_NAME}"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            
            # Reintentar la conexión en caso de problemas DNS o de carga del modelo (error 503)
            import time
            response = None
            last_error = None
            
            for attempt in range(4):
                try:
                    response = requests.post(api_url, headers=headers, json={"inputs": query_text}, timeout=10)
                    if response.status_code == 200:
                        break
                    elif response.status_code == 503:
                        # El modelo se está cargando en Hugging Face, esperar y reintentar
                        err_msg = response.json().get("error", "Model loading")
                        print(f"Intento {attempt + 1}: Modelo cargándose ({err_msg}). Reintentando en 4s...")
                        time.sleep(4)
                    else:
                        raise ValueError(f"HTTP {response.status_code}: {response.text}")
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_err:
                    last_error = conn_err
                    print(f"Intento {attempt + 1}: Error de red/DNS ({conn_err}). Reintentando en 2s...")
                    time.sleep(2)
            
            if response is None or response.status_code != 200:
                if last_error:
                    raise last_error
                raise ValueError(f"No se pudo conectar a la API de Hugging Face. Status {response.status_code if response else 'Desconocido'}: {response.text if response else ''}")
                
            res_json = response.json()
            if isinstance(res_json, dict) and "error" in res_json:
                raise ValueError(f"API Error: {res_json['error']}")
            
            # La API devuelve una lista de floats (el embedding)
            query_embedding = np.array([res_json], dtype="float32")
            faiss.normalize_L2(query_embedding)
            
    except Exception as e:
        print(f"Error al generar embeddings de consulta: {e}")
        raise HTTPException(status_code=500, detail=f"Error al generar embeddings de consulta: {e}")

    scores, indices = index.search(query_embedding, top_k)

    hits = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        chunk = chunks[int(idx)]
        
        weight = w_others
        if weights:
            for key, val in weights.items():
                # 'frac' key maps to both FRAC files and the folleto PDF
                if key.lower() == 'frac' and ('frac' in chunk.source.lower() or 'folleto' in chunk.source.lower()):
                    weight = val
                    break
                elif key.lower() in chunk.source.lower():
                    weight = val
                    break
                    
        weighted_score = float(score) * weight
        hits.append(
            {
                "original_score": float(score),
                "score": weighted_score,
                "source": chunk.source,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "text": chunk.text,
                "citation": citation_for(chunk),
            }
        )
        
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits

def build_context(hits: list[dict]) -> str:
    blocks = []
    for item_number, hit in enumerate(hits, start=1):
        text = hit["text"][:2200]
        blocks.append(
            f"[Fuente {item_number}] {hit['citation']}\n"
            f"Similitud: {hit['score']:.3f}\n"
            f"{text}"
        )
    return "\n\n".join(blocks)

def generate_answer(question: str, context: str, knowledge_level: str) -> str:
    if not HF_TOKEN:
        return (
            "Error de Configuración:\n"
            "La variable de entorno HF_TOKEN no está configurada.\n\n"
            "Por favor, configure su token de acceso a Hugging Face."
        )
        
    system_prompt = (
        "Eres PassiBot, un asistente agricola y fitopatologico basado en recuperacion documental.\n\n"
        f"Nivel de conocimiento del usuario: {knowledge_level}\n"
    )
    if "Básico" in knowledge_level:
        system_prompt += (
            "- Responde con lenguaje sencillo y de divulgacion popular. Evita terminos cientificos excesivos o jerga compleja.\n"
            "- Usa analogias cotidianas para explicar conceptos tecnicos cuando sea posible.\n"
            "- Explica brevemente cualquier termino tecnico que sea indispensable mencionar.\n"
        )
    elif "Técnico" in knowledge_level:
        system_prompt += (
            "- Responde con enfoque profesional y practico. Usa terminos tecnicos estandar de la agronomia.\n"
            "- Concentrate en el manejo agronomico practico en campo, manejo integrado de plagas/enfermedades y prevencion.\n"
        )
    elif "Científico" in knowledge_level:
        system_prompt += (
            "- Responde con maximo rigor academico, cientifico y formal.\n"
            "- Utiliza nomenclatura cientifica completa (ej. nombres de patogenos en latin en cursiva).\n"
            "- Detalla a nivel molecular, genetico o bioquimico cuando se hable de mecanismos de accion de fungicidas o procesos de infeccion.\n"
        )

    system_prompt += """
Reglas obligatorias:
- Usa exclusivamente el CONTEXTO proporcionado.
- No uses conocimiento externo, memoria del modelo ni suposiciones no respaldadas.
- Si el CONTEXTO no contiene evidencia suficiente, responde exactamente: "No encontre informacion suficiente en las fuentes proporcionadas."
- Responde en espanol, salvo que el usuario pida otro idioma.
- Cita las afirmaciones tecnicas con el formato [documento.pdf, p. N].
- Si las fuentes tienen matices o contradicciones, explicalo y cita cada fuente relevante.
- No recomiendes aplicaciones de productos quimicos sin mencionar que deben verificarse registro, etiqueta y asesoria local cuando aplique.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "CONTEXTO:\n"
                f"{context}\n\n"
                "PREGUNTA:\n"
                f"{question}\n\n"
                "RESPUESTA:"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=messages,
            max_tokens=700,
            temperature=0.1,
        )
        ans = response.choices[0].message.content
        ans = re.sub(r"<think>.*?</think>", "", ans, flags=re.DOTALL | re.IGNORECASE).strip()
        return ans
    except Exception as e:
        return f"Error al consultar el modelo en Hugging Face:\n{str(e)}"

@app.post("/chat")
def api_chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    hits = retrieve(question, top_k=req.top_k, weights=req.weights, w_others=req.w_others)
    if not hits or hits[0]["score"] < req.min_score:
        return {
            "answer": "No encontré información suficiente en las fuentes proporcionadas.",
            "hits": []
        }

    context = build_context(hits)
    answer = generate_answer(question, context, req.knowledge_level)

    if "No encontre informacion suficiente" in answer or "No encontré información suficiente" in answer:
        return {
            "answer": "No encontré información suficiente en las fuentes proporcionadas.",
            "hits": []
        }

    return {
        "answer": answer,
        "hits": hits
    }

@app.post("/feedback")
def api_feedback(req: FeedbackRequest):
    feedback_file = BASE_DIR / "feedback_log.csv"
    file_exists = feedback_file.exists()
    try:
        with open(feedback_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "liked", "message_text"])
            writer.writerow([
                datetime.datetime.now().isoformat(),
                req.liked,
                req.message_text
            ])
        return {"status": "success", "message": "Feedback registrado con éxito."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar feedback: {e}")

@app.get("/")
def get_index():
    return FileResponse(str(BASE_DIR / "index.html"))

@app.get("/style.css")
def get_style():
    return FileResponse(str(BASE_DIR / "style.css"))

@app.get("/script.js")
def get_script():
    return FileResponse(str(BASE_DIR / "script.js"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
