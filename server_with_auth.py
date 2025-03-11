#!/usr/bin/python3

import asyncio
import websockets
from websocket_handler import WebSocketHandler
import logging
import json
import signal

shutdown_event = asyncio.Event()

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
    handler = WebSocketHandler(
        websocket, auth_callback,
        shutdown_event = shutdown_event,
        #log_level=logging.DEBUG
    )

    await handler.run()

def handle_ctrl_c():
    shutdown_event.set()
    print("\nWebSocket server got CTRL+C")

async def main():
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_ctrl_c)

    async with websockets.serve(handle_connection, "0.0.0.0", 8765) as server:
        print("WebSocket server started")
        await shutdown_event.wait()
        print("WebSocket server shutting down...")

    print("WebSocket server shutdown completed")

if __name__ == "__main__":
    asyncio.run(main())
