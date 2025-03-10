import asyncio
import concurrent.futures
import os
import pty
import signal
import websockets
import selectors
import re
import fcntl, termios, struct
import logging
from websocket_logger import WebSocketLoggerFactory

class WebSocketHandler:
    def __init__(self,
        websocket,
        logger = None,
        log_id = None,
        log_level=logging.INFO, # with the built-in logger, WebSocketLoggerFactory.DEBUG_MIN is also an option
        user_shell_command = None,
        shell_logout_wait = 1,
        shell_terminate_wait = 3
    ):
        self.websocket = websocket
        self.ws_connected = True
        if not logger:
            if not log_id:
                log_id = websocket.id
            self.logger = WebSocketLoggerFactory(log_id, log_level).getLogger()
        else:
            self.logger = logger

        # If a custom `logger` is provided, it may not have `debug_min`.
        # Ensure `debug_min` exists, otherwise alias it to `debug`.
        if not hasattr(self.logger, 'debug_min'):
            self.logger.debug_min = self.logger.debug

        if not user_shell_command:
            self.user_shell_command = ['/bin/bash', '-l'] # login shell
        else:
            self.user_shell_command = user_shell_command

        self.shell_logout_wait = shell_logout_wait # seconds
        self.shell_terminate_wait = shell_terminate_wait # seconds

        self.custom_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

        self.terminate = []

    async def _wait_for_shell_exit(self):
        sent_kills = 0

        while True:
            if self.terminate:
                self.logger.debug_min('wait_for_shell_exit(): This connection is being terminated')
                if sent_kills < self.shell_logout_wait:
                    self.logger.debug_min('wait_for_shell_exit(): Signalling the shell with SIGHUP to logout')
                    try:
                        self.process.send_signal(signal.SIGHUP) # logout # XXX TODO
                    except:
                        self.logger.exception('wait_for_shell_exit(): signal.SIGHUP failed')
                else:
                    self.logger.warning('wait_for_shell_exit(): Signalling the shell with SIGKILL to terminate')
                    try:
                        self.process.send_signal(signal.SIGKILL) # forcefully # XXX TODO
                    except:
                        self.logger.exception('wait_for_shell_exit(): signal.SIGKILL failed')

                if sent_kills > self.shell_terminate_wait:
                    self.logger.error('wait_for_shell_exit(): Shell did not terminate; leaving it alive; hope for the best')
                    break

                sent_kills += 1

            try:
                retcode = await asyncio.wait_for(
                    self.process.wait(),
                    timeout=1
                )
                self.logger.debug_min("wait_for_shell_exit(): Shell process exited; exiting")
                if retcode >= 0:
                    self.terminate.append(f'shell exit code {retcode}')
                else:
                    signal_value = -retcode # number
                    try:
                        signal_value = signal.Signals(signal_value).name
                    except:
                        pass
                    self.terminate.append(f'shell killed by signal {signal_value}')
                break

            except asyncio.TimeoutError:
                self.logger.debug("wait_for_shell_exit(): Shell process still alive check (timeout)")
                continue

    async def wait_for_shell_exit(self):
        try:
            await self._wait_for_shell_exit()
        except:
            self.logger.exception('wait_for_shell_exit(): Unexpected exception')
            self.terminate.append('Unexpected exception')

        self.logger.debug_min("wait_for_shell_exit(): Loop ended")

    async def _read_from_shell(self):
        """Reads output from the PTY and sends it to the WebSocket."""

        loop = asyncio.get_running_loop()
        selector = selectors.DefaultSelector()
        selector.register(self.master_fd, selectors.EVENT_READ)

        while True:
            events = await loop.run_in_executor(self.custom_executor, selector.select, 1)
            if not events:
                if self.terminate:
                    self.logger.debug_min("read_from_shell(): This connection is being terminated; exiting")
                    break
                else:
                    self.logger.debug("read_from_shell(): No data received from shell (timeout)")
                    continue

            output = await loop.run_in_executor(self.custom_executor, os.read, self.master_fd, 1024)
            self.logger.debug("read_from_shell(): read() -> sending to WebSocket")

            try:
                await self.websocket.send(output.decode(
                    encoding='utf-8',errors='replace' # XXX: only UTF-8 is supported
                ))
            except websockets.exceptions.ConnectionClosed:
                _msg = 'WebSocket client disconnected during send()'
                self.logger.debug_min(f'read_from_shell(): {_msg}; exiting')
                if self.ws_connected:
                    self.ws_connected = False
                    self.terminate.append(_msg)
                break

        selector.unregister(self.master_fd)
        selector.close()

    async def read_from_shell(self):
        try:
            await self._read_from_shell()
        except:
            self.logger.exception('read_from_shell(): Unexpected exception')
            self.terminate.append('Unexpected exception')

        self.logger.debug_min("read_from_shell(): Loop ended")

    async def _read_from_websocket_recv(self, timeout):
        try:
            message = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=timeout
            )
        except websockets.exceptions.ConnectionClosed:
            _msg = 'WebSocket client disconnected during recv()'
            self.logger.debug_min(f'read_from_websocket(): {_msg}; exiting')
            if self.ws_connected:
                self.ws_connected = False
                self.terminate.append(_msg)
            return None, True # break
        except asyncio.TimeoutError:
            if self.terminate:
                self.logger.debug_min("read_from_websocket(): This connection is being terminated; exiting")
                return None, True # break
            else:
                self.logger.debug("read_from_websocket(): No data received from websocket (timeout)")
                return None, False # continue
        return message, None

    async def _read_from_websocket(self):
        """Reads user input from WebSocket and sends it to the shell."""

        ESCAPE_SEQ_PATTERN = re.compile(r'^\033\[8;(\d+);(\d+)t$')

        while True:
            message, error = await self._read_from_websocket_recv(1)
            if message is None:
                if error:
                    break
                else:
                    continue

            self.logger.debug("read_from_websocket(): read() -> sending to shell")

            if message.startswith('\033'):
                m = ESCAPE_SEQ_PATTERN.match(message)
                if not m:
                    self.logger.debug("read_from_websocket(): Unknown control sequence; passing it through")
                else:
                    self.logger.debug_min("read_from_websocket(): Terminal resized")
                    rows = int(m.group(1))
                    cols = int(m.group(2))
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
                    #self.process.send_signal(signal.SIGWINCH) # XXX TODO
                    continue # don't send to Bash because it echoes the data back

            os.write(self.master_fd, message.encode(
                encoding='utf-8', errors='strict' # XXX: only UTF-8 is supported
            ))

    async def read_from_websocket(self):
        try:
            await self._read_from_websocket()
        except:
            self.logger.exception('read_from_websocket(): Unexpected exception')
            self.terminate.append('Unexpected exception')

        self.logger.debug_min("read_from_websocket(): Loop ended")

    async def _run_shell_and_pass_data(self):
        self.master_fd, self.slave_fd = pty.openpty()

        try:
            try:
                self.process = await asyncio.create_subprocess_exec(
                    *self.user_shell_command,
                    stdin=self.slave_fd,
                    stdout=self.slave_fd,
                    stderr=self.slave_fd,
                    preexec_fn=os.setsid  # Start a new session
                )
            except:
                self.process = None
                self.logger.exception(f'run(): Unable to start shell')
                await self.websocket.send('Error: Unable to start shell')

            if self.process:
                await asyncio.gather(
                    self.read_from_shell(),
                    self.read_from_websocket(),
                    self.wait_for_shell_exit()
                )
        finally:
            try:
                os.close(self.master_fd)
                os.close(self.slave_fd)
                self.logger.debug_min("run(): PTY closed")
            except:
                self.logger.exception("run(): PTY close failed")

            try:
                self.custom_executor.shutdown(wait=True)
                self.logger.debug_min("run(): custom_executor shut down")
            except:
                self.logger.exception("run(): custom_executor shutdown failed")

    async def run(self):
        if self.logger.getEffectiveLevel() < logging.INFO: # we are in DEBUG
            log_prefix = 'run(): '
        else:
            log_prefix = ''

        self.logger.info(f'{log_prefix}New WebSocket connection')

        await self._run_shell_and_pass_data()

        self.logger.info(f'{log_prefix}Closing the WebSocket connection: ' + '; '.join(self.terminate))
