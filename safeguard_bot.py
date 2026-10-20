import streamlit as st
import os
import datetime
import requests
import base64

# =====================================================================================
# ⚙️ MASTER BUSINESS & ADMINISTRATIVE GLOBAL SETTINGS
# =====================================================================================
PREMIUM_DURATION_DAYS = 90

# API keys are stored in .streamlit/secrets.toml, never in this source file.
# The app tries Key 1 first, then Key 2 if the request fails.
def get_gemini_api_keys():
    keys = []
    for name in ("GEMINI_API_KEY_1", "GEMINI_API_KEY_2"):
        try:
            value = st.secrets.get(name, "")
        except Exception:
            value = ""
        if value and value not in keys:
            keys.append(value)

    # Backward compatibility with an existing single key if configured.
    try:
        old_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        old_key = os.getenv("GEMINI_API_KEY", "")
    if old_key and old_key not in keys:
        keys.append(old_key)
    return keys

try:
    YOUR_PERSONAL_UPI_ID = st.secrets.get("UPI_ID", "YOUR_UPI_ID")
except Exception:
    YOUR_PERSONAL_UPI_ID = os.getenv("UPI_ID", "YOUR_UPI_ID")
SUBSCRIPTION_PRICE = "9"
COMPANY_NAME = "DigiNebula"
GEMINI_MODEL = "gemini-3.8-flash"  # Change to a model ID enabled for your API projects.
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def generate_with_key_fallback(contents_payload):
    """Try both configured Gemini keys. Timeout and transient HTTP errors trigger fallback."""
    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise RuntimeError(
            "No Gemini API key configured. Add GEMINI_API_KEY_1 and GEMINI_API_KEY_2 "
            "to .streamlit/secrets.toml."
        )

    payload = {"contents": [{"parts": contents_payload}]}
    errors = []

    for index, api_key in enumerate(api_keys, start=1):
        try:
            response = requests.post(
                GEMINI_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=payload,
                timeout=(10, 90),
            )
            if response.status_code in (408, 429, 500, 502, 503, 504):
                errors.append(f"Key {index}: HTTP {response.status_code}")
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            errors.append(f"Key {index}: request timed out")
        except requests.exceptions.ConnectionError:
            errors.append(f"Key {index}: connection error")
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            # Avoid printing response bodies that could contain sensitive details.
            errors.append(f"Key {index}: HTTP {status}")
            # Try the other key for this request as well.
        except requests.exceptions.RequestException as exc:
            errors.append(f"Key {index}: network request failed ({type(exc).__name__})")
        except ValueError:
            errors.append(f"Key {index}: server returned invalid JSON")

    raise RuntimeError("All configured Gemini keys failed. " + "; ".join(errors))

# =====================================================================================
# 🧠 AI ENGINE RULES INFRASTRUCTURE
# =====================================================================================
PROMPT_INSTRUCTION = (
    "You are the DigiNebula AI engine. Your task is to process the user's uploaded assignment—which may be "
    "provided as raw text, a programming code block, or a photograph of handwritten notebook pages (including math, "
    "science, Hindi, or engineering code).\n"
    "1. If an image is provided, perform high-precision OCR to read the handwriting or code cleanly.\n"
    "2. Rewrite the vocabulary, sentence layout, formatting, or variable names while preserving the original meaning.\n"
    "3. CRITICAL FOR ALL SUBJECTS:\n"
    "   - For Coding: Change variable names or structure when appropriate while preserving correct logic.\n"
    "   - For Math/Science: Keep core formulas, numerical derivations, and constants identical.\n"
    "   - For Hindi/Theory: Rewrite using contextual synonyms while maintaining the exact original meaning.\n"
    "4. Reply ONLY with the final rewritten text or code."
)

# =====================================================================================
# 💾 PERSISTENT FILE-BASED DATABASE STORAGE ENGINE (LOCAL MACHINE LAYER)
# =====================================================================================
DB_FILE = "database.txt"


