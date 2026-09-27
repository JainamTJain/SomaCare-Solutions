-- Upgrade a database created before the sensing spec.
ALTER TABLE event ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE event ADD COLUMN IF NOT EXISTS device_id TEXT;
ALTER TABLE event DROP CONSTRAINT IF EXISTS event_kind_check;
ALTER TABLE event ADD CONSTRAINT event_kind_check CHECK (kind IN (
  'position','movement','presence_start','presence_end','bed_exit',
  'bathroom_trip','bath_start','bath_end','turn','care_visit','camera_offline','heartbeat',
  'stillness','bed_return','night_vitals','device_offline'
));
CREATE TABLE IF NOT EXISTS device (
  id TEXT PRIMARY KEY,
  kind TEXT CHECK (kind IN ('bed_sensor','vision_partner','vision_edge','camera','skin_camera')),
  room_id UUID REFERENCES room,
  resident_id UUID REFERENCES resident,
  installed_at TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  config JSONB,
  active BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS home_install (
  id UUID PRIMARY KEY,
  home_name TEXT,
  steps JSONB,
  updated_at TIMESTAMPTZ
);
