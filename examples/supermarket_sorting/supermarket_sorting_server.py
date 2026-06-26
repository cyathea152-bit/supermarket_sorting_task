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


def write_runtime_xml():
    text = SOURCE_XML.read_text().replace("__REPO_ROOT__", str(TASK_DIR))
    RUNTIME_XML.write_text(text)
    return str(RUNTIME_XML)


def build_config():
    cfg = MMK2Cfg()
    cfg.mjcf_file_path = write_runtime_xml()
    cfg.use_gaussian_renderer = True

    # 货架场景的 3DGS 绑定:保留 MMK2Cfg 默认的机器人 link 绑定,追加 background + 货架物体
    layout = json.loads(LAYOUT_JSON.read_text())
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


def main():
    rclpy.init()
    np.set_printoptions(precision=3, suppress=True, linewidth=500)

    exec_node = MMK2ROS2(build_config())
    exec_node.reset()

    spin_thread = threading.Thread(target=lambda: rclpy.spin(exec_node), daemon=True)
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
        rclpy.shutdown()


if __name__ == "__main__":
    main()
