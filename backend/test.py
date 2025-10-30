import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

response = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Explain the importance of fast language models"
        }
    ],
    model="llama-3.3-70b-versatile"  # Example model name
)

print(response.choices[0].message.content)
