# Wiring Sorety into a hall that already runs

Sorety does not add a second chart, a second schedule, or a second set of morning vitals. It sits on the work the hall already does.

## What stays

- The morning vital-signs round. Blood pressure, pulse, temperature, oxygen, and weight stay on the sheet or the device export the night nurse already files. Sorety reads that chart. The CNA does not type it again.
- Google Calendar, or any calendar that imports an `.ics` file. The file is the same visits already on the shift: one event per stop, fifteen minutes, name and room. The next visit can also be dropped straight onto Google Calendar. There is no parallel task list.
- The care plan the nurse already approved. Camera and model data may only tighten a limit. The diet view does not write an order.

## What is added in the building

One near-infrared camera per bed, about 850 nm, aimed from the foot of the bed toward the head. Power it with the hall's existing PoE switch. No microphone. No network video recorder. Frames are read in memory on a small computer in the corridor closet (one box can cover the hall) and then dropped. Only an event leaves the room: position, confidence, and the rule version `position-v0.0.0-rules`.

A color webcam is rejected. The edge box measures color in the frame. If the picture has chroma, it does not classify position and it does not pretend to be a night camera. SLP has no near-infrared night images, so a night claim waits on consented team recordings. Those recordings are not in this repo.

The phone on the CNA's pocket is the screen. It shows the next person, the infrared position as a moving figure (not a video), the morning chart, and the lines already written into the record. Confirmed turns and changes are the documentation. There is no second note to file for a routine turn the camera saw.

## Diet map

For someone who stays in bed (Braden activity and mobility both 1 or 2), Sorety counts changes and turns the hall already recorded, in four blocks of the day. If changes cluster after the evening meal, dietary sees that pattern. It is labeled a pilot and it is not an order. It does not change the turn limit or the menu by itself.

## What is still not in this repo

- An SLP-trained position model. The live classifier is the shoulder-hip rule.
- A MIMIC-IV risk model. Risk on the floor is the version-1 rule set. MIMIC-IV needs credentialed access and is ICU data, not a long-term-care deployment.
- A skin classifier shown to staff. Captures stay encrypted and `shown_to_staff` stays false.
- Native-speaker sign-off on the Spanish and Tagalog strings.

Access steps are in `docs/data_licenses.md`.
