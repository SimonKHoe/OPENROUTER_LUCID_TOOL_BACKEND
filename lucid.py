# -*- coding: utf-8 -*-
"""
Flask backend server for the LUCID Qualtrics chat interface.

Acts as a proxy between the Qualtrics frontend JavaScript and the OpenAI API.
Handles CORS, fetches configuration from environment variables, makes API calls,
and returns responses. Includes a root endpoint to display deployment status
and the necessary Qualtrics URL.
"""
from flask import Flask, request, jsonify, make_response
import json
import os      # Used for accessing environment variables (API keys, config)
import requests # Used for making HTTP requests to the OpenAI API
import html

# Initialize the Flask application
app = Flask(__name__)

# --- Configuration & CORS ---

def get_allowed_origins_config():
    """
    Reads the ALLOWED_ORIGINS environment variable and parses it into a list.
    Defaults to allowing all origins ('*') if the variable is not set.
    Uses print for logging and visible in Vercel Function Logs.
    """
    origins_str = os.getenv('ALLOWED_ORIGINS')
    print(f"[DEBUG ENV] Raw ALLOWED_ORIGINS: '{origins_str}'") # Vercel Log

    if not origins_str:
        # Default to wildcard if environment variable is missing or empty
        print("[WARN ENV] ALLOWED_ORIGINS not set. Defaulting CORS to allow all ('*').") # Vercel Log
        return ['*']

    # Parse comma-separated list, removing empty strings and stripping whitespace
    allowed_list = [origin.strip() for origin in origins_str.split(',') if origin.strip()]
    print(f"[DEBUG ENV] Parsed ALLOWED_ORIGINS: {allowed_list}") # Vercel Log
    return allowed_list

@app.before_request
def handle_preflight():
    """
    Handles CORS preflight (OPTIONS) requests specifically for the /lucid endpoint.
    Checks the request's Origin header against the ALLOWED_ORIGINS config
    and returns appropriate CORS headers if allowed, or a 403 if denied.
    Echoes back requested headers. Only adds 'Access-Control-Allow-Credentials'
    when needed and with the value 'true'.
    """
    # Intercept only OPTIONS requests targetting the main API endpoint
    # UPDATED: Changed request.method.upper() == 'OPTIONS' to request.method == 'OPTIONS' (Flask normalizes it)
    if request.method == 'OPTIONS' and request.path == '/lucid':
        print(f"[INFO] Intercepting OPTIONS request for {request.path}") # Vercel Log
        origin = request.headers.get('Origin') # Get the origin of the requesting domain
        allowed_origins = get_allowed_origins_config() # Fetch the configured allowed origins

        print(f"[DEBUG PREFLIGHT] Request Origin: '{origin}'") # Vercel Log
        print(f"[DEBUG PREFLIGHT] Checking against Allowed: {allowed_origins}") # Vercel Log

        ac_allow_origin = None # Initialize
        send_credentials = False # Initialize

        # ---- decide origin & credentials ------------------------
        if '*' in allowed_origins:
            ac_allow_origin = '*'
            send_credentials = False        # wildcard ⇒ no creds
            print("[DEBUG PREFLIGHT] Policy: Allowed Wildcard (*), Credentials False") # Vercel Log
        elif origin and origin in allowed_origins: # Added check for origin existence
            ac_allow_origin = origin
            send_credentials = True
            print(f"[DEBUG PREFLIGHT] Policy: Allowed Specific Origin ({origin}), Credentials True") # Vercel Log
        else:
            # Origin not allowed by configuration
            print(f"[WARN] Preflight origin '{origin}' denied by policy for /lucid.") # Vercel Log
            return make_response('Origin not permitted for CORS preflight', 403)

        # ---- echo back ALL requested headers --------------------
        # Retrieve the headers the browser wants to send in the actual request
        req_hdrs = request.headers.get(
            'Access-Control-Request-Headers', ''
        )  # e.g. "X-Requested-With,Content-Type" or just "Content-Type" etc.
        print(f"[DEBUG PREFLIGHT] Access-Control-Request-Headers received: '{req_hdrs}'") # Vercel Log

        # Construct the response for the preflight request (204 No Content)
        res = make_response('', 204)

        # Build the core CORS headers
        cors_headers = {
            'Access-Control-Allow-Origin': ac_allow_origin,
            'Access-Control-Allow-Methods': 'POST, OPTIONS', # Allowed methods for the actual request
            # Allow the headers the browser requested, default to Content-Type if none specified
            'Access-Control-Allow-Headers': req_hdrs if req_hdrs else 'Content-Type',
            'Access-Control-Max-Age': '86400' # Cache preflight response for 1 day
        }

        # --- Add Allow-Credentials header ONLY if needed and with value 'true' ---
        if send_credentials:
            cors_headers['Access-Control-Allow-Credentials'] = 'true'
            print("[DEBUG PREFLIGHT] Adding Access-Control-Allow-Credentials: true") # Vercel Log
        else:
             print("[DEBUG PREFLIGHT] Not adding Access-Control-Allow-Credentials header") # Vercel Log

        # Update response headers
        res.headers.update(cors_headers)

        print(f"[INFO] Preflight OK for /lucid. Sending 204 with headers: {dict(res.headers)}") # Vercel Log
        return res

    # If not an OPTIONS request for /lucid, proceed to the actual route function
    pass

