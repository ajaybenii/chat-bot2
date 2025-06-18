from dotenv import load_dotenv
import os
import asyncio
import httpx
import json
import re

from google import genai
from datetime import datetime
from pydantic import BaseModel
from typing import List
from fastapi import Request
from fastapi import FastAPI, Request

from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.responses import JSONResponse
from starlette.responses import Response
from google.genai import types

load_dotenv()

app = FastAPI()

# CORS setup - Updated for Render domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://chat-bot2-xy11.onrender.com",  # Your frontend domain
        "http://localhost:3000",  # For local development
        "https://localhost:3000"   # For local HTTPS development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# MongoDB connection with improved settings
mongo_uri = os.getenv("MONGO_URI")
print(f"MongoDB URI (masked): {mongo_uri[:20]}...{mongo_uri[-20:] if len(mongo_uri) > 40 else mongo_uri}")

# Create MongoDB client with better timeout settings
client = AsyncIOMotorClient(
    mongo_uri,
    serverSelectionTimeoutMS=10000,  # 10 seconds
    connectTimeoutMS=10000,          # 10 seconds
    socketTimeoutMS=10000,           # 10 seconds
    maxPoolSize=10,
    retryWrites=True,
    w="majority"
)

db = client["propertylst"]
collection = db["property_listing"]
chat_history_collection = db["chat_history"]

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
    user_id: str | None = None


# Pydantic models for quiz
class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str

class QuizResponse(BaseModel):
    user_id: str
    answers: List[str]

class QuizState(BaseModel):
    user_id: str
    city: str
    attempts_left: int
    questions_asked: List[str]
    score: int

# Helper function to get or create user ID based on phone number or request body
async def get_user_id(request: Request, chat_request: ChatRequest = None) -> str:
    # First, try to get user_id from the request body (for chat endpoint)
    if chat_request and chat_request.user_id:
        return chat_request.user_id
    
    # Then try to get from header
    phone_number = request.headers.get("X-User-Phone", "anonymous")
    if phone_number == "anonymous":
        print("Warning: No X-User-Phone header or user_id provided, using anonymous user_id")
    return phone_number

# Update chat history with retry mechanism
async def update_chat_history(user_id: str, message: str):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            history = await chat_history_collection.find_one({"user_id": user_id})
            if history:
                questions = history.get("questions", [])
                questions.append({"question": message, "timestamp": datetime.utcnow().isoformat()})
                if len(questions) > 10:
                    questions = questions[-10:]
                await chat_history_collection.update_one({"user_id": user_id}, {"$set": {"questions": questions}})
            else:
                await chat_history_collection.insert_one({"user_id": user_id, "questions": [{"question": message, "timestamp": datetime.utcnow().isoformat()}]})
            break
        except Exception as e:
            print(f"Chat history update attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                print("Failed to update chat history after all retries")
            else:
                await asyncio.sleep(1)  # Wait 1 second before retry

# Get chat history with retry mechanism
async def get_chat_history(user_id: str) -> list:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            history = await chat_history_collection.find_one({"user_id": user_id})
            return history.get("questions", []) if history else []
        except Exception as e:
            print(f"Chat history retrieval attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                print("Failed to get chat history after all retries, returning empty list")
                return []
            else:
                await asyncio.sleep(1)  # Wait 1 second before retry
Listingfaq = "Q: What are the advantages of taking an owner subscription? A: The foremost advantage is that there is no limit on the number of listings. Other unique features include 10X More Visibility, Unlimited Enquiries, 20 Matching Buyer Leads, Relationship Manager (RM) Assistance, Assisted Listing, Access Buyer Verification (Litigation Report), and Recent Registered Transactions. Q: What is the total price of the owner plan? A: The price starts from ₹3999 (including GST) and varies based on individual requirements. Q: Is Post Property as an owner, free? A: Yes, owners can list 3 properties for free and see the inquiries. However, the Seller Prime Subscription is recommended for more benefits. Q: Will I get genuine/interested clients, even after posting a free property? A: Yes, you will be able to see inquiries from interested clients on free listings. Q: What modes of payment are possible to buy owner subscription? A: Payment modes include Debit/Credit Card, UPI, and Net Banking. Q: How much time will it take for the subscription to get active? A: In most cases, it's instant, but sometimes it may take 24 to 48 hours. Q: How many interested clients I will get after posting a property? A: There is no limit. Better images attract more clients. Q: Is the amount of subscription refundable? A: No."

# print(faq)
# Gemini chat endpoint
@app.post("/api/chat")
async def chat_with_gemini(request: ChatRequest, req: Request):
    try:
        user_id = await get_user_id(req, request)  # Pass both request and chat_request
        await update_chat_history(user_id, request.message)

        base_prompt = (
            "You are a professional real-estate AI chatbot for SquareYards."
            "You are Squareyards AI Chat-bot, dont promote any other organisation, only talk about squareyards"
            "Provide accurate, concise, and helpful responses to user queries about properties, real estate markets."
            "If a city is provided, tailor the response to that city ({city}). "
            "Use data from Google Search tools to ensure accuracy and relevance. "
            "If user asks about different city, then give answer according to your knowledge. "
            "You are a smart AI chatbot of SquareYards. If the query is unrelated to real estate, politely redirect to real-estate topics. "
            "Only give answers related to real estate, do not respond to unrelated questions."
            "Give me response in well-formatted HTML that works for both day and night modes of the chat-bot UI. "
            "Response length should be concise like a chatbot. "
            "Directly give the response without explanations. "
            "You are only trained for real-estate query, Only gave answer related to real-estate dont give answer of unrelated question of real-estate."
            "If someone asks beyond the SquareYards, then dont give answer."
            "If Someone trying to ask this type of question, where did you get all info or something other unrelevent non-real estate querys, then politely redirect to real-estate topics."
            "As the AI chatbot for Square Yards, you must exclusively represent Square Yards. Do not mention or promote any other organization in any user query."
            f"If user question related to these FAQ {Listingfaq} then give answer using provided details,"
            "This is the Url link (https://www.squareyards.com/prime) for Prime Membership of Square Yards"
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
        
        # Add CORS headers for chat endpoint too
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"status": "success", "response": content},
            headers=headers
        )

    except Exception as e:
        print(f"Chat Error: {str(e)}")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"error": f"Error generating chat response: {str(e)}"},
            status_code=500,
            headers=headers
        )


