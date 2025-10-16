from flask import Flask, request, render_template_string
from database import AirQualityReading, SessionLocal
from datetime import datetime
import requests
import json
from sqlalchemy import func, desc, asc
from flask import jsonify
from sqlalchemy import extract


app = Flask(__name__)

city_coords = {
    "Athens": [37.9838, 23.7275],
    "Heraklion": [35.341846, 25.148254],
    "Thessaloniki": [40.6401, 22.9444],
    "Patras": [38.24444, 21.73444],
    "Larissa": [39.643452, 	22.413208],
    "Chania": [35.51124, 24.02921]

}

API_KEY = "70945163e0f54e0f9fd3673273b464d552fdc21d961b6930458b58633982f925"

@app.route("/")
def index():
    with open("aqfrontend.html") as file:
        return file.read()


# ... (keep your imports and Flask setup)

@app.route("/get_data", methods=["POST"])
def get_data():
    city = request.form["city"]
    coordinates = city_coords.get(city)
    if not coordinates:
        return f"Unknown city: {city}", 400

    lat, lon = coordinates
    headers = {"X-API-Key": API_KEY}
    url = f"https://api.openaq.org/v3/locations?coordinates={lat},{lon}&radius=9000&limit=1000"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return f"Error fetching locations: {response.status_code}"

    results = response.json().get("results", [])
    if not results:
        return "No sensors found."

    raw_readings_by_param = {3: [], 4: [], 5: []}  # O₃, CO, NO₂

    for location in results:
        for sensor in location.get("sensors", []):
            param_id = sensor["parameter"]["id"]
            if param_id in raw_readings_by_param:
                sensor_id = sensor["id"]
                sensor_url = f"https://api.openaq.org/v3/sensors/{sensor_id}/days/monthly?limit=24"
                r = requests.get(sensor_url, headers=headers)
                if r.status_code == 200:
                    data = r.json().get("results", [])
                    for measurement in data:
                        value = measurement.get("value")
                        period = measurement.get("period", {})
                        time = period.get("datetimeFrom", {}).get("utc")
                        if value is not None and time:
                            raw_readings_by_param[param_id].append({
                                "value": value,
                                "time": time,
                                "sensor": sensor["parameter"]["displayName"],
                                "location": location["name"]
                            })

    db = SessionLocal()
    results_html = f"<h2>Most Recent Unique-Timestamp Readings for {city}</h2><ul>"
    chart_data = {}  # store data for separate charts

    param_names = {3: "O₃", 4: "CO", 5: "NO₂"}

    for param_id, readings in raw_readings_by_param.items():
        if not readings:
            results_html += f"<li><strong>{param_names[param_id]}</strong>: No data available.</li>"
            continue

        sorted_readings = sorted(readings, key=lambda x: x["time"], reverse=True)
        seen_times = set()
        unique_readings = []

        for entry in sorted_readings:
            if entry["time"] not in seen_times:
                unique_readings.append(entry)
                seen_times.add(entry["time"])
            if len(unique_readings) == 24:
                break

        if unique_readings:
            sensor_name = unique_readings[0]['sensor']
            results_html += f"<li><strong>{sensor_name}</strong> readings:<ul>"
            times = []
            values = []
            for entry in unique_readings:
                db.add(AirQualityReading(
                    city=city,
                    parameter=entry['sensor'],
                    value=entry['value'],
                    time=datetime.fromisoformat(entry['time'].replace("Z", "+00:00")),
                    location=entry['location']
                ))
                results_html += f"<li>{entry['time']} ({entry['location']}): {entry['value']}</li>"
                times.append(entry['time'])
                values.append(entry['value'])
            chart_data[param_names[param_id]] = {"times": times[::-1], "values": values[::-1]}
            results_html += "</ul></li>"
        else:
            results_html += f"<li><strong>{param_names[param_id]}</strong>: No unique timestamp data available.</li>"

    db.commit()
    db.close()
    results_html += "</ul>"

    # HTML with separate charts
    chart_html = "<h2>Air Quality Charts</h2>"
    chart_html += "".join(
        f'<h3>{param}</h3><canvas id="{param}Chart" width="800" height="400"></canvas>'
        for param in chart_data.keys()
    )

    chart_html += "<script src='https://cdn.jsdelivr.net/npm/chart.js'></script><script>"
    for param, data in chart_data.items():
        chart_html += f"""
        new Chart(document.getElementById('{param}Chart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(data['times'])},
                datasets: [{{
                    label: '{param}',
                    data: {json.dumps(data['values'])},
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time' }}, ticks: {{ maxRotation: 90, minRotation: 45 }} }},
                    y: {{ title: {{ display: true, text: 'Value' }} }}
                }}
            }}
        }});
        """
    chart_html += "</script>"

    return f"<html><head><title>Air Quality Data for {city}</title></head><body>{results_html}{chart_html}</body></html>"



