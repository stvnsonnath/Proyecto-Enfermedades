# Asistente Conversacional para Soporte Fitopatológico en Pasifloras

Este repositorio contiene dos desarrollos independientes que abordan el soporte fitopatológico para cultivos de pasifloras en Colombia bajo dos enfoques técnicos completamente distintos:

---

## 🤖 1. Proyecto FitoBot (Enfoque: Fine-Tuning / Ajuste Fino)
*Ubicación: `Proyecto FitoBot/`*

Este proyecto representa la **primera versión del asistente**. Su enfoque se basa en la **modificación de los pesos internos de un modelo de lenguaje** para adaptar su estilo de respuesta y comportamiento.

*   **Método**: Ajuste Fino Supervisado (SFT) utilizando **QLoRA** (Quantized Low-Rank Adaptation) con la librería **Unsloth**.
*   **Modelo Base**: `Llama-3.2-3B-Instruct` (cuantizado a 4 bits).
*   **Datos**: Entrenado con un dataset estructurado de **412 preguntas y respuestas** sobre agronomía y fitopatología local.
*   **Características**:
    *   Destaca en la adaptación de roles (conversación coloquial para agricultores o técnica para profesionales).
    *   No tiene acceso a documentos externos en tiempo de ejecución.
    *   Es propenso a alucinaciones factuales en dosificaciones o datos numéricos específicos fuera de su dataset de entrenamiento.

---

## 🔍 2. Proyecto PassiBot (Enfoque: RAG / Generación Aumentada por Recuperación)
*Ubicación: `Proyecto PassiBot/`*

Este proyecto constituye la **segunda versión (avanzada y recomendada)**. Su enfoque se basa en la **recuperación de información externa en tiempo real** para alimentar al modelo, eliminando la necesidad de reentrenarlo.

*   **Método**: Generación Aumentada por Recuperación (RAG) utilizando una base de datos vectorial local.
*   **Buscador Semántico**: Índice vectorial flat en **FAISS** con embeddings generados por el modelo multilingüe **E5-Base** (`intfloat/multilingual-e5-base`).
*   **Base de Conocimiento**: Indexa **14 manuales y documentos científicos** (más de 2,200 páginas de manuales de AgroSavia, clasificaciones del FRAC y normativas del ICA).
*   **Generador**: Inferencia serverless remota usando el modelo de escala superior **`Qwen2.5-7B-Instruct`**.
*   **Características**:
    *   Garantiza veracidad factual al limitar las respuestas estrictamente a la literatura provista (0% alucinaciones de dosis).
    *   Cita la fuente bibliográfica exacta (nombre de archivo PDF y número de página).
    *   Requiere un consumo mínimo de hardware local (<150 MB de RAM).

---

