# Sorety plan v3

Sep 27, 2026. Sequence first. The care engine, the three-language app, and the alert audit stay. New caregiver-facing features wait until Gate 1 reports, including a negative report.

The honesty rules that already hold stay in force. Pressure ulcers prevented are not estimated. Position events are `position-v0.0.0-rules`, a shoulder-hip geometry, not an SLP-trained model. No language model scores care. Skin images are not shown to staff. Spanish and Tagalog still need a native-speaking CNA before a real pilot. Demo rows are Harbor House seed data. "Tested" in this repo means pytest on that seed and on synthetic trials. It does not mean a resident under a blanket.

## The sensing claim

A near-infrared baby monitor sees reflected light off whatever is in view. A blanket blocks that light. The academic in-bed pose sets pair a camera with a pressure mat or a depth sensor for this reason. Sorety does not have that second sensor. A confident camera label under a cover is the unsafe failure: the fusion would treat it as a reposition and clear a timer. The engine now refuses that. Cover `sheet`, `blanket`, or `unknown` stays `uncertain` and does not reset the clock. Cover `none` can reset in the lab and is stored as `per_side_unvalidated`. Gate 1 status is `not_run`. Protocol: `docs/gate1_occlusion.md`.

A failed Gate 1 narrows the claim to movement and stillness, with no per-side pressure budget from the camera. That fallback is a decision, not a device. This repository does not ship bed-sensor firmware, an Emfit adapter, or an AltumView adapter.

## Frozen until Gate 1 reports

- New caregiver-facing features.
- Skin and wound image analysis. Research track, no date. Automatic wound characterization is the kind of function counsel has to scope before it is a feature. It is not in the investor story.
- A MIMIC-IV risk model. No clinical or data-use partner.
- Multi-home operator tooling.
- Real-time Google Calendar sync. The shift already exports one `.ics` file and a link for the next visit. That stays. A live two-way sync does not get built.

## Gates

Each one is a go or a no-go.

| Gate | Question | Fail means |
| --- | --- | --- |
| 1 | On labeled trials, what are agreement, uncertain rate, and false-confirmed rate for no cover, a sheet, and a blanket, kept separate? | No per-side claim from the camera. Do not keep polishing the same architecture. |
| 2 | After a real pilot, does a home keep paying, and does the acquisition cost from `docs/cac.md` fit the price the home will actually bear? | Stop expansion spend. |

Gate 1 has not been run. Gate 2 has not been run. There is no paid pilot and no hour of sensor data on a resident.

## Market, as hypotheses

California board-and-care homes are small, often about six residents, private-pay, and licensed one home at a time. A price of $59 per resident per month and a target of $50 million ARR imply on the order of 70,600 monitored residents, which at about five beds a home is on the order of 14,000 homes. That arithmetic is a hypothesis to falsify. It is not a forecast. Nothing here models multi-state expansion or a move into assisted living as a finished plan.

Competitors, one sentence each, so the wedge is explicit:

- SafelyYou sells camera fall detection and care insights into memory-care chains and already has clinical data and enterprise relationships.
- Inspiren AUGi sells into assisted living and skilled nursing with the same kind of head start.
- Emfit-class bed sensors detect movement and tossing. They do not name which side a body is on, and Sorety does not integrate one.
- AltumView Sentinare is stick-figure sensing for this use case. It is a competitor now, not a reserved partner.

The wedge to test, not to assume: a six-bed home run by one or two live-in caregivers is a small, high-touch sale those companies have not had to win. Moving upmarket later means competing with them after they have had more years of evidence. There is no Medicare or Medicaid code identified for this service in board and care. Willingness to pay is whatever a thin-margin private home will spend out of pocket.

## Money, as hypotheses

Do not read a cell as a plan to defend. The pilot is what would replace it. Ulcers prevented stay unestimated.

| Scenario | Price per resident per month | Residents for $50M ARR | Homes at 5 beds | What would have to be true |
| --- | --- | --- | --- | --- |
| Implicit case in the earlier plan | $59 | about 70,600 | about 14,100 | Vision works under blankets. California board and care alone is enough. No reimbursement. |
| Sensing narrows to movement and stillness | $35 | about 119,000 | about 23,800 | The claim is weaker. Likely needs more than one state. |
| Vision works, and only about 30% of California's small homes are reachable | $59 | about 70,600 | more homes than that reachable base | Expansion past board and care, into buyers SafelyYou and Inspiren already sell to. |

Hardware under $50 a bed is a list-price remark about a shared computer at four or more cameras. It is not an installed cost. Small homes can land above that before labor and replacement. The acquisition formula, with a fully labeled guess illustration, is `docs/cac.md`. The highest-leverage unknown is the cost to acquire one paying home.

## Regulatory, unscoped

Two questions for a healthcare attorney, unanswered here. Treat the answers as gates.

1. Does automatic skin-image analysis trigger FDA software-as-a-medical-device review?
2. What does California actually require before an in-room camera runs for a resident whose consent goes through a power of attorney?

Also unscoped: HIPAA, California CMIA, and biometric-adjacent rules. Position, continence, and charted vitals on a named resident are sensitive. The demo database is local SQLite (`resident_data: demo_only` on `/health`). No real resident data belongs on it.

A missed alert before a pressure injury or a fall is a foreseeable harm. Before any paid pilot the paperwork has to say the product supplements caregiver rounds and does not replace them, and someone has to own the insurance question. That language is not only a line in the app.

No clinical or licensing advisor is named in this repository.

## Pitch

Say this in your own words. The second paragraph is the boundary. Do not cross it in the room.

In a six-bed care home, one caregiver is awake all night doing two things on a schedule: turning residents, and checking if they are wet. Those are two interruptions, and the proof is a paper log if it exists at all. Sorety is built to collapse both into one sensor-driven check, hold it against the nurse's plan, and wake someone when a window is about to be missed. A confirmed turn becomes a timestamped record an inspector, a hospice partner, or a family can look at. The care engine, the alerts, and a caregiver app in three languages run on seeded data. The open question is whether the camera can tell a resident was repositioned under a blanket. That experiment is Gate 1. It has not been run. If vision cannot see through the cover, the claim narrows to whether a reposition happened, and that narrower claim is also unvalidated because there is no bed sensor here yet.

Do not say the camera works under a blanket. Do not say ulcers were prevented. Do not say $50 million is a forecast. "Tested end to end" means the software on Harbor House seed, not a night in a real room.

Fall detection reports something that already went wrong. This product is aimed at a missed window on a care plan, and at the record of the visit. SafelyYou and Inspiren already sell monitoring as a safety cost into larger buildings. The six-bed wedge is the bet that they will not chase that sale first. It is a bet, and it should be said that way.

Close on the reframe: the workload problem is real, merging the two checks is the unit of the product, and the hard sensing claim gets proved before the easy software is scaled.
