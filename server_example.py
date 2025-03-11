#!/usr/bin/python3

import asyncio
import websockets
from websocket_handler import WebSocketHandler
import logging
import json
import signal
import argparse

shutdown_event = asyncio.Event()
cmd_args = None

async def auth_callback(message, websocket, logger):
    logger.debug(f'Got auth message: {message}')
    data = json.loads(message)

    if data['token'] == 'abc' and data['signature'] == 'letmein':
        logger.info('auth_callback(): Valid credentials')
        return True

    await websocket.send('Error: Bad credentials')
    logger.info('auth_callback(): Bad credentials')
    return False

async def handle_connection(websocket):
    if cmd_args.auth_mode != 'noauth':
        auth_func = auth_callback
    else:
        auth_func = None

    handler = WebSocketHandler(
        websocket, auth_func,
        shutdown_event = shutdown_event,
        #log_level=logging.DEBUG
    )

    await handler.run()
    #print("handle_connection(): WebSocket is completely closed")

def handle_ctrl_c():
    shutdown_event.set()
    print("\nWebSocket server got CTRL+C")

def parse_argv():
    parser = argparse.ArgumentParser(description="Example WebSocket server.")

    parser.add_argument(
        "auth_mode",
        choices=["auth", "noauth"],
        help="authentication mode (choose 'auth' for authentication or 'noauth' for no authentication)"
    )

    return parser.parse_args()

async def main():
    global cmd_args
    cmd_args = parse_argv()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_ctrl_c)

    async with websockets.serve(handle_connection, "0.0.0.0", 8765) as server:
        print("WebSocket server started")
        await shutdown_event.wait()
        print("WebSocket server shutting down...")

    print("WebSocket server shutdown completed")

if __name__ == "__main__":
    asyncio.run(main())
