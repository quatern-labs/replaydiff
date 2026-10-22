import hashlib

import pytest

import prepare_recording as pr


@pytest.fixture
def bag(tmp_path):
    p = tmp_path / "x.bag"
    p.write_bytes(b"not a real bag")
    return p, hashlib.sha256(b"not a real bag").hexdigest()


def test_verify_sha256(bag):
    p, digest = bag
    assert pr.verify_sha256(p, digest.upper()) == digest
    with pytest.raises(pr.Sha256Mismatch, match="pinned"):
        pr.verify_sha256(p, "0" * 64)


def test_cache_key_changes_with_each_input():
    d = "a" * 64
    keys = {pr.cache_key(1, d), pr.cache_key(2, d), pr.cache_key(1, "b" * 64), pr.cache_key(1, d, (10, 60)),
            pr.cache_key(1, d, (10, 45))}
    assert len(keys) == 5
    assert pr.cache_key(1, d.upper()) == pr.cache_key(1, d)


def steps(calls):
    def convert(src, dst, start, duration, keep_cloud):
        calls.append(("convert", keep_cloud))
        (pr.Path(dst)).mkdir(parents=True)
        (pr.Path(dst) / "cloud.txt").write_text("raw cloud")

    def laserscan(cloud, out):
        calls.append(("laserscan",))
        pr.Path(out).mkdir(parents=True)
        (pr.Path(out) / "r.mcap").write_text("scan")

    def check(path):
        calls.append(("check",))
        return ["/odom", "/scan"]
    return convert, laserscan, check


def test_prepare_then_cache_hit(bag, tmp_path):
    p, digest = bag
    cache, calls = tmp_path / "cache", []
    out = tmp_path / "o1" / "recording"
    r = pr.prepare(str(p), digest, 7, out, cache, (5, 60), *steps(calls))
    assert r["cached"] is False and r["topics"] == ["/odom", "/scan"]
    assert calls == [("convert", True), ("laserscan",), ("check",)]
    assert not (out.parent / "recording.work").exists()  # raw cloud intermediate removed
    calls.clear()
    out2 = tmp_path / "o2" / "recording"
    r2 = pr.prepare(str(p), digest, 7, out2, cache, (5, 60), *steps(calls))
    assert r2["cached"] is True and r2["key"] == r["key"]
    assert calls == [("check",)] and (out2 / "r.mcap").read_text() == "scan"


def test_hash_mismatch_runs_nothing(bag, tmp_path):
    calls = []
    with pytest.raises(pr.Sha256Mismatch):
        pr.prepare(str(bag[0]), "f" * 64, 7, tmp_path / "o", tmp_path / "c", (0, 60), *steps(calls))
    assert calls == []


def test_failed_check_is_not_cached(bag, tmp_path):
    p, digest = bag
    convert, laserscan, _ = steps([])

    def bad(path):
        raise ValueError("refusing /velodyne_points")
    with pytest.raises(ValueError):
        pr.prepare(str(p), digest, 7, tmp_path / "o", tmp_path / "c", (0, 60), convert, laserscan, bad)
    assert not list((tmp_path / "c").glob("*/prepared.json"))


def test_cli_verify_and_key(bag, capsys):
    p, digest = bag
    assert pr.main(["verify", str(p), digest]) == 0
    assert pr.main(["verify", str(p), "0" * 64]) == 1
    capsys.readouterr()
    assert pr.main(["key", "--file-id", "9", "--sha256", digest, "--start", "5", "--duration", "60"]) == 0
    assert capsys.readouterr().out.strip() == f"scand-9-{digest[:16]}-s5-d60"


def test_laserscan_commands_shape():
    cmds = pr.laserscan_commands("in", "out")
    assert cmds[0][:3] == ["ros2", "run", "pointcloud_to_laserscan"] and cmds[2][-1] == "in" and "out" in cmds[1]
