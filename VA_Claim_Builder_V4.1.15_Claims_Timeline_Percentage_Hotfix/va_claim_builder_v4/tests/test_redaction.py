from core.security.redaction import redact_identifiers

def test_redaction():
    result, counts = redact_identifiers("SSN 123-45-6789 email nick@example.com phone 813-555-1212")
    assert "123-45-6789" not in result
    assert "nick@example.com" not in result
    assert counts["ssn"] == 1
