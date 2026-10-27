from ytscript.models.segment import Segment


def test_segment_exposes_start_and_text():
    segment = Segment(12.5, "olá")
    assert segment.start == 12.5
    assert segment.text == "olá"


def test_segment_unpacks_as_tuple():
    start, text, duration = Segment(1, "a", 2)
    assert (start, text, duration) == (1, "a", 2)
