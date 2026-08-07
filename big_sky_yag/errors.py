class BigSkyYagError(RuntimeError):
    """Base exception for device communication and operation failures."""


class BigSkyYagTransportError(BigSkyYagError):
    """The serial transport did not provide a complete usable response."""


class BigSkyYagProtocolError(BigSkyYagError):
    """The controller returned a response that does not match its protocol."""


class BigSkyYagTransitionError(BigSkyYagError):
    """The laser did not reach a requested operational state."""
