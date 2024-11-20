import abc
import argparse
import logging

from colorlog import ColoredFormatter
from freezing.model import init_model

from freezing.sync.config import config, init_logging
from freezing.sync.exc import CommandError


class BaseCommand(metaclass=abc.ABCMeta):
    logger: logging.Logger = None

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """
        :return: The short name for the command.
        """

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """
        :return: The description for this command
        """

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=self.description)

        log_g = parser.add_mutually_exclusive_group()

        log_g.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Whether to log at debug level.",
        )

        log_g.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Whether to suppress non-error log output.",
        )

        parser.add_argument(
            "--color",
            action="store_true",
            default=False,
            help="Whether to output logs with color.",
        )

        return parser

    def parse(self, args=None):
        parser = self.build_parser()
        return parser.parse_args(args)

    def init_logging(self, options):
        """
        Initialize the logging subsystem and create a logger for this class, using passed in optparse options.

        :param options: Optparse options.
        :return:
        """
        if options.quiet:
            loglevel = logging.ERROR
        elif options.debug:
            loglevel = logging.DEBUG
        else:
            loglevel = logging.INFO

        init_logging(loglevel=loglevel, color=options.color)

        self.logger = logging.getLogger(self.name)

    def run(self, argv=None):
        parser = self.build_parser()
        assert (
            parser is not None
        ), "{}.build_parser() method did not return a parser object.".format(
            self.__class__.__name__
        )

        args = parser.parse_args(argv)

        self.init_logging(args)
        init_model(sqlalchemy_url=config.SQLALCHEMY_URL)

        try:
            self.execute(args)
        except CommandError as ce:
            parser.error(str(ce))
            raise SystemExit(127)

    @abc.abstractmethod
    def execute(self, args):
        """
        Perform actual implementation for this command.

        :param args: The parsed options/args from argparse.
        """
