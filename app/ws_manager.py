from typing import List
from fastapi import WebSocket

class ConnectionManager:
    """គ្រប់គ្រងការតភ្ជាប់ WebSocket ទាំងអស់"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """ផ្ញើសារទៅកាន់អតិថិជនដែលកំពុងភ្ជាប់ទាំងអស់"""
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)

manager = ConnectionManager()

async def broadcast_products_changed():
    """ប្រកាសទៅគ្រប់ Client ថាផលិតផលបានផ្លាស់ប្តូរ (បង្កើត/កែ/លុប)"""
    await manager.broadcast({"type": "products_changed", "message": "Products have been updated"})

async def broadcast_alerts_changed():
    """ប្រកាសទៅគ្រប់ Client ថា Alert / Popup បានផ្លាស់ប្តូរ (បង្កើត/កែ/លុប)"""
    await manager.broadcast({"type": "alerts_changed", "message": "Alerts have been updated"})
