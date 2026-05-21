from zygo_datax.cli import _aperture_mm


def test_aperture_parser():
    assert _aperture_mm("40.24,41.16") == (40.24, 41.16)
