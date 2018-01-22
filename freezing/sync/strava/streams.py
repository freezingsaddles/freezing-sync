import os
import json
import logging
from typing import Dict, Any, List

from geoalchemy import WKTSpatialElement
from polyline.codec import PolylineCodec
from sqlalchemy import update, or_, and_

from stravalib.model import Activity, Stream

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideTrack

from freezing.sync.config import config
from freezing.sync.exc import ConfigurationError
from freezing.sync.utils import wktutils

from . import StravaClientForAthlete


class ActivityStreamFetcher:

    def __init__(self, logger:logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def cache_dir(self, athlete_id:int) -> str:
        """
        Gets the cache directory for specific athlete.
        :param athlete_id: The athlete ID.
        :return: The cache directory.
        """
        cache_basedir = config.strava_activity_cache_dir
        if not cache_basedir:
            raise ConfigurationError("STRAVA_ACTIVITY_CACHE_DIR not configured!")

        directory = os.path.join(cache_basedir, str(athlete_id))
        if not os.path.exists(directory):
            os.makedirs(directory)

        return directory

    def cache_stream(self, ride: Ride, activity_data: Dict[str, Any]) -> str:
        """
        Write streams to cache dir.

        :param ride: The Ride model object.
        :param activity_data: The raw JSON for the activity.
        :return: The path where file was written.
        """
        directory = self.cache_dir(ride.athlete_id)

        streams_fname = '{}_streams.json'.format(ride.id)
        cache_path = os.path.join(directory, streams_fname)

        with open(cache_path, 'w') as fp:
            json.dump(fp, activity_data, indent=2)

        return cache_path

    def get_cached_streams_json(self, ride):
        """
        Get the cached streams JSON for specified ride.

        :param ride: The Ride model object.
        :type ride: bafs.model.Ride

        :return: A matched Strava Activity JSON object or None if there was no cache.
        :rtype: dict
        """
        directory = self.cache_dir(ride.athlete_id)

        streams_fname = '{}_streams.json'.format(ride.id)

        cache_path = os.path.join(directory, streams_fname)

        streams_json = None
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as fp:
                streams_json = json.load(fp)

        return streams_json

    def execute(self, athlete_id: int = None, rewrite: bool = False, max_records: int = None,
                use_cache: bool = True, only_cache: bool = False):

        self.session = meta.session_factory()

        q = self.session.query(Ride)

        # We do not fetch streams for private rides.  Or manual rides (since there would be none).
        q = q.filter(and_(Ride.private == False,
                          Ride.manual == False))

        if not rewrite:
            q = q.filter(Ride.track_fetched==False,)

        if athlete_id:
            self.logger.info("Filtering activity details for {}".format(athlete_id))
            q = q.filter(Ride.athlete_id == athlete_id)

        if max_records:
            self.logger.info("Limiting to {} records".format(max_records))
            q = q.limit(max_records)

        use_cache = use_cache or only_cache

        self.logger.info("Fetching gps tracks for {} activities".format(q.count()))

        for ride in q:
            try:
                client = StravaClientForAthlete(ride.athlete)

                streams_json = self.get_cached_streams_json(ride) if use_cache else None

                if streams_json is None:

                    if only_cache:
                        self.logger.info("[CACHE-MISS] Skipping ride {} since there is no cached stream.".format(ride))
                        continue

                    self.logger.info("[CACHE-MISS] Fetching streams for {!r}".format(ride))

                    # We do this manually, so that we can cache the JSON for later use.
                    streams_json = client.protocol.get(
                            '/activities/{id}/streams/{types}'.format(id=ride.id, types='latlng,time,altitude'),
                            resolution='low'
                    )

                    streams = [Stream.deserialize(stream_struct, bind_client=client) for stream_struct in streams_json]

                    try:
                        self.logger.info("Caching streams for {!r}".format(ride))
                        self.cache_stream(ride, streams_json)
                    except:
                        self.logger.error("Error caching streams for activity {} (ignoring)".format(ride),
                                  exc_info=self.logger.isEnabledFor(logging.DEBUG))

                else:
                    streams = [Stream.deserialize(stream_struct, bind_client=client) for stream_struct in streams_json]
                    self.logger.info("[CACHE-HIT] Using cached streams detail for {!r}".format(ride))

                self.write_ride_streams(streams, ride)

                self.session.commit()
            except:
                self.logger.exception("Error fetching/writing activity streams for {}, athlete {}".format(ride, ride.athlete))
                self.session.rollback()

    def write_ride_streams(self, streams:List[Stream], ride: Ride):
        """
        Store GPS track for activity as geometry (linesring) and json types in db.

        :param streams: The Strava streams.
        :param ride: The db model object for ride.
        """
        try:
            streams_dict: Dict[str, Stream] = {s.type: s for s in streams}

            lonlat_points = [(lon,lat) for (lat,lon) in streams_dict['latlng'].data]

            if not lonlat_points:
                raise ValueError("No data points in latlng streams.")

        except (KeyError, ValueError) as x:
            self.logger.info("No GPS track for activity {} (skipping): {}".format(ride, x), exc_info=self.logger.isEnabledFor(logging.DEBUG))
            ride.track_fetched = None
        else:
            # Start by removing any existing segments for the ride.
            meta.engine.execute(RideTrack.__table__.delete().where(RideTrack.ride_id == ride.id))

            gps_track = WKTSpatialElement(wktutils.linestring_wkt(lonlat_points))

            ride_track = RideTrack()
            ride_track.gps_track = gps_track
            ride_track.ride_id = ride.id
            ride_track.elevation_stream = streams_dict['altitude'].data
            ride_track.time_stream = streams_dict['time'].data
            self.session.add(ride_track)

        ride.track_fetched = True
