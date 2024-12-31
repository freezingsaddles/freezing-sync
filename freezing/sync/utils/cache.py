import abc
import json
import logging
import os
from typing import Any, Dict, List, Optional

from freezing.model.orm import Ride
from stravalib.client import Client
from stravalib.exc import ObjectNotFound
from stravalib.model import Activity, IdentifiableEntity, Stream


class CachingAthleteObjectFetcher(metaclass=abc.ABCMeta):
    """
    A class to fetch and cache athlete objects.
    """

    @property
    @abc.abstractmethod
    def object_type(self):
        """
        The type of object being fetched.
        """
        pass

    def __init__(self, cache_basedir: str, client: Client):
        """
        Initialize the fetcher with a cache directory and a client.

        :param cache_basedir: The base directory for caching.
        :param client: The client to use for fetching objects.
        """
        assert cache_basedir, "No cache_basedir provided."
        self.logger = logging.getLogger(
            "{0.__module__}.{0.__name__}".format(self.__class__)
        )
        self.cache_basedir = cache_basedir
        self.client = client

    def filename(self, *, athlete_id: int, object_id: int):
        """
        Generate the filename for the cached object.

        :param athlete_id: The athlete ID.
        :param object_id: The object ID.
        :return: The filename for the cached object.
        """
        return "{}.json".format(athlete_id)

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

        object_fname = self.filename(athlete_id=athlete_id, object_id=object_id)
        cache_path = os.path.join(directory, object_fname)

        with open(cache_path, "w") as fp:
            fp.write(json.dumps(object_json, indent=2))

        return cache_path

    def get_cached_object_json(
        self, athlete_id: int, activity_id: int
    ) -> Dict[str, Any]:
        """
        Retrieves raw object from cached directory.
        """
        directory = self.cache_dir(athlete_id)

        activity_fname = "{}.json".format(activity_id)

        cache_path = os.path.join(directory, activity_fname)

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
    ) -> Optional[IdentifiableEntity]:
        """
        Fetch the object, possibly from cache.

        :param athlete_id: The athlete ID.
        :param object_id: The object ID.
        :param use_cache: Whether to use the cache.
        :param only_cache: Whether to use only the cache.
        :return: The fetched object.
        """
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
        :param use_cache: Allow use of cache.
        :param only_cache: Only use cache (no download)
        :return:
        """
        if use_cache:
            object_json = self.get_cached_object_json(
                athlete_id=athlete_id, activity_id=object_id
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
                "[CACHE-MISS] Fetching {} detail for {!r}".format(
                    self.object_type, object_id
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
            except:
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
    """
    A class to fetch and cache activities.
    """
    object_type = "activity"

    def download_object_json(
        self, *, athlete_id: int, object_id: int
    ) -> Dict[str, Any]:
        """
        Download the activity JSON.

        :param athlete_id: The athlete ID.
        :param object_id: The activity ID.
        :return: The activity JSON.
        """
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
    ) -> Optional[Activity]:
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
            return Activity.deserialize(activity_json, bind_client=self.client)


class CachingStreamFetcher(CachingAthleteObjectFetcher):
    """
    A class to fetch and cache activity streams.
    """
    object_type = "streams"

    def filename(self, *, athlete_id: int, object_id: int):
        """
        Generate the filename for the cached stream.

        :param athlete_id: The athlete ID.
        :param object_id: The activity ID.
        :return: The filename for the cached stream.
        """
        return "{}_streams.json".format(athlete_id)

    def download_object_json(
        self, *, athlete_id: int, object_id: int
    ) -> Dict[str, Any]:
        """
        Download the stream JSON.

        :param athlete_id: The athlete ID.
        :param object_id: The activity ID.
        :return: The stream JSON.
        """
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
