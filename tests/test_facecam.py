"""engine.facecam._live_face: which haar cluster is the streamer."""
import numpy as np

from engine.facecam import _live_face, near


def _cluster(rng, n, cx, cy, h, jitter):
    return [(cx + rng.normal(0, jitter), cy + rng.normal(0, jitter), h)
            for _ in range(n)]


def test_plush_toy_with_more_hits_than_the_face_loses():
    # Clip 9 of the first live run: a toy on the shelf hit 31 of 40 frames
    # and its box wobbled just over the old fixed 2px floor; his face hit
    # fewer frames but drifted.
    rng = np.random.default_rng(0)
    toy = _cluster(rng, 31, 1446, 995, 72, 1.4)
    face = _cluster(rng, 20, 1718, 935, 74, 5.0)
    best = _live_face(toy + face, 40)
    assert best is not None
    assert abs(np.median(best[:, 0]) - 1718) < 10


def test_only_still_objects_means_no_face():
    rng = np.random.default_rng(1)
    hits = _cluster(rng, 40, 1526, 872, 58, 0.5) + _cluster(rng, 40, 1479, 994, 72, 1.1)
    assert _live_face(hits, 40) is None


def test_too_few_hits_is_not_a_face():
    rng = np.random.default_rng(2)
    assert _live_face(_cluster(rng, 9, 1548, 638, 50, 4.0), 40) is None


def test_no_hits():
    assert _live_face([], 40) is None


def _live(rng, n, cx, cy, h, jitter, live):
    return [(x, y, hh, live) for x, y, hh in _cluster(rng, n, cx, cy, h, jitter)]


def test_over_a_vod_the_most_frequent_live_face_wins():
    # A watchparty player is bigger and livelier than the webcam but on
    # screen less often; over a whole VOD the webcam is the face seen most.
    rng = np.random.default_rng(3)
    cam = _live(rng, 110, 1710, 385, 90, 8.0, 0.9)
    player = _live(rng, 50, 860, 400, 160, 60.0, 2.5)
    assert abs(np.median(_live_face(cam + player, 120, 0.03, 1.0, 0.25, by_count=True)[:, 0]) - 1710) < 20
    assert abs(np.median(_live_face(cam + player, 120, 0.03, 1.0, 0.25)[:, 0]) - 860) < 60


def test_near_keeps_only_faces_around_the_webcam():
    hits = [(1730, 390, 90, 0.9), (860, 400, 160, 2.5), (1900, 560, 80, 1.0)]
    cam = (1572, 279, 1888, 502)
    assert [h[0] for h in near(hits, cam)] == [1730, 1900]
    assert near(hits, None) == hits


def test_a_broadcast_closeup_cannot_outscore_the_webcam_near_it():
    # FNS 2885323336 clip 5: a T1 player held in close-up for the whole clip
    # is bigger and livelier than the webcam, so the open search picks him.
    rng = np.random.default_rng(4)
    cam = _live(rng, 38, 1730, 390, 70, 6.0, 0.6)
    player = _live(rng, 40, 1065, 385, 260, 30.0, 2.0)
    open_pick = _live_face(cam + player, 40, 0.03, 1.0, 0.75)
    assert abs(np.median(open_pick[:, 0]) - 1065) < 60
    pick = _live_face(near(cam + player, (1572, 279, 1888, 502)), 40, 0.03, 1.0, 0.75)
    assert abs(np.median(pick[:, 0]) - 1730) < 20
