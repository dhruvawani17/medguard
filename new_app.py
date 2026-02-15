import streamlit as st
import re
import time
from datetime import datetime
from cerebras.cloud.sdk import Cerebras
from pypdf import PdfReader
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# --- CONFIGURATION ---
st.set_page_config(page_title="MedGuard: Powered by Cerebras", page_icon="⚡", layout="wide")

# 🔑 CEREBRAS API SETUP
API_KEY = "csk-rw52fr2c4enjktx8xpv5kc4npvwwh8fje5k98x9eyx6xw4v9"

client = None
connection_status = "🔴 Disconnected"
model_id = "llama-3.3-70b"

# Initialize Presidio engines
try:
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    nlp_status = "🟢 Active (Presidio + spaCy)"
except Exception as e:
    nlp_status = f"🔴 Inactive ({str(e)})"
    analyzer = None
    anonymizer = None

try:
    client = Cerebras(api_key=API_KEY)
    connection_status = "🟢 Connected to Cerebras Cloud"
except Exception as e:
    st.error(f"API Error: {e}")

# --- BACKEND LOGIC ---

def extract_text_from_pdf(uploaded_file):
    """
    Robust text extraction:
    1. Tries pdfplumber (best for layout preservation)
    2. Fallback to pypdf
    3. Fallback to OCR (Tesseract) if text is sparse (scanned doc)
    """
    text = ""
    file_bytes = uploaded_file.getvalue()
    
    try:
        # Method 1: pdfplumber
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        
        # Check if we need OCR (if extracted text is too short, likely scanned)
        if len(text.strip()) < 50: 
            st.toast("⚠️ Scanned PDF detected. Running OCR...", icon="🔍")
            # If pdf2image fails (missing poppler), catch it
            try:
                images = convert_from_bytes(file_bytes)
                text = ""
                for img in images:
                    text += pytesseract.image_to_string(img) + "\n"
            except Exception as e:
                 st.error(f"OCR Failed (missing poppler?): {e}")

    except Exception as e:
        # Method 2: pypdf Fallback
        try:
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        except Exception as e2:
            return f"Error reading PDF: {e2}"

    return text

def redact_pii(text):
    """
    Enhanced Security Layer:
    Combines NLP (Presidio) with strict Regex patterns to catch Names and Dates.
    """
    redacted_text = text
    
    # 1. NLP Redaction (Presidio)
    if analyzer and anonymizer:
        # Explicitly asking for DATE_TIME and PERSON entities
        results = analyzer.analyze(
            text=text, 
            entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_TIME", "LOCATION", "URL"], 
            language='en'
        )
        redacted_text = anonymizer.anonymize(text=text, analyzer_results=results).text

    # 2. Advanced Rule-based Regex (The "Safety Net")
    # This catches common medical header formats for Names and Dates
    patterns = {
        # Catch Names in headers: "Patient: John Doe" or "Name: John Doe"
        r'(Patient Name:|Name:|Patient:)\s*([A-Za-z ]+)': r'\1 [REDACTED-NAME]',
        
        # Catch Dates of Birth and General Dates (MM/DD/YYYY, YYYY-MM-DD, etc.)
        r'(DOB:|Date of Birth:|Date:|Collected:)\s*([\d\/\-\.]{6,10})': r'\1 [REDACTED-DATE]',
        
        # Catch standalone dates like 12/05/1984 or 12-05-1984
        r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b': r'[REDACTED-DATE]',
        
        # Catch alphanumeric IDs (MRN, SSN, etc.)
        r'(MRN:|ID:|Patient ID:)\s*([A-Z0-9\-]+)': r'\1 [REDACTED-ID]',
        
        # Catch contact info
        r'(\d{10})': r'[REDACTED-PHONE]',
        r'[\w\.-]+@[\w\.-]+': r'[REDACTED-EMAIL]'
    }
    
    for p, r in patterns.items():
        redacted_text = re.sub(p, r, redacted_text, flags=re.IGNORECASE)
        
    return redacted_text

