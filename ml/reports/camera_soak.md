# Camera soak

Status: **not run**. No Tapo C210 or C113 was connected. No ONVIF discovery was run against a live network. No 72-hour soak was run.

| Check | Result |
| --- | --- |
| RTSP from a real camera reaches `POST /events` | not run |
| ONVIF discovery on a site network | not run |
| 10-minute run leaves no image file | not run on hardware. The in-memory pipeline test still writes no file. |
| Audio dropped | the reader never opens an audio track. Not confirmed on a Tapo. |
| Infrared only | color frames are rejected in unit tests. Not confirmed on a Tapo night stream. |
| Latency from a real position change to an event | not run. No H3 target was measured. |
| Dropped frames, CPU temperature | not run |

Engineer-board camera rows for Harbor House are seeded. Each one is marked `simulated: true` and `live: false`. They are not this camera's uptime.

A discovered SafelyYou or Inspiren address is classified not usable, because Sorety does not read another vendor's cloud. That classifier is unit-tested with fake records. It has not scanned a building.
