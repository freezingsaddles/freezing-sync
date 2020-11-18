import logging
from datetime import timedelta
from decimal import Decimal
from statistics import mean
from pytz import timezone

from sqlalchemy import text

from freezing.model import meta, orm

from freezing.sync.utils.wktutils import parse_point_wkt
from freezing.sync.wx.climacell.api import HistoClimaCell

from freezing.sync.config import config

from freezing.sync.data import BaseSync


class WeatherSync(BaseSync):
    """
    Synchronize rides from data with the database.
    """

    name = "sync-weather"
    description = "Sync all ride weather"

    def sync_weather(
        self, clear: bool = False, limit: int = None, cache_only: bool = False
    ):
        sess = meta.scoped_session()

        if clear:
            self.logger.info("Clearing all weather data!")
            sess.query(orm.RideWeather).delete()

        if limit:
            self.logger.info("Fetching weather for first {0} rides".format(limit))
        else:
            self.logger.info("Fetching weather for all rides")

        # Find rides that have geo, but no weather
        sess.query(orm.RideWeather)
        q = text(
            """
            select R.id from rides R
            join ride_geo G on G.ride_id = R.id
            left join ride_weather W on W.ride_id = R.id
            where W.ride_id is null
            and date(R.start_date) < CURDATE() -- Only include rides from yesterday or before
            and time(R.start_date) != '00:00:00' -- Exclude bad entries.
            ;
            """
        )

        climacell = HistoClimaCell(
            api_key=config.CLIMACELL_API_KEY,
            cache_dir=config.CLIMACELL_CACHE_DIR,
            cache_only=cache_only,
            logger=self.logger,
        )

        rows = meta.engine.execute(q).fetchall()  # @UndefinedVariable
        num_rides = len(rows)

        for i, r in enumerate(rows):

            if limit and i >= limit:
                logging.info("Limit ({0}) reached".format(limit))
                break

            ride = sess.query(orm.Ride).get(r["id"])
            self.logger.info(
                "Processing ride: {0} ({1}/{2})".format(ride.id, i, num_rides)
            )

            try:
                # Because we cache daily data rather than pulling the weather data between
                # ride start and ride end, this just does not even consider handling a ride
                # that starts before and ends after midnight, it will just pull data for the
                # start day and use what data it gets. Doing better would, frankly, be hard
                # because we still want the daily low/high/sunrise/sunset which is then
                # ambiguous.

                start_geo_wkt = meta.scoped_session().scalar(ride.geo.start_geo.wkt)
                point = parse_point_wkt(start_geo_wkt)

                # We round lat/lon to decrease the granularity and allow better re-use of cache data.
                # Gives about an 80% hit rate vs about 20% for 2 decimals.
                lon = round(Decimal(point.lon), 1)
                lat = round(Decimal(point.lat), 1)

                self.logger.debug(
                    "Ride metadata: time={0} dur={1} loc={2}/{3}".format(
                        ride.start_date, ride.elapsed_time, lat, lon
                    )
                )

                ride_start = timezone(ride.timezone).localize(ride.start_date)
                ride_end = ride_start + timedelta(seconds=ride.elapsed_time)

                hist = climacell.histo_forecast(
                    time=ride_start, latitude=lat, longitude=lon
                )

                self.logger.info(
                    f"Start: {ride_start.isoformat()}, End: {ride_end.isoformat()}"
                )
                self.logger.info(
                    f"Sunup: {hist.daily.sunrise_time.isoformat()}, down: {hist.daily.sunset_time.isoformat()}"
                )
                for o in hist.observations:
                    self.logger.info(f"{o.time} - {o.temperature} - {o.precip_rate} - {o.precip_type}")

                # NOTE: if elapsed_time is significantly more than moving_time then we need to assume
                # that the rider wasn't actually riding for this entire time (and maybe just grab temps closest to start of
                # ride as opposed to averaging observations during ride.

                ride_observations = [
                    o for o in hist.observations if ride_start <= o.time <= ride_end
                ]

                start_obs = min(
                    hist.observations,
                    key=lambda o: abs((o.time - ride_start).total_seconds()),
                )
                end_obs = min(
                    hist.observations,
                    key=lambda o: abs((o.time - ride_end).total_seconds())
                )

                if len(ride_observations) <= 2:
                    # if we don't have many observations, bookend the list with the start/end observations without double counting
                    ride_observations = (
                        [start_obs]
                        + [
                            o
                            for o in ride_observations
                            if o is not start_obs and o is not end_obs
                        ]
                        + [end_obs]
                    )

                for x in ride_observations:
                    self.logger.debug("Observation: {0}".format(x.__dict__))

                rw = orm.RideWeather()
                rw.ride_id = ride.id
                rw.ride_temp_start = start_obs.temperature
                rw.ride_temp_end = end_obs.temperature

                rw.ride_temp_avg = mean([o.temperature for o in ride_observations])

                rw.ride_windchill_start = start_obs.apparent_temperature
                rw.ride_windchill_end = end_obs.apparent_temperature
                rw.ride_windchill_avg = mean(
                    [o.apparent_temperature for o in ride_observations]
                )

                # take the average precipitation rate in inches per hour and scale by ride time
                precip_rate = mean([o.precip_rate for o in ride_observations])
                rw.ride_precip = (precip_rate * ride.elapsed_time / 3600)
                rw.ride_rain = any([o.precip_type == "rain" for o in ride_observations])
                rw.ride_snow = any([o.precip_type == "snow" for o in ride_observations])

                rw.day_temp_min = hist.daily.temperature_min
                rw.day_temp_max = hist.daily.temperature_max
                rw.sunrise = hist.daily.sunrise_time.time()
                rw.sunset = hist.daily.sunset_time.time()

                self.logger.debug("Ride weather: {0}".format(rw.__dict__))

                sess.add(rw)
                sess.flush()

            except:
                self.logger.exception(
                    "Error getting weather data for ride: {0}".format(ride)
                )
                sess.rollback()

            else:
                sess.commit()
