from openaq import OpenAQ
import requests

# Initialize client
client = OpenAQ(api_key="70945163e0f54e0f9fd3673273b464d552fdc21d961b6930458b58633982f925")

# Coordinates for Heraklion
coordinates = [35.341846, 25.148254]

# Get locations within 12 km
response = client.locations.list(coordinates=coordinates, radius=12000, limit=1000)

# Extract sensors from the first location only
matching_sensors = []

print("\nMatching sensors in the first found location:\n")

if response.results:
    location = response.results[0]
    print(f"Location: {location.name} (ID: {location.id})")

    for sensor in location.sensors:
        param_id = sensor.parameter.id
        if param_id==3 or param_id==4 or param_id==5:  # 3: O₃, 4: CO, 5: NO₂
            print(f"  Sensor ID: {sensor.id}, Parameter: {sensor.parameter.name} ({sensor.parameter.display_name})")
            matching_sensors.append(sensor)
else:
    print("❌ No locations found within the specified area.")


client.close()

# Ping each sensor for daily measurements
print("\nFetching daily measurements from sensors...\n")

for sensor in matching_sensors:
    sensor_id = sensor.id
    url = f"https://api.openaq.org/v3/sensors/{sensor_id}/days/monthly"
    headers = {
        "X-API-Key": "70945163e0f54e0f9fd3673273b464d552fdc21d961b6930458b58633982f925"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Failed to get data for Sensor ID {sensor_id}")
        print(response.text)
        continue

    data = response.json().get("results", [])

    if not data:
        print(f"No daily data available for Sensor ID {sensor_id}")
        continue

    print(f"\n📊 Daily measurements for Sensor ID {sensor_id} ({sensor.parameter.display_name}):")

    # Extract just the value and the period start time (UTC)
    simplified_measurements = []
    for entry in data:
        value = entry.get("value")
        period = entry.get("period", {})
        datetime_from = period.get("datetimeFrom", {})
        utc_time = datetime_from.get("utc")
        simplified_measurements.append({"value": value, "utc": utc_time})

    # Print the simplified measurements nicely
    for entry in simplified_measurements:
        print(f"  - Value: {entry['value']}, Time (UTC): {entry['utc']}")