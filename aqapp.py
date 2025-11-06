from flask import Flask, request, render_template_string
from database import AirQualityReading, SessionLocal
from datetime import datetime
import requests
import json
from sqlalchemy import func, desc, asc, and_
from flask import jsonify
from sqlalchemy import extract
from flask import Flask, request, render_template, redirect, url_for, Response
from datetime import datetime, timezone




app = Flask(__name__)

city_coords = {
    "Athens": [37.9838, 23.7275],
    "Heraklion": [35.341846, 25.148254],
    "Thessaloniki": [40.6401, 22.9444],
    "Patras": [38.24444, 21.73444],
    "Larissa": [39.643452, 	22.413208],
    "Chania": [35.51124, 24.02921],
    "Volos": [39.3610, 22.9420],
    "Grevena": [40.08452, 21.42744],
    "Kozani":[40.30069, 21.78896],
    "Karditsa": [39.36485, 21.92191],
    "Trikala":[39.55493, 21.76837]

}

API_KEY = "70945163e0f54e0f9fd3673273b464d552fdc21d961b6930458b58633982f925"

@app.route("/")
def index():
    with open("aqfrontend.html") as file:
        return file.read()


from flask import Response
from datetime import datetime, timezone
import json
import requests

from flask import Response
from datetime import datetime, timezone

from flask import request, Response
from datetime import datetime, timezone
import requests
import json
from sqlalchemy.orm import Session

