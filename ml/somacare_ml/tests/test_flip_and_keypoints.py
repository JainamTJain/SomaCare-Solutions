import numpy as np
from somacare_ml.position.features import swap_lr, flip_image
from somacare_ml.position import keypoints, synth
from somacare_ml.position.train import featurize


def test_swap_lr():
    assert swap_lr("left") == "right" and swap_lr("right") == "left"
    assert swap_lr("back") == "back" and swap_lr("sitting") == "sitting"


def test_flip_twice_is_identity():
    img = synth.render("left", "none", 1, np.random.default_rng(0))
    assert np.array_equal(flip_image(flip_image(img)), img)


def test_flip_augmentation_doubles_data_with_swapped_labels():
    rng = np.random.default_rng(0)
    bg = synth.empty_background()
    ds = [(synth.render("left", "none", 1, rng), "left", 1, "none")]
    X, y, person, cover = featurize(ds, bg, flip_augment=True)
    assert list(y) == ["left", "right"]


def test_mirror_landmarks_swaps_pairs_and_is_an_involution():
    lm = np.random.default_rng(1).random((33, 3))
    m = keypoints.mirror_landmarks(lm)
    assert np.allclose(m[11, :2], [1 - lm[12, 0], lm[12, 1]])      # left shoulder becomes mirrored right shoulder
    assert np.allclose(keypoints.mirror_landmarks(m), lm)
