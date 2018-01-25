class InvalidAuthorizationToken(RuntimeError):
    pass


class ConfigurationError(RuntimeError):
    pass


class CommandError(RuntimeError):
    pass


class DataEntryError(ValueError):
    pass

