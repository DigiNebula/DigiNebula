import os
import re
import base64
import datetime as dt
import requests
import streamlit as st

st.set_page_config(page_title="Campus Safeguard | DigiNebula", layout="centered")

PREMIUM_DURATION_DAYS = 90
SUBSCRIPTION_PRICE = 9
COMPANY_NAME = "DigiNebula"
GEMINI_MODEL = "gemini-3.8-flash"  # Keep your configured model; verify it is enabled for your API project.
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


SUPABASE_URL = secret("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = secret("SUPABASE_KEY") or secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = secret("SUPABASE_SERVICE_ROLE_KEY")
ADMIN_PASSWORD = secret("ADMIN_PASSWORD")
UPI_ID = secret("UPI_ID", "YOUR_UPI_ID")


def supabase_request(method, path, token=None, service=False, params=None, payload=None, prefer=None):
    key = SUPABASE_SERVICE_ROLE_KEY if service else SUPABASE_KEY
    if not SUPABASE_URL or not key:
        raise RuntimeError("Supabase settings are missing. Check Streamlit Secrets.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {token or key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    response = requests.request(
        method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers,
        params=params, json=payload, timeout=20
    )
    if not response.ok:
        # Do not expose database response bodies or credentials in the UI.
        raise RuntimeError(f"Supabase request failed (HTTP {response.status_code}). Check schema and RLS policies.")
    return response.json() if response.text else None


def auth_request(endpoint, payload):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/{endpoint}",
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        json=payload, timeout=20
    )
    if not response.ok:
        try:
            message = response.json().get("msg") or response.json().get("message")
        except Exception:
            message = None
        raise RuntimeError(message or f"Authentication failed (HTTP {response.status_code}).")
    return response.json()


def get_profile(user_id, token):
    rows = supabase_request(
        "GET", "profiles", token=token,
        params={"select": "user_id,free_credits,premium_until", "user_id": f"eq.{user_id}", "limit": "1"}
    )
    if not rows:
        raise RuntimeError("Profile not found. Run the SQL migration below, then log out and log in again.")
    return rows[0]


def is_premium(profile):
    value = profile.get("premium_until")
    if not value:
        return False
    try:
        expiry = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=dt.timezone.utc)
        return expiry > dt.datetime.now(dt.timezone.utc)
    except (ValueError, TypeError):
        return False


def consume_credit(token):
    result = supabase_request("POST", "rpc/consume_credit", token=token, payload={})
    if isinstance(result, int):
        if result < 0:
            raise RuntimeError("No free credits remain.")
        return result
    raise RuntimeError("Credit function returned an unexpected result. Run the SQL migration.")


def get_gemini_api_keys():
    keys = []
    for name in ("GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY"):
        value = secret(name)
        if value and value not in keys:
            keys.append(value)
    return keys


def generate_with_key_fallback(parts):
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("Add GEMINI_API_KEY_1 or GEMINI_API_KEY_2 to Streamlit Secrets.")
    errors = []
    payload = {"contents": [{"parts": parts}]}
    for number, key in enumerate(keys, start=1):
        try:
            response = requests.post(
                GEMINI_URL,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload, timeout=(10, 90)
            )
            if response.status_code in (408, 429, 500, 502, 503, 504):
                errors.append(f"Key {number}: HTTP {response.status_code}")
                continue
            if not response.ok:
                errors.append(f"Key {number}: HTTP {response.status_code}")
                continue
            return response.json()
        except requests.exceptions.RequestException as exc:
            errors.append(f"Key {number}: {type(exc).__name__}")
        except ValueError:
            errors.append(f"Key {number}: invalid JSON")
    raise RuntimeError("Gemini requests failed. " + "; ".join(errors))


PROMPT = (
    "Rewrite the user's assignment, code, or handwritten notes while preserving meaning and correctness. "
    "Read images carefully. Keep mathematical formulas, constants, and derivations correct. "
    "For code, preserve intended logic. Reply only with the final rewritten text or code."
)


def submit_payment(user_id, token, utr):
    if not re.fullmatch(r"[A-Za-z0-9]{8,30}", utr):
        raise ValueError("Enter a transaction reference containing 8–30 letters or digits.")
    # The unique database constraint prevents a UTR from being reused.
    supabase_request(
        "POST", "payments", token=token,
        payload={"user_id": user_id, "utr": utr, "amount": SUBSCRIPTION_PRICE, "status": "pending"},
        prefer="return=minimal"
    )


def get_payment_history(user_id, token):
    return supabase_request(
        "GET", "payments", token=token,
        params={"select": "utr,amount,status,created_at", "user_id": f"eq.{user_id}",
                "order": "created_at.desc", "limit": "10"}
    )


def review_payment(utr, approve):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Admin review is not configured.")
    if not re.fullmatch(r"[A-Za-z0-9]{8,30}", utr):
        raise ValueError("Enter a valid UTR.")
    # One database RPC performs payment status and premium updates in a single transaction.
    rpc = "admin_approve_payment" if approve else "admin_reject_payment"
    supabase_request("POST", f"rpc/{rpc}", service=True, payload={"p_utr": utr})


# -------------------- SESSION --------------------
for key, default in {
    "access_token": "", "refresh_token": "", "user_id": "", "email": "",
    "processed_output": "", "output_language": "text", "admin_authenticated": False,
    "admin_login_attempts": 0, "admin_locked_until": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def sign_out():
    for key in ("access_token", "refresh_token", "user_id", "email", "processed_output"):
        st.session_state[key] = ""
    st.rerun()


def refresh_session_if_needed():
    token = st.session_state.access_token
    refresh = st.session_state.refresh_token
    if not token or not refresh:
        return
    # Refresh proactively when the JWT is near expiry; if parsing fails, leave it to API response.
    try:
        import json
        segment = token.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        exp = json.loads(base64.urlsafe_b64decode(segment.encode()).decode()).get("exp", 0)
        if exp > int(dt.datetime.now(dt.timezone.utc).timestamp()) + 60:
            return
    except Exception:
        return
    data = auth_request("token?grant_type=refresh_token", {"refresh_token": refresh})
    st.session_state.access_token = data["access_token"]
    st.session_state.refresh_token = data.get("refresh_token", refresh)
    if data.get("user"):
        st.session_state.user_id = data["user"]["id"]
        st.session_state.email = data["user"].get("email", st.session_state.email)


# -------------------- PAGE --------------------
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Set SUPABASE_URL and SUPABASE_KEY in Streamlit Secrets.")
    st.stop()

if os.path.exists("logo.png"):
    st.image("logo.png", width=180)
elif os.path.exists("logo.png.png"):
    st.image("logo.png.png", width=180)

st.title("Campus Safeguard")
st.caption("An AI-powered assignment rewriting tool by DigiNebula")
st.divider()

if not st.session_state.access_token:
    st.subheader("Account")
    mode = st.radio("Choose an option", ["Log in", "Create account"], horizontal=True)
    with st.form("auth_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(mode, type="primary")
    if submitted:
        if not email.strip() or not password:
            st.error("Enter your email and password.")
        else:
            try:
                if mode == "Create account":
                    data = auth_request("signup", {"email": email.strip(), "password": password})
                    if not data.get("access_token"):
                        st.success("Account created. Confirm your email if required, then log in.")
                    else:
                        st.session_state.access_token = data["access_token"]
                        st.session_state.refresh_token = data.get("refresh_token", "")
                        st.session_state.user_id = data["user"]["id"]
                        st.session_state.email = data["user"].get("email", email.strip())
                        st.rerun()
                else:
                    data = auth_request("token?grant_type=password", {"email": email.strip(), "password": password})
                    st.session_state.access_token = data["access_token"]
                    st.session_state.refresh_token = data.get("refresh_token", "")
                    st.session_state.user_id = data["user"]["id"]
                    st.session_state.email = data["user"].get("email", email.strip())
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not {mode.lower()}: {exc}")
    st.stop()

try:
    refresh_session_if_needed()
except Exception:
    sign_out()

st.caption(f"Signed in as {st.session_state.email}")
if st.button("Log out"):
    sign_out()

try:
    profile = get_profile(st.session_state.user_id, st.session_state.access_token)
except Exception as exc:
    st.error(f"Could not load profile: {exc}")
    st.info("Confirm the SQL migration has run. If your session is old, log out and log in again.")
    st.stop()

premium = is_premium(profile)
credits = int(profile.get("free_credits", 0))

# -------------------- PAYMENT SCREEN --------------------
if not premium and credits <= 0:
    st.error("Your free credits have been used.")
    st.subheader(f"Premium access — ₹{SUBSCRIPTION_PRICE} for {PREMIUM_DURATION_DAYS} days")
    st.write("Pay by UPI. Premium is activated only after manual payment verification.")
    upi_url = f"upi://pay?pa={UPI_ID}&pn={COMPANY_NAME}&am={SUBSCRIPTION_PRICE}&cu=INR"
    st.markdown(f"[Pay ₹{SUBSCRIPTION_PRICE} using your UPI app]({upi_url})")
    st.write(f"UPI ID: `{UPI_ID}`")
    with st.form("payment_form"):
        utr = st.text_input("UPI transaction reference / UTR")
        payment_submitted = st.form_submit_button("Submit for manual approval")
    if payment_submitted:
        try:
            submit_payment(st.session_state.user_id, st.session_state.access_token, utr.strip())
            st.success("Payment reference submitted. Premium remains locked until approved.")
        except Exception as exc:
            st.error(f"Payment submission failed: {exc}. A duplicate UTR may already exist.")
    st.subheader("Recent payment submissions")
    try:
        history = get_payment_history(st.session_state.user_id, st.session_state.access_token)
        if history:
            st.dataframe(history, use_container_width=True, hide_index=True)
        else:
            st.caption("No payment submissions yet.")
    except Exception as exc:
        st.warning(f"Could not load payment history: {exc}")
    st.stop()

# -------------------- ASSIGNMENT REWRITER --------------------
if premium:
    st.success(f"Premium active until {profile.get('premium_until')}")
else:
    st.info(f"Free credits remaining: {credits}")

uploaded = st.file_uploader(
    "Upload assignment, code, photo, or PDF",
    type=["py", "java", "cpp", "txt", "png", "jpg", "jpeg", "pdf"],
)
typed = st.text_area("Or paste assignment text/code", height=150)

if st.button("Rewrite assignment", type="primary"):
    parts = [{"text": PROMPT}]
    extension = ""
    has_input = False
    if uploaded is not None:
        extension = uploaded.name.rsplit(".", 1)[-1].lower()
        raw = uploaded.read()
        if extension in ("png", "jpg", "jpeg", "pdf"):
            mime = "application/pdf" if extension == "pdf" else ("image/jpeg" if extension in ("jpg", "jpeg") else "image/png")
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("utf-8")}})
        else:
            try:
                parts.append({"text": raw.decode("utf-8")})
            except UnicodeDecodeError:
                st.error("The uploaded text/code file is not UTF-8 encoded.")
                st.stop()
        has_input = True
    if typed.strip():
        parts.append({"text": typed.strip()})
        has_input = True
    if not has_input:
        st.warning("Upload a file or enter text first.")
    else:
        # Reserve/deduct a free credit before calling Gemini to prevent concurrent free use.
        credit_reserved = False
        try:
            if not premium:
                remaining = consume_credit(st.session_state.access_token)
                credit_reserved = True
                credits = remaining
            with st.spinner("DigiNebula is processing your submission..."):
                result = generate_with_key_fallback(parts)
                candidates = result.get("candidates", [])
                response_parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                output = "\n".join(p["text"] for p in response_parts if isinstance(p, dict) and "text" in p).strip()
                if not output:
                    detail = result.get("error", {}).get("message", "")
                    raise RuntimeError(detail or "Gemini returned no text. Try again.")
                st.session_state.processed_output = output
                st.session_state.output_language = extension if extension in ("py", "java", "cpp") else "text"
                st.rerun()
        except Exception as exc:
            if credit_reserved:
                st.warning("A free credit was reserved before processing. If Gemini failed, contact support to request a credit review.")
            st.error(f"Could not process submission: {exc}")

if st.session_state.processed_output:
    if st.button("Clear processed output"):
        st.session_state.processed_output = ""
        st.session_state.output_language = "text"
        st.rerun()
    st.subheader("Processed output")
    st.code(st.session_state.processed_output, language=st.session_state.output_language)
    st.download_button("Download output", st.session_state.processed_output, file_name="rewritten_output.txt", mime="text/plain")

# -------------------- ADMIN PAYMENT REVIEW --------------------
st.divider()
with st.expander("Admin: review payments"):
    if not SUPABASE_SERVICE_ROLE_KEY or not ADMIN_PASSWORD:
        st.warning("Admin review is disabled. Configure SUPABASE_SERVICE_ROLE_KEY and ADMIN_PASSWORD in Streamlit Secrets.")
    elif not st.session_state.admin_authenticated:
        locked_until = st.session_state.admin_locked_until
        if locked_until and dt.datetime.now(dt.timezone.utc) < locked_until:
            st.warning("Admin login is temporarily locked after repeated failed attempts.")
        else:
            with st.form("admin_login"):
                entered = st.text_input("Admin password", type="password")
                unlock = st.form_submit_button("Unlock admin review")
            if unlock:
                if entered == ADMIN_PASSWORD:
                    st.session_state.admin_authenticated = True
                    st.session_state.admin_login_attempts = 0
                    st.session_state.admin_locked_until = None
                    st.rerun()
                else:
                    st.session_state.admin_login_attempts += 1
                    if st.session_state.admin_login_attempts >= 5:
                        st.session_state.admin_locked_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
                        st.session_state.admin_login_attempts = 0
                    st.error("Incorrect admin password.")
    else:
        st.caption("Approve only after verifying payment in your UPI/bank app.")
        review_utr = st.text_input("UTR to review", key="review_utr")
        left, right = st.columns(2)
        with left:
            if st.button("Approve payment"):
                try:
                    review_payment(review_utr.strip(), True)
                    st.success("Payment approved and premium activated.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Approval failed: {exc}")
        with right:
            if st.button("Reject payment"):
                try:
                    review_payment(review_utr.strip(), False)
                    st.success("Payment rejected.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Rejection failed: {exc}")
        if st.button("Lock admin review"):
            st.session_state.admin_authenticated = False
            st.rerun()
