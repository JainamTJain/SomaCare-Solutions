# Demo bath photos

Name each photo `room{ID}_{site}_t{careMinute}[_nurse-{finding}].jpg`

- ID: resident id 1 to 6 (see backend/somacare_live/seed_residents.json)
- site: sacrum, lhip, rhip or heels
- careMinute: minutes after 22:00 when the photo is "taken" in the replay (a 3 min clip at
  time scale 60 covers minutes 0 to 180)
- optional nurse finding applied 7 minutes later: intact, blanch, stage1 or stage2

Example: `room6_rhip_t75_nurse-blanch.jpg`

Only photos we own and have consent to publish: team members' skin, or a makeup mark staged the
way nursing schools do. Never real residents, never dataset images (PIID is not ours to share).
Files with other names are skipped with a message.
