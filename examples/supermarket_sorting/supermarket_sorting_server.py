#!/usr/bin/env python3
"""超市分拣任务的 ROS2 server。

加载 retail_competition 场景，复用本仓库 examples/ros2/mmk2_ros2.py 的
MMK2ROS2 发布相机、里程计、关节状态等标准话题，供
supermarket_sorting_client.py 控制机器人完成抓取放置。
"""
import json
import os
import sys
import threading
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
import rclpy
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException

# 可迁移:从脚本自身位置推导示例目录和仓库根目录
TASK_DIR = Path(__file__).resolve().parent
REPO_ROOT = TASK_DIR.parents[1]
ROS2_EXAMPLES_DIR = REPO_ROOT / "examples" / "ros2"
if str(ROS2_EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(ROS2_EXAMPLES_DIR))

ASSETS_DIR = TASK_DIR / "models"
os.environ["DISCOVERSE_ASSETS_DIR"] = str(ASSETS_DIR)

from discoverse.robots_env.mmk2_base import MMK2Cfg
from mmk2_ros2 import MMK2ROS2

SOURCE_XML = TASK_DIR / "mjcf" / "retail_competition.xml"
RUNTIME_XML = Path("/tmp/retail_competition_ros2_runtime.xml")
LAYOUT_JSON = TASK_DIR / "retail_competition_layout.json"
START_XY = np.array([1.92, -3.17], dtype=float)   # 出发区


def env_flag(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def local_robot_gs_model_dict():
    gs_model_dict = {}
    for name, path in MMK2Cfg.gs_model_dict.items():
        if path.startswith("mobile_chassis/mmk2/"):
            gs_model_dict[name] = path.replace("mobile_chassis/mmk2/", "mmk2/")
        elif path.startswith("manipulator/airbot_play/"):
            gs_model_dict[name] = path.replace("manipulator/airbot_play/", "airbot_play/")
        else:
            gs_model_dict[name] = path
    return gs_model_dict


# 货架每层台面高度(世界 z)。物体静止 z = 台面 + 该物体自身半高。
SHELF_SURFACE = {"L1": 0.600, "L2": 0.900, "L3": 1.200}


def write_runtime_xml(pos_overrides=None):
    """Render the runtime MJCF. If pos_overrides is given, rewrite each named
    body's pos="x y z" so the whole body (collision geom + gs ply travel
    together) moves to its randomized shelf slot."""
    text = SOURCE_XML.read_text().replace("__REPO_ROOT__", str(TASK_DIR))
    if pos_overrides:
        import re
        for body_name, (x, y, z) in pos_overrides.items():
            pattern = re.compile(
                r'(<body name="' + re.escape(body_name) + r'"[^>]*?pos=")[^"]*(")'
            )
            text, n = pattern.subn(rf"\g<1>{x:.5f} {y:.5f} {z:.5f}\g<2>", text)
            if n != 1:
                raise RuntimeError(
                    f"randomize: expected exactly 1 body pos for {body_name}, got {n}")
    RUNTIME_XML.write_text(text)
    return str(RUNTIME_XML)


def randomize_positions(layout, seed=None):
    """Shuffle which shelf slot each object body occupies.

    Each body keeps its own collision geom AND its own gs ply (they stay bound);
    only the body's world position moves to another slot.  The new z is the new
    shelf surface plus the body's intrinsic half-height (derived from its
    original z), so the object rests on the shelf instead of clipping/floating.

    Returns (new_layout, pos_overrides) where pos_overrides maps body name ->
    (x, y, z) for the runtime MJCF rewrite.
    """
    import random
    rng = random.Random(seed)
    # target slot positions (x, y, level) taken from the original layout
    slots = [(s["world_position"][0], s["world_position"][1], s["level"]) for s in layout]
    # each body's intrinsic half-height = original z - its original shelf surface
    half_h = [s["world_position"][2] - SHELF_SURFACE[s["level"]] for s in layout]

    order = list(range(len(layout)))
    rng.shuffle(order)   # body i -> slot order[i]

    new_layout, pos_overrides = [], {}
    for body_i, slot_i in enumerate(order):
        x, y, level = slots[slot_i]
        z = SHELF_SURFACE[level] + half_h[body_i]
        body = layout[body_i]["body"]
        pos_overrides[body] = (x, y, z)
        ns = layout[body_i].copy()
        ns["world_position"] = [x, y, z]
        new_layout.append(ns)
    return new_layout, pos_overrides


def build_config():
    cfg = MMK2Cfg()
    cfg.use_gaussian_renderer = env_flag("SUPERMARKET_USE_GS", True)
    cfg.enable_render = env_flag("SUPERMARKET_ENABLE_RENDER", True)
    cfg.headless = env_flag("SUPERMARKET_HEADLESS", False)

    # 货架场景的 3DGS 绑定:保留 MMK2Cfg 默认的机器人 link 绑定,追加 background + 货架物体
    layout = json.loads(LAYOUT_JSON.read_text())

    # 随机摆放功能(默认开启,给选手用):整把物体(碰撞geom+3DGS一起)随机搬到别的货架格子
    pos_overrides = None
    if env_flag("SUPERMARKET_RANDOMIZE", True):
        seed_str = os.getenv("SUPERMARKET_SEED")
        seed = int(seed_str) if seed_str and seed_str.isdigit() else None
        layout, pos_overrides = randomize_positions(layout, seed)
        print(f"[server] randomized object positions (seed={seed})")
    else:
        print("[server] fixed layout (SUPERMARKET_RANDOMIZE=0)")

    cfg.mjcf_file_path = write_runtime_xml(pos_overrides)

    cfg.obj_list = [slot["body"] for slot in layout]
    cfg.gs_model_dict = local_robot_gs_model_dict()
    cfg.gs_model_dict["background"] = "shentoon/dummy_background.ply"
    for slot in layout:
        cfg.gs_model_dict[slot["body"]] = slot["gs_ply"]

    cfg.obs_rgb_cam_id = [0, 1, 2]     # head / lft / rgt
    cfg.obs_depth_cam_id = [0]
    cfg.lidar_s2_sim = False
    cfg.render_set = {"fps": 24, "width": 640, "height": 480}

    # 起始位姿:出发区,朝北(+Y)
    cfg.init_state["base_position"] = [float(START_XY[0]), float(START_XY[1]), 0.0]
    cfg.init_state["base_orientation"] = Rotation.from_euler("z", np.pi / 2.0).as_quat()[[3, 0, 1, 2]].tolist()
    return cfg


def spin_node(node):
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, RCLError):
        pass


def main():
    rclpy.init()
    np.set_printoptions(precision=3, suppress=True, linewidth=500)

    exec_node = MMK2ROS2(build_config())
    exec_node.reset()

    spin_thread = threading.Thread(target=spin_node, args=(exec_node,), daemon=True)
    spin_thread.start()

    pubtopic_thread = threading.Thread(target=exec_node.thread_pubros2topic, args=(24,), daemon=True)
    pubtopic_thread.start()

    try:
        while rclpy.ok() and exec_node.running:
            exec_node.step(exec_node.target_control)
    except KeyboardInterrupt:
        pass
    finally:
        exec_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
