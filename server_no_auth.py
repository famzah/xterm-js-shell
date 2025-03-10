#!/usr/bin/python3

import asyncio
import websockets
from websocket_handler import WebSocketHandler

async def handle_connection(websocket):
    handler = WebSocketHandler(websocket)
    await handler.run()
    #print("handle_connection(): WebSocket is completely closed")

async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 8765) as server:
        print("WebSocket server started")
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
