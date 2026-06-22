"""
Discoverse -> Zenoh Publisher (RGB JPEG + Depth ZSTD-Float32 + PCL)

Publishes:
  - env/{CAMERA_ID}/rgb   : ImageData(jpeg)
  - env/{CAMERA_ID}/depth : ImageData(zstd-depth32 float32 meters)
  - env/{CAMERA_ID}/pcl   : raw bytes float32 (N,4) [x,y,z,packed_rgb_bits_as_float]
"""
import argparse
import os
import time

import numpy as np
import mujoco

from subscribe_joint_state import ArmGripperSubscriber

import discoverse
from discoverse import DISCOVERSE_ROOT_DIR
from discoverse.robots_env.airbot_play_base import AirbotPlayBase, AirbotPlayCfg

from zenoh_bridge import (
    ZenohPub, ZenohPubConfig,
    GpuPclProjector,
    publish_rgb_depth,
    publish_pcl,
)

# -------------------------
# Config
# -------------------------
CAMERA_ID = "SN_57524755"
MJ_CAM_NAME = "stream_cam"
FPS_PUB = 20.0

PCL_HZ = 10.0
PCL_STRIDE = 1
PCL_MAX_DEPTH = 4.0

MJCF_PATH = os.path.join(
    DISCOVERSE_ROOT_DIR,
    "models/mjcf/manipulator/roombia/airplay_pick_blocks.xml"
)

# 3DGS: xml body name -> grasp_gen_obj ply (参照 open_drawer.py)
# plate -> plate.ply, block -> brick.ply, env -> scene.ply
GS_GRASP_GEN = "grasp_gen_obj"
cfg_gs_model_dict = {
    "background": f"{GS_GRASP_GEN}/scene.ply",   # env
    "plate":      f"{GS_GRASP_GEN}/plate.ply",   # xml body "plate"
    # "block":      f"{GS_GRASP_GEN}/brick.ply",   # xml body "block" -> brick.ply
    "block":      f"{GS_GRASP_GEN}/bottle.ply",   # xml body "block" -> brick.ply
}

# 保存 RGB/Depth 的默认目录，供 export_yaml 的 RGB_PATH / DEPTH_PATH 读取
DEBUG_RGBD_DIR = "debug_rgbd"


class SimNode(AirbotPlayBase):
    def resetState(self):
        # 你要求：不 reset 初始 state
        pass


def _set_geom_contact_params(model: mujoco.MjModel, geom_name: str,
                            friction=(3.0, 0.0, 0.0),
                            condim=3,
                            solref=(0.01, 1.0),
                            solimp=(0.95, 0.95, 0.002)):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, geom_name)
    if gid < 0:
        print(f"[WARN] geom '{geom_name}' not found, skip")
        return False

    # friction: (slide, torsion, roll)
    model.geom_friction[gid, 0] = float(friction[0])
    model.geom_friction[gid, 1] = float(friction[1])
    model.geom_friction[gid, 2] = float(friction[2])

    # contact dimension
    model.geom_condim[gid] = int(condim)

    # solref: (timeconst, dampratio)  -- length 2
    model.geom_solref[gid, 0] = float(solref[0])
    model.geom_solref[gid, 1] = float(solref[1])

    # solimp: (dmin, dmax, width, midpoint, power) -- length 5
    # 你给的是 3 个值，我们按常用方式填前 3 个，其它保持默认
    model.geom_solimp[gid, 0] = float(solimp[0])
    model.geom_solimp[gid, 1] = float(solimp[1])
    model.geom_solimp[gid, 2] = float(solimp[2])

    print(f"[OK] patched geom '{geom_name}': "
          f"friction={model.geom_friction[gid]} condim={model.geom_condim[gid]} "
          f"solref={model.geom_solref[gid]} solimp={model.geom_solimp[gid]}")
    return True


def patch_finger_pads(sim):
    # 你贴的 MJCF 里 pad 名字就是这两个
    _set_geom_contact_params(sim.mj_model, "left_finger_pad",
                             friction=(3.0, 0.0, 0.0),
                             condim=3,
                             solref=(0.01, 1.0),
                             solimp=(0.95, 0.95, 0.002))
    _set_geom_contact_params(sim.mj_model, "right_finger_pad",
                             friction=(3.0, 0.0, 0.0),
                             condim=3,
                             solref=(0.01, 1.0),
                             solimp=(0.95, 0.95, 0.002))

