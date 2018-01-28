import os
import threading
import enum
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from greenstalk import Client, TimedOutError

from freezing.model.msg.mq import DefinedTubes

from freezing.sync.config import config, init
from freezing.sync.autolog import log



def tick():
    print('Tick! The time is: %s' % datetime.now())


def main():
    init()

    shutdown_event = threading.Event()

    scheduler = BackgroundScheduler()
    scheduler.add_job(tick, 'interval', seconds=3)
    scheduler.start()

    beanclient = Client(host=config.BEANSTALKD_HOST, port=config.BEANSTALKD_PORT,
                        watch=[DefinedTubes.activity_update.value])

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while not shutdown_event.is_set():
            try:
                message = beanclient.reserve(timeout=30)
                log.info("Received message: {!r}".format(message))
            except TimedOutError:
                log.debug("Internal beanstalkdc connection timeout; reconnecting.")
                pass
    except (KeyboardInterrupt, SystemExit):
        log.info("Exiting on user request.")
    except:
        log.exception("Error running sync/listener.")
    finally:
        scheduler.shutdown()


if __name__ == '__main__':
    main()