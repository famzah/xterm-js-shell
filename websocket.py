#!/usr/bin/python3

import asyncio
import concurrent.futures
import os
import pty
import signal
import websockets
import selectors
import re
import fcntl, termios, struct

class WebSocketHandler:
    def __init__(self, websocket, user_shell_command = None, shell_logout_wait = 1, shell_terminate_wait = 3):
        self.websocket = websocket

        if not user_shell_command:
            self.user_shell_command = ['/bin/bash', '-l'] # login shell
        else:
            self.user_shell_command = user_shell_command

        self.shell_logout_wait = shell_logout_wait # seconds
        self.shell_terminate_wait = shell_terminate_wait # seconds

        self.custom_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

        self.terminate = False

    async def wait_for_shell_exit(self):
        sent_kills = 0

        while True:
            if self.terminate:
                print('wait_for_shell_exit(): This connection is being terminated')
                if sent_kills < self.shell_logout_wait:
                    print('wait_for_shell_exit(): Signalling the shell with SIGHUP to logout')
                    self.process.send_signal(signal.SIGHUP) # logout # XXX TODO
                else:
                    print('wait_for_shell_exit(): Signalling the shell with SIGKILL to terminate')
                    self.process.send_signal(signal.SIGKILL) # forcefully # XXX TODO

                if sent_kills > self.shell_terminate_wait:
                    print('wait_for_shell_exit(): Shell did not terminate; leaving it alive; hope for the best')
                    break

                sent_kills += 1

            try:
                await asyncio.wait_for(
                    self.process.wait(),
                    timeout=1
                )
                print("wait_for_shell_exit(): Shell process exited; exiting")
                self.terminate = True
                break

            except asyncio.TimeoutError:
                print("wait_for_shell_exit(): Shell process still alive check (timeout)")
                continue

        print("wait_for_shell_exit(): Loop ended")

    async def read_from_shell(self):
        """Reads output from the PTY and sends it to the WebSocket."""

        loop = asyncio.get_running_loop()
        selector = selectors.DefaultSelector()
        selector.register(self.master_fd, selectors.EVENT_READ)

        while True:
            events = await loop.run_in_executor(self.custom_executor, selector.select, 1)
            if not events:
                if self.terminate:
                    print("read_from_shell(): This connection is being terminated; exiting")
                    break
                else:
                    print("read_from_shell(): No data received from shell (timeout)")
                    continue

            output = await loop.run_in_executor(self.custom_executor, os.read, self.master_fd, 1024)
            print("read_from_shell(): read() -> sending to WebSocket")

            try:
                await self.websocket.send(output.decode(
                    encoding='utf-8',errors='replace' # XXX: only UTF-8 is supported
                ))
            except websockets.exceptions.ConnectionClosed:
                print("read_from_shell(): WebSocket client disconnected during send(); exiting")
                self.terminate = True
                break

        selector.unregister(self.master_fd)
        selector.close()

        print("read_from_shell(): Loop ended")

    async def read_from_websocket(self):
        """Reads user input from WebSocket and sends it to the shell."""

        ESCAPE_SEQ_PATTERN = re.compile(r'^\033\[8;(\d+);(\d+)t$')

        while True:
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=1
                )
            except websockets.exceptions.ConnectionClosed:
                print("read_from_websocket(): WebSocket client disconnected during recv(); exiting")
                self.terminate = True
                break
            except asyncio.TimeoutError:
                if self.terminate:
                    print("read_from_websocket(): This connection is being terminated; exiting")
                    break
                else:
                    print("read_from_websocket(): No data received from websocket (timeout)")
                    continue

            print("read_from_websocket(): read() -> sending to shell")

            if message.startswith('\033'):
                m = ESCAPE_SEQ_PATTERN.match(message)
                if not m:
                    print("read_from_websocket(): Unknown control sequence; passing it through")
                else:
                    print("read_from_websocket(): Terminal resized")
                    rows = int(m.group(1))
                    cols = int(m.group(2))
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
                    #self.process.send_signal(signal.SIGWINCH) # XXX TODO
                    continue # don't send to Bash because it echoes the data back

            os.write(self.master_fd, message.encode(
                encoding='utf-8', errors='strict' # XXX: only UTF-8 is supported
            ))

        print("read_from_websocket(): Loop ended")

    async def run(self):
        print("run(): New WebSocket connection")

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
                await self.websocket.send('Unable to start shell')
                raise

            await asyncio.gather(
                self.read_from_shell(),
                self.read_from_websocket(),
                self.wait_for_shell_exit()
            )
        finally:
            os.close(self.master_fd)
            print("run(): WebConnection is completely closed")
            self.custom_executor.shutdown(wait=True)
            print("run(): custom_executor shut down")


async def handle_connection(websocket):
    handler = WebSocketHandler(websocket)
    await handler.run()

async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 8765) as server:
        print("WebSocket server started")
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
