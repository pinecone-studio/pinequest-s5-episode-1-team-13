from scripts.check_model import NOT_USABLE, PARTIAL, READY, check, main
from app.detection.classes import parse_mapping

OURS = {0: "person", 1: "helmet", 2: "no_helmet", 3: "work_uniform", 4: "no_work_uniform"}


def test_our_own_model_is_ready():
    verdict, lines = check(OURS, {})
    assert verdict == READY and not any("Problems" in line for line in lines)


def test_plain_coco_model_is_not_usable():
    verdict, lines = check({0: "person", 1: "bicycle", 2: "car"}, {})
    assert verdict == NOT_USABLE
    assert any("No helmet classes" in line for line in lines)


def test_hardhat_model_with_mapping_is_partial():
    names = {0: "Person", 1: "Hardhat", 2: "NO-Hardhat"}
    verdict, lines = check(names, parse_mapping("Person:person,Hardhat:helmet,NO-Hardhat:no_helmet"))
    assert verdict == PARTIAL
    assert any("No uniform classes" in line for line in lines)


def test_unmapped_names_get_a_hint():
    verdict, lines = check({0: "Person", 1: "Hardhat"}, {})
    assert verdict == NOT_USABLE and any("CLASS_MAPPING=" in line for line in lines)


def test_missing_file(tmp_path):
    assert main([str(tmp_path / "nope.onnx")]) == 1
