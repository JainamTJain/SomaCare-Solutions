-- Consent records, power-of-attorney contacts, and PIN lockout.
ALTER TABLE staff_credential ADD COLUMN IF NOT EXISTS failed_attempts INT DEFAULT 0;
ALTER TABLE staff_credential ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS poa_contact (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  full_name TEXT,
  relationship TEXT,
  email TEXT,
  phone TEXT,
  is_primary BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS consent_record (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  scope TEXT CHECK (scope IN ('position_monitoring','skin_capture','continence_tracking')),
  status TEXT CHECK (status IN ('requested','sent','signed','declined','revoked')),
  explanation_shown TEXT,
  form_version INT,
  requested_by UUID REFERENCES staff,
  requested_at TIMESTAMPTZ,
  sent_to TEXT,
  sent_at TIMESTAMPTZ,
  signed_at TIMESTAMPTZ,
  signature_ref TEXT,
  revoked_at TIMESTAMPTZ,
  revoked_reason TEXT
);
