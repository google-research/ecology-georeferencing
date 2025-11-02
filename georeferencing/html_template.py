"""
HTML template for georeferencing visualization.

This template uses .format() placeholders:
- {figures_json}: JSON data for successfully georeferenced figures
- {failed_json}: JSON data for failed georeferencing attempts
"""

VISUALIZATION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Georeferencing Results</title>

    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossorigin=""/>

    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""></script>

    <!-- Marked.js for markdown rendering -->
    <script src="https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js"></script>

    <!-- Google Generative AI SDK -->
    <script type="importmap">
    {{
        "imports": {{
            "@google/generative-ai": "https://esm.run/@google/generative-ai"
        }}
    }}
    </script>

    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            height: 100vh;
            display: flex;
            overflow: hidden;
        }}

        #left-sidebar {{
            width: 300px;
            background-color: #f8f9fa;
            border-right: 1px solid #dee2e6;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }}

        #map-container {{
            flex: 1;
            position: relative;
        }}

        #map {{
            width: 100%;
            height: 100%;
        }}

        #right-sidebar {{
            width: 450px;
            background-color: #f8f9fa;
            border-left: 1px solid #dee2e6;
            overflow-y: auto;
            display: none;
            flex-direction: column;
        }}

        #right-sidebar.visible {{
            display: flex;
        }}

        #sidebar-content {{
            padding: 20px;
            overflow-y: auto;
            flex-shrink: 0;
        }}

        #resize-handle {{
            height: 8px;
            background-color: #dee2e6;
            cursor: ns-resize;
            position: relative;
            flex-shrink: 0;
        }}

        #resize-handle:hover {{
            background-color: #007bff;
        }}

        #resize-handle::before {{
            content: '';
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 40px;
            height: 4px;
            background-color: #6c757d;
            border-radius: 2px;
        }}

        #chat-container {{
            background-color: #ffffff;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
            min-height: 200px;
            overflow: hidden;
        }}

        .sidebar-header {{
            padding: 20px;
            background-color: #343a40;
            color: white;
            border-bottom: 1px solid #dee2e6;
        }}

        .sidebar-header h2 {{
            font-size: 18px;
            margin-bottom: 5px;
        }}

        .sidebar-header p {{
            font-size: 12px;
            color: #adb5bd;
            margin: 0;
        }}

        .figure-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}

        .figure-item {{
            padding: 12px 20px;
            border-bottom: 1px solid #dee2e6;
            cursor: pointer;
            transition: background-color 0.2s;
        }}

        .figure-item:hover {{
            background-color: #e9ecef;
        }}

        .figure-item.active {{
            background-color: #007bff;
            color: white;
        }}

        .figure-item.failed {{
            opacity: 0.6;
            cursor: default;
            background-color: #fff3cd;
        }}

        .figure-item.failed:hover {{
            background-color: #fff3cd;
        }}

        .figure-title {{
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 4px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .figure-item.active .figure-title {{
            white-space: normal;
            word-wrap: break-word;
            overflow: visible;
        }}

        .figure-subtitle {{
            font-size: 12px;
            color: #6c757d;
        }}

        .figure-item.active .figure-subtitle {{
            color: #e9ecef;
        }}

        .section-header {{
            padding: 12px 20px;
            background-color: #e9ecef;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            color: #495057;
            border-bottom: 1px solid #dee2e6;
        }}

        .detail-section {{
            margin-bottom: 20px;
        }}

        .detail-section h3 {{
            font-size: 14px;
            margin-bottom: 8px;
            color: #343a40;
            text-transform: uppercase;
            font-weight: 600;
        }}

        .detail-section p, .detail-section a {{
            font-size: 13px;
            line-height: 1.6;
            color: #495057;
        }}

        .detail-section a {{
            color: #007bff;
            text-decoration: none;
            word-wrap: break-word;
        }}

        .detail-section a:hover {{
            text-decoration: underline;
        }}

        .detail-image {{
            width: 100%;
            height: auto;
            border-radius: 4px;
            border: 1px solid #dee2e6;
            margin-top: 8px;
        }}

        .confidence-badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            background-color: #28a745;
            color: white;
        }}

        .nav-buttons {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            display: none;
            gap: 10px;
        }}

        .nav-buttons.visible {{
            display: flex;
        }}

        .nav-button {{
            padding: 10px 20px;
            background-color: white;
            border: 2px solid #343a40;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .nav-button:hover {{
            background-color: #343a40;
            color: white;
        }}

        .nav-button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .nav-button:disabled:hover {{
            background-color: white;
            color: #343a40;
        }}

        /* Chat interface styles */
        .api-key-section {{
            padding: 12px;
            background-color: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .api-key-section label {{
            display: block;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
            color: #495057;
        }}

        .api-key-section input {{
            width: 100%;
            padding: 6px 8px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
        }}

        .api-key-section small {{
            display: block;
            margin-top: 4px;
            font-size: 11px;
            color: #6c757d;
        }}

        #chat-messages {{
            flex-grow: 1;
            overflow-y: auto;
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .chat-message {{
            padding: 10px 12px;
            border-radius: 8px;
            max-width: 100%;
            word-wrap: break-word;
        }}

        .chat-message.user {{
            background-color: #007bff;
            color: white;
            align-self: flex-end;
            margin-left: 20%;
        }}

        .chat-message.assistant {{
            background-color: #e9ecef;
            color: #212529;
            align-self: flex-start;
            margin-right: 20%;
        }}

        .chat-message.error {{
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}

        .chat-message.loading {{
            background-color: #e9ecef;
            color: #6c757d;
            font-style: italic;
        }}

        .chat-message p {{
            margin: 0 0 8px 0;
        }}

        .chat-message p:last-child {{
            margin-bottom: 0;
        }}

        .chat-message ul {{
            margin: 8px 0;
            padding-left: 20px;
        }}

        .chat-message li {{
            margin: 4px 0;
        }}

        .chat-message strong {{
            font-weight: 600;
        }}

        .chat-message em {{
            font-style: italic;
        }}

        #chat-input-container {{
            padding: 12px;
            border-top: 1px solid #dee2e6;
            background-color: #f8f9fa;
        }}

        #chat-input {{
            width: 100%;
            padding: 8px 10px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            font-size: 14px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            resize: vertical;
            min-height: 90px;
        }}

        #chat-input:focus {{
            outline: none;
            border-color: #007bff;
        }}

        .chat-buttons {{
            display: flex;
            gap: 8px;
            margin-top: 8px;
        }}

        .chat-button {{
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .chat-button.primary {{
            background-color: #007bff;
            color: white;
        }}

        .chat-button.primary:hover:not(:disabled) {{
            background-color: #0056b3;
        }}

        .chat-button.secondary {{
            background-color: #6c757d;
            color: white;
        }}

        .chat-button.secondary:hover:not(:disabled) {{
            background-color: #545b62;
        }}

        .chat-button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .chat-header {{
            padding: 12px 15px;
            background-color: #343a40;
            color: white;
            font-size: 14px;
            font-weight: 600;
            border-bottom: 1px solid #dee2e6;
        }}
    </style>
</head>
<body>
    <div id="left-sidebar">
        <div class="sidebar-header">
            <h2>Georeferencing Results</h2>
            <p id="summary-text">Loading...</p>
        </div>
        <div class="section-header">Georeferenced Figures</div>
        <ul id="figure-list" class="figure-list">
        </ul>
        <div id="failed-section" style="display: none;">
            <div class="section-header">Failed Georeferencing</div>
            <ul id="failed-list" class="figure-list">
            </ul>
        </div>
    </div>

    <div id="map-container">
        <div id="map"></div>
        <div id="nav-buttons" class="nav-buttons">
            <button id="prev-button" class="nav-button">← Previous</button>
            <button id="next-button" class="nav-button">Next →</button>
        </div>
    </div>

    <div id="right-sidebar">
        <div id="sidebar-content">
            <div class="detail-section">
                <h3>Paper</h3>
                <p id="detail-paper-title"></p>
                <p><a id="detail-pdf-link" href="#" target="_blank">Open PDF</a></p>
            </div>

            <div class="detail-section">
                <h3>Figure</h3>
                <img id="detail-image" class="detail-image" src="" alt="Map figure">
            </div>

            <div class="detail-section">
                <h3>Georeferencing</h3>
                <p><strong>Confidence:</strong> <span id="detail-confidence" class="confidence-badge"></span></p>
                <p style="margin-top: 8px;"><strong>Explanation:</strong></p>
                <p id="detail-explanation"></p>
            </div>
        </div>

        <div id="resize-handle"></div>

        <div id="chat-container">
            <div class="chat-header">Ask Questions About This Paper</div>
            <div class="api-key-section">
                <label for="api-key-input">Gemini API Key:</label>
                <input type="password" id="api-key-input" placeholder="Enter your Gemini API key">
                <small>Your key is stored locally in your browser.</small>
            </div>
            <div id="chat-messages"></div>
            <div id="chat-input-container">
                <textarea id="chat-input" placeholder="Ask a question about this map or paper..."></textarea>
                <div class="chat-buttons">
                    <button id="suggest-question-btn" class="chat-button secondary">Suggest a Question</button>
                    <button id="send-question-btn" class="chat-button primary">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script type="module">
        import {{ GoogleGenerativeAI }} from "@google/generative-ai";

        // Data from Python
        const figuresData = {figures_json};
        const failedData = {failed_json};
        const prompts = {prompts_json};

        // State
        let currentIndex = -1;
        let map = null;
        let polygons = {{}};

        // Initialize map
        function initMap() {{
            map = L.map('map').setView([20, 0], 2);

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 19
            }}).addTo(map);
        }}

        // Create polygon from coordinates
        function createPolygon(coords, index) {{
            const latLngs = [
                [coords.upper_left.lat, coords.upper_left.lon],
                [coords.upper_right.lat, coords.upper_right.lon],
                [coords.lower_right.lat, coords.lower_right.lon],
                [coords.lower_left.lat, coords.lower_left.lon]
            ];

            const polygon = L.polygon(latLngs, {{
                color: '#007bff',
                fillColor: '#007bff',
                fillOpacity: 0,  // Default: outline only
                weight: 2
            }}).addTo(map);

            // Add click event
            polygon.on('click', function() {{
                selectFigure(index);
            }});

            return polygon;
        }}

        // Populate figure list
        function populateFigureList() {{
            const listElement = document.getElementById('figure-list');
            listElement.innerHTML = '';

            figuresData.forEach((figure, index) => {{
                const li = document.createElement('li');
                li.className = 'figure-item';
                li.innerHTML = `
                    <div class="figure-title">${{figure.pdf_title}}</div>
                    <div class="figure-subtitle">Page ${{figure.page + 1}} • Confidence: ${{(figure.confidence * 100).toFixed(0)}}%</div>
                `;
                li.onclick = () => selectFigure(index);
                listElement.appendChild(li);
            }});

            // Update summary
            const summaryText = document.getElementById('summary-text');
            summaryText.textContent = `${{figuresData.length}} figure(s) georeferenced`;
        }}

        // Populate failed list
        function populateFailedList() {{
            if (failedData.length === 0) return;

            const failedSection = document.getElementById('failed-section');
            const listElement = document.getElementById('failed-list');
            listElement.innerHTML = '';

            failedData.forEach((figure) => {{
                const li = document.createElement('li');
                li.className = 'figure-item failed';
                li.innerHTML = `
                    <div class="figure-title">${{figure.pdf_title}}</div>
                    <div class="figure-subtitle">Page ${{figure.page + 1}} • Failed</div>
                `;
                listElement.appendChild(li);
            }});

            failedSection.style.display = 'block';
        }}

        // Show details in right sidebar
        function showDetails(index) {{
            const figure = figuresData[index];
            const sidebar = document.getElementById('right-sidebar');

            document.getElementById('detail-paper-title').textContent = figure.pdf_title;
            document.getElementById('detail-pdf-link').href = figure.pdf_path;
            document.getElementById('detail-image').src = figure.image_path;
            document.getElementById('detail-confidence').textContent = `${{(figure.confidence * 100).toFixed(0)}}%`;
            document.getElementById('detail-explanation').textContent = figure.explanation;

            sidebar.classList.add('visible');
        }}

        // Select a figure (click in list or polygon)
        function selectFigure(index) {{
            currentIndex = index;

            // Update active state in list
            document.querySelectorAll('.figure-item').forEach((item, i) => {{
                if (i === index) {{
                    item.classList.add('active');
                }} else {{
                    item.classList.remove('active');
                }}
            }});

            // Reset all polygons to outline only, fill the selected one
            Object.values(polygons).forEach(p => p.setStyle({{fillOpacity: 0}}));
            if (polygons[index]) {{
                polygons[index].setStyle({{fillOpacity: 0.2}});
            }}

            // Show details
            showDetails(index);

            // Pan and zoom to polygon
            const polygon = polygons[index];
            if (polygon) {{
                map.fitBounds(polygon.getBounds(), {{padding: [50, 50]}});
            }}

            // Show navigation buttons
            document.getElementById('nav-buttons').classList.add('visible');
            updateNavButtons();
        }}

        // Update navigation button states
        function updateNavButtons() {{
            const prevButton = document.getElementById('prev-button');
            const nextButton = document.getElementById('next-button');

            prevButton.disabled = currentIndex <= 0;
            nextButton.disabled = currentIndex >= figuresData.length - 1;
        }}

        // Navigate to previous figure
        function goToPrevious() {{
            if (currentIndex > 0) {{
                selectFigure(currentIndex - 1);
            }}
        }}

        // Navigate to next figure
        function goToNext() {{
            if (currentIndex < figuresData.length - 1) {{
                selectFigure(currentIndex + 1);
            }}
        }}

        // ===== CHAT FUNCTIONALITY =====

        // API key management (localStorage)
        const API_KEY_STORAGE_KEY = 'gemini_api_key';

        function getApiKey() {{
            return localStorage.getItem(API_KEY_STORAGE_KEY) || '';
        }}

        function saveApiKey(key) {{
            localStorage.setItem(API_KEY_STORAGE_KEY, key);
        }}

        // Simple markdown renderer (basic support for bold, italic, lists)
        function renderMarkdown(text) {{
            // Convert **bold** to <strong>
            text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            // Convert *italic* to <em>
            text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
            // Convert bullet lists (lines starting with - or *)
            const lines = text.split('\\n');
            let inList = false;
            let result = [];

            for (let i = 0; i < lines.length; i++) {{
                const line = lines[i];
                const bulletMatch = line.match(/^[\s]*[-\*]\s+(.+)$/);

                if (bulletMatch) {{
                    if (!inList) {{
                        result.push('<ul>');
                        inList = true;
                    }}
                    result.push(`<li>${{bulletMatch[1]}}</li>`);
                }} else {{
                    if (inList) {{
                        result.push('</ul>');
                        inList = false;
                    }}
                    if (line.trim()) {{
                        result.push(`<p>${{line}}</p>`);
                    }}
                }}
            }}

            if (inList) {{
                result.push('</ul>');
            }}

            return result.join('');
        }}

        // Add message to chat
        function addChatMessage(text, type = 'assistant', isLoading = false) {{
            const chatMessages = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${{type}} ${{isLoading ? 'loading' : ''}}`;

            if (type === 'assistant' && !isLoading) {{
                // Render markdown for assistant messages
                messageDiv.innerHTML = renderMarkdown(text);
            }} else {{
                messageDiv.textContent = text;
            }}

            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            return messageDiv;
        }}

        // Format text context for prompt
        function formatTextContext(textContext) {{
            const parts = [];

            if (textContext.first_page) {{
                parts.push(`TEXT FROM FIRST PAGE:\\n${{textContext.first_page}}`);
            }}
            if (textContext.page_before && textContext.page_before !== "[Same as first_page]") {{
                parts.push(`\\nTEXT FROM PAGE BEFORE IMAGE:\\n${{textContext.page_before}}`);
            }}
            if (textContext.image_page && textContext.image_page !== "[Same as first_page]") {{
                parts.push(`\\nTEXT FROM IMAGE PAGE:\\n${{textContext.image_page}}`);
            }}
            if (textContext.page_after) {{
                parts.push(`\\nTEXT FROM PAGE AFTER IMAGE:\\n${{textContext.page_after}}`);
            }}

            return parts.join('');
        }}

        // Send question to Gemini
        async function sendQuestion(question, issuggestion = false) {{
            const apiKey = getApiKey();

            if (!apiKey) {{
                addChatMessage('Please enter your Gemini API key above.', 'error');
                return;
            }}

            if (currentIndex < 0) {{
                addChatMessage('Please select a figure first.', 'error');
                return;
            }}

            const figure = figuresData[currentIndex];

            // Add user message (only if not a suggestion)
            if (!issuggestion) {{
                addChatMessage(question, 'user');
            }}

            // Add loading message
            const loadingMsg = addChatMessage('Thinking...', 'assistant', true);

            // Disable buttons
            document.getElementById('send-question-btn').disabled = true;
            document.getElementById('suggest-question-btn').disabled = true;

            try {{
                const genAI = new GoogleGenerativeAI(apiKey);
                const model = genAI.getGenerativeModel({{ model: "gemini-2.0-flash-exp" }});

                // Build prompt with map image and context
                const imagePath = figure.image_path;

                // Fetch image and convert to base64
                const imageResponse = await fetch(imagePath);
                const imageBlob = await imageResponse.blob();
                const imageBase64 = await new Promise((resolve) => {{
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.readAsDataURL(imageBlob);
                }});

                // Format the context
                const textContext = formatTextContext(figure.text_context || {{}});
                const coordsText = `Geographic coordinates:\\n- Upper-left: ${{figure.coordinates.upper_left.lat}}, ${{figure.coordinates.upper_left.lon}}\\n- Upper-right: ${{figure.coordinates.upper_right.lat}}, ${{figure.coordinates.upper_right.lon}}\\n- Lower-left: ${{figure.coordinates.lower_left.lat}}, ${{figure.coordinates.lower_left.lon}}\\n- Lower-right: ${{figure.coordinates.lower_right.lat}}, ${{figure.coordinates.lower_right.lon}}`;

                const fullPrompt = `${{prompts.chat}}\\n\\nPDF Link: ${{figure.pdf_path}}\\n\\n${{coordsText}}\\n\\n${{textContext}}\\n\\nUser question: ${{question}}`;

                const result = await model.generateContent([
                    {{
                        inlineData: {{
                            mimeType: 'image/jpeg',
                            data: imageBase64
                        }}
                    }},
                    {{ text: fullPrompt }}
                ]);

                const response = await result.response;
                const responseText = response.text();

                // Remove loading message and add response
                loadingMsg.remove();
                addChatMessage(responseText, 'assistant');
            }} catch (error) {{
                console.error('Error:', error);
                loadingMsg.remove();
                addChatMessage(`Error: ${{error.message}}`, 'error');
            }} finally {{
                // Re-enable buttons
                document.getElementById('send-question-btn').disabled = false;
                document.getElementById('suggest-question-btn').disabled = false;
            }}
        }}

        // Suggest a good question
        async function suggestQuestion() {{
            const apiKey = getApiKey();

            if (!apiKey) {{
                addChatMessage('Please enter your Gemini API key above.', 'error');
                return;
            }}

            if (currentIndex < 0) {{
                addChatMessage('Please select a figure first.', 'error');
                return;
            }}

            const figure = figuresData[currentIndex];

            // Add loading message
            const loadingMsg = addChatMessage('Generating a question...', 'assistant', true);

            // Disable buttons
            document.getElementById('send-question-btn').disabled = true;
            document.getElementById('suggest-question-btn').disabled = true;

            try {{
                const genAI = new GoogleGenerativeAI(apiKey);
                const model = genAI.getGenerativeModel({{ model: "gemini-2.0-flash-exp" }});

                // Fetch image and convert to base64
                const imagePath = figure.image_path;
                const imageResponse = await fetch(imagePath);
                const imageBlob = await imageResponse.blob();
                const imageBase64 = await new Promise((resolve) => {{
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.readAsDataURL(imageBlob);
                }});

                // Format the context
                const textContext = formatTextContext(figure.text_context || {{}});
                const coordsText = `Geographic coordinates:\\n- Upper-left: ${{figure.coordinates.upper_left.lat}}, ${{figure.coordinates.upper_left.lon}}\\n- Upper-right: ${{figure.coordinates.upper_right.lat}}, ${{figure.coordinates.upper_right.lon}}\\n- Lower-left: ${{figure.coordinates.lower_left.lat}}, ${{figure.coordinates.lower_left.lon}}\\n- Lower-right: ${{figure.coordinates.lower_right.lat}}, ${{figure.coordinates.lower_right.lon}}`;

                const fullPrompt = `${{prompts.suggest_question}}\\n\\nPDF Link: ${{figure.pdf_path}}\\n\\n${{coordsText}}\\n\\n${{textContext}}`;

                const result = await model.generateContent([
                    {{
                        inlineData: {{
                            mimeType: 'image/jpeg',
                            data: imageBase64
                        }}
                    }},
                    {{ text: fullPrompt }}
                ]);

                const response = await result.response;
                const suggestedQuestion = response.text().trim();

                // Remove loading message
                loadingMsg.remove();

                // Populate input (user will click Send to submit)
                document.getElementById('chat-input').value = suggestedQuestion;

                // Re-enable buttons
                document.getElementById('send-question-btn').disabled = false;
                document.getElementById('suggest-question-btn').disabled = false;
            }} catch (error) {{
                console.error('Error:', error);
                loadingMsg.remove();
                addChatMessage(`Error: ${{error.message}}`, 'error');
                document.getElementById('send-question-btn').disabled = false;
                document.getElementById('suggest-question-btn').disabled = false;
            }}
        }}

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {{
            initMap();
            populateFigureList();
            populateFailedList();

            // Create polygons
            figuresData.forEach((figure, index) => {{
                polygons[index] = createPolygon(figure.coordinates, index);
            }});

            // Fit map to show all polygons
            if (figuresData.length > 0) {{
                const group = L.featureGroup(Object.values(polygons));
                map.fitBounds(group.getBounds(), {{padding: [50, 50]}});
            }}

            // Setup navigation buttons
            document.getElementById('prev-button').onclick = goToPrevious;
            document.getElementById('next-button').onclick = goToNext;

            // Setup chat functionality
            // Load saved API key
            const savedKey = getApiKey();
            if (savedKey) {{
                document.getElementById('api-key-input').value = savedKey;
            }}

            // Save API key on change
            document.getElementById('api-key-input').addEventListener('change', (e) => {{
                saveApiKey(e.target.value);
            }});

            // Send question button
            document.getElementById('send-question-btn').addEventListener('click', () => {{
                const question = document.getElementById('chat-input').value.trim();
                if (question) {{
                    sendQuestion(question);
                    document.getElementById('chat-input').value = '';
                }}
            }});

            // Enter key in textarea
            document.getElementById('chat-input').addEventListener('keydown', (e) => {{
                if (e.key === 'Enter' && !e.shiftKey) {{
                    e.preventDefault();
                    const question = e.target.value.trim();
                    if (question) {{
                        sendQuestion(question);
                        e.target.value = '';
                    }}
                }}
            }});

            // Suggest question button
            document.getElementById('suggest-question-btn').addEventListener('click', suggestQuestion);

            // Setup resize functionality
            const resizeHandle = document.getElementById('resize-handle');
            const sidebarContent = document.getElementById('sidebar-content');
            const chatContainer = document.getElementById('chat-container');
            const rightSidebar = document.getElementById('right-sidebar');

            let isResizing = false;
            let startY = 0;
            let startContentHeight = 0;
            let startChatHeight = 0;

            resizeHandle.addEventListener('mousedown', (e) => {{
                isResizing = true;
                startY = e.clientY;
                startContentHeight = sidebarContent.offsetHeight;
                startChatHeight = chatContainer.offsetHeight;
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            }});

            document.addEventListener('mousemove', (e) => {{
                if (!isResizing) return;

                const deltaY = e.clientY - startY;
                const sidebarHeight = rightSidebar.offsetHeight;
                const handleHeight = resizeHandle.offsetHeight;

                // Calculate new heights
                let newContentHeight = startContentHeight + deltaY;
                let newChatHeight = startChatHeight - deltaY;

                // Enforce minimum heights
                const minContentHeight = 200;
                const minChatHeight = 200;

                if (newContentHeight < minContentHeight) {{
                    newContentHeight = minContentHeight;
                    newChatHeight = sidebarHeight - minContentHeight - handleHeight;
                }} else if (newChatHeight < minChatHeight) {{
                    newChatHeight = minChatHeight;
                    newContentHeight = sidebarHeight - minChatHeight - handleHeight;
                }}

                // Apply new heights
                sidebarContent.style.height = newContentHeight + 'px';
                sidebarContent.style.flexShrink = '0';
                chatContainer.style.flexGrow = '0';
                chatContainer.style.height = newChatHeight + 'px';
            }});

            document.addEventListener('mouseup', () => {{
                if (isResizing) {{
                    isResizing = false;
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }}
            }});
        }});
    </script>
</body>
</html>
"""
