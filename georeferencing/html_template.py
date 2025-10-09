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
            width: 350px;
            background-color: #f8f9fa;
            border-left: 1px solid #dee2e6;
            overflow-y: auto;
            padding: 20px;
            display: none;
        }}

        #right-sidebar.visible {{
            display: block;
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
        <div class="detail-section">
            <h3>Paper</h3>
            <p id="detail-paper-title"></p>
            <p><a id="detail-pdf-link" href="#" target="_blank">Open PDF</a></p>
        </div>

        <div class="detail-section">
            <h3>Figure</h3>
            <img id="detail-image" class="detail-image" src="" alt="Map figure">
            <p style="margin-top: 8px; font-size: 12px;" id="detail-page"></p>
        </div>

        <div class="detail-section">
            <h3>Georeferencing</h3>
            <p><strong>Confidence:</strong> <span id="detail-confidence" class="confidence-badge"></span></p>
            <p style="margin-top: 8px;"><strong>Explanation:</strong></p>
            <p id="detail-explanation"></p>
        </div>
    </div>

    <script>
        // Data from Python
        const figuresData = {figures_json};
        const failedData = {failed_json};

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
                fillOpacity: 0.2,
                weight: 2
            }}).addTo(map);

            // Add hover and click events
            polygon.on('mouseover', function() {{
                this.setStyle({{fillOpacity: 0.4}});
                showDetails(index);
            }});

            polygon.on('mouseout', function() {{
                this.setStyle({{fillOpacity: 0.2}});
            }});

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
            document.getElementById('detail-page').textContent = `Page ${{figure.page + 1}} • ${{figure.image_filename}}`;
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
        }});
    </script>
</body>
</html>
"""
