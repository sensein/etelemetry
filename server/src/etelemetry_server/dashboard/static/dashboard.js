/**
 * etelemetry dashboard JavaScript.
 *
 * Initializes Leaflet map and handles htmx-driven filter updates.
 */

/* global L, htmx */

var dashboardMap = null;
var geoJsonLayer = null;

/**
 * Initialize the dashboard for a specific project.
 * @param {string} owner - Project owner.
 * @param {string} repo - Project repository name.
 */
function initDashboard(owner, repo) {
    var mapEl = document.getElementById("map");
    if (!mapEl) {
        return;
    }

    // Initialize Leaflet map
    dashboardMap = L.map("map").setView([20, 0], 2);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
    }).addTo(dashboardMap);

    // Load GeoJSON data
    fetchGeoJSON(owner, repo);

    // Listen for htmx events to refresh map data after filter changes
    document.body.addEventListener("htmx:afterSwap", function () {
        fetchGeoJSON(owner, repo);
    });
}

/**
 * Fetch GeoJSON data and render circle markers on the map.
 * @param {string} owner - Project owner.
 * @param {string} repo - Project repository name.
 */
function fetchGeoJSON(owner, repo) {
    var url = "/dashboard/api/geo/" + owner + "/" + repo;

    // Include granularity filter if present
    var granularitySelect = document.getElementById("granularity-select");
    if (granularitySelect) {
        url += "?granularity=" + granularitySelect.value;
    }

    fetch(url)
        .then(function (response) {
            return response.json();
        })
        .then(function (data) {
            renderGeoJSON(data);
        })
        .catch(function (err) {
            console.error("Failed to fetch GeoJSON:", err);
        });
}

/**
 * Render GeoJSON FeatureCollection as circle markers on the map.
 * @param {object} geojson - GeoJSON FeatureCollection.
 */
function renderGeoJSON(geojson) {
    if (!dashboardMap) {
        return;
    }

    // Remove existing layer
    if (geoJsonLayer) {
        dashboardMap.removeLayer(geoJsonLayer);
    }

    if (!geojson || !geojson.features || geojson.features.length === 0) {
        return;
    }

    // Find max count for scaling
    var maxCount = 1;
    geojson.features.forEach(function (feature) {
        var count = feature.properties.count || 0;
        if (count > maxCount) {
            maxCount = count;
        }
    });

    geoJsonLayer = L.geoJSON(geojson, {
        pointToLayer: function (feature, latlng) {
            var count = feature.properties.count || 0;
            var radius = Math.max(5, Math.sqrt(count / maxCount) * 30);
            return L.circleMarker(latlng, {
                radius: radius,
                fillColor: "#2563eb",
                color: "#1d4ed8",
                weight: 1,
                opacity: 0.8,
                fillOpacity: 0.5,
            });
        },
        onEachFeature: function (feature, layer) {
            var props = feature.properties;
            var parts = [];
            if (props.city) parts.push(props.city);
            if (props.region) parts.push(props.region);
            if (props.country) parts.push(props.country);
            var location = parts.join(", ") || "Unknown";
            layer.bindPopup(
                "<strong>" + location + "</strong><br>Checks: " + props.count
            );

            // Click handler for drill-down
            layer.on("click", function () {
                layer.openPopup();
            });
        },
    }).addTo(dashboardMap);

    // Fit map to markers
    dashboardMap.fitBounds(geoJsonLayer.getBounds(), { padding: [20, 20] });
}
