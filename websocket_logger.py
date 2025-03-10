import logging

class WebSocketLoggerFactory:
    """A self-contained logger with a custom debug level (DEBUG_MIN)."""

    DEBUG_MIN = 15  # Custom log level between DEBUG (10) and INFO (20)

    def __init__(self, ws_id, log_level):
        self.ws_id = ws_id  # Unique WebSocket ID
        self.logger = logging.getLogger(f"WebSocket-{ws_id}")
        self.logger.setLevel(log_level)

        # Add custom level only to this instance
        self.logger.debug_min = self.debug_min

        # Console handler
        handler = logging.StreamHandler()
        formatter = logging.Formatter(f"%(asctime)s [{self.ws_id}] %(levelname)s: %(message)s")
        handler.setFormatter(formatter)

        if not self.logger.hasHandlers():
            self.logger.addHandler(handler)

    def debug_min(self, message, *args, **kwargs):
        """Custom debug level logging."""
        if self.logger.isEnabledFor(self.DEBUG_MIN):
            self.logger._log(self.DEBUG_MIN, message, args, **kwargs)

    def getLogger(self):
        return self.logger
