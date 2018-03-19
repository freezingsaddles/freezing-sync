import os
import threading
import enum
from functools import partial
from datetime import datetime

import arrow
from apscheduler.schedulers.background import BackgroundScheduler
from greenstalk import Client, TimedOutError

from freezing.model import init_model
from freezing.model.msg.mq import DefinedTubes

from freezing.sync.config import config, init_logging, statsd
from freezing.sync.autolog import log
# from freezing.sync.workflow import configured_publisher
from freezing.sync.subscribe import ActivityUpdateSubscriber
from freezing.sync.data.activity import ActivitySync
from freezing.sync.data.weather import WeatherSync
from freezing.sync.data.athlete import AthleteSync


def main():

    init_logging()
    init_model(config.SQLALCHEMY_URL)

    shutdown_event = threading.Event()

    scheduler = BackgroundScheduler()

    # workflow_publisher = configured_publisher()

    activity_sync = ActivitySync()
    weather_sync = WeatherSync()
    athlete_sync = AthleteSync()

    # Every hour run a sync on the activities for athletes fall into the specified segment
    # athlete_id % total_segments == segment
    # TODO: Probably it would be more prudent to split into 15-minute segments, to match rate limits
    # Admittedly that will make the time-based segment calculation a little trickier.
    def segmented_sync_activities():
        activity_sync.sync_rides_distributed(total_segments=24, segment=arrow.now().hour)

    scheduler.add_job(segmented_sync_activities, 'cron', minute='50')

    # This should generally not pick up anytihng.
    scheduler.add_job(activity_sync.sync_rides_detail, 'cron', minute='20')

    # Sync weather at 8am UTC
    scheduler.add_job(weather_sync.sync_weather, 'cron', hour='8')

    # Sync athletes once a day at 6am UTC
    scheduler.add_job(athlete_sync.sync_athletes, 'cron', minute='30')

    scheduler.start()

    beanclient = Client(host=config.BEANSTALKD_HOST, port=config.BEANSTALKD_PORT,
                        watch=[DefinedTubes.activity_update.value])

    subscriber = ActivityUpdateSubscriber(beanstalk_client=beanclient, shutdown_event=shutdown_event)

    def shutdown_app():
        shutdown_event.wait()
        scheduler.shutdown()

    shutdown_monitor = threading.Thread(target=shutdown_app)
    shutdown_monitor.start()

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        subscriber.run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Exiting on user request.")
    except:
        log.exception("Error running sync/listener.")
    finally:
        shutdown_event.set()
        shutdown_monitor.join()


if __name__ == '__main__':
    main()
