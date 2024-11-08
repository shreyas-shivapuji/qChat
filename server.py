import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sqlite3
import uuid
import uvicorn

app = FastAPI()

# Database Setup
def init_db():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_id TEXT,
            sender_id TEXT,
            message TEXT,
            delivered BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Models for registration and login
class User(BaseModel):
    username: str
    password: str

# Route for user registration
@app.post("/register/")
async def register(user: User):
    try:
        conn = sqlite3.connect("chat.db")
        cursor = conn.cursor()
        user_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO users (id, username, password) VALUES (?, ?, ?)", (user_id, user.username, user.password))
        conn.commit()
        conn.close()
        return {"status": "success", "user_id": user_id}
    except sqlite3.IntegrityError:
        return {"status": "error", "detail": "Username already taken"}

# Route for user login
@app.post("/login/")
async def login(user: User):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (user.username, user.password))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"status": "success", "user_id": result[0]}
    else:
        return {"status": "error", "detail": "Invalid credentials"}

# WebSocket connections handling
connected_clients = {}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connected_clients[user_id] = websocket
    # Deliver undelivered messages upon connection
    await deliver_undelivered_messages(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            await handle_message(data, user_id)
    except WebSocketDisconnect:
        del connected_clients[user_id]
    except Exception as e:
        print(f"Error handling WebSocket message: {e}")
        if user_id in connected_clients:
            del connected_clients[user_id]

# Handling received messages with username lookup
async def handle_message(data, sender_id):
    message_data = json.loads(data)
    recipient_username = message_data["recipient_username"]
    message = message_data["message"]

    # Lookup the recipient's user_id based on the username
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (recipient_username,))
    recipient = cursor.fetchone()
    
    if recipient:
        recipient_id = recipient[0]
        if recipient_id in connected_clients:
            # Send directly to recipient if online
            await connected_clients[recipient_id].send_text(json.dumps({"sender_id": sender_id, "message": message}))
        else:
            # Store in database for later delivery
            cursor.execute("INSERT INTO messages (recipient_id, sender_id, message) VALUES (?, ?, ?)", (recipient_id, sender_id, message))
            conn.commit()
    else:
        print(f"Recipient username {recipient_username} not found.")
    
    conn.close()

# Check for undelivered messages for a user
async def deliver_undelivered_messages(websocket, user_id):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sender_id, message FROM messages WHERE recipient_id = ? AND delivered = 0", (user_id,))
    undelivered_messages = cursor.fetchall()
    for sender_id, message in undelivered_messages:
        await websocket.send_text(json.dumps({"sender_id": sender_id, "message": message}))
        cursor.execute("UPDATE messages SET delivered = 1 WHERE recipient_id = ? AND sender_id = ? AND message = ?", (user_id, sender_id, message))
    conn.commit()
    conn.close()

# Starting the server with uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
