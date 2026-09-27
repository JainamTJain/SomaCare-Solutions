-- Charted doses. Diuretic and sedating are flags, not guesses from the drug name.
CREATE TABLE IF NOT EXISTS medication_log (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  ts TIMESTAMPTZ,
  medication_name TEXT,
  dose TEXT,
  route TEXT,
  is_diuretic BOOLEAN DEFAULT FALSE,
  is_sedating BOOLEAN DEFAULT FALSE,
  given_by UUID REFERENCES staff,
  scheduled BOOLEAN,
  notes TEXT
);
