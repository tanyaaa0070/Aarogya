import os
from datetime import datetime
import json
from typing import Optional
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import io

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase: Optional[Client] = None
supabase_admin: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"[WARN] Could not create Supabase client: {e}")
        supabase = None
else:
    print("[INFO] SUPABASE_URL or SUPABASE_KEY not set. Running in demo mode with no database.")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Log available models on startup for debugging
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"[INFO] Available Gemini models: {available_models[:5]}...")  # Limit to first 5 for brevity
        if 'models/gemini-1.5-flash' not in available_models:
            print("[WARN] 'gemini-1.5-flash' not available. Check API key or region.")
    except Exception as e:
        print(f"[WARN] Could not list models: {e}")


def get_ai_diagnosis_from_api(symptoms_text, image_url, patient_info):
    if not GEMINI_API_KEY:
        return {
            'main_diagnosis': 'Simulation Mode (No API Key)',
            'confidence': 75,
            'triage_level': 'URGENT',
            'explanation': 'API Key not found. This is a simulated response. Please provide a Gemini API key in the .env file for real analysis.'
        }

    # Select a supported model dynamically. Prefer stable/latest model names available in the account.
    preferred_candidates = [
        'models/gemini-pro-latest',
        'models/gemini-flash-latest',
        'models/gemini-2.5-flash',
        'models/gemini-2.5-pro',
        'models/gemini-2.0-flash',
    ]

    model = None
    try:
        models = list(genai.list_models())
        available = {m.name for m in models}
        chosen = None
        for candidate in preferred_candidates:
            if candidate in available:
                chosen = candidate
                break

        if not chosen:
            for m in models:
                if getattr(m, 'supported_generation_methods', None) and 'generateContent' in m.supported_generation_methods:
                    chosen = m.name
                    break

        if not chosen:
            print('[ERROR] No model supporting generateContent is available for this API key.')
            return {
                'main_diagnosis': 'AI Unavailable',
                'confidence': 0,
                'triage_level': 'URGENT',
                'explanation': 'No generative model available in your account. Please verify the API key and model access.'
            }

        print(f"[INFO] Using generative model: {chosen}")
        model = genai.GenerativeModel(chosen)
    except Exception as e:
        print(f"[ERROR] Failed selecting/initializing model: {e}")
        return {
            'main_diagnosis': 'AI Initialization Error',
            'confidence': 0,
            'triage_level': 'URGENT',
            'explanation': f'Unable to initialize AI model. Error: {e}'
        }

    prompt_parts = [
        "You are an expert medical AI assistant for Community Health Workers in rural India.",
        "Your goal is to provide a preliminary analysis and triage recommendation based on patient data.",
        "Do NOT give a definitive diagnosis. Your response must be cautious and guide the health worker.",
        "Keep responses concise to respect rate limits.",
        f"Patient Information: Age: {patient_info.get('age', 'N/A')}, Gender: {patient_info.get('gender', 'N/A')}.",
        f"Text Symptoms from Patient/Worker: {symptoms_text if symptoms_text else 'No text symptoms provided.'}",
        "---",
        "Analyze the provided information and respond ONLY with a single, valid JSON object in the following format (no extra text, code blocks, or explanations):",
        """
        {
          "main_diagnosis": "Most probable condition (e.g., 'Possible Bacterial Skin Infection')",
          "confidence": <An integer confidence score between 50 and 95>,
          "triage_level": "<One of: 'CRITICAL', 'URGENT', or 'STABLE'>",
          "explanation": "<A brief, simple explanation and recommendation in 1-2 sentences for the health worker. Start with 'Recommendation:' and advise on next steps (e.g., refer immediately, monitor symptoms, provide basic care).>"
        }
        """,
        "---"
    ]

    if image_url:
        prompt_parts.insert(5, f"Visual symptoms from uploaded image at: {image_url}")

    try:
        prompt_text = "\n".join(prompt_parts)
        if image_url:
            try:
                import requests
                from io import BytesIO
                r = requests.get(image_url, timeout=10)
                r.raise_for_status()
                image_bytes = BytesIO(r.content)
            except Exception as img_e:
                print(f"[WARN] Could not download image for vision analysis: {img_e}")
                image_bytes = None

            if image_bytes:
                try:
                    response = model.generate_content([prompt_text, image_bytes])
                except Exception:
                    response = model.generate_content(prompt_text)
            else:
                response = model.generate_content(prompt_text)
        else:
            response = model.generate_content(prompt_text)

        cleaned_response = getattr(response, 'text', str(response)).strip().replace('```json', '').replace('```', '').replace('json', '')
        try:
            ai_result = json.loads(cleaned_response)
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON in response: {cleaned_response[:200]}...")
            ai_result = {
                'main_diagnosis': 'Parsing Error - Incomplete Analysis',
                'confidence': 50,
                'triage_level': 'URGENT',
                'explanation': 'Recommendation: Response format issue. Proceed with caution and refer to a clinic.'
            }
        return ai_result
    except Exception as e:
        error_str = str(e)
        print(f"Gemini API call failed: {error_str}")
        if "404" in error_str or "not found" in error_str.lower():
            return {
                'main_diagnosis': 'API Model Error',
                'confidence': 0,
                'triage_level': 'URGENT',
                'explanation': 'Recommendation: Model not accessible (e.g., 404 error). Manual triage required—seek professional help now.'
            }
        elif "quota" in error_str.lower() or "rate limit" in error_str.lower():
            return {
                'main_diagnosis': 'Rate Limit Exceeded',
                'confidence': 0,
                'triage_level': 'STABLE',
                'explanation': 'Recommendation: API quota reached. Wait and retry, or use manual assessment.'
            }
        return {
            'main_diagnosis': 'AI Analysis Error',
            'confidence': 50,
            'triage_level': 'URGENT',
            'explanation': 'Recommendation: The AI service could not process the request. Please proceed with manual assessment.'
        }


