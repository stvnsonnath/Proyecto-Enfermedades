---
title: PassiBot
emoji: 🌱
colorFrom: green
colorTo: green
sdk: gradio
sdk_version: 4.19.2
app_file: RAG/app.py
pinned: false
---

# PassiBot - Asistente Fitopatológico (RAG)

PassiBot es un chatbot inteligente basado en **Recuperación Documental Aumentada (RAG)**. Su objetivo es responder consultas técnicas sobre cultivos de pasifloras (granadilla, curuba, gulupa), enfermedades, control biológico y fitopatología en general, utilizando exclusivamente un conjunto de documentos científicos e institucionales indexados.

---

## 🛠️ Cómo Funciona el Bot (Arquitectura RAG)

El funcionamiento del bot sigue un flujo de tres etapas ante cada pregunta del usuario:

1. **Generación de Embeddings (Local)**:
   La pregunta del usuario es convertida en un vector numérico de 768 dimensiones. Para esto, utiliza el modelo multilingüe de alta calidad **`intfloat/multilingual-e5-base`** de forma local (procesado en la CPU/RAM mediante la librería `sentence-transformers`), garantizando inmunidad ante problemas de conexión o caídas de DNS.

2. **Búsqueda Vectorial y Ponderación Dinámica (Retrieval)**:
   El vector de la pregunta se contrasta contra la base de datos indexada con **FAISS**. El sistema busca los fragmentos (chunks) de texto más similares. 
   * **Sliders de Relevancia**: Si el usuario ajusta la importancia de ciertas fuentes en la barra lateral (ej. dar más peso al libro de Agrios o bajar la relevancia de FRAC), el backend multiplica los puntajes de similitud por los pesos indicados por el usuario para reordenar la relevancia en tiempo real.

3. **Generación de la Respuesta (LLM Remoto)**:
   El sistema recopila los fragmentos de texto más relevantes (el contexto) y construye un prompt personalizado según el nivel de conocimiento seleccionado:
   * **Básico / Divulgativo**: Explicaciones directas, analogías y eliminación de tecnicismos complejos.
   * **Técnico / Profesional**: Foco en manejo agronómico práctico en campo y control de plagas.
   * **Científico / Investigador**: Foco en rigor bioquímico, molecular y nomenclatura científica en latín.
   
   Este prompt se envía mediante una conexión segura a la API serverless de Hugging Face para ejecutar el modelo de lenguaje **`Qwen/Qwen2.5-7B-Instruct`**, el cual redacta la respuesta final citando los PDFs consultados.

---

## 📂 Descripción de Archivos del Proyecto

A continuación se detalla la estructura y el propósito de cada archivo del repositorio:

* **`sources/` (Carpeta)**: Contiene los archivos PDF originales que componen la base de conocimientos del bot (guías de pasifloras, manuales de fitopatología de Agrios, clasificaciones de la OMS, listas de códigos FRAC, etc.).
* **`index.py`**: Script de indexación. Lee todos los PDFs en `sources/`, limpia el texto, lo divide en fragmentos con solapamiento, calcula los vectores tridimensionales con el modelo de embeddings y genera los archivos en la carpeta de artefactos. Solo debe ejecutarse cuando se agreguen o modifiquen PDFs en `sources/`.
* **`app.py`**: El backend principal construido sobre **FastAPI**. 
  * Carga la base de datos vectorial de FAISS.
  * Carga el modelo de embeddings localmente en memoria.
  * Define los endpoints `/chat` (para procesar preguntas) y `/feedback` (para guardar likes/dislikes).
  * Sirve los archivos del frontend de forma nativa.
* **`index.html`**: Interfaz de usuario (frontend). Contiene la pantalla de inicio para la elección de perfil (onboarding), la barra lateral colapsable con los sliders de ponderación y el área del chat.
* **`style.css`**: Hoja de estilos con diseño moderno oscuro y verde (premium), transiciones fluidas para el panel de configuración, animaciones de carga y adaptabilidad para dispositivos móviles.
* **`script.js`**: Control de la interfaz e interacciones. Envía las preguntas y los valores de los sliders al backend mediante llamadas asíncronas (`fetch`) y gestiona las animaciones del chat.
* **`rag_artifacts/` (Carpeta)**: Carpeta generada automáticamente que contiene la base de datos del bot:
  * `sources.faiss`: El índice de vectores para búsquedas rápidas.
  * `chunks.json`: Contiene el texto original y la metadata (nombre de archivo, páginas) de cada fragmento indexado.
* **`requirements.txt`**: Archivo de dependencias del proyecto de Python.
* **`Dockerfile`**: Archivo de configuración para empaquetar el bot en un contenedor y facilitar su despliegue en la nube (especialmente en Hugging Face Spaces con Docker SDK).
* **`feedback_log.csv`**: Archivo generado automáticamente en el servidor para almacenar la retroalimentación de los usuarios (likes/dislikes y comentarios de ayuda).

---
