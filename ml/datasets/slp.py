"""SLP in-bed pose loader.

Home-setting participants are split 70 / 15 / 17. The hospital subset and the
team's own recordings are held out of training entirely.

Horizontal flips swap left and right. Forgetting that swap teaches the model
the wrong side.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

HOME_SPLIT = (70, 15, 17)
LABELS = ("back", "left", "right", "sitting", "out_of_bed")
_SIDE_SWAP = {"left": "right", "right": "left"}
_JOINT_SWAP = {
    "left_shoulder": "right_shoulder",
    "right_shoulder": "left_shoulder",
    "left_hip": "right_hip",
    "right_hip": "left_hip",
    "left_knee": "right_knee",
    "right_knee": "left_knee",
    "left_ankle": "right_ankle",
    "right_ankle": "left_ankle",
}


@dataclass
class PositionExample:
    participant_id: str
    label: str
    cover: str
    image: np.ndarray
    keypoints: dict | None = None
    setting: str = "home"  # home, hospital, team


@dataclass
class PositionDataset:
    examples: list[PositionExample]
    augment: bool = False
    flip_prob: float = 0.5
    seed: int = 0
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> PositionExample:
        example = self.examples[index]
        if self.augment and self._rng.random() < self.flip_prob:
            return horizontal_flip(example)
        return example


def split_participants(
    participant_ids: list[str],
    n_train: int,
    n_val: int,
    n_test: int,
    seed: int = 0,
) -> tuple[list[str], list[str], list[str]]:
    """Subject-wise split. No person appears in more than one part."""
    unique = sorted(set(participant_ids))
    if len(unique) != n_train + n_val + n_test:
        raise ValueError(
            f"split {n_train}/{n_val}/{n_test} does not partition {len(unique)} participants"
        )
    shuffled = unique[:]
    random.Random(seed).shuffle(shuffled)
    train = shuffled[:n_train]
    val = shuffled[n_train : n_train + n_val]
    test = shuffled[n_train + n_val :]
    parts = (set(train), set(val), set(test))
    if parts[0] & parts[1] or parts[0] & parts[2] or parts[1] & parts[2]:
        raise RuntimeError("subject split overlapped")
    return train, val, test


def assert_held_out(train_ids: list[str], held_out_ids: list[str]) -> None:
    overlap = set(train_ids) & set(held_out_ids)
    if overlap:
        raise ValueError(f"held-out participants leaked into training: {sorted(overlap)[:5]}")


def horizontal_flip(example: PositionExample) -> PositionExample:
    """Flip the image and swap left/right labels and joint names."""
    flipped = np.flip(example.image, axis=1).copy()
    label = _SIDE_SWAP.get(example.label, example.label)
    keypoints = None
    if example.keypoints:
        width = example.image.shape[1]
        keypoints = {}
        for name, point in example.keypoints.items():
            swapped = _JOINT_SWAP.get(name, name)
            x, y, conf = point
            keypoints[swapped] = (width - 1 - x, y, conf)
    return PositionExample(
        participant_id=example.participant_id,
        label=label,
        cover=example.cover,
        image=flipped,
        keypoints=keypoints,
        setting=example.setting,
    )


def training_recipe() -> dict:
    """Model A hyperparameters from the spec. Used by ml/position/train.py."""
    return {
        "optimizer": "AdamW",
        "learning_rate": 3.0e-4,
        "weight_decay": 1.0e-4,
        "schedule": "cosine",
        "epochs": 30,
        "warmup_epochs": 2,
        "batch_size": 64,
        "loss": "cross_entropy",
        "label_smoothing": 0.05,
        "augmentations": {
            "grayscale": "always",
            "horizontal_flip": 0.5,
            "rotation_degrees": 15,
            "brightness_contrast": 0.3,
            "gaussian_noise": 0.02,
            "gaussian_blur": 0.2,
            "random_erasing": 0.25,
        },
        "balance": "sample evenly across cover conditions",
        "flip_swaps_left_right": True,
    }
