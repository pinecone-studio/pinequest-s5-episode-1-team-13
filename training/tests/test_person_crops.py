from person_crops import MAX_UPSCALE, crop_region, scale_for


def test_crop_region_adds_margin_and_clips_to_the_frame():
    x1, y1, x2, y2 = crop_region(100, 100, 200, 300, 1000, 1000)
    assert (x1, y1) == (65, 70) and (x2, y2) == (236, 331)             # 35% өргөн, 15% өндрийн margin
    assert crop_region(0, 0, 50, 50, 50, 50) == (0, 0, 50, 50)            # frame-ээс хэтрэхгүй


def test_scale_for_shrinks_large_and_caps_the_upscale_of_small_crops():
    assert scale_for(1024, 512) == 0.5
    assert scale_for(10, 10) == MAX_UPSCALE
