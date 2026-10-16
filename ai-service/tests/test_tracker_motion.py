from app.detection.tracker import PersonTracker


def test_walking_person_keeps_one_id():
    t = PersonTracker()
    # 60 px wide person moving 50 px per check: boxes barely overlap (old tracker gave a new id every time)
    assert [t.update([(100 + 50 * i, 100, 160 + 50 * i, 300)])[0] for i in range(8)] == [1] * 8


def test_two_people_crossing_keep_their_ids():
    t = PersonTracker()
    for i in range(6):
        a, b = t.update([(100 + 40 * i, 100, 160 + 40 * i, 300), (400 - 40 * i, 100, 460 - 40 * i, 300)])
    assert (a, b) == (1, 2)


def test_far_away_or_different_size_is_a_new_person():
    t = PersonTracker()
    t.update([(100, 100, 160, 300)])
    assert t.update([(600, 100, 660, 300)]) == [2]  # far away
    t2 = PersonTracker()
    t2.update([(100, 100, 160, 300)])
    assert t2.update([(110, 150, 140, 200)]) == [2]  # much smaller box nearby = someone else


def test_short_miss_keeps_the_id():
    t = PersonTracker()
    t.update([(100, 100, 160, 300)])
    t.update([(140, 100, 200, 300)])
    t.update([])  # missed for one check
    assert t.update([(220, 100, 280, 300)]) == [1]  # where the walk predicted
