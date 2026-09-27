"""A skin window opens only during care that is already happening."""

from turnwise.skinwindow import skin_window


def test_skin_window_needs_consent_and_an_uncovered_bath():
    blocked = skin_window(consent_signed=False, persons_in_zone=2, lights_on=True, keypoint_visibility=0.9)
    assert blocked == {"open": False, "reason": "consent_missing"}
    dark = skin_window(consent_signed=True, persons_in_zone=2, lights_on=False, keypoint_visibility=0.9)
    assert dark["reason"] == "lights_off"
    alone = skin_window(consent_signed=True, persons_in_zone=1, lights_on=True, keypoint_visibility=0.9)
    assert alone["reason"] == "no_second_person"
    covered = skin_window(consent_signed=True, persons_in_zone=2, lights_on=True, keypoint_visibility=0.2)
    assert covered["reason"] == "occluded"
    open_window = skin_window(consent_signed=True, persons_in_zone=2, lights_on=True, keypoint_visibility=0.9)
    assert open_window == {"open": True, "reason": "care_already_happening"}


def test_discovery_rejects_another_vendors_cloud():
    from edge.capture.discover import compatibility_report

    report = compatibility_report(
        [
            {"name": "room-12", "rtsp": "rtsp://192.168.1.20/stream1", "infrared": True},
            {"name": "SafelyYou hall", "vendor": "safelyyou", "rtsp": "rtsp://cloud.safelyyou.com/a", "infrared": True},
            {"name": "color webcam", "rtsp": "rtsp://192.168.1.21/stream1", "infrared": False},
        ],
        continence_note=None,
        live_scan=False,
    )
    assert report["live_scan"] is False
    assert report["usable_count"] == 1
    reasons = {row["reason"] for row in report["not_usable"]}
    assert "cloud_or_no_local_rtsp" in reasons
    assert "no_infrared" in reasons