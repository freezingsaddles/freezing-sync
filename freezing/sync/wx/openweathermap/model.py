from datetime import datetime
from pytz import timezone, tzinfo


def from_k(k: float):
    return (k - 273.15) * 1.8 + 32


def from_mm(mm: float):
    return mm / 25.4


class Observation(object):

    time: datetime
    temperature: float
    apparent_temperature: float
    rain: float
    snow: float

    def __init__(self, json, tz: tzinfo):
        self.time = datetime.fromtimestamp(json["dt"], tz)
        self.temperature = from_k(json["temp"])
        self.apparent_temperature = from_k(json["feels_like"])
        self.rain = from_mm(json.get("rain", {}).get("1h", 0.0))
        self.snow = from_mm(json.get("snow", {}).get("1h", 0.0))


class Day(object):

    sunrise_time: datetime
    sunset_time: datetime
    temperature_min: float
    temperature_max: float

    def __init__(self, json, tz: tzinfo, observations: [Observation]):
        self.sunrise_time = datetime.fromtimestamp(json["sunrise"], tz)
        self.sunset_time = datetime.fromtimestamp(json["sunset"], tz)
        self.temperature_min = min([o.temperature for o in observations])
        self.temperature_max = max([o.temperature for o in observations])


class Forecast(object):

    latitude: float
    longitude: float
    daily: Day
    observations: [Observation]

    def __init__(self, json):
        tz = timezone(json["timezone"])
        self.observations = [Observation(d, tz) for d in json["hourly"]]
        self.latitude = json["lat"]
        self.longitude = json["lon"]
        self.daily = Day(json["current"], tz, self.observations)
