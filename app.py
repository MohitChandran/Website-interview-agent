from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import shutil
from pathlib import Path
from starlette.websockets import WebSocketState  # For safe send

from backend.conversation import ConversationManager
from backend.resume_parser import ResumeParser
from config.config import config

app = FastAPI(title="AI Interview Bot")
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Store active conversations
active_conversations = {}

@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """Serve the frontend HTML."""
    frontend_path = Path("frontend/index.html")
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return HTMLResponse("<h1>AI Interview Bot</h1><p>Frontend not found. Please create frontend/index.html</p>")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "deepgram_configured": bool(config.DEEPGRAM_API_KEY),
        "groq_configured": bool(config.GROQ_API_KEY),
        "elevenlabs_configured": bool(config.ELEVENLABS_API_KEY)
    }

@app.post("/api/upload-resume")
async def upload_resume(
    name: str = Form(...),
    role: str = Form(...),
    resume: UploadFile = File(...)
):
    """
    Handle resume upload and parse it.
    
    Args:
        name: Candidate name
        role: Role applying for
        resume: Resume PDF file
    
    Returns:
        Parsed resume data and session ID
    """
    try:
        # Save uploaded file
        file_path = UPLOAD_DIR / f"{name.replace(' ', '_')}_{resume.filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(resume.file, buffer)
        
        # Parse resume
        resume_data = ResumeParser.parse_pdf(str(file_path))
        
        # Create session ID
        session_id = f"{name}_{role}_{os.urandom(4).hex()}"
        
        # Store candidate info for later use
        active_conversations[session_id] = {
            "candidate_info": {"name": name, "role": role},
            "resume_data": resume_data,
            "file_path": str(file_path)
        }
        
        return {
            "success": True,
            "session_id": session_id,
            "resume_data": {
                "skills": resume_data.get("skills", []),
                "projects": resume_data.get("projects", []),
                "has_content": bool(resume_data.get("full_text"))
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def safe_send_json(websocket: WebSocket, data):
    """Send json only if websocket is connected."""
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.send_json(data)

@app.websocket("/ws/interview/{session_id}")
async def interview_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time interview.
    
    Args:
        websocket: WebSocket connection
        session_id: Session identifier
    """
    await websocket.accept()
    
    try:
        # Get session data
        if session_id not in active_conversations:
            await safe_send_json(websocket, {
                "type": "error",
                "message": "Invalid session ID"
            })
            await websocket.close()
            return
        
        session_data = active_conversations[session_id]
        
        # Create conversation manager
        conversation = ConversationManager(
            candidate_info=session_data["candidate_info"],
            resume_data=session_data["resume_data"]
        )
        
        # Send start signal and initial greeting
        greeting = await conversation.start_interview(websocket)
        await safe_send_json(websocket, greeting)
        
        # Handle incoming audio stream
        while conversation.interview_active:
            try:
                # Receive audio data from client
                data = await websocket.receive()
                
                if "bytes" in data:
                    # Process audio chunk
                    audio_chunk = data["bytes"]
                    await conversation.process_audio_chunk(audio_chunk)
                
                elif "text" in data:
                    # Handle text messages (control signals)
                    import json
                    message = json.loads(data["text"])
                    
                    if message.get("type") == "stop":
                        await conversation.stop()
                        break
                    elif message.get("type") == "ai_audio_completed":
                        # Reset the speaking flag to resume VAD and processing
                        conversation.is_ai_speaking = False
                        print(f"[WebSocket] Received ai_audio_completed, resuming listening")
            
            except WebSocketDisconnect:
                print(f"WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                print(f"Error processing websocket data: {e}")
                try:
                    await safe_send_json(websocket, {
                        "type": "error",
                        "message": str(e)
                    })
                except Exception:
                    # Connection may be closed, break loop
                    pass
                break
        
        # Cleanup
        await conversation.stop()
        
        # Remove from active conversations and cleanup files
        if session_id in active_conversations:
            file_path = active_conversations[session_id].get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            del active_conversations[session_id]
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await safe_send_json(websocket, {
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except Exception:
            # Connection might have been closed
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

@app.get("/api/sessions")
async def get_active_sessions():
    """Get list of active interview sessions (for debugging)."""
    return {
        "active_sessions": len(active_conversations),
        "sessions": [
            {
                "session_id": sid,
                "candidate": data["candidate_info"]["name"],
                "role": data["candidate_info"]["role"]
            }
            for sid, data in active_conversations.items()
        ]
    }

@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources."""
    if session_id in active_conversations:
        file_path = active_conversations[session_id].get("file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        del active_conversations[session_id]
        return {"success": True, "message": "Session deleted"}
    
    return {"success": False, "message": "Session not found"}

if __name__ == "__main__":
    # Ensure required directories exist
    Path("frontend").mkdir(exist_ok=True)
    Path("uploads").mkdir(exist_ok=True)
    Path("config").mkdir(exist_ok=True)
    
    # Check for required API keys
    if not config.DEEPGRAM_API_KEY:
        print("WARNING: DEEPGRAM_API_KEY not set in .env file")
    if not config.GROQ_API_KEY:
        print("WARNING: GROQ_API_KEY not set in .env file")
    if not config.ELEVENLABS_API_KEY:
        print("WARNING: ELEVENLABS_API_KEY not set in .env file")
    
    print("Starting AI Interview Bot server...")
    print(f"Interview duration: {config.INTERVIEW_DURATION_MINUTES} minutes")
    print(f"Silence threshold: {config.SILENCE_THRESHOLD_SECONDS} seconds")
    print("Server will be available at: http://localhost:8000")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )







# from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
# from fastapi.responses import HTMLResponse, FileResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.middleware.cors import CORSMiddleware
# import uvicorn
# import os
# import shutil
# from pathlib import Path

# from backend.conversation import ConversationManager
# from backend.resume_parser import ResumeParser
# from config.config import config
# from fastapi.staticfiles import StaticFiles



# app = FastAPI(title="AI Interview Bot")
# app.mount("/static", StaticFiles(directory="frontend"), name="static")
# # CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Create uploads directory
# UPLOAD_DIR = Path("uploads")
# UPLOAD_DIR.mkdir(exist_ok=True)

# # Store active conversations
# active_conversations = {}


# @app.get("/", response_class=HTMLResponse)
# async def get_frontend():
#     """Serve the frontend HTML."""
#     frontend_path = Path("frontend/index.html")
#     if frontend_path.exists():
#         return FileResponse(frontend_path)
#     return HTMLResponse("<h1>AI Interview Bot</h1><p>Frontend not found. Please create frontend/index.html</p>")


# @app.get("/health")
# async def health_check():
#     """Health check endpoint."""
#     return {
#         "status": "healthy",
#         "deepgram_configured": bool(config.DEEPGRAM_API_KEY),
#         "gemini_configured": bool(config.GEMINI_API_KEY),
#         "elevenlabs_configured": bool(config.ELEVENLABS_API_KEY)
#     }


# @app.post("/api/upload-resume")
# async def upload_resume(
#     name: str = Form(...),
#     role: str = Form(...),
#     resume: UploadFile = File(...)
# ):
#     """
#     Handle resume upload and parse it.
    
#     Args:
#         name: Candidate name
#         role: Role applying for
#         resume: Resume PDF file
    
#     Returns:
#         Parsed resume data and session ID
#     """
#     try:
#         # Save uploaded file
#         file_path = UPLOAD_DIR / f"{name.replace(' ', '_')}_{resume.filename}"
        
#         with open(file_path, "wb") as buffer:
#             shutil.copyfileobj(resume.file, buffer)
        
#         # Parse resume
#         resume_data = ResumeParser.parse_pdf(str(file_path))
        
#         # Create session ID
#         session_id = f"{name}_{role}_{os.urandom(4).hex()}"
        
#         # Store candidate info for later use
#         active_conversations[session_id] = {
#             "candidate_info": {"name": name, "role": role},
#             "resume_data": resume_data,
#             "file_path": str(file_path)
#         }
        
#         return {
#             "success": True,
#             "session_id": session_id,
#             "resume_data": {
#                 "skills": resume_data.get("skills", []),
#                 "projects": resume_data.get("projects", []),
#                 "has_content": bool(resume_data.get("full_text"))
#             }
#         }
    
#     except Exception as e:
#         return {
#             "success": False,
#             "error": str(e)
#         }


# @app.websocket("/ws/interview/{session_id}")
# async def interview_websocket(websocket: WebSocket, session_id: str):
#     """
#     WebSocket endpoint for real-time interview.
    
#     Args:
#         websocket: WebSocket connection
#         session_id: Session identifier
#     """
#     await websocket.accept()
    
#     try:
#         # Get session data
#         if session_id not in active_conversations:
#             await websocket.send_json({
#                 "type": "error",
#                 "message": "Invalid session ID"
#             })
#             await websocket.close()
#             return
        
#         session_data = active_conversations[session_id]
        
#         # Create conversation manager
#         conversation = ConversationManager(
#             candidate_info=session_data["candidate_info"],
#             resume_data=session_data["resume_data"]
#         )
        
#         # Send start signal and initial greeting
#         greeting = await conversation.start_interview(websocket)
#         await websocket.send_json(greeting)
        
#         # Handle incoming audio stream
#         while conversation.interview_active:
#             try:
#                 # Receive audio data from client
#                 data = await websocket.receive()
                
#                 if "bytes" in data:
#                     # Process audio chunk
#                     audio_chunk = data["bytes"]
#                     await conversation.process_audio_chunk(audio_chunk)
                
#                 elif "text" in data:
#                     # Handle text messages (control signals)
#                     import json
#                     message = json.loads(data["text"])
                    
#                     if message.get("type") == "stop":
#                         await conversation.stop()
#                         break
            
#             except WebSocketDisconnect:
#                 print(f"WebSocket disconnected for session {session_id}")
#                 break
#             except Exception as e:
#                 print(f"Error processing websocket data: {e}")
#                 await websocket.send_json({
#                     "type": "error",
#                     "message": str(e)
#                 })
        
#         # Cleanup
#         await conversation.stop()
        
#         # Remove from active conversations
#         if session_id in active_conversations:
#             # Cleanup uploaded file
#             file_path = active_conversations[session_id].get("file_path")
#             if file_path and os.path.exists(file_path):
#                 os.remove(file_path)
            
#             del active_conversations[session_id]
    
#     except Exception as e:
#         print(f"WebSocket error: {e}")
#         await websocket.send_json({
#             "type": "error",
#             "message": f"Server error: {str(e)}"
#         })
#     finally:
#         try:
#             await websocket.close()
#         except:
#             pass


# @app.get("/api/sessions")
# async def get_active_sessions():
#     """Get list of active interview sessions (for debugging)."""
#     return {
#         "active_sessions": len(active_conversations),
#         "sessions": [
#             {
#                 "session_id": sid,
#                 "candidate": data["candidate_info"]["name"],
#                 "role": data["candidate_info"]["role"]
#             }
#             for sid, data in active_conversations.items()
#         ]
#     }


# @app.delete("/api/session/{session_id}")
# async def delete_session(session_id: str):
#     """Delete a session and cleanup resources."""
#     if session_id in active_conversations:
#         # Cleanup file
#         file_path = active_conversations[session_id].get("file_path")
#         if file_path and os.path.exists(file_path):
#             os.remove(file_path)
        
#         del active_conversations[session_id]
#         return {"success": True, "message": "Session deleted"}
    
#     return {"success": False, "message": "Session not found"}


# if __name__ == "__main__":
#     # Ensure required directories exist
#     Path("frontend").mkdir(exist_ok=True)
#     Path("uploads").mkdir(exist_ok=True)
#     Path("config").mkdir(exist_ok=True)
    
#     # Check for required API keys
#     if not config.DEEPGRAM_API_KEY:
#         print("WARNING: DEEPGRAM_API_KEY not set in .env file")
#     if not config.GEMINI_API_KEY:
#         print("WARNING: GEMINI_API_KEY not set in .env file")
#     if not config.ELEVENLABS_API_KEY:
#         print("WARNING: ELEVENLABS_API_KEY not set in .env file")
    
#     print("Starting AI Interview Bot server...")
#     print(f"Interview duration: {config.INTERVIEW_DURATION_MINUTES} minutes")
#     print(f"Silence threshold: {config.SILENCE_THRESHOLD_SECONDS} seconds")
#     print("Server will be available at: http://localhost:8000")
    
#     uvicorn.run(
#         "app:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=True,
#         log_level="info"
#     )
