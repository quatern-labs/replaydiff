import numpy as np

import scand_pin


def _entry(i, name, size, label=""):
    return {"dataFile": {"id": i, "filename": name, "filesize": size, "checksum": {"type": "MD5", "value": "x"}},
            "directoryLabel": label}


def test_jackal_bags_filters_and_sorts_smallest_first():
    listing = {"data": [_entry(1, "A_Jackal_x.bag", 900), _entry(2, "A_Spot_y.bag", 10),
                        _entry(3, "b.bag", 500, "Jackal"), _entry(4, "Jackal_notes.txt", 1)]}
    assert [b["id"] for b in scand_pin.jackal_bags(listing)] == [3, 1]


def test_steady_window_picks_the_steady_stretch():
    t = np.arange(0, 100, 0.1)
    v = np.where((t > 40) & (t < 75), 1.0, 0.2)  # steady 1 m/s from 40 to 75 s
    w = scand_pin.steady_window(t, v, 30.0)
    assert 41 <= w["start"] <= 45 and w["min_speed"] == 1.0
    assert scand_pin.steady_window(t, v, 200.0) is None


def test_hashes_with_and_without_dataverse_algo(tmp_path):
    p = tmp_path / "x.bag"
    p.write_bytes(b"abc")
    sha, md5 = scand_pin._hashes(str(p), "MD5")
    assert sha.startswith("ba7816bf") and md5 == "900150983cd24fb0d6963f7d28e17f72"
    assert scand_pin._hashes(str(p), "") == (sha, "")