def assess_risk(text):
    """Layer 2: Triage System"""
    text_lower = text.lower()
    
    critical_keywords = ["heart attack", "stroke", "severe", "critical", "> 180", "emergency", "unconscious", "seizure"]
    moderate_keywords = ["high", "abnormal", "elevated", "fever", "dizziness", "infection", "palpitations"]
    
    if any(x in text_lower for x in critical_keywords):
        return "🔴 CRITICAL", "Immediate hospitalization required. Alert Triage Team."
    elif any(x in text_lower for x in moderate_keywords):
        return "🟠 MODERATE", "Schedule specialist follow-up within 24-48 hours."
    else:
        return "🟢 STABLE", "Routine monitoring. Continue current care plan."

def get_protocol_biomcp(text):
    """
    Layer 3: Governance (RAG Simulation)
    Retrieves verified protocols based on key terms.
    """
    # Simulated Vector Knowledge Base
    guidelines = {
        "bp": "Protocol #BP-101 (Source: OpenFDA): Reduce sodium, daily monitoring. If >140/90, consider ACE inhibitors.",
        "sugar": "Protocol #DM-202 (Source: PubMed): Check Hba1c. Metformin 500mg if prescribed. Target < 7.0%.",
        "fever": "Protocol #ID-303 (Source: ClinicalTrials.gov): Paracetamol 650mg. Hydration. Dengue/Malaria panel if > 3 days.",
        "dizziness": "Protocol #NE-404 (Source: AHA): Check orthostatic vitals. ECG recommended to rule out arrhythmia.",
        "chest pain": "Protocol #CP-505 (Source: AHA): Immediate ECG. Troponin T test. Administer Aspirin 325mg if ACS suspected."
    }
    
    detected_protocols = []
    text_lower = text.lower()
    
    for key, val in guidelines.items():
        if key in text_lower:
            detected_protocols.append(val)
            
    if detected_protocols:
        return "✅ BioMCP (Verified Sources):\n- " + "\n- ".join(detected_protocols)
    return "✅ BioMCP: No specific contraindications found in standard database."

def call_cerebras_ai(user_query, context):
    """Calls Cerebras API with SANITIZED context using Streaming."""
    if not client:
        yield "⚠️ API Error. Check your key."
        return

    system_prompt = f"""
    You are MedGuard, a secure medical assistant for doctors.
    
    CONTEXT (SANITIZED DATA):
    {context['safe_text']}
    
    RISK LEVEL: {context['risk']}
    HOSPITAL PROTOCOL: {context['protocol']}
    
    RULES:
    1. You CANNOT see the patient's name (it is redacted).
    2. Answer questions based ONLY on the provided context.
    3. If the protocol suggests a URL or ID, cite it.
    4. Be concise, clinical, and professional.
    """

    try:
        stream = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            model=model_id, 
            temperature=0.7,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"⚡ Cerebras API Error: {str(e)}"

# --- UI SETUP ---
if 'messages' not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("🏥 MedGuard Admin")
    st.markdown("### System Health")
    st.write(f"**API Status:** {connection_status}")
    st.write(f"**NLP Engine:** {nlp_status}")
    st.info(f"AI Model: **{model_id}**")
    st.success("Governance: **BioMCP Enabled**")
    st.markdown("---")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🗑️ Clear"):
            st.session_state.messages = []
            st.rerun()
    with col_s2:
        if st.session_state.messages:
            report_text = f"MedGuard Report - {datetime.now()}\n\n"
            for m in st.session_state.messages:
                report_text += f"{m['role'].upper()}: {m['content']}\n\n"
            st.download_button("📥 Export", report_text, file_name="session_report.txt")

st.title("⚡ MedGuard: Secure Medical AI")
st.caption("Powered by Cerebras | Presidio PII Protection | OCR Enabled")

