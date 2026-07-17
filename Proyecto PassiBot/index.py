# /// script
# dependencies = [
#   "sentence-transformers",
#   "faiss-cpu",
#   "pymupdf",
#   "numpy",
#   "torch",
#   "python-dotenv",
#   "requests",
# ]
# ///

from __future__ import annotations

import os
import gc
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
import faiss
try: import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Directorios y rutas de archivos
BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = BASE_DIR / "rag_artifacts"
SOURCE_DIR = BASE_DIR / "sources"
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"

# Cargar variables de entorno (para obtener el HF_TOKEN)
load_dotenv(dotenv_path=BASE_DIR / ".env")
HF_TOKEN = os.getenv("HF_TOKEN")

# Dataclasses
@dataclass
class PageRecord:
    source: str
    page: int
    text: str

@dataclass
class ChunkRecord:
    chunk_id: int
    source: str
    page_start: int
    page_end: int
    text: str

def clean_pdf_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf_pages(pdf_path: Path) -> list[PageRecord]:
    import fitz  # PyMuPDF
    records = []
    try:
        with fitz.open(pdf_path) as doc:
            for page_index, page in enumerate(doc, start=1):
                raw_text = page.get_text("text", sort=True)
                text = clean_pdf_text(raw_text)
                if len(text) >= 80:
                    records.append(PageRecord(source=pdf_path.name, page=page_index, text=text))
    except Exception as e:
        print(f"Error procesando {pdf_path.name}: {e}")
    return records

def make_page_chunks(page: PageRecord, next_chunk_id: int) -> tuple[list[ChunkRecord], int]:
    MAX_CHUNK_WORDS = 700
    OVERLAP_WORDS = 120
    MIN_CHUNK_WORDS = 40
    
    words = page.text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return [], next_chunk_id

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + MAX_CHUNK_WORDS, len(words))
        window = words[start:end]
        if len(window) >= MIN_CHUNK_WORDS:
            chunks.append(
                ChunkRecord(
                    chunk_id=next_chunk_id,
                    source=page.source,
                    page_start=page.page,
                    page_end=page.page,
                    text=" ".join(window),
                )
            )
            next_chunk_id += 1
        if end == len(words):
            break
        start = max(end - OVERLAP_WORDS, start + 1)
    return chunks, next_chunk_id

def rebuild_index():
    print("=== INICIANDO PROCESAMIENTO DE PDFs E INDEXACIÓN ===")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    
    pdf_files = sorted(SOURCE_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No se encontraron archivos PDF en la carpeta: {SOURCE_DIR}")
        return False
        
    print(f"Encontrados {len(pdf_files)} archivos PDF para indexar:")
    for i, pdf in enumerate(pdf_files, 1):
        size_mb = pdf.stat().st_size / 1024 / 1024
        print(f"  {i}. {pdf.name} ({size_mb:.2f} MB)")
        
    pages = []
    for pdf_path in pdf_files:
        print(f"  -> Extrayendo páginas de {pdf_path.name}...")
        pages.extend(extract_pdf_pages(pdf_path))
        
    if not pages:
        print("ERROR: No se pudo extraer texto de ningún archivo PDF.")
        return False
        
    chunks = []
    next_chunk_id = 0
    for page in pages:
        page_chunks, next_chunk_id = make_page_chunks(page, next_chunk_id)
        chunks.extend(page_chunks)
        
    print(f"\nProcesamiento de texto finalizado:")
    print(f"  - Total páginas con texto extraído: {len(pages)}")
    print(f"  - Total fragmentos (chunks) creados: {len(chunks)}")
    
    # Generar embeddings
    print(f"\nCalculando embeddings para los fragmentos...")
    passage_inputs = [f"passage: {chunk.text}" for chunk in chunks]
    
    loaded_via_api = False
    if HF_TOKEN and not HF_TOKEN.startswith("PON_TU_TOKEN"):
        try:
            print("Intentando generar embeddings a través de la API remota de Hugging Face (rápido)...")
            if requests is None:
                raise ImportError("requests library is not installed")

            api_url = f"https://api-inference.huggingface.co/models/{EMBEDDING_MODEL}"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            
            embeddings_list = []
            # Procesar en lotes de 32 para evitar límites de tamaño de request
            batch_size = 32
            for i in range(0, len(passage_inputs), batch_size):
                sys.stdout.write(f"\r  Procesando lote {i//batch_size + 1} de {len(passage_inputs)//batch_size + 1}...")
                sys.stdout.flush()
                batch = passage_inputs[i:i+batch_size]
                
                # Realizar llamada HTTP POST directa al modelo
                response = requests.post(api_url, headers=headers, json={"inputs": batch})
                if response.status_code == 200:
                    batch_emb = response.json()
                else:
                    raise ValueError(f"HTTP {response.status_code}: {response.text}")
                
                if isinstance(batch_emb, dict) and "error" in batch_emb:
                    raise ValueError(f"API Error: {batch_emb['error']}")
                
                embeddings_list.extend(batch_emb)
            print("\n  Lotes procesados exitosamente.")
            
            chunk_embeddings = np.array(embeddings_list, dtype="float32")
            # Normalizar L2 para producto punto (IndexFlatIP)
            faiss.normalize_L2(chunk_embeddings)
            loaded_via_api = True
            print("Embeddings generados exitosamente mediante la API de Hugging Face.")
        except Exception as e:
            print(f"\nAdvertencia: Falló la generación por API ({e}). Usando procesamiento local en CPU...")
            
    if not loaded_via_api:
        print(f"Cargando modelo de embeddings local: {EMBEDDING_MODEL} (esto puede ser lento en CPU)...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Usando dispositivo: {device.upper()}")
        encoder = SentenceTransformer(EMBEDDING_MODEL, device=device)
        
        print("Generando embeddings locales...")
        chunk_embeddings = encoder.encode(
            passage_inputs,
            batch_size=16,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        ).astype("float32")
    
    print(f"Embeddings listos: {chunk_embeddings.shape}")
    
    print("\nCreando índice vectorial FAISS...")
    index = faiss.IndexFlatIP(chunk_embeddings.shape[1])
    index.add(chunk_embeddings)
    
    # Guardar
    faiss_path = ARTIFACT_DIR / "sources.faiss"
    chunks_path = ARTIFACT_DIR / "chunks.json"
    
    print(f"Guardando índice vectorial en: {faiss_path}")
    faiss.write_index(index, str(faiss_path))
    
    print(f"Guardando fragmentos en: {chunks_path}")
    with chunks_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(chunk) for chunk in chunks], f, ensure_ascii=False, indent=2)
        
    print("\n=== INDEXACIÓN COMPLETADA CON ÉXITO ===")
    print("Tu base de datos vectorial local está actualizada y lista para usarse.")
    return True

if __name__ == "__main__":
    success = rebuild_index()
    if not success:
        sys.exit(1)
