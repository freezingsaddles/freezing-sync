import logging
import threading

import greenstalk
from freezing.model import meta
from freezing.model.msg.mq import ActivityUpdate, ActivityUpdateSchema
from freezing.model.msg.strava import AspectType
from freezing.model.orm import Athlete
from time import sleep

from freezing.sync.autolog import log
from freezing.sync.config import Config, statsd
from freezing.sync.data.activity import ActivitySync
from freezing.sync.data.streams import StreamSync
from freezing.sync.exc import ActivityNotFound, IneligibleActivity


class ActivityUpdateSubscriber:
    def __init__(
        self, beanstalk_client: greenstalk.Client, shutdown_event: threading.Event
    ):
        self.client = beanstalk_client
        self.shutdown_event = shutdown_event
        self.logger = logging.getLogger(__name__)
        self.activity_sync = ActivitySync(self.logger)
        self.streams_sync = StreamSync(self.logger)

        """Delay between requests to Strava API to avoid rate limiting."""
        self._THROTTLE_DELAY = 3.0

    def handle_message(self, message: ActivityUpdate):
        self.logger.info("Processing activity update {}".format(message))

        with meta.transaction_context() as session:
            athlete: Athlete = session.query(Athlete).get(message.athlete_id)
            if not athlete:
                self.logger.warning(
                    "Athlete {} not found in database, "
                    "ignoring activity update message {}".format(
                        message.athlete_id, message
                    )
                )
                return  # Makes the else a little unnecessary, but reads easier.
            try:
                if message.operation is AspectType.delete:
                    statsd.increment(
                        "strava.activity.delete",
                        tags=["team:{}".format(athlete.team_id)],
                    )
                    self.activity_sync.delete_activity(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )

                elif message.operation is AspectType.update:
                    statsd.increment(
                        "strava.activity.update",
                        tags=["team:{}".format(athlete.team_id)],
                    )
                    self.activity_sync.fetch_and_store_activity_detail(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
                    # (We'll assume the stream doens't need re-fetching.)

                elif message.operation is AspectType.create:
                    statsd.increment(
                        "strava.activity.create",
                        tags=["team:{}".format(athlete.team_id)],
                    )
                    self.activity_sync.fetch_and_store_activity_detail(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
                    self.streams_sync.fetch_and_store_activity_streams(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
            except (ActivityNotFound, IneligibleActivity) as x:
                log.info(str(x))

    def run_forever(self):
        # This is expecting to run in the main thread. Needs a bit of redesign
        # if this is to be moved to a background thread.
        try:
            schema = ActivityUpdateSchema()

            while not self.shutdown_event.is_set():
                try:
                    job = self.client.reserve(timeout=30)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except greenstalk.TimedOutError:
                    self.logger.debug(
                        "Internal beanstalkd connection timeout; reconnecting."
                    )
                    continue
                else:
                    try:
                        self.logger.info("Received message: {!r}".format(job.body))
                        update = schema.loads(job.body)
                        self.handle_message(update)
                    except Exception:
                        msg = "Error processing message, will requeue w/ delay of {} seconds."
                        self.logger.exception(msg.format(Config.REQUEUE_DELAY))
                        statsd.increment("strava.webhook.error")
                        self.client.release(
                            job, delay=Config.REQUEUE_DELAY
                        )  # We put it back with a delay
                    else:
                        self.client.delete(job)
                        # FIXME: Work around stravalib 1.2's incomplete understanding of Strava Rate limits by just sleeping for a bit between requests.
                        sleep(self._THROTTLE_DELAY)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.logger.exception("Unhandled error in tube subscriber loop, exiting.")
            self.shutdown_event.set()
            raise
