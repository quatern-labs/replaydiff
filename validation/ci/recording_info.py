#!/usr/bin/env python3
"""Print topics, message counts, duration and sha256 of the recording in a rosbag2 directory (CI log)."""
import glob
import hashlib
import sys

from mcap.reader import make_reader

for path in sorted(glob.glob(sys.argv[1] + "/*.mcap")):
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(path, "rb") as f:
        s = make_reader(f).get_summary().statistics
        print(f"{path}: sha256 {digest}")
        print(f"  messages {s.message_count}, duration {(s.message_end_time - s.message_start_time) / 1e9:.1f} s")
    with open(path, "rb") as f:
        summ = make_reader(f).get_summary()
        for cid, ch in summ.channels.items():
            print(f"  {ch.topic}: {summ.statistics.channel_message_counts.get(cid, 0)}")