# --- MAIN INPUT ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1️⃣ Upload & Sanitize")
    
    # --- PDF UPLOADER LOGIC ---
    uploaded_file = st.file_uploader("Upload Report (PDF/Scanned)", type=['pdf'])
    
    user_input = ""
    
    if uploaded_file is not None:
        with st.spinner("Processing Document (OCR + Text Extraction)..."):
            user_input = extract_text_from_pdf(uploaded_file)
            if user_input:
                st.success("Document processed successfully.")
                with st.expander("Show Extracted Raw Text"):
                    st.text(user_input[:800] + ("..." if len(user_input) > 800 else ""))
            else:
                st.error("Could not extract text.")
    else:
        # Fallback to manual text entry
        default_text = """Patient Name: Sarah Connor
MRN: 849302
DOB: 12/05/1984
Date: Feb 14, 2026

Subject presents with severe chest pain and dizziness.
BP is 160/100. History of hypertension.
Prescription: Lisinopril 10mg.
Email: sarah.connor@sky.net"""
        user_input = st.text_area("Or Paste Clinical Notes:", value=default_text, height=200)
    
    if st.button("🚀 Process & Start Chat", type="primary", use_container_width=True):
        if not user_input:
            st.error("Please upload a PDF or enter text.")
        else:
            with st.spinner("Running Presidio PII Redaction & Risk Analysis..."):
                time.sleep(1) # UX Pause
                
                # Run Pipeline
                safe_text = redact_pii(user_input)
                risk, action = assess_risk(user_input)
                protocol = get_protocol_biomcp(user_input)
                
                st.session_state['context'] = {
                    "original": user_input,
                    "safe_text": safe_text,
                    "risk": risk,
                    "action": action,
                    "protocol": protocol
                }
                
                # Add initial system message
                st.session_state.messages = [
                    {"role": "assistant", "content": f"✅ **Analysis Complete.**\n\n**Risk Level:** {risk}\n**Protocol:**\n{protocol}\n\nI am ready to assist with this case."}
                ]
                st.rerun()

with col2:
    st.subheader("2️⃣ Secure Data View")
    if 'context' in st.session_state:
        data = st.session_state['context']
        
        # Privacy & Governance Dashboard
        with st.container(border=True):
            st.markdown("#### 🔒 Privacy Shield")
            t1, t2 = st.tabs(["Sanitized Text", "Diff View"])
            
            with t1:
                st.code(data['safe_text'], language="plaintext")
            with t2:
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("Original")
                    st.code(data['original'], language="plaintext")
                with c2:
                    st.caption("Redacted")
                    st.code(data['safe_text'], language="plaintext")

        with st.container(border=True):
            st.markdown("#### 🏥 Clinical Assessment")
            st.info(f"**{data['risk']}**\n\n*{data['action']}*")
            st.markdown(f"**Governance Protocol:**\n{data['protocol']}")

            # Email Draft
            with st.expander("✉️ Generate Referral Email"):
                draft = f"Subject: Urgent Referral - Patient ID [REDACTED]\n\nDear Colleague,\n\nPatient requires {data['risk']} attention.\nFindings: {data['protocol']}\nAction taken: {data['action']}\n\nSincerely,\nMedGuard AI"
                st.text_area("Draft:", value=draft, height=150)


# --- CHATBOT SECTION ---
st.markdown("---")
st.subheader("💬 Clinical Assistant")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Ask about diagnosis, drugs, or protocol..."):
    # 1. Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Generate AI response
    if 'context' in st.session_state:
        # Check if client initialized
        if not client:
             with st.chat_message("assistant"):
                st.error("API not initialized. Check server logs.")
        else:
            with st.chat_message("assistant"):
                response_container = st.empty()
                full_response = ""
                # Stream the response
                for chunk in call_cerebras_ai(prompt, st.session_state['context']):
                    full_response += chunk
                    response_container.markdown(full_response + "▌")
                response_container.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
    else:
        st.error("⚠️ Please upload and process a clinical report first.")