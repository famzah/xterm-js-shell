#!/usr/bin/python3

import asyncio
import websockets
from websocket_handler import WebSocketHandler
import logging
import json

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
        #log_level=logging.DEBUG
    )

    await handler.run()

async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 8765) as server:
        print("WebSocket server started")
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