@app.post("/api/quiz/game")
async def quiz_game(request: ChatRequest, req: Request):
    try:
        user_id = await get_user_id(req, request)
        city = request.city or "Wanaparthy"
        
        # Check quiz state in MongoDB
        quiz_state = await db["quiz_state"].find_one({"user_id": user_id})
        if not quiz_state:
            quiz_state = {
                "user_id": user_id,
                "city": city,
                "attempts_left": 3,
                "questions_asked": [],
                "score": 0
            }
            await db["quiz_state"].insert_one(quiz_state)

        if quiz_state["attempts_left"] <= 0:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "No attempts left. Please start a new listing.",
                    "buttons": [
                        {"text": "Start New Listing", "action": "start_new_listing"}
                    ]
                },
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )

        # Generate 3 new unique questions
        base_prompt = (
            f"You are a Real-estate Quiz generator for {city}. "
            f"Generate exactly 3 unique multiple choice questions about the real-estate market in {city}. "
            "Each question should have exactly 4 options (A, B, C, D) and one correct answer. "
            f"Do not repeat these questions: {', '.join(quiz_state['questions_asked']) if quiz_state['questions_asked'] else 'None'}. "
            "Return ONLY a valid JSON array with this exact structure: "
            '[{"question": "Your question here?", "options": ["Option A", "Option B", "Option C", "Option D"], "correct_answer": "Option A"}]. '
            "Do not include any markdown formatting, explanations, or additional text. "
            "Make sure the correct_answer matches exactly one of the options."
        )

        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=base_prompt,
            config=types.GenerateContentConfig(
                tools=gemini_tools,
                max_output_tokens=2048,
                temperature=0.3,  # Lower temperature for more consistent formatting
            )
        )

        # Clean and parse the response
        response_text = response.text.strip()
        
        # Remove any markdown formatting
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        print(f"Raw Gemini response: {response_text}")
        
        try:
            questions = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Response text: {response_text}")
            
            # Fallback: create default questions
            questions = [
                {
                    "question": f"What is the average property price range in {city}?",
                    "options": ["₹20-30 lakhs", "₹30-50 lakhs", "₹50-70 lakhs", "₹70+ lakhs"],
                    "correct_answer": "₹30-50 lakhs"
                },
                {
                    "question": f"Which area in {city} is considered prime for residential investment?",
                    "options": ["City Center", "Outskirts", "Industrial Area", "Agricultural Zone"],
                    "correct_answer": "City Center"
                },
                {
                    "question": f"What type of properties are most in demand in {city}?",
                    "options": ["1 BHK Apartments", "2-3 BHK Apartments", "Villas", "Commercial Spaces"],
                    "correct_answer": "2-3 BHK Apartments"
                }
            ]
        
        # Validate questions structure
        validated_questions = []
        for i, q in enumerate(questions[:3]):  # Ensure only 3 questions
            if not isinstance(q, dict):
                continue
                
            question_text = q.get("question", f"Sample question {i+1} about {city} real estate?")
            options = q.get("options", [f"Option A", f"Option B", f"Option C", f"Option D"])
            correct_answer = q.get("correct_answer", options[0] if options else "Option A")
            
            # Ensure we have exactly 4 options
            if len(options) != 4:
                options = options[:4] if len(options) > 4 else options + [f"Option {chr(65+len(options)+i)}" for i in range(4-len(options))]
            
            # Ensure correct_answer is one of the options
            if correct_answer not in options:
                correct_answer = options[0]
            
            validated_questions.append({
                "question": question_text,
                "options": options,
                "correct_answer": correct_answer
            })
        
        # Ensure we have exactly 3 questions
        while len(validated_questions) < 3:
            validated_questions.append({
                "question": f"What is a key factor to consider when buying property in {city}?",
                "options": ["Location", "Price", "Amenities", "All of the above"],
                "correct_answer": "All of the above"
            })
        
        # Update quiz state
        question_texts = [q["question"] for q in validated_questions]
        updated_questions_asked = quiz_state["questions_asked"] + question_texts
        
        await db["quiz_state"].update_one(
            {"user_id": user_id},
            {"$set": {
                "questions_asked": updated_questions_asked,
                "current_questions": validated_questions
            }}
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": f"You have {quiz_state['attempts_left']} chance(s) to get up to 50% off on our membership!",
                "questions": validated_questions,
                "attempts_left": quiz_state["attempts_left"]
            },
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )

    except Exception as e:
        print(f"Quiz Error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        
        return JSONResponse(
            content={"error": f"Error generating quiz: {str(e)}"},
            status_code=500,
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )

@app.post("/api/quiz/submit")
async def submit_quiz_answers(request: QuizResponse, req: Request):
    try:
        user_id = request.user_id
        quiz_state = await db["quiz_state"].find_one({"user_id": user_id})
        
        if not quiz_state:
            return JSONResponse(
                content={"status": "error", "message": "No active quiz found"},
                status_code=404,
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )

        # Get current questions
        current_questions = quiz_state.get("current_questions", [])
        
        if not current_questions:
            return JSONResponse(
                content={"status": "error", "message": "No questions found for this quiz"},
                status_code=400,
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )

        # Verify answers
        correct_count = 0
        for i, user_answer in enumerate(request.answers):
            if i < len(current_questions):
                correct_answer = current_questions[i].get("correct_answer", "")
                if user_answer == correct_answer:
                    correct_count += 1
        
        # Update quiz state
        new_attempts_left = quiz_state["attempts_left"] - 1
        
        await db["quiz_state"].update_one(
            {"user_id": user_id},
            {"$set": {
                "attempts_left": new_attempts_left,
                "score": correct_count
            }}
        )

        if correct_count == 3:
            # Perfect score - delete quiz state to reset
            await db["quiz_state"].delete_one({"user_id": user_id})
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "Congratulations! You got all answers correct! Buy our membership now and get up to 50% off!",
                    "score": f"{correct_count}/3",
                    "buttons": [
                        {"text": "Buy Membership", "action": "buy_membership"},
                        {"text": "Start New Listing", "action": "start_new_listing"}
                    ]
                },
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )
        else:
            if new_attempts_left > 0:
                message = f"You got {correct_count}/3 correct. {new_attempts_left} chance(s) left. Try again!"
                buttons = [
                    {"text": "Play Quiz Again", "action": "play_quiz"},
                    {"text": "Start New Listing", "action": "start_new_listing"}
                ]
                status = "retry"
            else:
                # No attempts left - reset quiz state
                await db["quiz_state"].delete_one({"user_id": user_id})
                message = f"You got {correct_count}/3 correct. No attempts left. Start a new listing to try again!"
                buttons = [{"text": "Start New Listing", "action": "start_new_listing"}]
                status = "failed"

            return JSONResponse(
                content={
                    "status": status,
                    "message": message,
                    "score": f"{correct_count}/3",
                    "buttons": buttons
                },
                headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
            )

    except Exception as e:
        print(f"Quiz Submit Error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        
        return JSONResponse(
            content={"error": f"Error submitting quiz answers: {str(e)}"},
            status_code=500,
            headers={"Access-Control-Allow-Origin": req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")}
        )
    

# OTP send endpoint with proper CORS handling
@app.options("/api/otp/send")
async def options_otp_send(request: Request):
    origin = request.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
    print(f"OPTIONS /api/otp/send Origin: {origin}")
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
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://apigee.squareyards.com/api/otp/send",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
        
        print(f"OTP Send Output: Status={response.status_code}, Response={response.text}")
        
        # Set CORS headers
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return JSONResponse(content=response.json(), status_code=response.status_code, headers=headers)
        else:
            return JSONResponse(
                content={"message": response.text or "OTP sent successfully"},
                status_code=response.status_code,
                headers=headers
            )
    except httpx.RequestError as e:
        print(f"OTP Send Error: {str(e)}")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"message": f"Failed to send OTP: {str(e)}"},
            status_code=500,
            headers=headers
        )

