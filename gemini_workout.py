import os
from dotenv import load_dotenv
from google import genai

# 1. Load the environment variable configuration
load_dotenv()

# 2. Initialize the client (it automatically detects GEMINI_API_KEY from your .env file)
client = genai.Client()

user_prompt = "Design a 20-minute bodyweight core routine that requires zero equipment."

print("Reaching out to Gemini... Calculating rep structures...")

try:
    # 3. Call the highly efficient Gemini 2.5 Flash model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=f"Act as a professional calisthenics coach. {user_prompt}",
    )
    
    # 4. Display your new routine
    print("\n=== GEMINI CORE WORKOUT PLAN ===")
    print(response.text)

except Exception as e:
    print(f"\nAn error occurred while calling the Gemini API: {e}")