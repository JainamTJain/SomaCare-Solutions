# Photos for the website skin check

Put the 15-20 photos you want visitors to try here (jpg, png or webp, any size).
Then run `python backend/tools/score_site_photos.py --out <FRONTEND>/public/demo/photos`.
It scores each photo once with the real model, resizes it to 1024 px, removes phone metadata
(including GPS location), and writes manifest.json with the results. Originals here are not pushed.
