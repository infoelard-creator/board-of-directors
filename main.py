from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow requests from frontend (browser)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for demo; later you can restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

class AgentReply(BaseModel):
    agent: str
    text: str

@app.post("/api/board", response_model=list[AgentReply])
async def board_chat(req: ChatRequest):
    user_msg = req.message

    replies = [
        {"agent": "ceo", "text": f"CEO: strategic view on: {user_msg}"},
        {"agent": "cfo", "text": f"CFO: financial assessment of the idea: {user_msg}"},
        {"agent": "cpo", "text": f"CPO: product and UX perspective on: {user_msg}"},
        {"agent": "marketing", "text": f"Marketing: how to position and sell: {user_msg}"},
        {"agent": "skeptic", "text": f"Skeptic: what can go wrong with: {user_msg}"},
    ]
    return replies

