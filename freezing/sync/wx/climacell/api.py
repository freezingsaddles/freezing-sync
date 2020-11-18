import os

from datetime import datetime
from pytz import utc
from logging import Logger, getLogger

from json import dumps, load, loads
from requests import get
from requests.exceptions import HTTPError

from .model import Forecast


class HistoClimaCell(object):
    """
    Histomorphic climacell.
    """

    def __init__(
        self,
        api_key: str,
        cache_dir: str = None,
        cache_only: bool = False,
        logger: Logger = None,
    ):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.cache_only = cache_only
        self.logger = logger or getLogger(__name__)
        if cache_only and not cache_dir:
            raise RuntimeError("Cache only but no cache dir 8(")

    def histo_forecast(
        self, time: datetime, latitude: float, longitude: float
    ) -> Forecast:
        json = self._get_cached(
            path=self._cache_file(time=time, longitude=longitude, latitude=latitude),
            fetch=lambda: self._forecast(
                time=time, latitude=latitude, longitude=longitude
            ),
        )
        return Forecast(time, latitude, longitude, json)

    def forecast(self, time: datetime, latitude: float, longitude: float) -> Forecast:
        return Forecast(
            time, latitude, longitude,
            self._forecast(time=time, latitude=latitude, longitude=longitude)
        )

    def _forecast(self, time: datetime, latitude: float, longitude: float):
        start_time = time.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(utc)
        end_time = time.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(utc)
        query_params = {
            "lat": latitude,
            "lon": longitude,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "unit_system": "us",
            "fields": "precipitation,precipitation_type,temp,feels_like"
        }
        self.logger.debug(f"Query parameters: {query_params}")
        response = get(
            url="https://api.climacell.co/v3/weather/historical/station",
            params=query_params,
            headers={
                "Accept-Encoding": "gzip",
                "ApiKey": self.api_key
            },
            timeout=60,  # yes, it can be quite slow, our cache helps a lot
        )
        if response.status_code is not 200:
            raise HTTPError(
                f"Bad response: {response.status_code} {response.reason}: {response.text}"
            )
        return loads(response.text)

    def _cache_file(self, time: datetime, longitude: float, latitude: float):
        if not self.cache_dir:
            return None  # where are all the monads
        directory = os.path.join(self.cache_dir, f"{longitude}x{latitude}")
        return os.path.join(directory, f'{time.strftime("%Y-%m-%d")}.json')

    def _get_cached(self, path: str, fetch):
        if not path:
            return fetch()

        if os.path.exists(path):
            self.logger.debug(f"Cache hit for {path}")
            try:
                with open(path, "r") as file:
                    return load(file)
            except:
                self.logger.warning(f"Error reading cache file {path}")
                os.remove(path)

        if self.cache_only:
            raise RuntimeError(f"No cache entry for {path} and cache_only is true")

        self.logger.debug(f"Cache miss for {path}")

        json = fetch()

        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)

        with open(path, "w") as file:
            file.write(dumps(json, indent=2))

        return json