def load_user_database():
    if not os.path.exists(DB_FILE):
        return {"free_credits": 3, "activation_date": "None"}
    try:
        with open(DB_FILE, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                return {"free_credits": int(lines[0]), "activation_date": lines[1]}
    except:
        pass
    return {"free_credits": 3, "activation_date": "None"}


def save_user_database(credits_count, activation_date_str):
    with open(DB_FILE, "w") as f:
        f.write(f"{credits_count}\n{activation_date_str}")


user_data = load_user_database()
if "free_credits" not in st.session_state:
    st.session_state.free_credits = user_data["free_credits"]
if "activation_date" not in st.session_state:
    st.session_state.activation_date = user_data["activation_date"]
if "processed_output" not in st.session_state:
    st.session_state.processed_output = ""
if "output_language" not in st.session_state:
    st.session_state.output_language = "text"

is_currently_premium = False

if st.session_state.activation_date != "None":
    try:
        activation_time = datetime.datetime.strptime(
            st.session_state.activation_date, "%Y-%m-%d %H:%M:%S"
        )
        time_elapsed = datetime.datetime.now() - activation_time
        if time_elapsed.days < PREMIUM_DURATION_DAYS:
            is_currently_premium = True
        else:
            st.session_state.activation_date = "None"
            st.session_state.free_credits = 0
            save_user_database(0, "None")
    except:
        pass

# =====================================================================================
# 🎨 WEB SYSTEM DISPLAY WINDOW (CHROME ENGINE LAYOUT)
# =====================================================================================
st.set_page_config(page_title="Campus Safeguard | DigiNebula", layout="centered")

if os.path.exists("logo.png"):
    st.image("logo.png", width=180)
elif os.path.exists("logo.png.png"):
    st.image("logo.png.png", width=180)

st.title("Campus Safeguard")
st.caption("🚀 An Advanced Multimodal Web App powered by DigiNebula AI Systems")
st.markdown("---")

if st.session_state.free_credits <= 0 and not is_currently_premium:
    st.error("⚠️ **Free Access Limits Exhausted!**")
    st.markdown(
        f"### Unlock DigiNebula Premium for the Whole Semester Cycle\n"
        f"You have used up all your complimentary trial parses. Upgrade right now to get **unlimited submissions** "
        f"for the next **{PREMIUM_DURATION_DAYS} Days**."
    )

    upi_intent_string = (
        f"upi://pay?pa={YOUR_PERSONAL_UPI_ID}&pn={COMPANY_NAME}"
        f"&am={SUBSCRIPTION_PRICE}&cu=INR"
    )
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📱 Mobile App Link:")
        st.markdown(
            f'<a href="{upi_intent_string}" style="display: inline-block; padding: 12px 24px; '
            f'background-color: #7928CA; color: white; text-align: center; text-decoration: none; '
            f'font-weight: bold; border-radius: 8px; width: 100%;">⚡ Tap Here to Pay (GPay/PhonePe)</a>',
            unsafe_allow_html=True
        )

    with col2:
        st.markdown("#### 💻 Desktop/Laptop QR Scan:")
        st.warning(
            f"🔹 **Amount:** ₹{SUBSCRIPTION_PRICE}\n"
            f"🔹 **UPI ID:** `{YOUR_PERSONAL_UPI_ID}`"
        )

    st.markdown("---")
    st.markdown("### 📥 Activation Validation")
    utr_number = st.text_input(
        "Enter your 12-digit UPI Transaction Ref Number / UTR below after making payment:",
        placeholder="e.g. 629481039572"
    )

    st.caption("Note: Entering a UTR checks only its format; it does not independently verify that payment was received.")

    if st.button("🔓 Verify Payment & Activate System", type="secondary"):
        if len(utr_number.strip()) == 12 and utr_number.isdigit():
            timestamp_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.activation_date = timestamp_now
            st.session_state.free_credits = 999999
            save_user_database(999999, timestamp_now)
            st.success(
                f"🌟 **Account Activated for {PREMIUM_DURATION_DAYS} Days!**"
            )
            st.rerun()
        else:
            st.error(
                "❌ Invalid UTR parameters. Please paste a valid 12-digit numeric bank code."
            )

else:
    uploaded_file = st.file_uploader(
        "📸 Drop a notebook photo or upload your assignment file here:",
        type=["py", "java", "cpp", "txt", "png", "jpg", "jpeg", "pdf"]
    )

    user_input = st.text_area(
        "📝 Or, paste your assignment text/code manually below if not using a file/image:",
        placeholder="Drop text here...",
        height=150
    )

    if not is_currently_premium:
        st.info(
            f"📊 Account Status: Free Launch Batch "
            f"({st.session_state.free_credits} Free Credits Remaining)"
        )
    else:
        st.success(
            f"🌟 Account Status: Corporate Premium Pass "
            f"(Active for {PREMIUM_DURATION_DAYS} Days)"
        )

    if st.button("📤 Rewrite & Clear Plagiarism", type="primary"):
        contents_payload = []

        # Inject structural API layout
        contents_payload.append({"text": PROMPT_INSTRUCTION})

        if uploaded_file is not None:
            file_extension = uploaded_file.name.split(".")[-1].lower()

            # Process images and PDFs as inline file data
            if file_extension in ["png", "jpg", "jpeg", "pdf"]:
                try:
                    file_bytes = uploaded_file.read()
                    encoded_file = base64.b64encode(file_bytes).decode("utf-8")
                    if file_extension == "pdf":
                        mime_type = "application/pdf"
                    else:
                        mime_type = f"image/{'jpeg' if file_extension == 'jpg' else file_extension}"

                    contents_payload.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": encoded_file
                        }
                    })
                except Exception as file_err:
                    st.error(f"❌ File processing error: {file_err}")

            # Process plain text and code files
            else:
                try:
                    text_data = uploaded_file.read().decode("utf-8")
                    contents_payload.append({"text": text_data})
                except Exception as txt_err:
                    st.error(f"❌ Text decode error: {txt_err}")

        if user_input.strip():
            contents_payload.append({"text": user_input.strip()})

        if len(contents_payload) <= 1:
            st.warning(
                "⚠️ Please upload a file/image or enter text strings before triggering AI engines."
            )
        else:
            with st.spinner(
                "🌌 DigiNebula engines are processing your assignment..."
            ):
                try:
                    response_json = generate_with_key_fallback(contents_payload)

                    # Safely parse the generated text
                    candidates = response_json.get("candidates", [])
                    if not candidates:
                        api_message = response_json.get("error", {}).get("message", "")
                        if api_message:
                            raise ValueError(f"Gemini returned no text candidate: {api_message}")
                        raise ValueError("Gemini returned no text candidate. Try a different file or prompt.")

                    parts = candidates[0].get("content", {}).get("parts", [])
                    output_text = "\n".join(
                        part["text"] for part in parts if "text" in part
                    ).strip()
                    if not output_text:
                        raise ValueError("Gemini returned an empty result. Please try again.")

                    st.session_state.processed_output = output_text
                    st.session_state.output_language = (
                        file_extension
                        if uploaded_file is not None and file_extension in ["py", "java", "cpp"]
                        else "markdown"
                    )

                    if not is_currently_premium:
                        st.session_state.free_credits = max(0, st.session_state.free_credits - 1)
                        save_user_database(
                            st.session_state.free_credits,
                            st.session_state.activation_date
                        )
                        st.rerun()

                except Exception as api_err:
                    st.error("❌ Gemini is temporarily unavailable or the request could not be completed.")
                    st.caption(str(api_err))

    # Keep the latest processed result visible on subsequent Streamlit reruns
    if st.session_state.processed_output:
        st.markdown("### 📥 Processed Output:")
        st.code(
            st.session_state.processed_output,
            language=st.session_state.output_language
        )
