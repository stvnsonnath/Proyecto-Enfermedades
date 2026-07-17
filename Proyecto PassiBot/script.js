function initPassiBot() {
    const chatMessagesCheck = document.getElementById('chat-messages');
    if (!chatMessagesCheck) {
        setTimeout(initPassiBot, 100);
        return;
    }

    // === ELEMENTOS DEL DOM ===
    const chatForm = document.getElementById('chat-form');
    const questionInput = document.getElementById('question-input');
    const chatMessages = document.getElementById('chat-messages');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
    const sidebar = document.getElementById('sidebar');
    const onboardingOverlay = document.getElementById('onboarding-overlay');
    const onboardingButtons = document.querySelectorAll('.onboarding-btn');
    
    // Sliders de Configuración
    const sliderTopK = document.getElementById('slider-top-k');
    const valTopK = document.getElementById('val-top-k');
    const sliderMinScore = document.getElementById('slider-min-score');
    const valMinScore = document.getElementById('val-min-score');
    const knowledgeLevel = document.getElementById('knowledge-level');

    const weightSliders = {
        'poscosecha': document.getElementById('w-poscosecha'),
        'enfermedades': document.getElementById('w-enfermedades'),
        'ecofisiologa': document.getElementById('w-ecofisiologa'),
        'agrios': document.getElementById('w-agrios'),
        'frac': document.getElementById('w-frac'),
        'postharvest': document.getElementById('w-postharvest'),
        'confirmed-cases': document.getElementById('w-confirmed-cases'),
        'others': document.getElementById('w-others')
    };

    // === INICIALIZACIÓN Y EVENTOS DE INTERFAZ ===

    // Toggle del panel lateral de configuración
    if (toggleSidebarBtn && sidebar) {
        toggleSidebarBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }

    // Manejo de la selección inicial del nivel de conocimiento (Onboarding)
    if (onboardingOverlay && onboardingButtons) {
        onboardingButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const selectedLevel = btn.getAttribute('data-level');
                if (knowledgeLevel) {
                    knowledgeLevel.value = selectedLevel;
                }
                // Ocultar el overlay con una transición suave
                onboardingOverlay.classList.add('hidden');
            });
        });
    }

    // Sincronizar sliders generales con sus badges
    sliderTopK.addEventListener('input', (e) => {
        valTopK.textContent = e.target.value;
    });

    sliderMinScore.addEventListener('input', (e) => {
        valMinScore.textContent = parseFloat(e.target.value).toFixed(2);
    });

    // Sincronizar sliders de pesos con sus badges
    Object.entries(weightSliders).forEach(([key, slider]) => {
        const valBadge = document.getElementById(`val-w-${key}`);
        slider.addEventListener('input', (e) => {
            valBadge.textContent = parseFloat(e.target.value).toFixed(1);
        });
    });

    // Auto-ajustar altura del textarea de entrada
    questionInput.addEventListener('input', () => {
        questionInput.style.height = 'auto';
        questionInput.style.height = (questionInput.scrollHeight) + 'px';
    });

    // Enviar pregunta al presionar Enter (sin Shift)
    questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Asignar click a los botones de preguntas sugeridas
    document.querySelectorAll('.suggestion-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.textContent.trim();
            questionInput.value = question;
            // Remover la cuadrícula de sugerencias
            const grid = document.querySelector('.suggestions-grid');
            if (grid) grid.remove();
            
            chatForm.dispatchEvent(new Event('submit'));
        });
    });

    // === LÓGICA DE PROCESAMIENTO RAG ===

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const question = questionInput.value.trim();
        if (!question) return;

        // Limpiar entrada
        questionInput.value = '';
        questionInput.style.height = 'auto';

        // Remover sugerencias si aún existen en pantalla
        const grid = document.querySelector('.suggestions-grid');
        if (grid) grid.remove();

        // Agregar mensaje de usuario al chat
        appendMessage('user', question);
        scrollToBottom();

        // Agregar cargando
        const loadingElement = appendLoading();
        scrollToBottom();

        const weights = {
            'poscosecha': parseFloat(weightSliders.poscosecha.value),
            'enfermedades': parseFloat(weightSliders.enfermedades.value),
            'ecofisiologa': parseFloat(weightSliders.ecofisiologa.value),
            'agrios': parseFloat(weightSliders.agrios.value),
            'frac': parseFloat(weightSliders.frac.value),
            'postharvest': parseFloat(weightSliders.postharvest.value),
            'confirmed-cases': parseFloat(weightSliders['confirmed-cases'].value)
        };
        const w_others = parseFloat(weightSliders.others.value);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: question,
                    knowledge_level: knowledgeLevel.value,
                    top_k: parseInt(sliderTopK.value),
                    min_score: parseFloat(sliderMinScore.value),
                    weights: weights,
                    w_others: w_others
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Eliminar cargando
            loadingElement.remove();

            // Agregar respuesta del bot
            appendBotMessage(data.answer, data.hits);
            scrollToBottom();

        } catch (error) {
            console.error('Error al consultar RAG:', error);
            loadingElement.remove();
            appendMessage('bot', `Error: Ocurrió un error al conectarse con el servidor: ${error.message}`);
            scrollToBottom();
        }
    });

    // === FUNCIONES AUXILIARES DE RENDERIZADO ===

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendMessage(sender, text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const p = document.createElement('p');
        p.textContent = text;
        contentDiv.appendChild(p);
        
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        return messageDiv;
    }

    function appendLoading() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message loading-msg';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const loadingContainer = document.createElement('div');
        loadingContainer.className = 'loading-container';
        
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        
        const span = document.createElement('span');
        span.textContent = 'Buscando en documentos e infiriendo respuesta...';
        
        loadingContainer.appendChild(spinner);
        loadingContainer.appendChild(span);
        contentDiv.appendChild(loadingContainer);
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        return messageDiv;
    }

    function appendBotMessage(answer, hits) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Renderizar respuesta con formato markdown básico
        const textDiv = document.createElement('div');
        textDiv.innerHTML = parseMarkdown(answer);
        contentDiv.appendChild(textDiv);
        
        // Si hay documentos recuperados, renderizar el acordeón de fuentes
        if (hits && hits.length > 0) {
            const accordion = document.createElement('div');
            accordion.className = 'sources-accordion';
            
            const header = document.createElement('div');
            header.className = 'sources-header';
            header.innerHTML = `<span><i class="fa-solid fa-book-open"></i> Profundizar en las fuentes (${hits.length})</span> <i class="fa-solid fa-chevron-down"></i>`;
            
            const content = document.createElement('div');
            content.className = 'sources-content';
            
            const list = document.createElement('ul');
            list.className = 'sources-list';
            
            hits.forEach(hit => {
                const li = document.createElement('li');
                li.className = 'source-item';
                
                const title = document.createElement('div');
                title.className = 'source-title';
                title.textContent = hit.citation;
                
                const meta = document.createElement('div');
                meta.className = 'source-meta';
                
                const scoreSpan = document.createElement('span');
                scoreSpan.innerHTML = `Similitud: <strong>${hit.score.toFixed(3)}</strong>`;
                
                const originalScoreSpan = document.createElement('span');
                originalScoreSpan.textContent = `(Original: ${hit.original_score.toFixed(3)})`;
                
                meta.appendChild(scoreSpan);
                meta.appendChild(originalScoreSpan);
                li.appendChild(title);
                li.appendChild(meta);
                list.appendChild(li);
            });
            
            content.appendChild(list);
            accordion.appendChild(header);
            accordion.appendChild(content);
            contentDiv.appendChild(accordion);
            
            // Evento para abrir/cerrar el acordeón
            header.addEventListener('click', () => {
                accordion.classList.toggle('open');
            });
        }
        
        // Agregar controles de calificación/feedback
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'message-feedback';
        
        const upBtn = document.createElement('button');
        upBtn.className = 'feedback-btn liked';
        upBtn.innerHTML = '<i class="fa-regular fa-thumbs-up"></i>';
        upBtn.title = 'Me gusta la respuesta';
        
        const downBtn = document.createElement('button');
        downBtn.className = 'feedback-btn disliked';
        downBtn.innerHTML = '<i class="fa-regular fa-thumbs-down"></i>';
        downBtn.title = 'No me gusta / Error en la respuesta';
        
        feedbackDiv.appendChild(upBtn);
        feedbackDiv.appendChild(downBtn);
        contentDiv.appendChild(feedbackDiv);
        
        // Registrar eventos de feedback
        upBtn.addEventListener('click', () => sendFeedback(upBtn, downBtn, answer, true));
        downBtn.addEventListener('click', () => sendFeedback(upBtn, downBtn, answer, false));
        
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        return messageDiv;
    }

    async function sendFeedback(btnUp, btnDown, text, liked) {
        // Deshabilitar botones para evitar multi-clicks
        btnUp.disabled = true;
        btnDown.disabled = true;
        
        if (liked) {
            btnUp.classList.add('active');
            btnUp.innerHTML = '<i class="fa-solid fa-thumbs-up"></i>';
        } else {
            btnDown.classList.add('active');
            btnDown.innerHTML = '<i class="fa-solid fa-thumbs-down"></i>';
        }

        try {
            const response = await fetch('/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message_text: text,
                    liked: liked
                })
            });
            if (response.ok) {
                console.log('Feedback guardado con éxito.');
            }
        } catch (error) {
            console.error('Error al registrar feedback:', error);
        }
    }

    // === PARSER DE MARKDOWN BÁSICO ===
    function parseMarkdown(text) {
        if (!text) return '';
        
        let html = text;
        
        // Escapar caracteres HTML básicos
        html = html
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
            
        // Restaurar etiquetas HTML específicas que queremos renderizar (como detalles y listas que use el backend)
        html = html
            .replace(/&lt;details&gt;/g, "<details>")
            .replace(/&lt;\/details&gt;/g, "</details>")
            .replace(/&lt;summary&gt;/g, "<summary>")
            .replace(/&lt;\/summary&gt;/g, "</summary>")
            .replace(/&lt;ul&gt;/g, "<ul>")
            .replace(/&lt;\/ul&gt;/g, "</ul>")
            .replace(/&lt;li&gt;/g, "<li>")
            .replace(/&lt;\/li&gt;/g, "</li>")
            .replace(/&lt;b&gt;/g, "<b>")
            .replace(/&lt;\/b&gt;/g, "</b>");

        // Negrita (**texto**)
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Cursiva (*texto*)
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Elementos de lista (- item o * item) al inicio de línea
        html = html.replace(/^(?:-|\*)\s+(.*?)$/gm, '<li>$1</li>');
        // Envolver grupos de <li> continuos en <ul>
        // (Nota: esta es una aproximación simple, pero funciona muy bien para respuestas de LLM)
        html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
        
        // Salto de línea
        html = html.replace(/\n/g, '<br>');
        
        // Citas resaltadas [archivo.pdf, p. N]
        html = html.replace(/\[([a-zA-Z0-9_\-\s\.]+\.pdf,\s*pp?\.\s*\d+(?:\-\d+)?)\]/g, '<span class="citation-tag">[$1]</span>');
        
        return html;
    }
}
initPassiBot();
