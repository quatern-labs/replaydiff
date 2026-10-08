"""Launch nav2's controller_server (default Humble DWB), planner_server and map_server on a replayed recording, then
the bag, then the recorded goals. Order is by launch events, not timers:
  nav2 nodes + tf relay start -> lifecycle_manager's /is_active wait (waiter) exits -> OnProcessExit starts the bag
  play -> OnProcessStart of the bag play starts the goal sender (which waits for /clock to reach each goal's offset).
Arguments (launch_arguments): params (merged params yaml), map (map yaml), recording, rate, goals (goals.yaml).
Nav2's cmd_vel is remapped to /sut/cmd_vel so the comparison step reads it as before.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import LifecycleNode, Node

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = {"use_sim_time": True}


def generate_launch_description():
    params = LC("params")
    nodes = [
        Node(package="nav2_map_server", executable="map_server", name="map_server", output="screen",
             parameters=[params, SIM, {"yaml_filename": LC("map")}]),
        Node(package="nav2_planner", executable="planner_server", name="planner_server", output="screen",
             parameters=[params, SIM]),
        Node(package="nav2_controller", executable="controller_server", name="controller_server", output="screen",
             parameters=[params, SIM], remappings=[("cmd_vel", "/sut/cmd_vel")]),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager", name="lifecycle_manager_replay",
             output="screen", parameters=[params, SIM]),
        ExecuteProcess(cmd=["python3", f"{HERE}/nav2_replay_nodes.py", "tf", "--ros-args", "-p", "use_sim_time:=true"],
                       output="screen"),
    ]
    # waits until the lifecycle manager reports every managed node active, then exits
    wait_active = ExecuteProcess(
        cmd=["bash", "-c", "until ros2 service call /lifecycle_manager_replay/is_active std_srvs/srv/Trigger "
                           "| grep -q 'success=True'; do sleep 1; done"], output="screen")
    play = ExecuteProcess(
        cmd=["ros2", "bag", "play", LC("recording"), "--clock", "1000", "-r", LC("rate"), "--topics", "/odom", "/scan",
             "/tf", "/tf_static", "--remap", "/tf:=/tf_in", "/tf_static:=/tf_static_in"], output="screen")
    goals = ExecuteProcess(
        cmd=["python3", f"{HERE}/nav2_replay_nodes.py", "goals", "--goals", LC("goals"),
             "--ros-args", "-p", "use_sim_time:=true"], output="screen")
    return LaunchDescription([
        *[DeclareLaunchArgument(n) for n in ("params", "map", "recording", "rate", "goals")],
        *nodes,
        RegisterEventHandler(OnProcessStart(target_action=nodes[3], on_start=[wait_active])),
        RegisterEventHandler(OnProcessExit(target_action=wait_active, on_exit=[play])),
        RegisterEventHandler(OnProcessStart(target_action=play, on_start=[goals])),
    ])