# OTP verify endpoint with proper CORS handling
@app.options("/api/otp/verify")
async def options_otp_verify(request: Request):
    origin = request.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
    print(f"OPTIONS /api/otp/verify Origin: {origin}")
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/api/otp/verify")
async def proxy_verify_otp(request: OtpVerify, req: Request):
    try:
        print(f"Request Headers: {req.headers}")
        print(f"Request Origin: {req.headers.get('origin')}")
        print(f"OTP Verify Input: {request.dict()}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://apigee.squareyards.com/api/otp/verify",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
        
        print(f"OTP Verify Output: Status={response.status_code}, Response={response.text}")
        
        # Set CORS headers
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return JSONResponse(content=response.json(), status_code=response.status_code, headers=headers)
        else:
            return JSONResponse(
                content={"message": response.text or "Verification successful"},
                status_code=response.status_code,
                headers=headers
            )
    except httpx.HTTPStatusError as e:
        print(f"OTP Verify HTTP Error: Status={e.response.status_code}, Response={e.response.text}")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        try:
            return JSONResponse(
                status_code=e.response.status_code, 
                content=e.response.json(),
                headers=headers
            )
        except Exception:
            return JSONResponse(
                status_code=e.response.status_code, 
                content={"message": e.response.text or "Verification failed"},
                headers=headers
            )
    except httpx.RequestError as e:
        print(f"OTP Verify Error: {str(e)}")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            status_code=500,
            content={"message": f"Error verifying OTP: {str(e)}"},
            headers=headers
        )

