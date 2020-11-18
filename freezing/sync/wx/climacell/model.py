from datetime import datetime
from pytz import tzinfo
from re import sub
from astral import Observer
from astral.sun import sun


class Observation(object):

    time: datetime
    temperature: float
    apparent_temperature: float
    precip_type: str
    precip_rate: float  # in/hour

    def __init__(self, json, time: datetime):
        self.time = datetime.fromisoformat(sub(r'Z', '+00:00', json["observation_time"]["value"])).astimezone(time.tzinfo)
        self.temperature = json["temp"]["value"]
        self.apparent_temperature = json["feels_like"]["value"]
        self.precip_type = json["precipitation_type"]["value"] or "none"
        self.precip_rate = json["precipitation"]["value"] or 0.0  # may be NULL (!) in the json


class Day(object):

    sunrise_time: datetime
    sunset_time: datetime
    temperature_min: float
    temperature_max: float

    def __init__(self, time: datetime, latitude: float, longitude: float, observations: [Observation]):
        # the API claims to support sunrise/sunset but factually does not
        observer = Observer(latitude, longitude, 0.0)
        sundata = sun(observer, date=time, tzinfo=time.tzinfo)
        self.sunrise_time = sundata["sunrise"]
        self.sunset_time = sundata["sunset"]
        self.temperature_min = min([o.temperature for o in observations])
        self.temperature_max = max([o.temperature for o in observations])


class Forecast(object):

    latitude: float
    longitude: float
    daily: Day
    observations: [Observation]

    def __init__(self, time: datetime, latitude: float, longitude: float, json):
        self.observations = [Observation(d, time) for d in json]
        self.latitude = latitude
        self.longitude = longitude
        self.daily = Day(time, latitude, longitude, self.observations)