def main():
    parser = argparse.ArgumentParser(description="Discoverse -> Zenoh publisher (RGB + Depth + PCL)")
    parser.add_argument(
        "--debug-save-pcl",
        action="store_true",
        help="Save every published PCL to debug_pcl/pcl_000000.ply, ...",
    )
    parser.add_argument(
        "--debug-save-rgbd",
        action="store_true",
        help="Save RGB/depth to debug_rgbd/rgb.npy, depth.npy (for export_yaml RGB_PATH/DEPTH_PATH)",
    )
    parser.add_argument(
        "--invert-gripper",
        action="store_true",
        help="Invert gripper direction if open/close is reversed",
    )
    parser.add_argument(
        "--use-gs",
        action="store_true",
        help="Use gaussian splatting renderer (3DGS)",
    )
    args = parser.parse_args()

    print(discoverse.__logo__)
    np.set_printoptions(precision=3, suppress=True)

    # resolve camera numeric id
    _m = mujoco.MjModel.from_xml_path(MJCF_PATH)
    cam_id = mujoco.mj_name2id(_m, mujoco.mjtObj.mjOBJ_CAMERA, MJ_CAM_NAME)
    del _m
    if cam_id < 0:
        raise RuntimeError(f"Camera '{MJ_CAM_NAME}' not found in MJCF: {MJCF_PATH}")

    # discoverse cfg（模仿 open_drawer.py 嵌入 airbot + 3DGS）
    cfg = AirbotPlayCfg()
    cfg.mjcf_file_path = MJCF_PATH
    cfg.obs_rgb_cam_id = [cam_id]
    cfg.obs_depth_cam_id = [cam_id]
    cfg.timestep = 1 / 240
    cfg.decimation = 4
    cfg.sync = True
    cfg.headless = False
    cfg.render_set = {"fps": int(FPS_PUB), "width": 600, "height": 600}
    cfg.init_qpos = np.array([0.0, -1.0, 1.2, 1.5708, -1.2, -1.5708, 0.0])

    # 3DGS: env(background) + plate + block，与 xml body 一一对应
    for k, v in cfg_gs_model_dict.items():
        cfg.gs_model_dict[k] = v
    cfg.obj_list = ["plate", "block"]
    cfg.use_gaussian_renderer = args.use_gs

    sim = SimNode(cfg)
    # patch_finger_pads(sim)
    
    print("sim.nj =", sim.nj)
    print("actuator ctrlrange =", sim.mj_model.actuator_ctrlrange[: sim.nj])

    # zenoh publishers + gpu projector
    pubs = ZenohPub(ZenohPubConfig(camera_id=CAMERA_ID, shm_mb=256, jpeg_quality=85, zstd_level=1))
    projector = GpuPclProjector(stride=PCL_STRIDE, max_depth=PCL_MAX_DEPTH, device="cuda")

    # --- subscribe arm + gripper -> action ---
    sub = ArmGripperSubscriber(
        arm_topic="robot/state/joint",
        gripper_topic="gripper/sim_two_finger/state",
        sim_nj=sim.nj,                 # 通常 7：6 arm + 1 gripper
        gripper_ctrl_min=0.0,
        gripper_ctrl_max=0.04,
        invert_gripper=bool(args.invert_gripper),
    )

    # action init (fallback)
    action = sim.mj_data.ctrl[: sim.nj].copy()

    # publish schedule
    period = 1.0 / FPS_PUB
    next_pub_wall = time.time()

    logging_every = 2.0
    next_log = time.time() + logging_every

    try:
        while sim.running:
            # 1) 控制仿真（用最新 action）
            latest = sub.get_latest_action()
            if latest is not None and latest.shape[0] == sim.nj:
                ctrl_low = sim.mj_model.actuator_ctrlrange[: sim.nj, 0]
                ctrl_high = sim.mj_model.actuator_ctrlrange[: sim.nj, 1]
                action = np.clip(latest, ctrl_low, ctrl_high)

            obs, *_ = sim.step(action)

            # 2) 发布图像
            now = time.time()
            if now < next_pub_wall:
                continue
            next_pub_wall += period

            rgb = obs.get("img", {}).get(cam_id, None)
            depth = obs.get("depth", {}).get(cam_id, None)
            publish_rgb_depth(pubs, rgb, depth)
            if args.debug_save_rgbd and rgb is not None and depth is not None:
                os.makedirs(DEBUG_RGBD_DIR, exist_ok=True)
                np.save(os.path.join(DEBUG_RGBD_DIR, "rgb.npy"), rgb)
                np.save(os.path.join(DEBUG_RGBD_DIR, "depth.npy"), depth.astype(np.float32))

            # 可选：点云
            # if rgb is not None and depth is not None:
            #     publish_pcl(pubs, projector, sim, cam_id, rgb, depth, save_to_disk=args.debug_save_pcl)

            if now >= next_log:
                next_log = now + logging_every
                grip = float(action[6]) if sim.nj >= 7 else float("nan")
                print(f"[ctrl] t={sim.mj_data.time:.2f}s grip={grip:.4f} action={action.round(3)}")

    finally:
        sub.close()
        print("Exited.")


if __name__ == "__main__":
    # export MUJOCO_GL=glfw   # 如果 GLX BadAccess
    main()