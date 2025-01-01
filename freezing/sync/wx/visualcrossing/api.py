import os
from datetime import datetime
from json import dumps, load, loads
from logging import Logger, getLogger

from requests import get
from requests.exceptions import HTTPError

from .model import Forecast


class HistoVisualCrossing(object):
    """
    Histomorphic visual crossing. Kinda like animal crossing, but for weather data.
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
        return Forecast(json)

    def forecast(self, time: datetime, latitude: float, longitude: float) -> Forecast:
        return Forecast(
            self._forecast(time=time, latitude=latitude, longitude=longitude)
        )

    def _forecast(self, time: datetime, latitude: float, longitude: float):
        response = get(
            url=f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{latitude},{longitude}/{time.strftime('%Y-%m-%d')}",
            params={"unitGroup": "us", "include": "hours", "key": self.api_key},
            headers={"Accept-Encoding": "gzip"},
            timeout=15,
        )
        if response.status_code != 200:
            raise HTTPError(
                f"Bad response: {response.status_code} {response.reason}: {response.text}"
            )
        return loads(response.text)

    def _cache_file(self, time: datetime, longitude: float, latitude: float):
        if not self.cache_dir:
            return None  # where are all the monads
        directory = os.path.join(self.cache_dir, f"{longitude}x{latitude}")
        return os.path.join(directory, f'{time.strftime("%Y-%m-%dT%H")}.json')

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
