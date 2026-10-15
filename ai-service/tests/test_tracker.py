from app.detection.tracker import PersonTracker, iou


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0
    assert round(iou((0, 0, 10, 10), (5, 0, 15, 10)), 3) == 0.333


def test_same_person_keeps_id_while_walking():
    t = PersonTracker()
    [a] = t.update([(100, 100, 200, 400)])
    for step in range(1, 10):
        [same] = t.update([(100 + step * 10, 100, 200 + step * 10, 400)])
        assert same == a


def test_two_people_and_a_newcomer():
    t = PersonTracker()
    a, b = t.update([(0, 0, 100, 300), (500, 0, 600, 300)])
    b2, a2, c = t.update([(505, 0, 605, 300), (5, 0, 105, 300), (900, 0, 1000, 300)])
    assert (a2, b2) == (a, b) and c not in (a, b)


def test_short_disappearance_keeps_id_long_one_does_not():
    t = PersonTracker(max_missing=3)
    [a] = t.update([(0, 0, 100, 300)])
    for _ in range(3):
        t.update([])
    assert t.update([(0, 0, 100, 300)]) == [a]
    for _ in range(5):
        t.update([])
    assert t.update([(0, 0, 100, 300)]) != [a]
