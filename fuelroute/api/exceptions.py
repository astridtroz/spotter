class InputError(Exception):
    """Bad input from the caller, becomes a 400."""


class RoutingError(Exception):
    """Couldn't produce a route or a fuel plan, becomes a 422 (or 502 if an outside service is down)."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status
