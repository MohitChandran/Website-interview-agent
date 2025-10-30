from groq import Groq
from typing import List, Dict


class InterviewerAI:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = "openai/gpt-oss-120b"  # or your model name
        self.messages = []  # conversation history
    
    def start_interview(self, candidate_name: str, role: str, resume_data: Dict) -> str:
        skills_text = ", ".join(resume_data.get("skills", [])) or "various skills"
        projects_text = "\n".join(resume_data.get("projects", [])[:2]) or "interesting projects"
        
        system_prompt = f"""You are Nikki, a professional and friendly AI interviewer conducting a {role} interview. 
Candidate Information:
- Name: {candidate_name}
- Role: {role}
- Skills: {skills_text}
- Notable Projects: {projects_text}
Interview Guidelines:
- Be conversational, friendly, and professional
- Ask relevant technical and behavioral questions based on their resume
- Follow up on their answers with deeper questions
- Keep responses concise (2-3 sentences max)
- When the user response with simple response like "yes" ,"ok" ask the same question again and make sure the user knows the answer
- Adapt questions based on their experience level
- Cover both technical skills and soft skills
- End gracefully after 10 minutes
Start with a warm greeting introducing yourself. and always avoid generating ** or other symbols in the text, make sure they are in a human readable form"""
        
        self.messages = [{"role": "system", "content": system_prompt}]
        
        greeting_prompt = f"Introduce yourself as Nikki and ask {candidate_name} if they're ready to begin the {role} interview. Keep it brief and friendly."
        self.messages.append({"role": "user", "content": greeting_prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages
        )
        
        assistant_message = response.choices[0].message.content
        print(f"start_interview: assistant_message:\n{assistant_message}\n")
        self.messages.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    
    def generate_response(self, user_transcript: str, conversation_history: List[Dict]) -> str:
        try:
            self.messages.append({"role": "user", "content": user_transcript})
            print(f"generate_response: user_transcript:\n{user_transcript}\n")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages
            )
            
            assistant_message = response.choices[0].message.content
            print(f"generate_response: Nikki response:\n{assistant_message}\n")
            
            self.messages.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message
        
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I see. Could you tell me more about that?"
    
    def generate_closing(self, candidate_name: str) -> str:
        closing_prompt = f"The 10-minute interview with {candidate_name} is now complete. Thank them warmly and professionally, and let them know what to expect next. Keep it brief."
        try:
            self.messages.append({"role": "user", "content": closing_prompt})
            print(f"generate_closing: closing_prompt:\n{closing_prompt}\n")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages
            )
            
            assistant_message = response.choices[0].message.content
            print(f"generate_closing: Nikki closing response:\n{assistant_message}\n")
            self.messages.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message
        except Exception as e:
            print(f"Error generating closing: {e}")
            return f"Thank you so much for your time today, {candidate_name}. We'll be in touch soon!"