def _load_local_records():
    """Return list of records saved in data/local_records.jsonl (each line is a JSON object)."""
    data_dir = os.path.join(app.root_path, 'data')
    local_file = os.path.join(data_dir, 'local_records.jsonl')
    records = []
    try:
        if os.path.exists(local_file):
            with open(local_file, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
    except Exception as ex:
        print(f"[WARN] Could not read local records: {ex}")
    return records


def _find_local_record(record_id):
    if not record_id:
        return None
    for r in _load_local_records():
        if str(r.get('id')) == str(record_id):
            return r
    return None

    try:
        # The SDK exposes `generate_content` which can accept either a prompt string or a list.
        # When including images, pass the prompt and the image bytes via the SDK's supported interfaces.
        # For text-only, provide the joined prompt.
        prompt_text = "\n".join(prompt_parts)
        if image_url:
            # Download image bytes and let the model handle vision if supported
            try:
                import requests
                from io import BytesIO
                r = requests.get(image_url, timeout=10)
                r.raise_for_status()
                image_bytes = BytesIO(r.content)
            except Exception as img_e:
                print(f"[WARN] Could not download image for vision analysis: {img_e}")
                image_bytes = None

            if image_bytes:
                # Some SDK versions accept a list [prompt_text, image_bytes] or attach the image via the `inputs` param.
                try:
                    response = model.generate_content([prompt_text, image_bytes])
                except Exception:
                    # Fallback to text-only if vision call fails
                    response = model.generate_content(prompt_text)
            else:
                response = model.generate_content(prompt_text)
        else:
            response = model.generate_content(prompt_text)

        cleaned_response = getattr(response, 'text', str(response)).strip().replace('```json', '').replace('```', '').replace('json', '')
        # Robust JSON parsing with error handling
        try:
            ai_result = json.loads(cleaned_response)
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON in response: {cleaned_response[:200]}...")
            # Fallback: Parse if it's almost valid or simulate
            ai_result = {
                'main_diagnosis': 'Parsing Error - Incomplete Analysis',
                'confidence': 50,
                'triage_level': 'URGENT',
                'explanation': 'Recommendation: Response format issue. Proceed with caution and refer to a clinic.'
            }
        return ai_result
    except Exception as e:
        error_str = str(e)
        print(f"Gemini API call failed: {error_str}")
        if "404" in error_str or "not found" in error_str.lower():
            return {
                'main_diagnosis': 'API Model Error',
                'confidence': 0,
                'triage_level': 'URGENT',
                'explanation': 'Recommendation: Model not accessible (e.g., 404 error). Manual triage required—seek professional help now.'
            }
        elif "quota" in error_str.lower() or "rate limit" in error_str.lower():
            return {
                'main_diagnosis': 'Rate Limit Exceeded',
                'confidence': 0,
                'triage_level': 'STABLE',
                'explanation': 'Recommendation: API quota reached. Wait and retry, or use manual assessment.'
            }
        return {
            'main_diagnosis': 'AI Analysis Error',
            'confidence': 50,
            'triage_level': 'URGENT',
            'explanation': 'Recommendation: The AI service could not process the request. Please proceed with manual assessment.'
        }


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/record')
def record():
    return render_template('record.html')


@app.route('/dashboard')
def dashboard():
    try:
        if not supabase:
            records = []
            stats = {'total': 0, 'critical': 0, 'urgent': 0, 'stable': 0}
            return render_template('dashboard.html', records=records, stats=stats)

        response = supabase.table('patient_records').select(
            '*').order('created_at', desc=True).execute()
        records = response.data

        stats = {
            'total': len(records),
            'critical': len([r for r in records if r.get('triage_level') == 'CRITICAL']),
            'urgent': len([r for r in records if r.get('triage_level') == 'URGENT']),
            'stable': len([r for r in records if r.get('triage_level') == 'STABLE'])
        }
        return render_template('dashboard.html', records=records, stats=stats)
    except Exception as e:
        return f"Error fetching dashboard data: {e}"


@app.route('/result/<record_id>')
def result(record_id):
    try:
        if not supabase:
            # Check local fallback
            local = _find_local_record(record_id)
            return render_template('result.html', record=local)

        response = supabase.table('patient_records').select(
            '*').eq('id', record_id).single().execute()
        record = response.data
        if not record:
            # Attempt to load from local fallback
            record = _find_local_record(record_id)
        return render_template('result.html', record=record)
    except Exception as e:
        return f"Error fetching result data: {e}"


@app.route('/result')
def result_query():
    """Support the frontend call to /result?id=... by reading the query param.
    This keeps compatibility with code that expects /result?id=<id> instead of /result/<id>.
    """
    record_id = request.args.get('id') or None
    if not record_id or not supabase:
        # If supabase not configured, try local fallback
        local = _find_local_record(record_id)
        return render_template('result.html', record=local)

    try:
        response = supabase.table('patient_records').select(
            '*').eq('id', record_id).single().execute()
        record = response.data
        if not record:
            record = _find_local_record(record_id)
        return render_template('result.html', record=record)
    except Exception as e:
        print(f"Error fetching result by query id {record_id}: {e}")
        return render_template('result.html', record=None)


@app.route('/abdm-record/<record_id>')
def abdm_record(record_id):
    try:
        if not supabase:
            local = _find_local_record(record_id)
            return render_template('abdm-record.html', record=local)

        response = supabase.table('patient_records').select(
            '*').eq('id', record_id).single().execute()
        record = response.data
        if not record:
            record = _find_local_record(record_id)
        return render_template('abdm-record.html', record=record)
    except Exception as e:
        return f"Error fetching ABDM data: {e}"


@app.route('/abdm-record')
def abdm_record_query():
    """Support query-style calls to /abdm-record?id=... from the frontend.
    This mirrors the behavior of /result and keeps backwards compatibility.
    """
    record_id = request.args.get('id') or None
    if not record_id or not supabase:
        local = _find_local_record(record_id)
        return render_template('abdm-record.html', record=local)

    try:
        response = supabase.table('patient_records').select(
            '*').eq('id', record_id).single().execute()
        record = response.data
        if not record:
            record = _find_local_record(record_id)
        return render_template('abdm-record.html', record=record)
    except Exception as e:
        print(f"Error fetching ABDM by query id {record_id}: {e}")
        return render_template('abdm-record.html', record=None)


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.form
        patient_info = {
            'patient_name': data.get('patient_name'),
            'age': int(data.get('age')),
            'gender': data.get('gender')
        }
        symptoms_text = data.get('symptoms_text')

        image_file_url = None
        voice_file_url = None

        if 'image_file' in request.files and request.files['image_file'].filename != '':
            image_file = request.files['image_file']
            file_ext = image_file.filename.split('.')[-1]
            file_name = f"img_{datetime.now().timestamp()}.{file_ext}"
            # choose admin storage client when available
            storage_client = supabase_admin if 'supabase_admin' in globals() and supabase_admin else supabase
            if storage_client:
                try:
                    upload_resp = storage_client.storage.from_('media').upload(
                        file=image_file.read(), path=file_name, file_options={"content-type": image_file.mimetype})
                    print(f"[DEBUG] image upload response: {getattr(upload_resp, 'error', upload_resp)}")
                    image_file_url = storage_client.storage.from_('media').get_public_url(file_name)
                except Exception as ex:
                    print(f"[ERROR] image upload failed: {ex}")
                    image_file_url = None
            else:
                image_file_url = None
            # Fallback: if Supabase upload did not produce a URL, save locally to static/uploads
            if not image_file_url:
                try:
                    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
                    os.makedirs(uploads_dir, exist_ok=True)
                    local_path = os.path.join(uploads_dir, file_name)
                    # If we already read file contents into memory via image_file.read() above, we need to re-seek
                    image_file.stream.seek(0)
                    with open(local_path, 'wb') as f:
                        f.write(image_file.read())
                    image_file_url = url_for('static', filename=f'uploads/{file_name}', _external=True)
                    print(f"[INFO] Saved image locally to {local_path}")
                except Exception as ex:
                    print(f"[ERROR] Local image save failed: {ex}")

        if 'voice_file' in request.files and request.files['voice_file'].filename != '':
            voice_file = request.files['voice_file']
            file_ext = voice_file.filename.split(
                '.')[-1] if '.' in voice_file.filename else 'webm'
            file_name = f"voice_{datetime.now().timestamp()}.{file_ext}"

            storage_client = supabase_admin if 'supabase_admin' in globals() and supabase_admin else supabase
            if storage_client:
                try:
                    upload_resp = storage_client.storage.from_('media').upload(
                        file=voice_file.read(), path=file_name, file_options={"content-type": voice_file.mimetype})
                    print(f"[DEBUG] voice upload response: {getattr(upload_resp, 'error', upload_resp)}")
                    voice_file_url = storage_client.storage.from_('media').get_public_url(file_name)
                except Exception as ex:
                    print(f"[ERROR] voice upload failed: {ex}")
                    voice_file_url = None
            else:
                voice_file_url = None
            # Fallback: save voice locally if upload failed
            if not voice_file_url:
                try:
                    uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
                    os.makedirs(uploads_dir, exist_ok=True)
                    local_path = os.path.join(uploads_dir, file_name)
                    voice_file.stream.seek(0)
                    with open(local_path, 'wb') as f:
                        f.write(voice_file.read())
                    voice_file_url = url_for('static', filename=f'uploads/{file_name}', _external=True)
                    print(f"[INFO] Saved voice locally to {local_path}")
                except Exception as ex:
                    print(f"[ERROR] Local voice save failed: {ex}")

        ai_result = get_ai_diagnosis_from_api(
            symptoms_text, image_file_url, patient_info)
        # Defensive: ensure ai_result is a dict to avoid NoneType errors
        if not isinstance(ai_result, dict):
            print(f"[WARN] ai_result unexpected type: {type(ai_result)}. Falling back to default result.")
            ai_result = {
                'main_diagnosis': 'AI Unavailable',
                'confidence': 0,
                'triage_level': 'URGENT',
                'explanation': 'Recommendation: AI did not return a valid response.'
            }

        # Defensive: ensure patient_info fields have expected types
        try:
            patient_info['age'] = int(patient_info.get('age') or 0)
        except Exception:
            patient_info['age'] = 0

        record_to_insert = {
            **patient_info,
            'symptoms_text': symptoms_text,
            'image_file_url': image_file_url,
            'voice_file_url': voice_file_url,
            'ai_diagnosis': ai_result.get('main_diagnosis') if isinstance(ai_result, dict) else None,
            'confidence': ai_result.get('confidence') if isinstance(ai_result, dict) else None,
            'triage_level': ai_result.get('triage_level') if isinstance(ai_result, dict) else None,
            'explanation': ai_result.get('explanation') if isinstance(ai_result, dict) else None
        }

        db_client = supabase_admin if 'supabase_admin' in globals() and supabase_admin else supabase
        if db_client:
            try:
                response = db_client.table('patient_records').insert(record_to_insert).execute()
                print(f"[DEBUG] insert response: {getattr(response, 'error', response)}")
                try:
                    new_record_id = response.data[0].get('id') if response.data and isinstance(response.data, list) else None
                except Exception:
                    new_record_id = None
            except Exception as ex:
                print(f"[ERROR] insert failed: {ex}")
                new_record_id = None
        # Fallback: if DB insert failed or no Supabase client, save record locally
        if not new_record_id:
            try:
                import uuid
                generated_id = str(uuid.uuid4())
                record_to_insert_local = dict(record_to_insert)
                record_to_insert_local['id'] = generated_id
                record_to_insert_local['created_at'] = datetime.utcnow().isoformat()
                data_dir = os.path.join(app.root_path, 'data')
                os.makedirs(data_dir, exist_ok=True)
                local_file = os.path.join(data_dir, 'local_records.jsonl')
                with open(local_file, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps(record_to_insert_local, ensure_ascii=False) + '\n')
                new_record_id = generated_id
                print(f"[INFO] Saved record locally to {local_file} with id {generated_id}")
            except Exception as ex:
                print(f"[ERROR] Failed to save record locally: {ex}")
        # If we still don't have a record id, return an error to the client
        if not new_record_id:
            print("[ERROR] Could not create or save record; returning failure to client")
            return jsonify({'success': False, 'error': 'Failed to save record'}), 500

        return jsonify({'success': True, 'record_id': new_record_id})

    except Exception as e:
        print(f"Error in /analyze: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("[DEBUG] Starting Flask app with debug=True")
    try:
        app.run(debug=True)
    except Exception as e:
        print(f"[ERROR] Flask failed to start: {e}")