# --- Application Routes ---

@app.route('/')
def hello_world():
    """
    Root endpoint (/). Primarily serves as a status check and provides a helpful
    HTML page displaying the correct URL needed for the Qualtrics setup,
    if deployed on Vercel (detects via VERCEL_URL env var).
    Also handles basic CORS headers for GET requests to the root.
    """
    print("[INFO] Root route '/' accessed.") # Vercel Log
    origin = request.headers.get('Origin')
    allowed_origins = get_allowed_origins_config()

    # Attempt to get the Vercel deployment URL from environment variables
    # --- Determine the correct backend URL using the incoming request context ---
    backend_url_for_qualtrics = "[Error determining backend URL from request]" # Default/fallback
    backend_url_base = "Unknown"
    try:
        # request.url_root gives "scheme://host:port/" - reflects how user accessed page
        # Strip the trailing '/' and append our specific endpoint path.
        backend_url_base = request.url_root.rstrip('/')
        backend_url_for_qualtrics = f"{backend_url_base}/lucid"
        backend_url_for_qualtrics = html.escape(backend_url_for_qualtrics) # Escape for safety
        print(f"[DEBUG URL] Derived base from request.url_root: {backend_url_base}")
        print(f"[DEBUG URL] Constructed Backend URL for Qualtrics: {backend_url_for_qualtrics}")
    except Exception as e:
        print(f"[ERROR URL] Failed to derive URL from request.url_root: {e}")

    # --- Format the displayed allowed origins ---
    # (Ensure allowed_origins is defined earlier in the function)
    escaped_origins_list = [html.escape(o) for o in allowed_origins]
    if escaped_origins_list == ['*']:
        allowed_origins_display = "<code>*</code> (Any origin - less secure)"
    else:
        allowed_origins_display = ", ".join(f"<code>{o}</code>" for o in escaped_origins_list)
        if not allowed_origins_display:
             allowed_origins_display = "<i>None specified (CORS likely misconfigured/denied)</i>"

    # --- Generate Simplified HTML Page ---
    # Uses only: backend_url_for_qualtrics, allowed_origins_display
    display_html = f"""
    <!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>LUCID Backend Deployed</title>
    <style>
        body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif; padding: 20px; line-height: 1.6; background-color: #f8f9fa; color: #212529; }}
        .container {{ max-width: 750px; margin: 40px auto; padding: 35px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; box-shadow: 0 4px 8px rgba(0,0,0,0.05); }}
        h1 {{ color: #0d6efd; border-bottom: 2px solid #0d6efd; padding-bottom: 10px; margin-bottom: 20px; }}
        h2 {{ color: #495057; margin-top: 30px; border-bottom: 1px solid #ced4da; padding-bottom: 8px;}}
        code {{ background-color: #e9ecef; padding: 0.2em 0.5em; border-radius: 4px; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 0.9em; color: #d63384;}}
        .url-box {{ background-color: #f1f3f5; padding: 12px 18px; border: 1px solid #adb5bd; border-radius: 5px; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; word-wrap: break-word; margin-bottom: 15px; font-size: 1.05em; color: #0b5ed7; }}
        button {{ padding: 10px 18px; cursor: pointer; border-radius: 5px; border: none; background-color: #0d6efd; color: white; font-size: 15px; transition: background-color 0.2s ease; }}
        button:hover {{ background-color: #0b5ed7; }}
        .copied-message {{ color: #198754; font-weight: bold; display: none; margin-left: 10px;}}
        .important {{ background-color: #fff3cd; border: 1px solid #ffeeba; color: #664d03; padding: 15px 20px; border-radius: 5px; margin-top: 20px; }}
        .important code {{ background-color: #fde7a0; color: #664d03; }}
        ul {{ margin-top: 10px; padding-left: 20px; }} li {{ margin-bottom: 5px; }}
        p {{ margin-bottom: 1rem; }}
    </style>
    </head>
    <body><div class="container">
        <h1>LUCID Backend Successfully Deployed!</h1>

        <h2>Next Step: Configure Qualtrics</h2>
        <p>To connect your Qualtrics survey to this backend:</p>
        <ol>
            <li><strong>Copy the full Backend URL below.</strong> This URL should reflect the main production domain when accessed via production. Use this URL for the <code>LUCIDBackendURL</code> Embedded Data field in Qualtrics.</li>
            <li>In your Qualtrics Survey Flow, create or update the Embedded Data field named <code>LUCIDBackendURL</code> and paste this URL as its value.</li>
        </ol>
        <p><strong>Backend URL (Value for <code>LUCIDBackendURL</code>):</strong></p>
        <div id="qualtricsUrlBox" class="url-box">{backend_url_for_qualtrics}</div>
        <button onclick="copyUrl()">Copy Backend URL</button>
        <span id="copiedMsg" class="copied-message">Copied!</span>
    </div>
    <script>function copyUrl() {{ const urlText = document.getElementById('qualtricsUrlBox').innerText; navigator.clipboard.writeText(urlText).then(() => {{ const msg = document.getElementById('copiedMsg'); msg.style.display = 'inline'; setTimeout(() => {{ msg.style.display = 'none'; }}, 2500); }}).catch(err => {{ console.error('Failed to copy: ', err); alert('Failed to copy URL.'); }}); }}</script>
    </body></html>
    """

    # Create Flask response object with the HTML
    resp = make_response(display_html)
    resp.headers['Content-Type'] = 'text/html' # Set correct MIME type

    # Apply basic CORS headers for the root route as well (GET requests usually simpler)
    origin_to_send = None
    send_credentials_get = False # Renamed variable to avoid conflict
    if '*' in allowed_origins:
        origin_to_send = '*'
    elif origin and origin in allowed_origins:
        origin_to_send = origin
        send_credentials_get = True # Allow credentials if specific origin matches
    if origin_to_send:
        resp.headers['Access-Control-Allow-Origin'] = origin_to_send
        resp.headers['Vary'] = 'Origin'
        # Only add credentials header if needed and true
        if send_credentials_get:
            resp.headers['Access-Control-Allow-Credentials'] = 'true'
    return resp