@app.route("/get_data", methods=["POST"])
def get_data():
    city = request.form["city"]

    # read date filters
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

    if start_date:
        start_date = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    if end_date:
        end_date = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)

    db = SessionLocal()

    # Create initial query
    query = db.query(AirQualityReading).filter(AirQualityReading.city == city)

    # Apply date filters only if provided
    if start_date:
        query = query.filter(AirQualityReading.time >= start_date)
    if end_date:
        query = query.filter(AirQualityReading.time <= end_date)

    # Execute query
    db_readings = query.order_by(AirQualityReading.time.asc()).all()
    print(f"[DEBUG] DB returned {len(db_readings)} rows for city {city}")

    # If DB is empty → fetch from API
    if not db_readings:
        lat, lon = city_coords.get(city)
        headers = {"X-API-Key": API_KEY}
        url = f"https://api.openaq.org/v3/locations?coordinates={lat},{lon}&radius=9000&limit=1000"
        res = requests.get(url, headers=headers).json().get("results", [])

        for location in res:
            for sensor in location.get("sensors", []):
                if sensor["parameter"]["id"] not in (3, 4, 5):
                    continue

                s_url = f"https://api.openaq.org/v3/sensors/{sensor['id']}/days/monthly?limit=24"
                r = requests.get(s_url, headers=headers)
                if r.status_code != 200:
                    continue

                for m in r.json().get("results", []):
                    time_str = m.get("period", {}).get("datetimeFrom", {}).get("utc")
                    value = m.get("value")
                    if not time_str or value is None:
                        continue

                    time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    db.add(AirQualityReading(
                        city=city,
                        parameter=sensor["parameter"]["displayName"],
                        value=float(value),
                        time=time,
                        location=location["name"]
                    ))

        db.commit()

        # reload filtered data
        query = db.query(AirQualityReading).filter(AirQualityReading.city == city)
        if start_date:
            query = query.filter(AirQualityReading.time >= start_date)
        if end_date:
            query = query.filter(AirQualityReading.time <= end_date)
        db_readings = query.order_by(AirQualityReading.time.asc()).all()

    db.close()

    # --- 2️ Align times and chart data ---
    param_map = {"O₃ mass": "O₃", "CO mass": "CO", "NO₂ mass": "NO₂"}
    all_times = sorted({row.time for row in db_readings})
    times = [t.isoformat() for t in all_times]

    chart_data = {"O₃": [], "CO": [], "NO₂": []}
    data_dict = {param: {} for param in chart_data}

    for row in db_readings:
        param = param_map.get(row.parameter)
        if not param:
            continue
        data_dict[param][row.time] = row.value

    for t in all_times:
        for param in chart_data:
            chart_data[param].append(data_dict[param].get(t, None))

    print(f"[DEBUG] First 5 times: {times[:5]}")
    print(f"[DEBUG] O₃ values (first 5): {chart_data['O₃'][:5]}")
    print(f"[DEBUG] CO values (first 5): {chart_data['CO'][:5]}")
    print(f"[DEBUG] NO₂ values (first 5): {chart_data['NO₂'][:5]}")

    # --- 3️ Build HTML with Chart.js ---
    chart_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Air Quality Data for {city}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background-color: #f8f9fa; }}
            .chart-card {{
                border-radius: 1rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                padding: 1.5rem;
                margin-bottom: 2rem;
                background-color: white;
            }}
            .chart-canvas {{
                max-height: 350px;
                height: 35vh;
            }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-light bg-white shadow-sm mb-4">
            <div class="container-fluid">
                <a href="/" class="btn btn-outline-primary">
                    <i class="bi bi-arrow-left"></i> Back to Dashboard
                </a>
                <span class="navbar-brand mb-0 h1">🌍 Air Quality for {city}</span>
            </div>
        </nav>
        <div class="container">
            <div class="row">
                <div class="col-12 mb-3">
                    <h2 class="text-center text-primary">Air Quality Charts for {city}</h2>
                </div>
            </div>
    """

    # Add one chart per parameter
    for param in chart_data:
        chart_html += f"""
        <div class="chart-card">
            <h4 class="text-secondary">{param}</h4>
            <canvas id="{param}Chart" class="chart-canvas"></canvas>
        </div>
        """

    # Chart.js script
    chart_html += "<script>"
    for param in chart_data:
        chart_html += f"""
        new Chart(document.getElementById('{param}Chart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(times)},
                datasets: [{{
                    label: '{param}',
                    data: {json.dumps(chart_data[param])},
                    borderColor: 'rgba(54, 162, 235, 0.8)',
                    backgroundColor: 'rgba(54, 162, 235, 0.3)',
                    tension: 0.3,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    tooltip: {{
                        mode: 'index',
                        intersect: false
                    }}
                }},
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time' }}, ticks: {{ maxRotation: 45, minRotation: 0 }} }},
                    y: {{ title: {{ display: true, text: 'Value' }}}}
                }}
            }}
        }});
        """
    chart_html += "</script></div></body></html>"

    return Response(chart_html, mimetype="text/html")














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
    

@app.route("/map_data/<param>")
def map_data(param):
    db = SessionLocal()

    param_map = {
        "o3": "O₃ mass",
        "co": "CO mass",
        "no2": "NO₂ mass"
    }

    if param not in param_map:
        db.close()
        return jsonify({"error": "Invalid pollutant"}), 400

    try:
        results = (
            db.query(
                AirQualityReading.city,
                func.avg(AirQualityReading.value).label("avg_value")
            )
            .filter(AirQualityReading.parameter == param_map[param])
            .group_by(AirQualityReading.city)
            .all()
        )

        data = [{"city": r.city, "avg_value": float(r.avg_value)} for r in results]
        return jsonify(data)

    finally:
        db.close()



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
    start = data.get("start_date")
    end = data.get("end_date")

    if not city1 or not city2 or not parameter:
        return jsonify({"error": "Missing parameters"}), 400

    # Convert UI param to DB param
    param_map = {
        "O₃": "O₃ mass",
        "CO": "CO mass",
        "NO₂": "NO₂ mass"
    }
    parameter = param_map.get(parameter, parameter)

    # Date conversion
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) if start else None
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else None

    color_map = {
        "O₃ mass": ["rgba(191,36,87,0.6)", "rgba(44,86,166,0.8)"],
        "CO mass": ["rgba(191,36,87,0.6)", "rgba(44,86,166,0.8)"],
        "NO₂ mass": ["rgba(191,36,87,0.6)", "rgba(44,86,166,0.8)"]
    }
    colors = color_map.get(parameter)

    db = SessionLocal()
    try:
        month_label = func.strftime('%Y-%m', AirQualityReading.time).label('month')

        query = (
            db.query(
                AirQualityReading.city,
                month_label,
                func.avg(AirQualityReading.value).label('avg_value')
            )
            .filter(AirQualityReading.parameter == parameter)
            .filter(AirQualityReading.city.in_([city1, city2]))
        )

        if start_dt:
            query = query.filter(AirQualityReading.time >= start_dt)
        if end_dt:
            query = query.filter(AirQualityReading.time <= end_dt)

        results = (
            query.group_by(AirQualityReading.city, month_label)
                 .order_by(month_label)
                 .all()
        )

        if not results:
            return jsonify({"labels": [], "datasets": []})

        months = sorted({r.month for r in results})
        per_city = {city1: {}, city2: {}}
        for city, month, avg in results:
            per_city.setdefault(city, {})[month] = float(avg)

        dataset_city1 = [per_city[city1].get(m) for m in months]
        dataset_city2 = [per_city[city2].get(m) for m in months]

        return jsonify({
            "labels": months,
            "datasets": [
                {"label": city1, "data": dataset_city1, "borderColor": colors[0], "backgroundColor": colors[0], "fill": False, "tension": 0.3},
                {"label": city2, "data": dataset_city2, "borderColor": colors[1], "backgroundColor": colors[1], "fill": False, "tension": 0.3}
            ]
        })

    finally:
        db.close()


@app.route("/filter_city", methods=["POST"])
def filter_city():
    data = request.get_json()
    city = data.get("city")
    parameter = data.get("parameter")
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    db = SessionLocal()
    query = db.query(AirQualityReading).filter(AirQualityReading.city == city)

    if parameter:
        query = query.filter(AirQualityReading.parameter == parameter)

    if start_date:
        query = query.filter(AirQualityReading.time >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(AirQualityReading.time <= datetime.fromisoformat(end_date))

    records = query.order_by(AirQualityReading.time).all()
    db.close()

    return jsonify({
        "labels": [r.time.isoformat() for r in records],
        "values": [r.value for r in records],
        "city": city,
        "parameter": parameter
    })





if __name__ == "__main__":

    app.run(debug=True)
