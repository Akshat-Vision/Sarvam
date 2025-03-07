from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import httpx  # Asynchronous HTTP client
import os
import logging
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter  # Rate limiting
from slowapi.util import get_remote_address  # Get client IP for rate limiting
from slowapi.errors import RateLimitExceeded  # Rate limit exceeded error

# Load environment variables
load_dotenv()

# Load Together AI API key from environment variable
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
if not TOGETHER_API_KEY:
    raise ValueError("Missing TOGETHER_API_KEY environment variable!")

# Initialize FastAPI app
app = FastAPI()

# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Replace with frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)  # Use client IP for rate limiting
app.state.limiter = limiter

# Define request body model
class ChatRequest(BaseModel):
    user_input: str

# Rate limit exceeded error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return HTTPException(status_code=429, detail="Too many requests. Please try again later.")

async def query_together_ai(prompt: str) -> str:
    """
    Sends user input to Together AI and fetches the chatbot's response asynchronously.
    """
    url = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "meta-llama/Llama-2-7b-chat-hf",  # Free model
        "messages": [{"role": "user", "content": prompt}]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)

            json_response = response.json()
            
            # Extract chatbot response safely
            chatbot_reply = (
                json_response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "No response received.")
            )

            logger.info(f"User: {prompt} | Chatbot: {chatbot_reply}")
            return chatbot_reply

        except httpx.RequestError as e:
            logger.error(f"Error calling Together AI API: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch response from Together AI.")

@app.get("/")
async def home():
    return {"message": "Chatbot API is running!"}

@app.post("/chat/")
@limiter.limit("5/minute")  # Allow 5 requests per minute per client
async def chat(request: Request, chat_request: ChatRequest):
    chatbot_reply = await query_together_ai(chat_request.user_input)
    return {"response": chatbot_reply}