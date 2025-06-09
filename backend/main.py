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
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://chat-bot2-xy11.onrender.com"  # Added frontend domain
    ],
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
    phone_number = request.headers.get("X-User-Phone", None) or "anonymous"
    if not phone_number:
        raise HTTPException(status_code=400, detail="User ID or phone number required")
    return phone_number

# Update chat history
async def update_chat_history(user_id: str, message: str):
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
        user_id = await get_user_id(req)
        await update_chat_history(user_id, request.message)

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
            "You are only trained for real-estate query, Only give answer related to real-estate dont give answer of unrelated question of real-estate "
            "if someone ask beyond the square yards, then dont give answer "
            "Include the following user context: {history}"
        )

        history = await get_chat_history(user_id)
        history_text = "\n".join([f"Previous Question: {q['question']}" for q in history]) or "No previous questions."

        full_prompt = base_prompt.format(city=request.city if request.city else "", history=history_text)
        user_message = request.message

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

# OTP send endpoint
@app.options("/api/otp/send")
async def options_otp_send(request: Request):
    origin = request.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/api/otp/send")
async def proxy_send_otp(request: OtpRequest, req: Request):
    try:
        print(f"Request Headers: {req.headers}")
        print(f"Request Origin: {req.headers.get('origin')}")
        print(f"OTP Send Input: {request.dict()}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://apigee.squareyards.com/api/otp/send",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
        print(f"OTP Send Output: Status={response.status_code}, Response={response.text}")
        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200:
            return JSONResponse(
                content={"message": "OTP sent Successfully on mobile"},
                status_code=200,
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )
        else:
            return JSONResponse(
                content={"message": response.text or "Failed to send OTP"},
                status_code=response.status_code,
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )
    except httpx.RequestError as e:
        print(f"OTP Send Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")

# OTP verify endpoint
@app.options("/api/otp/verify")
async def options_otp_verify(request: Request):
    origin = request.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/api/otp/verify")
async def proxy_verify_otp(request: OtpVerify, req: Request):
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
        headers = {"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        if "application/json" in content_type.lower():
            return JSONResponse(content=response.json(), status_code=response.status_code, headers=headers)
        else:
            return JSONResponse(
                content={"message": response.text or "Verification success"},
                status_code=response.status_code,
                headers=headers
            )
    except httpx.HTTPStatusError as e:
        print(f"OTP Verify HTTP Error: Status={e.response.status_code}, Response={e.response.text}")
        headers = {"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        try:
            return JSONResponse(status_code=e.response.status_code, content=e.response.json(), headers=headers)
        except Exception:
            return JSONResponse(status_code=e.response.status_code, content={"detail": e.response.text}, headers=headers)
    except httpx.RequestError as e:
        print(f"OTP Verify Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error verifying OTP: {str(e)}")

# Submit endpoint
@app.post("/submit")
async def submit(data: PropertyData, req: Request):
    try:
        data_dict = data.dict()
        data_dict["created_at"] = datetime.utcnow().isoformat()
        await collection.insert_one(data_dict)
        print(f"Submit Data: {data_dict}")
        return JSONResponse(
            content={"status": "success", "message": "Data submitted successfully"},
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )
    except Exception as e:
        print(f"Submit Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Ping DB endpoint
@app.get("/pingdb")
async def ping_db(req: Request):
    try:
        await db.command("ping")
        print("MongoDB ping successful")
        return JSONResponse(
            content={"message": "MongoDB connection is working ✅"},
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )
    except Exception as e:
        print(f"DB ping failed: {str(e)}")
        return JSONResponse(
            content={"message": f"DB ping failed: {str(e)}"},
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )