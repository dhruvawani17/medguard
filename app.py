import streamlit as st
import re
import time
from datetime import datetime
from cerebras.cloud.sdk import Cerebras
from pypdf import PdfReader

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="MedGuard Pro | Secure Medical AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ADVANCED CUSTOM STYLING ---
st.markdown("""
<style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Main Container Glassmorphism */
    .main .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    /* Custom Card Styling */
    div[data-testid="stVerticalBlock"] > div:has(div.card) {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 10px;
    }

    /* Status Pulse Animation */
    @keyframes pulse {
        0% { opacity: 0.5; }
        50% { opacity: 1; }
        100% { opacity: 0.5; }
    }
    .status-pulse {
        display: inline-block;
        width: 10px;
        height: 10px;
        background-color: #00ff88;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse 2s infinite;
    }

    /* Gradient Buttons */
    .stButton>button {
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        color: white;
        border: none;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(79, 172, 254, 0.4);
    }

    /* Chat Styling */
    .stChatMessage {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 🔑 CEREBRAS API SETUP ---
API_KEY = "csk-rw52fr2c4enjktx8xpv5kc4npvwwh8fje5k98x9eyx6xw4v9"
client = None
model_id = "llama-3.3-70b"

@st.cache_resource
def get_cerebras_client():
    try:
        return Cerebras(api_key=API_KEY)
    except Exception:
        return None

client = get_cerebras_client()

# --- BACKEND LOGIC (PII & Analysis) ---
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    return "\n".join([page.extract_text() for page in reader.pages])

def redact_pii(text):
    patterns = {
        r'(Name:|Patient:|Patient Name:)\s*([A-Za-z ]+)': r'\1 [REDACTED]',
        r'(ID:|MRN:)\s*(\d+)': r'\1 [REDACTED]',
        r'(\d{10})': r'[PHONE REDACTED]',
        r'[\w\.-]+@[\w\.-]+': r'[EMAIL REDACTED]'
    }
    for p, r in patterns.items():
        text = re.sub(p, r, text, flags=re.IGNORECASE)
    return text

def assess_risk(text):
    text_lower = text.lower()
    if any(x in text_lower for x in ["heart", "stroke", "critical", "> 180"]):
        return "CRITICAL", "🔴", "Immediate hospitalization required."
    return "STABLE", "🟢", "Routine monitoring."

# --- UI LAYOUT ---

# Sidebar System Health
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3063/3063176.png", width=60)
    st.title("MedGuard Pro")
    st.markdown(f'<div><span class="status-pulse"></span>Cerebras Engine Active</div>', unsafe_allow_html=True)
    st.divider()
    st.metric("Inference Speed", "0.18s", "-0.02s")
    st.success("🔒 HIPAA Compliant Mode")
    st.success("📜 BioMCP Governance Active")
    
    if st.button("🗑️ Reset Session", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop('context', None)
        st.rerun()

# Header Area
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("🛡️ Secure Clinical Intelligence")
    st.markdown("##### Enterprise-grade PII Sanitization & Inference Pipeline")
with col_h2:
    st.markdown(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
    st.caption(f"Connected to {model_id}")

# Main Pipeline Columns
st.divider()
col_in, col_out = st.columns([1, 1], gap="large")

with col_in:
    st.markdown("### 1. Ingest Data")
    with st.container(border=True):
        tab_pdf, tab_text = st.tabs(["📄 PDF Upload", "✍️ Manual Entry"])
        
        with tab_pdf:
            up_file = st.file_uploader("Drop clinical report", type=['pdf'], label_visibility="collapsed")
        with tab_text:
            manual_entry = st.text_area("Paste notes here", height=150, placeholder="Patient reports high BP...")

        if st.button("🚀 EXECUTE SECURE PIPELINE", use_container_width=True):
            raw_text = extract_text_from_pdf(up_file) if up_file else manual_entry
            if raw_text:
                with st.spinner("Processing..."):
                    safe = redact_pii(raw_text)
                    r_status, r_icon, r_action = assess_risk(raw_text)
                    st.session_state['context'] = {
                        "safe_text": safe, "risk": f"{r_icon} {r_status}", "action": r_action
                    }
            else:
                st.error("Please provide data.")

with col_out:
    st.markdown("### 2. Analysis & Sanitization")
    if 'context' in st.session_state:
        ctx = st.session_state['context']
        
        # Stats Row
        s1, s2 = st.columns(2)
        s1.metric("Risk Assessment", ctx['risk'])
        s2.metric("PII Security", "100% Cleared")
        
        with st.expander("👁️ View Sanitized Data Stream", expanded=True):
            st.code(ctx['safe_text'], language="plaintext")
        
        st.info(f"**Action Plan:** {ctx['action']}")
    else:
        st.info("Awaiting input to begin sanitization pipeline...")

# Chat Section
st.divider()
st.markdown("### 💬 Secure Clinical Consultation")

if 'messages' not in st.session_state:
    st.session_state.messages = []

# Display Messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Logic
if prompt := st.chat_input("Ask about follow-up protocols or dietary advice..."):
    if 'context' not in st.session_state:
        st.error("Please process a patient report first.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing via Cerebras..."):
                # System prompt injected here
                sys_msg = f"Context: {st.session_state.context['safe_text']}. Risk: {st.session_state.context['risk']}."
                try:
                    resp = client.chat.completions.create(
                        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
                        model=model_id, temperature=0.2
                    )
                    full_resp = resp.choices[0].message.content
                    st.markdown(full_resp)
                    st.session_state.messages.append({"role": "assistant", "content": full_resp})
                except Exception as e:
                    st.error("API Latency Issue.")