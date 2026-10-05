# Recordings used by the validation experiment

Recordings are downloaded or generated in CI only. They are never committed (`.gitignore` blocks `*.mcap`,
`*.db3`, `runs/` and `results/`).

## Result of the search for an existing public recording (October 2026)

No openly downloadable ROS 2 navigation recording with a stated permissive license was found:

| Candidate | Why not |
|---|---|
| TurtleBot5G Dataset, MMK Corridor (KTH), https://zenodo.org/records/14995354 | License CC-BY-4.0, but the Zenodo record is access-restricted (login / request), so CI cannot download it. sqlite3 bag, 574 MiB, LiDAR SLAM run, velocity commands on `/cmd_vel_stamped`, distro not stated |
| guilhermelawless/turtlebot3_datasets | ROS 1 bags, GPL-3.0 |
| Kaggle "ROSBAG DATASET TURTLEBOT3" | License "Unknown" |
| IEEE DataPort rosbag2_2024_07_19_11_01_37 | Vehicle data, paid subscription, no license shown |
| navigation2, turtlebot3 repositories | No bag found in-tree (not confirmed by a full tree listing; nav2's system tests run a live simulation) |

The search was a handful of web searches, not exhaustive. If you know of a permissively licensed nav2 or
TurtleBot3 bag, add it here and switch the workflow to download it.

## What the experiment uses instead: a generated recording

`validation/ci/gen_recording.sh` runs the TurtleBot3 (waffle) + nav2 simulation headless (`nav2_bringup`
`tb3_simulation_launch.py`, `headless:=True`), sends two fixed navigation goals, and records
`/odom /scan /tf /tf_static /cmd_vel /plan` with `ros2 bag record -s mcap --use-sim-time` (about 40 s).
One recording per ROS distro (Humble, Jazzy), uploaded as a short-lived workflow artifact and reused by every
replay job of that distro. It is simulated data, not a real-robot recording: real-robot noise (sensor jitter,
CPU load of a real stack) is not represented, and the README says so wherever results are quoted.

| Recording | Source | License | Where |
|---|---|---|---|
| `recording-humble` | generated in CI from ROS 2 Humble `nav2_bringup` + `turtlebot3_gazebo` (Apache-2.0) | the recording itself is generated data, not distributed; the packages that produce it are Apache-2.0 | workflow artifact, 3-day retention |
| `recording-jazzy` | generated in CI from ROS 2 Jazzy `nav2_bringup` + `nav2_minimal_tb3_sim` (Apache-2.0) | as above | workflow artifact, 3-day retention |

The sha256, topic list and message counts of each recording are printed in the "Generate recording" step log.
