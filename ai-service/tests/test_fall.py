from app.detection.fall import is_down, mark_down
from app.detection.types import PersonResult
from app.violations.rules import DB_TYPE, PERSON_DOWN, ViolationRules, violation_types


def person(box, pid=1):
    return PersonResult(id=pid, box=box, conf=0.9)


def test_lying_is_down_standing_and_sitting_are_not():
    assert is_down((100, 300, 595, 552), 1.2)  # w=495 h=252 (real fallen photo)
    assert not is_down((100, 100, 300, 500), 1.2)  # standing
    assert not is_down((100, 100, 438, 508), 1.2)  # sitting, ratio 0.83 (real photo)


def test_mark_down_sets_violation_and_off_switch():
    p = person((0, 300, 500, 500))
    mark_down([p], 0)
    assert not p.down
    mark_down([p], 1.2, frame_height=1080)
    assert p.down and p.violation
    assert violation_types(p) == [PERSON_DOWN]
    assert DB_TYPE[PERSON_DOWN] == "OTHER_SAFETY_VIOLATION"


def test_cut_off_at_bottom_is_not_down():
    p = person((0, 900, 500, 1080))  # close to the camera, cut by the frame
    mark_down([p], 1.2, frame_height=1080)
    assert not p.down


def test_must_stay_down_for_confirm_seconds_then_saved_once():
    rules = ViolationRules(confirm_seconds=2.0, cooldown_seconds=60)
    p = person((0, 300, 500, 500))
    mark_down([p], 1.2, frame_height=1080)
    assert rules.update([p], 0.0) == []
    assert rules.update([p], 1.0) == []
    assert rules.update([p], 2.1) == [(PERSON_DOWN, p)]
    assert rules.update([p], 3.0) == []  # same visit: not saved again
