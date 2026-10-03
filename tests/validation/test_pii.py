from pharmasense.validation.pii import scrub_text, scrub_messages
from pharmasense.llm.contracts import Message

def test_scrub_ssn():
    assert scrub_text("My SSN is 123-45-6789.") == "My SSN is [REDACTED_PII]."

def test_scrub_phone():
    assert scrub_text("Call me at 555-123-4567") == "Call me at [REDACTED_PII]"

def test_scrub_email():
    assert scrub_text("Email test@example.com") == "Email [REDACTED_PII]"
    
def test_scrub_patient_id():
    assert scrub_text("Patient PT-12345") == "Patient [REDACTED_PII]"

def test_scrub_messages():
    messages = [Message(role="user", content="Call 555-123-4567")]
    scrubbed = scrub_messages(messages)
    assert scrubbed[0].content == "Call [REDACTED_PII]"
    assert messages[0].content == "Call 555-123-4567" # original untouched
