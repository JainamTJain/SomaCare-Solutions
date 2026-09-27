# Wiring Sorety into a hall that already runs

Sorety does not add a second chart, a second schedule, or a second set of morning vitals. It sits on the work the hall already does.

## What stays

- The morning vital-signs round. Blood pressure, pulse, temperature, oxygen, and weight stay on the sheet or the device export the night nurse already files. Sorety reads that chart. The CNA does not type it again.
- Google Calendar, or any calendar that imports an `.ics` file. The file is the same visits already on the shift: one event per stop, fifteen minutes, name and room. The next visit can also be dropped straight onto Google Calendar. There is no parallel task list.
- The care plan the nurse already approved. Camera and model data may only tighten a limit. The diet view does not write an order.

## What is added in the building

One cheap infrared baby monitor per bed, in the class of a Tapo C210 (about $18–25), aimed from the foot of the bed toward the torso. There is no bed sensor. One shared computer in the home reads each camera over local RTSP at about one frame a second. The microphone stays off. Cloud recording stays off. The camera's internet is blocked at the router. An in-room camera needs written consent or a waiver.

Frames are classified in memory by the shoulder-hip rule (`position-v0.0.0-rules`) and then dropped. That rule is not a language model and it is not trained on SLP. Only an event leaves the computer: position, confidence, the camera id, and that rule version. A color frame is rejected, so a hallway webcam is not treated as the night camera. If the computer hears nothing from a camera for 120 seconds, it marks that monitor offline and the nurse's schedule is used. A frame below the confidence gate is logged and does not reset the pressure timer. A frame marked sheet, blanket, or unknown cover does not reset it either, no matter how high the confidence is. Near-infrared does not see through fabric. Gate 1, the covered-resident test, has not been run. See `docs/gate1_occlusion.md` and `docs/plan_v3.md`.

A real Tapo was not connected in this repo, and a 72-hour soak was not run. The engineer board shows the checklist and the per-camera status from events, not from stored video.

The phone on the CNA's pocket is the screen. It shows the next person, the infrared position as a moving figure (not a video), the morning chart, and the lines already written into the record. Confirmed turns and changes are the documentation. There is no second note to file for a routine turn the camera saw.

## Diet map

For someone who stays in bed (Braden activity and mobility both 1 or 2), Sorety counts changes and turns the hall already recorded, in four blocks of the day. If changes cluster after the evening meal, dietary sees that pattern. It is labeled a pilot and it is not an order. It does not change the turn limit or the menu by itself.

## What is still not in this repo

- An SLP-trained position model. The live classifier is the shoulder-hip rule.
- A MIMIC-IV risk model. Risk on the floor is the version-1 rule set. MIMIC-IV needs credentialed access and is ICU data, not a long-term-care deployment.
- A skin classifier shown to staff. Captures stay encrypted and `shown_to_staff` stays false.
- Native-speaker sign-off on the Spanish and Tagalog strings.

Access steps are in `docs/data_licenses.md`.
