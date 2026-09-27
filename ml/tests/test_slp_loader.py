"""The position loader swaps left and right when it flips, and splits by person."""

import numpy as np

from datasets.slp import (
    HOME_SPLIT,
    PositionDataset,
    PositionExample,
    assert_held_out,
    horizontal_flip,
    split_participants,
)


def _image() -> np.ndarray:
    image = np.zeros((8, 10), dtype=np.uint8)
    image[:, :2] = 255
    return image


def test_horizontal_flip_swaps_left_and_right():
    keypoints = {"left_shoulder": (1, 2, 0.9), "right_shoulder": (8, 2, 0.8)}
    left = PositionExample("p1", "left", "none", _image(), keypoints)
    flipped = horizontal_flip(left)
    assert flipped.label == "right"
    assert flipped.image[0, -1] == 255
    assert flipped.image[0, 0] == 0
    # x is mirrored and the joint name moves to the other side.
    assert "right_shoulder" in flipped.keypoints
    assert flipped.keypoints["right_shoulder"][0] == 10 - 1 - 1

    right = horizontal_flip(PositionExample("p1", "right", "sheet", _image()))
    assert right.label == "left"
    back = horizontal_flip(PositionExample("p1", "back", "blanket", _image()))
    assert back.label == "back"


def test_dataset_flip_path_uses_the_swap():
    example = PositionExample("p1", "left", "none", _image())
    dataset = PositionDataset([example], augment=True, flip_prob=1.0, seed=0)
    assert dataset[0].label == "right"


def test_home_split_is_subject_wise_and_hospital_is_held_out():
    ids = [f"home-{i:03d}" for i in range(sum(HOME_SPLIT))]
    train, val, test = split_participants(ids, *HOME_SPLIT, seed=1)
    assert len(train) == 70 and len(val) == 15 and len(test) == 17
    assert set(train).isdisjoint(val)
    assert set(train).isdisjoint(test)
    assert set(val).isdisjoint(test)
    hospital = [f"hosp-{i}" for i in range(7)]
    assert_held_out(train, hospital)
    try:
        assert_held_out(train, [train[0]])
    except ValueError:
        pass
    else:
        raise AssertionError("leak was not caught")
