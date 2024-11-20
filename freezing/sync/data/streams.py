import json
import logging
import os
from typing import Any, Dict, List

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideTrack
from geoalchemy import WKTSpatialElement
from polyline.codec import PolylineCodec
from sqlalchemy import and_, or_, update
from sqlalchemy.orm import joinedload
from stravalib.exc import ObjectNotFound
from stravalib.model import Activity, Stream

from freezing.sync.config import config
from freezing.sync.exc import ActivityNotFound, ConfigurationError
from freezing.sync.utils import wktutils
from freezing.sync.utils.cache import CachingStreamFetcher

from . import BaseSync, StravaClientForAthlete


class StreamSync(BaseSync):
    name = "sync-activity-streams"
    description = "Sync activity streams (GPS, etc.) JSON."

    def sync_streams(
        self,
        athlete_id: int = None,
        rewrite: bool = False,
        max_records: int = None,
        use_cache: bool = True,
        only_cache: bool = False,
    ):
        session = meta.scoped_session()

        q = session.query(Ride).options(joinedload(Ride.athlete))

        # We do not fetch streams for private rides.  Or manual rides (since there would be none).
        q = q.filter(and_(Ride.private == False, Ride.manual == False))

        if not rewrite:
            q = q.filter(
                Ride.track_fetched == False,
            )

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
                sf = CachingStreamFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )
                streams = sf.fetch(
                    athlete_id=ride.athlete_id,
                    object_id=ride.id,
                    use_cache=use_cache,
                    only_cache=only_cache,
                )
                if streams:
                    self.write_ride_streams(streams, ride)
                    session.commit()
                else:
                    self.logger.debug("No streams for {!r} (skipping)".format(ride))
            except:
                self.logger.exception(
                    "Error fetching/writing activity streams for "
                    "{}, athlete {}".format(ride, ride.athlete),
                    exc_info=True,
                )
                session.rollback()

    def fetch_and_store_activity_streams(
        self, *, athlete_id: int, activity_id: int, use_cache: bool = False
    ):
        with meta.transaction_context() as session:
            self.logger.info(
                "Fetching activity streams for athlete_id={}, activity_id={}".format(
                    athlete_id, activity_id
                )
            )

            ride = (
                session.query(Ride).options(joinedload(Ride.athlete)).get(activity_id)
            )
            if not ride:
                raise RuntimeError("Cannot load streams before fetching activity.")

            try:
                client = StravaClientForAthlete(ride.athlete)
                sf = CachingStreamFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )
                streams = sf.fetch(
                    athlete_id=athlete_id,
                    object_id=activity_id,
                    use_cache=use_cache,
                    only_cache=False,
                )
                if streams:
                    self.write_ride_streams(streams, ride)
                    session.commit()
                else:
                    self.logger.debug("No streams for {!r} (skipping)".format(ride))
            except ObjectNotFound:
                raise ActivityNotFound(
                    "Streams not found for {}, athlete {}".format(ride, ride.athlete)
                )
            except:
                self.logger.exception(
                    "Error fetching/writing activity streams for "
                    "{}, athlete {}".format(ride, ride.athlete),
                    exc_info=True,
                )
                raise

    def write_ride_streams(self, streams: List[Stream], ride: Ride):
        """
        Store GPS track for activity as geometry (linesring) and json types in db.

        :param streams: The Strava streams.
        :param ride: The db model object for ride.
        """
        session = meta.scoped_session()
        try:
            streams_dict: Dict[str, Stream] = {s.type: s for s in streams}

            lonlat_points = [(lon, lat) for (lat, lon) in streams_dict["latlng"].data]

            if not lonlat_points:
                raise ValueError("No data points in latlng streams.")

        except (KeyError, ValueError) as x:
            self.logger.info(
                "No GPS track for activity {} (skipping): {}".format(ride, x),
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )
            ride.track_fetched = None
        else:
            # Start by removing any existing segments for the ride.
            meta.engine.execute(
                RideTrack.__table__.delete().where(RideTrack.ride_id == ride.id)
            )

            gps_track = WKTSpatialElement(wktutils.linestring_wkt(lonlat_points))

            ride_track = RideTrack()
            ride_track.gps_track = gps_track
            ride_track.ride_id = ride.id
            ride_track.elevation_stream = streams_dict["altitude"].data
            ride_track.time_stream = streams_dict["time"].data
            session.add(ride_track)

        ride.track_fetched = True
