import logging
from datetime import timedelta
from decimal import Decimal
from statistics import mean
from pytz import timezone, utc

from sqlalchemy import text

from freezing.model import meta, orm

from freezing.sync.utils.wktutils import parse_point_wkt
from freezing.sync.wx.openweathermap.api import HistoOpenWeatherMap

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

        owm = HistoOpenWeatherMap(
            api_key=config.OPENWEATHERMAP_API_KEY,
            cache_dir=config.OPENWEATHERMAP_CACHE_DIR,
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

                hist = owm.histo_forecast(
                    time=ride_start, latitude=lat, longitude=lon
                )
                observations = hist.observations

                # OpenWeatherMap gives data in 24-hour blocks measured in UTC, so
                # a late evening ride may well span two "days" of weather data.

                # There's no great solution to this, so we take daily information
                # from the UTC day of the start of the ride and optionally pull additional
                # hourly information from the UTC day of the end of the ride.

                if ride_end.astimezone(utc).day > ride_start.astimezone(utc).day:
                    self.logger.debug("Fetching second date because of UTC overflow")
                    hist2 = owm.histo_forecast(
                        time=ride_end, latitude=lat, longitude=lon
                    )
                    observations = observations + hist2.observations

                ride_observations = [
                    o for o in observations if ride_start <= o.time <= ride_end
                ]

                start_obs = min(
                    observations,
                    key=lambda o: abs((o.time - ride_start).total_seconds()),
                )
                end_obs = min(
                    observations,
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
                precip_rate = mean([(o.rain + o.snow) for o in ride_observations])
                rw.ride_precip = (precip_rate * ride.elapsed_time / 3600)
                rw.ride_rain = any([o.rain > 0 for o in ride_observations])
                rw.ride_snow = any([o.snow > 0 for o in ride_observations])

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
