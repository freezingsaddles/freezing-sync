from datetime import datetime
from pytz import timezone, utc


# A minimal model with just the data we need.


class Hour(object):
    time: datetime
    temperature: float
    apparent_temperature: float
    precip_type: str
    precip_accumulation: float

    def __init__(self, json, tz):
        self.time = datetime.fromtimestamp(json["time"], tz)
        self.temperature = json["temperature"]
        self.apparent_temperature = json["apparentTemperature"]
        self.precip_type = json.get("precipType")
        self.precip_accumulation = json.get("precipAccumulation", 0.0)


class Day(object):
    sunrise_time: datetime
    sunset_time: datetime
    temperature_min: float
    temperature_max: float

    def __init__(self, json, tz):
        self.sunrise_time = datetime.fromtimestamp(json["sunriseTime"], tz)
        self.sunset_time = datetime.fromtimestamp(json["sunsetTime"], tz)
        self.temperature_min = json["temperatureMin"]
        self.temperature_max = json["temperatureMax"]


class Forecast(object):
    timezone: str
    latitude: float
    longitude: float
    daily: Day
    hourly: [Hour]

    def __init__(self, json):
        self.timezone = timezone(json["timezone"])
        self.latitude = json["latitude"]
        self.longitude = json["longitude"]
        self.daily = Day(json["daily"]["data"][0], self.timezone)
        self.hourly = [Hour(d, self.timezone) for d in json["hourly"]["data"]]
