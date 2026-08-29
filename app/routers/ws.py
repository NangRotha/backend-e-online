from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..ws_manager import manager

router = APIRouter(tags=["WebSocket"])

@router.websocket("/ws/products")
async def websocket_products(websocket: WebSocket):
    """Client (frontend-user) ភ្ជាប់មកទីនេះ ដើម្បីទទួលការជូនដំណឹងពេល Admin កែផលិតផល"""
    await manager.connect(websocket)
    try:
        while True:
            # រង់ចាំ ping / keep-alive ពី client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