@app.route('/lucid', methods=['POST'])
def lucid():
    """
    Main API endpoint (/lucid).
    Receives chat messages and configuration from Qualtrics frontend via POST request.
    Validates request origin using CORS settings.
    Calls the OpenRouter Chat Completions API.
    Returns the AI's response or an error message in JSON format.
    Includes necessary CORS headers on the response.
    """
    # --- Step 1: CORS Check for POST request ---
    origin = request.headers.get('Origin')
    allowed_origins = get_allowed_origins_config()

    print(f"[DEBUG /lucid] OPENROUTER_API_KEY length: {len(os.getenv('OPENROUTER_API_KEY') or '')}")

    origin_to_send = None
    allow_credentials_post = False
    is_request_allowed = False

    if '*' in allowed_origins:
        origin_to_send = '*'
        is_request_allowed = True
        allow_credentials_post = False
        print("[DEBUG POST /lucid] Policy: Allowed Wildcard (*), Credentials False")
    elif origin and origin in allowed_origins:
        origin_to_send = origin
        is_request_allowed = True
        allow_credentials_post = True
        print(f"[DEBUG POST /lucid] Policy: Allowed Specific Origin ({origin}), Credentials True")
    else:
        is_request_allowed = False
        print(f"[DEBUG POST /lucid] Policy: Denied Origin ({origin})")

    if not is_request_allowed:
        print(f"[WARN] POST to /lucid denied for origin: {origin}.")
        error_resp = make_response(jsonify({'error': 'Forbidden', 'message': 'Origin not permitted.'}), 403)
        if origin_to_send:
            error_resp.headers['Access-Control-Allow-Origin'] = origin_to_send
            error_resp.headers['Vary'] = 'Origin'
            if allow_credentials_post:
                error_resp.headers['Access-Control-Allow-Credentials'] = 'true'
        return error_resp

    print(f"[INFO] ------ Entered lucid function from allowed origin: {origin} ------")
    post_data = request.data
    print(f"[INFO /lucid] Received {len(post_data)} bytes.")

    response_data = {}
    status_code = 500

    try:
        body = json.loads(post_data.decode('utf-8'))

        # --- Step 2: Get API Key ---
        openrouter_api_key = (
            os.getenv('OPENROUTER_API_KEY') or
            os.getenv('openrouter_api_key')
        )

        if isinstance(openrouter_api_key, str) and len(openrouter_api_key) > 7:
            print(f"[DIAGNOSTIC /lucid] OpenRouter API Key Found (Length: {len(openrouter_api_key)}).")
        else:
            print("[CRITICAL /lucid] OPENROUTER_API_KEY not found in environment variables.")

        if not openrouter_api_key:
            response_data = {
                'error': 'Configuration Error',
                'message': 'OpenRouter API key not configured on server.'
            }
            status_code = 500
        else:
            # --- Step 3: Extract parameters from frontend ---
            model = body.get('model', 'gpt-oss-120b:free')
            messages = body.get('messages', [])
            temp_from_frontend = body.get('temperature')
            seed_from_frontend = body.get('seed')

            if not messages or not isinstance(messages, list):
                print("[WARN /lucid] Invalid or empty 'messages' list received.")
                response_data = {'error': 'Bad Request', 'message': 'Messages list is missing, empty, or invalid.'}
                status_code = 400
            else:
                used_temperature = 1.0
                if temp_from_frontend is not None:
                    try:
                        parsed_temp = float(temp_from_frontend)
                        if 0.0 <= parsed_temp <= 2.0:
                            used_temperature = parsed_temp
                        else:
                            print(f"[WARN /lucid] Temp '{parsed_temp}' out of range, using default.")
                    except (ValueError, TypeError):
                        print(f"[WARN /lucid] Invalid temp format ('{temp_from_frontend}'), using default.")
                print(f"[INFO /lucid] Using temperature: {used_temperature}")

                used_seed = None
                if seed_from_frontend is not None:
                    try:
                        used_seed = int(seed_from_frontend)
                    except (ValueError, TypeError):
                        print(f"[WARN /lucid] Invalid seed format ('{seed_from_frontend}'), using default (None).")
                print(f"[INFO /lucid] Using seed: {used_seed}")

                # --- Step 4: Call OpenRouter API ---
                openrouter_url = 'https://openrouter.ai/v1/chat/completions'
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {openrouter_api_key}',
                    'X-Title': 'LUCID Qualtrics Study'
                }
                data_payload = {
                    'model': model,
                    'messages': messages,
                    'temperature': used_temperature
                }
                if used_seed is not None:
                    data_payload['seed'] = used_seed

                print(f"[INFO /lucid] Calling OpenRouter API (model: {model}). Payload keys: {list(data_payload.keys())}")

                response_llm = requests.post(openrouter_url, headers=headers, json=data_payload, timeout=30)

                status = response_llm.status_code
                response_text = response_llm.text

                if status == 200:
                    try:
                        resp_json = response_llm.json()
                        generated_text = resp_json['choices'][0]['message']['content']
                        response_data = {
                            'generated_text': generated_text,
                            'used_temperature': used_temperature
                        }
                        if used_seed is not None:
                            response_data['used_seed'] = used_seed
                        status_code = 200
                        print("[INFO /lucid] Successfully processed OpenRouter response.")
                    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
                        print(f"[ERROR /lucid] OpenRouter response format error: {e}")
                        response_data = {'error': 'Internal Server Error', 'message': 'Invalid response format from AI service.'}
                        status_code = 500
                else:
                    print(f"[ERROR /lucid] OpenRouter API Error ({status}): {response_text}")
                    error_details = response_text
                    try:
                        error_json = response_llm.json()
                        if 'error' in error_json and 'message' in error_json['error']:
                            error_details = error_json['error']['message']
                    except json.JSONDecodeError:
                        pass
                    response_data = {'error': f'AI Service Error ({status})', 'message': error_details}
                    status_code = status if status < 600 else 500

    except requests.exceptions.Timeout:
        print("[ERROR /lucid] Request to OpenRouter timed out.")
        response_data = {'error': 'Gateway Timeout', 'message': 'Request to AI service timed out.'}
        status_code = 504
    except requests.exceptions.RequestException as e:
        print(f"[ERROR /lucid] Network error connecting to OpenRouter: {e}")
        response_data = {'error': 'Service Unavailable', 'message': 'Network error connecting to AI service.'}
        status_code = 503
    except json.JSONDecodeError:
        print("[ERROR /lucid] Invalid JSON received from client.")
        response_data = {'error': 'Bad Request', 'message': 'Invalid JSON format in request body.'}
        status_code = 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR /lucid] Unexpected server error: {e.__class__.__name__}: {e}")
        response_data = {'error': 'Internal Server Error', 'message': 'An unexpected error occurred processing the request.'}
        status_code = 500

    # --- Step 5: Return final response ---
    final_response = make_response(jsonify(response_data), status_code)
    final_response.headers['Access-Control-Allow-Origin'] = origin_to_send
    final_response.headers['Vary'] = 'Origin'
    if allow_credentials_post:
        final_response.headers['Access-Control-Allow-Credentials'] = 'true'
        print("[DEBUG POST /lucid] Adding Access-Control-Allow-Credentials: true to final response")
    else:
        print("[DEBUG POST /lucid] Not adding Access-Control-Allow-Credentials header to final response")
    final_response.headers['Content-Type'] = 'application/json'
    print(f"[INFO /lucid] Responding with status code: {status_code}")
    return final_response

# --- Main Execution Block (for local development) ---
if __name__ == '__main__':
    # This block only runs when the script is executed directly (e.g., `python lucid_api.py`)
    # It's ignored when run by a WSGI server like Vercel's Python runtime.
    print("[INFO] Starting Flask development server...")

    # Optional: Set environment variables locally for testing
    # os.environ['OPENAI_API_KEY'] = 'YOUR_LOCAL_TEST_KEY_HERE' # Use uppercase for testing
    # os.environ['ALLOWED_ORIGINS'] = '*' # Example: Allow all for local testing
    # os.environ['VERCEL_URL'] = 'localhost:8080' # Example for testing the root page

    # Run the Flask development server
    # Debug=True enables auto-reloading and provides detailed error pages (DO NOT use in production)
    local_port = int(os.getenv('PORT', 8080)) # Use PORT env var if set, otherwise default to 8080
    app.run(debug=True, port=local_port, host='0.0.0.0') # Host 0.0.0.0 makes it accessible on network
