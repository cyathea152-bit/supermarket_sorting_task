import argparse
import os
import time

import mujoco

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")
os.environ.setdefault("MAX_JOBS", "1")
os.environ.setdefault("FAST_COMPILE", "1")
os.environ.setdefault("TORCH_EXTENSIONS_DIR", "/tmp/torch_extensions_p7")
os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
os.environ.setdefault("TORCH_CUDA_ARCH_LIST", "12.0")

from discoverse.robots_env.mmk2_base import MMK2Base, MMK2Cfg


class ShentoonViewer(MMK2Base):
    xmartev_body_z = {
        "yellowbox": 1.2228054,
        "brownbox": 0.891876,
        "pinkbox": 0.568601,
    }

    def reset(self):
        obs = super().reset()
        self.apply_xmartev_z_offsets()
        return obs

    def apply_xmartev_z_offsets(self):
        for body_name, z_pos in self.xmartev_body_z.items():
            joint_id = self.free_body_qpos_ids.get(body_name)
            if joint_id is None:
                continue
            qpos_addr = self.mj_model.jnt_qposadr[joint_id]
            self.mj_data.qpos[qpos_addr + 2] = z_pos
        mujoco.mj_forward(self.mj_model, self.mj_data)

    def post_physics_step(self):
        pass

    def getChangedObjectPose(self):
        return {}

    def checkTerminated(self):
        return False

    def getObservation(self):
        return {}

    def getPrivilegedObservation(self):
        return {}

    def getReward(self):
        return 0.0


def build_cfg(args):
    cfg = MMK2Cfg()
    cfg.mjcf_file_path = args.mjcf
    cfg.use_gaussian_renderer = not args.no_gs
    cfg.sync = args.sync
    cfg.headless = args.headless
    cfg.decimation = 4
    cfg.render_set = {
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "window_title": "Shentoon 3DGS Viewer",
    }
    cfg.obs_rgb_cam_id = []
    cfg.obs_depth_cam_id = []

    xmartev = "xmartev_material_detection"
    object_models = {
        "pinkbox": f"{xmartev}/pinkbox.ply",
        "brownbox": f"{xmartev}/brownbox.ply",
        "yellowbox": f"{xmartev}/yellowbox.ply",
        "drill": f"{xmartev}/drill.ply",
        "hat": f"{xmartev}/hat.ply",
        "blue": f"{xmartev}/blue.ply",
        "toolbox": f"{xmartev}/toolbox.ply",
    }
    if args.only:
        names = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = sorted(set(names) - set(object_models))
        if unknown:
            raise ValueError(f"Unknown --only models: {unknown}. Available: {sorted(object_models)}")
        cfg.gs_model_dict = {name: object_models[name] for name in names}
    else:
        cfg.gs_model_dict = object_models
    if args.with_background:
        cfg.gs_model_dict["background"] = f"{xmartev}/scene.ply"
    if args.with_robot_gs:
        airbot = "airbot_play"
        cfg.gs_model_dict.update({
            "agv_link": "mmk2/agv_link.ply",
            "slide_link": "mmk2/slide_link.ply",
            "head_yaw_link": "mmk2/head_yaw_link.ply",
            "head_pitch_link": "mmk2/head_pitch_link.ply",

            "lft_arm_base": f"{airbot}/arm_base.ply",
            "lft_arm_link1": f"{airbot}/link1.ply",
            "lft_arm_link2": f"{airbot}/link2.ply",
            "lft_arm_link3": f"{airbot}/link3.ply",
            "lft_arm_link4": f"{airbot}/link4.ply",
            "lft_arm_link5": f"{airbot}/link5.ply",
            "lft_arm_link6": f"{airbot}/link6.ply",
            "lft_finger_left_link": f"{airbot}/left.ply",
            "lft_finger_right_link": f"{airbot}/right.ply",

            "rgt_arm_base": f"{airbot}/arm_base.ply",
            "rgt_arm_link1": f"{airbot}/link1.ply",
            "rgt_arm_link2": f"{airbot}/link2.ply",
            "rgt_arm_link3": f"{airbot}/link3.ply",
            "rgt_arm_link4": f"{airbot}/link4.ply",
            "rgt_arm_link5": f"{airbot}/link5.ply",
            "rgt_arm_link6": f"{airbot}/link6.ply",
            "rgt_finger_left_link": f"{airbot}/left.ply",
            "rgt_finger_right_link": f"{airbot}/right.ply",
        })
    return cfg


def main():
    parser = argparse.ArgumentParser(description="View shentoon.xml with 3DGS rendering.")
    parser.add_argument(
        "--mjcf",
        default="examples/shentoon/mjcf/shentoon1.xml",
        help="MJCF path, relative to the repo root, relative to models/, or absolute.",
    )
    parser.add_argument("--no-gs", action="store_true", help="Disable 3DGS and use MuJoCo rendering.")
    parser.add_argument("--headless", action="store_true", help="Run without opening a window.")
    parser.add_argument("--sync", action="store_true", help="Throttle rendering to --fps.")
    parser.add_argument("--with-background", action="store_true", help="Load scene.ply background.")
    parser.add_argument("--with-robot-gs", action="store_true", help="Load robot 3DGS models.")
    parser.add_argument(
        "--only",
        default="",
        help="Load only selected object 3DGS models, e.g. --only drill or --only drill,hat.",
    )
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=int, default=15)
    args = parser.parse_args()

    viewer = ShentoonViewer(build_cfg(args))
    print("Viewer started.")
    print("Loaded 3DGS models:", ", ".join(viewer.config.gs_model_dict.keys()))
    print("Keys: Ctrl+G toggle 3DGS, Esc free camera, [/] switch cameras, R reset, H help.")

    try:
        while viewer.running:
            viewer.view()
            if viewer.window is not None:
                import glfw

                if glfw.window_should_close(viewer.window):
                    break
            if not args.sync:
                time.sleep(0.001)
    finally:
        if hasattr(viewer, "_cleanup_before_exit"):
            viewer._cleanup_before_exit()


if __name__ == "__main__":
    main()