"""@app.route("/most_polluted")
def most_polluted():
    db = SessionLocal()
    
    # Compute average value per city across all parameters
    results = (
        db.query(
            AirQualityReading.city,
            func.avg(AirQualityReading.value).label("avg_pollution")
        )
        .group_by(AirQualityReading.city)
        .order_by(func.avg(AirQualityReading.value).desc())
        .all()
    )
    
    db.close()
    
    if not results:
        return "No data available yet. Please query a city first."
    
    most_polluted_city = results[0]
    
    return f"<h2>Most Polluted City:</h2><p>{most_polluted_city.city} (Average Value: {most_polluted_city.avg_pollution:.2f})</p>"""



@app.route("/most_polluted/<param>")
def most_polluted(param):
    db = SessionLocal()
    
    try:
        param_map = {
            "o3": "O₃ mass",
            "co": "CO mass",
            "no2": "NO₂ mass"
        }

        if param in param_map:
            parameter = param_map[param]
            result = (
                db.query(
                    AirQualityReading.city,
                    func.avg(AirQualityReading.value).label("avg_pollution")
                )
                .filter(AirQualityReading.parameter == parameter)
                .group_by(AirQualityReading.city)
                .order_by(desc("avg_pollution"))
                .first()
            )

            if result:
                return f"<b>Most polluted city for {parameter}:</b> {result.city} ({result.avg_pollution:.2f})"
            else:
                return f"No data found for {parameter}"

        elif param == "most_polluted":
            # Overall most polluted (highest average value across all parameters)
            result = (
                db.query(
                    AirQualityReading.city,
                    func.avg(AirQualityReading.value).label("avg_pollution")
                )
                .group_by(AirQualityReading.city)
                .order_by(desc("avg_pollution"))
                .first()
            )
            if result:
                return f"<b>Most polluted city overall:</b> {result.city} ({result.avg_pollution:.2f})"
            else:
                return "No data found."

        elif param == "cleanest":
            # Cleanest city overall (lowest average)
            result = (
                db.query(
                    AirQualityReading.city,
                    func.avg(AirQualityReading.value).label("avg_pollution")
                )
                .group_by(AirQualityReading.city)
                .order_by(asc("avg_pollution"))
                .first()
            )
            if result:
                return f"<b>Cleanest city overall:</b> {result.city} ({result.avg_pollution:.2f})"
            else:
                return "No data found."

        else:
            return "Invalid parameter.", 400

    finally:
        db.close()
    

@app.route("/map_data")
def map_data():
    db = SessionLocal()
    results = (
        db.query(
            AirQualityReading.city,
            func.avg(AirQualityReading.value).label("avg_pollution")
        )
        .group_by(AirQualityReading.city)
        .all()
    )
    db.close()

    city_pollution = {city: avg for city, avg in results}
    return jsonify(city_pollution)

@app.route("/map")
def map_page():
    with open("aqmap.html") as file:
        return file.read()


    

@app.route("/compare", methods=["POST"])
def compare():
    data = request.get_json() or {}
    city1 = data.get("city1")
    city2 = data.get("city2")
    parameter = data.get("parameter")

    if not city1 or not city2 or not parameter:
        return jsonify({"error": "Missing parameters"}), 400

    # Map pollutant short name to DB-stored parameter name
    param_map = {
        "O₃": "O₃ mass",
        "CO": "CO mass",
        "NO₂": "NO₂ mass"
    }
    parameter = param_map.get(parameter, parameter)

    db = SessionLocal()
    try:
        month_label = func.strftime('%Y-%m', AirQualityReading.time).label('month')
        results = (
            db.query(
                AirQualityReading.city,
                month_label,
                func.avg(AirQualityReading.value).label('avg_value')
            )
            .filter(AirQualityReading.parameter == parameter)
            .filter(AirQualityReading.city.in_([city1, city2]))
            .group_by(AirQualityReading.city, month_label)
            .order_by(month_label)
            .all()
        )

        if not results:
            return jsonify({"labels": [], "datasets": []})

        months = sorted({r.month for r in results})
        per_city = {city1: {}, city2: {}}
        for city, month, avg in results:
            per_city.setdefault(city, {})[month] = float(avg)

        dataset_city1 = [per_city[city1].get(m, None) for m in months]
        dataset_city2 = [per_city[city2].get(m, None) for m in months]

        return jsonify({
            "labels": months,
            "datasets": [
                {"label": city1, "data": dataset_city1, "backgroundColor": "rgba(54,162,235,0.6)"},
                {"label": city2, "data": dataset_city2, "backgroundColor": "rgba(255,99,132,0.6)"}
            ]
        })
    finally:
        db.close()





if __name__ == "__main__":
    app.run(debug=True)