import abc
import json
import logging
import os
from typing import Any, Dict, List, Optional

from stravalib.client import Client
from stravalib.exc import ObjectNotFound
from stravalib.model import BoundClientEntity, DetailedActivity, Stream


class CachingAthleteObjectFetcher(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def object_type(self):
        pass

    def __init__(self, cache_basedir: str, client: Client):
        assert cache_basedir, "No cache_basedir provided."
        self.logger = logging.getLogger(
            "{0.__module__}.{0.__name__}".format(self.__class__)
        )
        self.cache_basedir = cache_basedir
        self.client = client

    def filename(self, *, object_id: int):
        return "{}_{}.json".format(object_id, self.object_type)

    def cache_dir(self, athlete_id: int) -> str:
        """
        Gets the cache directory for specific athlete.
        :param athlete_id: The athlete ID.
        :return: The cache directory.
        """
        directory = os.path.join(self.cache_basedir, str(athlete_id))
        if not os.path.exists(directory):
            os.makedirs(directory)

        return directory

    def cache_object_json(
        self, *, athlete_id: int, object_id: int, object_json: Dict[str, Any]
    ) -> str:
        """
        Writes object (e.g. activity, stream) to cache dir.
        :return: The path to the cached file.
        """
        directory = self.cache_dir(athlete_id)

        object_fname = self.filename(object_id=object_id)
        cache_path = os.path.join(directory, object_fname)

        with open(cache_path, "w") as fp:
            fp.write(json.dumps(object_json, indent=2))

        return cache_path

    def get_cached_object_json(self, athlete_id: int, object_id: int) -> Dict[str, Any]:
        """
        Retrieves raw object from cached directory.
        """
        directory = self.cache_dir(athlete_id)

        object_fname = self.filename(object_id=object_id)
        cache_path = os.path.join(directory, object_fname)

        activity_json = None
        if os.path.exists(cache_path):
            with open(cache_path, "r") as fp:
                activity_json = json.load(fp)

        return activity_json

    @abc.abstractmethod
    def download_object_json(
        self, *, athlete_id: int, object_id: int
    ) -> Dict[str, Any]:
        """
        Download object json.
        :return: The object json structure.
        """

    @abc.abstractmethod
    def fetch(
        self,
        *,
        athlete_id: int,
        object_id: int,
        use_cache: bool = True,
        only_cache: bool = False
        # ):
    ) -> Optional[BoundClientEntity]:
        pass

    def retrieve_object_json(
        self,
        *,
        athlete_id: int,
        object_id: int,
        use_cache: bool = True,
        only_cache: bool = False
    ) -> Optional[Any]:
        """
        Fetches an object, possibly from cache, and returns the JSON for it.

        :param athlete_id:
        :param object_id:
        :param use_cache: Allow reading from cache.
        :param only_cache: Only read from cache (no download)
        :return:
        """
        if use_cache:
            object_json = self.get_cached_object_json(
                athlete_id=athlete_id, object_id=object_id
            )
        else:
            object_json = None

        if object_json is None:
            if only_cache:
                self.logger.info(
                    "[CACHE-MISS] Skipping {} {} "
                    "since there is no cached version.".format(
                        self.object_type, object_id
                    )
                )
                return None

            self.logger.info(
                "[CACHE-{}] Fetching {} detail for {!r}".format(
                    "MISS" if use_cache else "BYPASS", self.object_type, object_id
                )
            )

            # We do this with the low-level API, so that we can cache the JSON for later use.
            object_json = self.download_object_json(
                athlete_id=athlete_id, object_id=object_id
            )

            try:
                self.logger.info("Caching {} {}".format(self.object_type, object_id))
                self.cache_object_json(
                    athlete_id=athlete_id, object_id=object_id, object_json=object_json
                )
            except ObjectNotFound:
                self.logger.debug(
                    "{} not found (ignoring): {}".format(self.object_type, object_id)
                )
                return None
            except Exception:
                self.logger.error(
                    "Error caching {} {} (ignoring)".format(
                        self.object_type, object_id
                    ),
                    exc_info=self.logger.isEnabledFor(logging.DEBUG),
                )

        else:
            self.logger.info(
                "[CACHE-HIT] Using cached {} detail for {!r}".format(
                    self.object_type, object_id
                )
            )

        return object_json


class CachingActivityFetcher(CachingAthleteObjectFetcher):
    object_type = "activity"

    def download_object_json(
        self, *, athlete_id: int, object_id: int
    ) -> Dict[str, Any]:
        return self.client.protocol.get(
            "/activities/{id}", id=object_id, include_all_efforts=True
        )

    def fetch(
        self,
        *,
        athlete_id: int,
        object_id: int,
        use_cache: bool = True,
        only_cache: bool = False
    ) -> Optional[DetailedActivity]:
        """
        Fetches activity and returns it.

        :param athlete_id:
        :param object_id:
        :param use_cache:
        :param only_cache:
        :return:
        """
        activity_json = self.retrieve_object_json(
            athlete_id=athlete_id,
            object_id=object_id,
            use_cache=use_cache,
            only_cache=only_cache,
        )
        if activity_json:
            return DetailedActivity.deserialize(activity_json, bind_client=self.client)


class CachingStreamFetcher(CachingAthleteObjectFetcher):
    object_type = "streams"

    def download_object_json(
        self, *, athlete_id: int, object_id: int
    ) -> Dict[str, Any]:
        return self.client.protocol.get(
            "/activities/{id}/streams/{types}".format(
                id=object_id, types="latlng,time,altitude"
            ),
            resolution="low",
        )

    def fetch(
        self,
        *,
        athlete_id: int,
        object_id: int,
        use_cache: bool = True,
        only_cache: bool = False
    ) -> Optional[List[Stream]]:
        """
        Fetches activity and returns it.

        :param athlete_id:
        :param object_id:
        :param use_cache:
        :param only_cache:
        :return:
        """
        streams_json = self.retrieve_object_json(
            athlete_id=athlete_id,
            object_id=object_id,
            use_cache=use_cache,
            only_cache=only_cache,
        )

        if streams_json:
            return [
                Stream.deserialize(stream_struct, bind_client=self.client)
                for stream_struct in streams_json
            ]
