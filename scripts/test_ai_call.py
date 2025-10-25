import os
import json
from dotenv import load_dotenv
load_dotenv()

from app import get_ai_diagnosis_from_api

if __name__ == '__main__':
    sample = get_ai_diagnosis_from_api('fever and cough for 3 days, painful breathing', None, {'patient_name':'Test', 'age':65, 'gender':'M'})
    print('Result:', json.dumps(sample, indent=2, ensure_ascii=False))
