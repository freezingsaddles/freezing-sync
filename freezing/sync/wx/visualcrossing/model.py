from datetime import date, datetime, time

from pytz import timezone

# A minimal model with just the data we need.


class Hour(object):
    time: datetime
    temperature: float
    apparent_temperature: float
    precip_type: str  # rain,snow
    precip_accumulation: float
    source: str  # obs,fcst

    def __init__(self, json, date, tz):
        self.time = datetime.combine(
            date, time.fromisoformat(json["datetime"]).replace(tzinfo=tz)
        )
        self.temperature = json["temp"]
        self.apparent_temperature = json["feelslike"]
        precip_types = json["preciptype"]  # can be null
        # precip is rain plus melted snow which means if it snows then we have to overwrite this value
        # with the actual snowfall in order to avoid double-counting those molecules. we can't record a
        # ride as both rain and snow because then the ride rainfall would count instead the frozen snow
        # accumulation and massively overstate reality. so snow always trumps rain.
        self.precip_accumulation = json.get("precip", 0.0)
        if precip_types and "snow" in precip_types:
            self.precip_type = "snow"
            self.precip_accumulation = json.get("snow", 0.0)
        elif precip_types and (
            "sleet" in precip_types or "ice" in precip_types or "rain" in precip_types
        ):
            self.precip_type = "rain"  # count ice and sleet as rain
        else:
            self.precip_type = ""
        self.source = json["source"]


class Day(object):
    date: date
    sunrise: datetime
    sunset: datetime
    temperature_min: float
    temperature_max: float
    hours: [Hour]

    def __init__(self, json, tz):
        self.date = date.fromisoformat(json["datetime"])
        self.sunrise = datetime.combine(
            self.date, time.fromisoformat(json["sunrise"]).replace(tzinfo=tz)
        )
        self.sunset = datetime.combine(
            self.date, time.fromisoformat(json["sunset"]).replace(tzinfo=tz)
        )
        self.temperature_min = json["tempmin"]
        self.temperature_max = json["tempmax"]
        self.hours = [Hour(d, self.date, tz) for d in json["hours"]]


class Forecast(object):
    timezone: str
    latitude: float
    longitude: float
    day: Day

    def __init__(self, json):
        self.timezone = timezone(json["timezone"])
        self.latitude = json["latitude"]
        self.longitude = json["longitude"]
        self.day = Day(json["days"][0], self.timezone)