@app.options("/submit")
async def options_submit(request: Request):
    origin = request.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
    print(f"OPTIONS /submit Origin: {origin}")
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@app.post("/submit")
async def submit(data: PropertyData, req: Request):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Submit attempt {attempt + 1}: {data.dict()}")
            
            data_dict = data.dict()
            data_dict["created_at"] = datetime.utcnow().isoformat()
            
            # Use asyncio.wait_for to add a timeout
            await asyncio.wait_for(
                collection.insert_one(data_dict),
                timeout=10.0  # 10 second timeout
            )
            
            print(f"Submit Data successful: {data_dict}")
            
            origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
            headers = {"Access-Control-Allow-Origin": origin}
            return JSONResponse(
                content={"status": "success", "message": "Data submitted successfully"},
                headers=headers
            )
            
        except asyncio.TimeoutError:
            print(f"Submit attempt {attempt + 1} timed out")
            if attempt == max_retries - 1:
                origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
                headers = {"Access-Control-Allow-Origin": origin}
                return JSONResponse(
                    content={"message": "Database timeout - please try again later"},
                    status_code=503,
                    headers=headers
                )
            await asyncio.sleep(2)  # Wait 2 seconds before retry
            
        except Exception as e:
            print(f"Submit attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
                headers = {"Access-Control-Allow-Origin": origin}
                return JSONResponse(
                    content={"message": f"Error submitting data: {str(e)}"},
                    status_code=500,
                    headers=headers
                )
            await asyncio.sleep(2)  # Wait 2 seconds before retry

@app.get("/pingdb")
async def ping_db(req: Request):
    try:
        # Use asyncio.wait_for to add a timeout
        await asyncio.wait_for(
            db.command("ping"),
            timeout=5.0  # 5 second timeout
        )
        print("MongoDB ping successful")
        
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"message": "MongoDB connection is working ✅"},
            headers=headers
        )
    except asyncio.TimeoutError:
        print("DB ping timed out")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"message": "DB ping timed out - connection issues"},
            status_code=503,
            headers=headers
        )
    except Exception as e:
        print(f"DB ping failed: {str(e)}")
        origin = req.headers.get("origin", "https://chat-bot2-xy11.onrender.com")
        headers = {"Access-Control-Allow-Origin": origin}
        return JSONResponse(
            content={"message": f"DB ping failed: {str(e)}"},
            status_code=503,
            headers=headers
        )

# Add a health check endpoint for Render
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Backend is running on Render"}

# Root endpoint
@app.get("/")
async def root():
    return {"message": "SquareYards ChatBot Backend API", "status": "running"}

# Startup event to check database connection
@app.on_event("startup")
async def startup_event():
    try:
        await asyncio.wait_for(db.command("ping"), timeout=10.0)
        print("✅ MongoDB connection established successfully on startup")
    except Exception as e:
        print(f"❌ MongoDB connection failed on startup: {str(e)}")
        print("Application will continue but database operations may fail")

# Shutdown event to close database connection
@app.on_event("shutdown")
async def shutdown_event():
    client.close()
    print("MongoDB connection closed")