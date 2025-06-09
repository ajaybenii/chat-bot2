from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import httpx
from starlette.responses import Response
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
client = AsyncIOMotorClient(mongo_uri)
db = client["squareyards"]
collection = db["property_listings"]
chat_history_collection = db["chat_history"]  # New collection for chat history

# Initialize Gemini client
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './sqy-prod.json'
gemini_client = genai.Client(
    http_options=types.HttpOptions(api_version="v1beta1"),
    vertexai=True,
    project='sqy-prod',
    location='us-central1'
)

gemini_tools = [types.Tool(google_search=types.GoogleSearch())]

# Pydantic models
class PropertyData(BaseModel):
    userType: str
    listingType: str
    city: str
    name: str
    number: str

class OtpRequest(BaseModel):
    countryCode: str
    mobile: str

class OtpVerify(BaseModel):
    countryCode: str
    mobile: str
    otp: str

class ChatRequest(BaseModel):
    message: str
    city: str | None = None
    user_id: str | None = None  # Add user_id to track individual users

# Helper function to get or create user ID based on phone number
async def get_user_id(request: Request) -> str:
    # For simplicity, use phone number from session or form data; in production, use a secure session ID
    phone_number = request.headers.get("X-User-Phone", None) or "anonymous"  # Example: Fetch from header or default
    if not phone_number:
        raise HTTPException(status_code=400, detail="User ID or phone number required")
    return phone_number

# Update chat history
async def update_chat_history(user_id: str, message: str):
    # Fetch existing history
    history = await chat_history_collection.find_one({"user_id": user_id})
    if history:
        questions = history.get("questions", [])
        questions.append({"question": message, "timestamp": datetime.utcnow().isoformat()})
        if len(questions) > 10:
            questions = questions[-10:]  # Keep only last 10
        await chat_history_collection.update_one({"user_id": user_id}, {"$set": {"questions": questions}})
    else:
        await chat_history_collection.insert_one({"user_id": user_id, "questions": [{"question": message, "timestamp": datetime.utcnow().isoformat()}]})

# Get chat history
async def get_chat_history(user_id: str) -> list:
    history = await chat_history_collection.find_one({"user_id": user_id})
    return history.get("questions", []) if history else []

# Gemini chat endpoint
@app.post("/api/chat")
async def chat_with_gemini(request: ChatRequest, req: Request):
    try:
        user_id = await get_user_id(req)  # Get or generate user ID
        await update_chat_history(user_id, request.message)  # Store the new question

        # Construct the prompt with real-estate context and history
        base_prompt = (
            "You are a professional real-estate AI chatbot for SquareYards. "
            "Provide accurate, concise, and helpful responses to user queries about properties, real estate markets, or related topics. "
            "If a city is provided, tailor the response to that city ({city}). "
            "Use data from Google Search tools to ensure accuracy and relevance. "
            "If user ask with different city, then give answer according to your knowledge. "
            "You are a smart AI chatbot of SquareYards. If the query is unrelated to real estate, politely redirect to real-estate topics. "
            "Only give answers related to real estate, do not respond to unrelated questions. "
            "Give me response in well-formatted HTML that works for both day and night modes of the chat-bot UI. "
            "Response length should be concise like a chatbot. "
            "Directly give the response without explanations. "
            "You are only trained for real-estate query, Only give answer realted to real-estate dont give answera of unrealted question of real-estate"
            "if someone ask beyond the square yards , then dont give answer"

            "Include the following user context: {history}"
        )

        # Get the last 10 questions
        history = await get_chat_history(user_id)
        history_text = "\n".join([f"Previous Question: {q['question']}" for q in history]) or "No previous questions."

        # Format prompt with city and history
        full_prompt = base_prompt.format(city=request.city if request.city else "", history=history_text)
        user_message = request.message

        # Generate response using Gemini
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=f"{full_prompt}\n\nUser Query: {user_message}",
            config=types.GenerateContentConfig(
                tools=gemini_tools,
                max_output_tokens=8192,
                system_instruction=full_prompt,
                temperature=0.7,
            )
        )

        content = response.text.replace("```html", "").replace("```", "")
        return {"status": "success", "response": content}

    except Exception as e:
        print(f"Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {str(e)}")

# Existing endpoints remain unchanged
@app.options("/api/otp/send")
async def options_otp_send():
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": "http://127.0.0.1:5500",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/api/otp/send")
async def proxy_send_otp(request: OtpRequest):
    try:
        print(f"OTP Send Input: {request.dict()}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://apigee.squareyards.com/api/otp/send",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
        print(f"OTP Send Output: Status={response.status_code}, Response={response.text}")
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return JSONResponse(content=response.json(), status_code=response.status_code)
        else:
            return JSONResponse(
                content={"message": response.text or "Success"},
                status_code=response.status_code
            )
    except httpx.RequestError as e:
        print(f"OTP Send Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")

@app.options("/api/otp/verify")
async def options_otp_verify():
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": "http://127.0.0.1:5500",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/api/otp/verify")
async def proxy_verify_otp(request: OtpVerify):
    try:
        print(f"OTP Verify Input: {request.dict()}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://apigee.squareyards.com/api/otp/verify",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
        print(f"OTP Verify Output: Status={response.status_code}, Response={response.text}")
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return JSONResponse(content=response.json(), status_code=response.status_code)
        else:
            return JSONResponse(
                content={"message": response.text or "Verification success"},
                status_code=response.status_code
            )
    except httpx.HTTPStatusError as e:
        print(f"OTP Verify HTTP Error: Status={e.response.status_code}, Response={e.response.text}")
        try:
            return JSONResponse(status_code=e.response.status_code, content=e.response.json())
        except Exception:
            return JSONResponse(status_code=e.response.status_code, content={"detail": e.response.text})
    except httpx.RequestError as e:
        print(f"OTP Verify Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error verifying OTP: {str(e)}")

@app.post("/submit")
async def submit(data: PropertyData):
    try:
        data_dict = data.dict()
        data_dict["created_at"] = datetime.utcnow().isoformat()
        await collection.insert_one(data_dict)
        print(f"Submit Data: {data_dict}")
        return {"status": "success", "message": "Data submitted successfully"}
    except Exception as e:
        print(f"Submit Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pingdb")
async def ping_db():
    try:
        await db.command("ping")
        print("MongoDB ping successful")
        return {"message": "MongoDB connection is working ✅"}
    except Exception as e:
        print(f"DB ping failed: {str(e)}")
        return {"message": f"DB ping failed: {str(e)}"}