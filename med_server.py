from mcp.server.fastmcp import FastMCP
import re

# Initialize the MCP Server
mcp = FastMCP("MedGuard-Secure-Pipeline")


MEDICAL_GUIDELINES = {
    "high_bp": "Standard Protocol: Reduce sodium intake, increase aerobic exercise, monitor daily. Consult cardiologist if > 160/100.",
    "low_vitamin_d": "Standard Protocol: Supplement 600-800 IU daily, increase sun exposure (15 mins/day).",
    "high_glucose": "Standard Protocol: Fasting required. Immediate Hba1c test recommended. Reduce simple carbs."
}

@mcp.tool()
def redact_patient_info(text: str) -> str:
    """
    SECURITY TOOL: Scans the medical report and removes Patient Names and IDs 
    BEFORE sending data to the external AI model.
    Prevents Data Exfiltration.
    """
    
    redacted_text = re.sub(r'(Patient Name:|Name:)\s*([A-Za-z ]+)', r'\1 [REDACTED]', text)
    redacted_text = re.sub(r'(ID:|Patient ID:)\s*(\d+)', r'\1 [REDACTED-ID]', redacted_text)
    
    return f"SECURE_LOG: PII Removed.\nSanitized Text: {redacted_text}"

@mcp.tool()
def check_trusted_guidelines(condition: str) -> str:
    """
    GOVERNANCE TOOL: Looks up medical conditions in the HOSPITAL APPROVED database.
    Prevents AI Hallucinations.
    """
    # Normalize input
    key = condition.lower().replace(" ", "_")
    
    # Check if we have a protocol
    protocol = MEDICAL_GUIDELINES.get(key)
    
    if protocol:
        return f"AUTHORIZED PROTOCOL FOUND: {protocol}"
    else:
        return "WARNING: No authorized protocol found in hospital database. Advise manual doctor review."

# Start the server
if __name__ == "__main__":
    mcp.run()