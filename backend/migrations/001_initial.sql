-- Pilot schema. Clinical tables follow the engineering spec.
-- Braden total is generated so a stored score cannot drift from its subscales.

CREATE TABLE facility (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL
);
CREATE TABLE unit (
  id UUID PRIMARY KEY,
  facility_id UUID REFERENCES facility,
  name TEXT
);
CREATE TABLE room (
  id UUID PRIMARY KEY,
  unit_id UUID REFERENCES unit,
  label TEXT,
  camera_ref TEXT,
  camera_class TEXT CHECK (camera_class IN ('none','position_only','position_and_skin')),
  bed_zone JSONB,
  analysis_enabled BOOLEAN DEFAULT TRUE,
  hallway_order INT DEFAULT 0
);
CREATE TABLE resident (
  id UUID PRIMARY KEY,
  room_id UUID REFERENCES room,
  preferred_name TEXT NOT NULL,
  language TEXT,
  consent_position BOOLEAN DEFAULT FALSE,
  consent_skin_capture BOOLEAN DEFAULT FALSE,
  admitted_at DATE
);
CREATE TABLE staff (
  id UUID PRIMARY KEY,
  role TEXT CHECK (role IN ('cna','nurse','charge_nurse','admin')),
  display_name TEXT,
  ui_language TEXT CHECK (ui_language IN ('en','es','tl'))
);
CREATE TABLE shift (
  id UUID PRIMARY KEY,
  unit_id UUID REFERENCES unit,
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ
);
CREATE TABLE assignment (
  shift_id UUID REFERENCES shift,
  staff_id UUID REFERENCES staff,
  resident_id UUID REFERENCES resident,
  PRIMARY KEY (shift_id, resident_id)
);
CREATE TABLE braden_assessment (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  assessed_at TIMESTAMPTZ,
  sensory SMALLINT,
  moisture SMALLINT,
  activity SMALLINT,
  mobility SMALLINT,
  nutrition SMALLINT,
  friction_shear SMALLINT,
  total SMALLINT GENERATED ALWAYS AS (sensory+moisture+activity+mobility+nutrition+friction_shear) STORED
);
CREATE TABLE risk_factor (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  factor TEXT,
  source TEXT,
  confirmed_by UUID REFERENCES staff,
  confirmed_at TIMESTAMPTZ
);
CREATE TABLE plan (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  version INT,
  lying_limit_min INT,
  sitting_limit_min INT,
  night_lying_limit_min INT,
  continence_threshold REAL,
  mattress_type TEXT,
  two_person BOOLEAN,
  approved_by UUID REFERENCES staff,
  approved_at TIMESTAMPTZ,
  reason TEXT,
  status TEXT CHECK (status IN ('draft','approved','retired')),
  suggestion JSONB
);
CREATE TABLE preference (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  category TEXT CHECK (category IN ('turning','continence','comfort','communication')),
  code TEXT,
  params JSONB,
  text_en TEXT,
  text_es TEXT,
  text_tl TEXT,
  translated_flags JSONB,
  source_type TEXT,
  source_excerpt TEXT,
  source_date DATE,
  approved_by UUID REFERENCES staff,
  approved_at TIMESTAMPTZ
);
CREATE TABLE event (
  id BIGSERIAL PRIMARY KEY,
  room_id UUID REFERENCES room,
  resident_id UUID REFERENCES resident,
  ts TIMESTAMPTZ NOT NULL,
  kind TEXT CHECK (kind IN ('position','movement','presence_start','presence_end','bed_exit',
    'bathroom_trip','bath_start','bath_end','turn','care_visit','camera_offline','heartbeat',
    'stillness','bed_return','night_vitals','device_offline')),
  value JSONB,
  confidence REAL,
  model_version TEXT,
  source TEXT CHECK (source IS NULL OR source IN ('bed_sensor','vision','camera','manual')),
  device_id TEXT
);
CREATE TABLE continence_obs (
  id BIGSERIAL PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  kind TEXT CHECK (kind IN ('charted_wet','charted_dry','sensor_wet','bathroom_trip','change')),
  ts TIMESTAMPTZ,
  interval_start TIMESTAMPTZ
);
CREATE TABLE task (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  kind TEXT CHECK (kind IN ('turn','continence','check','meal','medication','bath','skin_capture')),
  due_at TIMESTAMPTZ,
  window_min INT,
  merged_into UUID REFERENCES task,
  source TEXT,
  status TEXT CHECK (status IN ('open','done','verified','skipped','escalated')),
  priority REAL DEFAULT 0,
  detail JSONB
);
CREATE TABLE alert (
  id UUID PRIMARY KEY,
  task_id UUID REFERENCES task,
  staff_id UUID REFERENCES staff,
  created_at TIMESTAMPTZ,
  rule TEXT,
  inputs JSONB,
  plan_version INT,
  model_version TEXT,
  status TEXT CHECK (status IN ('sent','accepted','passed','resolved','escalated')),
  accepted_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  charge_notified BOOLEAN DEFAULT FALSE
);
CREATE TABLE skin_capture (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  area TEXT,
  ts TIMESTAMPTZ,
  source TEXT CHECK (source IN ('phone','room')),
  image_ref TEXT,
  quality REAL,
  model_flag TEXT,
  model_version TEXT,
  shown_to_staff BOOLEAN DEFAULT FALSE
);
CREATE TABLE skin_assessment (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  area TEXT,
  ts TIMESTAMPTZ,
  finding TEXT CHECK (finding IN ('normal','blanchable_redness','nonblanchable_redness','stage2','stage3','stage4','unstageable','dti','iad')),
  warmth BOOLEAN,
  firmness BOOLEAN,
  pain BOOLEAN,
  assessed_by UUID REFERENCES staff
);
CREATE TABLE override (
  id UUID PRIMARY KEY,
  target_type TEXT,
  target_id UUID,
  by_staff UUID REFERENCES staff,
  reason TEXT,
  ts TIMESTAMPTZ
);
CREATE TABLE resident_state (
  resident_id UUID PRIMARY KEY REFERENCES resident,
  load JSONB,
  relief_since JSONB,
  last_known TEXT,
  position TEXT,
  last_ts TIMESTAMPTZ,
  confidence REAL,
  persons_in_zone INT,
  camera_online BOOLEAN,
  camera_spectrum TEXT DEFAULT 'infrared',
  settled BOOLEAN,
  model_version TEXT,
  last_change_at TIMESTAMPTZ,
  moist_minutes_24h REAL,
  night_movements_per_hour REAL
);
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT now(),
  staff_id UUID,
  action TEXT,
  target_type TEXT,
  target_id TEXT,
  detail JSONB
);
CREATE TABLE staff_credential (
  staff_id UUID PRIMARY KEY REFERENCES staff,
  pin_hash TEXT,
  pin_salt TEXT
);
CREATE TABLE help_request (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  requester_id UUID REFERENCES staff,
  teammate_id UUID REFERENCES staff,
  created_at TIMESTAMPTZ,
  eta_min INT,
  status TEXT
);
CREATE TABLE handoff_note (
  id UUID PRIMARY KEY,
  staff_id UUID REFERENCES staff,
  shift_id UUID REFERENCES shift,
  created_at TIMESTAMPTZ,
  audio_ref TEXT,
  transcript TEXT,
  transcript_status TEXT,
  text_note TEXT
);
CREATE TABLE morning_vital (
  id UUID PRIMARY KEY,
  resident_id UUID REFERENCES resident,
  recorded_on DATE,
  recorded_at TIMESTAMPTZ,
  systolic INT,
  diastolic INT,
  pulse INT,
  temp_c REAL,
  spo2 INT,
  weight_kg REAL,
  source TEXT,
  UNIQUE (resident_id, recorded_on)
);
CREATE TABLE ingest_batch (
  id UUID PRIMARY KEY,
  source_name TEXT,
  checksum TEXT,
  created_at TIMESTAMPTZ,
  summary JSONB,
  UNIQUE (source_name, checksum)
);
CREATE TABLE device (
  id TEXT PRIMARY KEY,
  kind TEXT CHECK (kind IN ('bed_sensor','vision_partner','vision_edge','camera')),
  room_id UUID REFERENCES room,
  resident_id UUID REFERENCES resident,
  installed_at TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  config JSONB,
  active BOOLEAN DEFAULT TRUE
);
CREATE TABLE home_install (
  id UUID PRIMARY KEY,
  home_name TEXT,
  steps JSONB,
  updated_at TIMESTAMPTZ
);
