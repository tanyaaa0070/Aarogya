from dotenv import load_dotenv
import os
import google.generativeai as genai

load_dotenv()
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    print('No GEMINI_API_KEY found in environment')
    exit(1)

try:
    genai.configure(api_key=api_key)
    models = genai.list_models()
    for m in models:
        name = getattr(m, 'name', None)
        supported = getattr(m, 'supported_generation_methods', None)
        print(f"MODEL: {name} | supported: {supported}")
except Exception as e:
    print('Error listing models:', e)
