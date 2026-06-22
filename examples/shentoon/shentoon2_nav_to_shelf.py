import argparse
import os
import time

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

from discoverse.robots_env.mmk2_base import MMK2Base, MMK2Cfg
from discoverse.utils import PIDarray


def wrap_to_pi(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def parse_xy_list(text):
    points = []
    for item in text.split(";"):
        item = item.strip()
        if not item:
            continue
        xy = [float(v.strip()) for v in item.split(",")]
        if len(xy) != 2:
            raise ValueError(f"Waypoint must be x,y, got: {item}")
        points.append(np.array(xy, dtype=float))
    return points


class Shentoon2NavDemo(MMK2Base):
    target_control = np.zeros(19)

    def __init__(self, config, target_xy, waypoints, stop_distance, final_yaw, yaw_tolerance):
        self.tctr_base = self.target_control[:2]
        self.pid_base_vel = PIDarray(
            kps=np.array([7.5, 7.5]),
            kis=np.array([0.0, 0.0]),
            kds=np.array([0.0, 0.0]),
            integrator_maxs=np.array([5.0, 5.0]),
        )
        self.target_xy = np.array(target_xy, dtype=float)
        self.waypoints = [np.array(p, dtype=float) for p in waypoints] + [self.target_xy]
        self.stop_distance = stop_distance
        self.final_yaw = final_yaw
        self.yaw_tolerance = yaw_tolerance
        self.waypoint_idx = 0
        super().__init__(config)

    def set_route(self, target_xy, waypoints, final_yaw=None):
        self.target_xy = np.array(target_xy, dtype=float)
        self.waypoints = [np.array(p, dtype=float) for p in waypoints] + [self.target_xy]
        self.waypoint_idx = 0
        if final_yaw is not None:
            self.final_yaw = final_yaw

    def resetState(self):
        super().resetState()
        self.pid_base_vel.reset()
        self.target_control[:] = self.init_joint_ctrl[:]
        self.waypoint_idx = 0

    def updateControl(self, action):
        wheel_force = self.pid_base_vel.output(
            np.clip(self.tctr_base - self.sensor_wheel_qvel, -2.5, 2.5),
            self.mj_model.opt.timestep,
        )
        self.mj_data.ctrl[:2] = np.clip(
            wheel_force,
            self.mj_model.actuator_ctrlrange[:2, 0],
            self.mj_model.actuator_ctrlrange[:2, 1],
        )
        self.mj_data.ctrl[2:self.njctrl] = np.clip(
            action[2:self.njctrl],
            self.mj_model.actuator_ctrlrange[2:self.njctrl, 0],
            self.mj_model.actuator_ctrlrange[2:self.njctrl, 1],
        )

    @property
    def base_yaw(self):
        return Rotation.from_quat(np.array(self.sensor_base_orientation)[[1, 2, 3, 0]]).as_euler("xyz")[2]

    def drive_toward_next_waypoint(self, max_linear, max_angular):
        pos_xy = np.array(self.sensor_base_position[:2], dtype=float)
        target_xy = self.waypoints[self.waypoint_idx]
        delta = target_xy - pos_xy
        dist = np.linalg.norm(delta)

        if dist < self.stop_distance and self.waypoint_idx < len(self.waypoints) - 1:
            self.waypoint_idx += 1
            target_xy = self.waypoints[self.waypoint_idx]
            delta = target_xy - pos_xy
            dist = np.linalg.norm(delta)

        yaw = self.base_yaw
        target_yaw = np.arctan2(delta[1], delta[0])
        yaw_error = wrap_to_pi(target_yaw - yaw)

        if self.reached_position:
            linear_vel = 0.0
            yaw_error = self.final_yaw_error
            angular_vel = np.clip(1.8 * yaw_error, -max_angular, max_angular)
        else:
            linear_vel = np.clip(0.75 * dist, 0.0, max_linear)
            if abs(yaw_error) > 0.7:
                linear_vel *= 0.25
            elif abs(yaw_error) > 0.35:
                linear_vel *= 0.55
            angular_vel = np.clip(1.8 * yaw_error, -max_angular, max_angular)

        self.set_base_twist(linear_vel, angular_vel)
        return pos_xy, target_xy, dist, yaw_error, linear_vel, angular_vel

    @property
    def reached_position(self):
        pos_xy = np.array(self.sensor_base_position[:2], dtype=float)
        return self.waypoint_idx == len(self.waypoints) - 1 and np.linalg.norm(self.target_xy - pos_xy) < self.stop_distance

    @property
    def final_yaw_error(self):
        return wrap_to_pi(self.final_yaw - self.base_yaw)

    @property
    def reached_target(self):
        return self.reached_position and abs(self.final_yaw_error) < self.yaw_tolerance

    def set_base_twist(self, linear_x, angular_z):
        self.tctr_base[0] = (linear_x - angular_z * self.wheel_distance) / self.wheel_radius
        self.tctr_base[1] = (linear_x + angular_z * self.wheel_distance) / self.wheel_radius

    def stop_base(self):
        self.set_base_twist(0.0, 0.0)

    def post_physics_step(self):
        pass

    def getChangedObjectPose(self):
        return {}

    def checkTerminated(self):
        return False

    def getObservation(self):
        return {
            "time": self.mj_data.time,
            "base_position": self.sensor_base_position.tolist(),
            "base_orientation": self.sensor_base_orientation.tolist(),
        }

    def getPrivilegedObservation(self):
        return self.getObservation()

    def getReward(self):
        return 0.0


def build_cfg(args):
    cfg = MMK2Cfg()
    cfg.mjcf_file_path = "examples/shentoon/mjcf/shentoon2.xml"
    cfg.use_gaussian_renderer = args.use_gs
    cfg.sync = not args.headless
    cfg.headless = args.headless
    cfg.enable_render = not args.headless
    cfg.decimation = 2
    cfg.render_set = {
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "window_title": "Shentoon2 Navigation Demo",
    }
    cfg.obs_rgb_cam_id = []
    cfg.obs_depth_cam_id = []
    cfg.init_state["base_position"] = [-3.8, -3.8, 0.0]
    cfg.init_state["base_orientation"] = Rotation.from_euler("z", np.pi / 4.0).as_quat()[[3, 0, 1, 2]].tolist()
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Navigate MMK2 through picking zone to the delivery zone.")
    parser.add_argument("--headless", action="store_true", help="Run without opening a window.")
    parser.add_argument("--use-gs", action="store_true", help="Enable Gaussian renderer. Requires local 3DGS assets or Hugging Face login.")
    parser.add_argument("--pick-target", default="-1.55,-0.45", help="Picking-zone target as x,y.")
    parser.add_argument(
        "--pick-waypoints",
        default="-1.9,-3.25;0.35,-3.10;2.45,-2.75;2.35,0.10",
        help="Semicolon-separated intermediate x,y waypoints: obstacle area, then picking-zone approach.",
    )
    parser.add_argument("--delivery-target", default="3.55,3.12", help="Reachable delivery-zone target as x,y.")
    parser.add_argument(
        "--delivery-waypoints",
        default="-0.35,-1.70;2.55,-1.45;3.15,0.85;3.45,2.50",
        help="Semicolon-separated intermediate x,y waypoints from picking zone to delivery zone.",
    )
    parser.add_argument("--stop-distance", type=float, default=0.18)
    parser.add_argument("--pick-yaw", type=float, default=np.pi / 2.0, help="Base yaw at picking zone in radians. Default faces the shelves.")
    parser.add_argument("--delivery-yaw", type=float, default=np.pi / 2.0, help="Final base yaw at delivery zone in radians.")
    parser.add_argument("--yaw-tolerance", type=float, default=0.05, help="Allowed final yaw error in radians.")
    parser.add_argument("--max-linear", type=float, default=0.55)
    parser.add_argument("--max-angular", type=float, default=1.0)
    parser.add_argument("--max-time", type=float, default=100.0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    pick_target_xy = parse_xy_list(args.pick_target)[0]
    pick_waypoints = parse_xy_list(args.pick_waypoints)
    delivery_target_xy = parse_xy_list(args.delivery_target)[0]
    delivery_waypoints = parse_xy_list(args.delivery_waypoints)

    sim_node = Shentoon2NavDemo(build_cfg(args), pick_target_xy, pick_waypoints, args.stop_distance, args.pick_yaw, args.yaw_tolerance)
    action = np.zeros_like(sim_node.target_control)
    obs = sim_node.reset()
    print("Navigation demo started.")
    print(f"Start: {np.array(obs['base_position'][:2])}")
    print(f"Pick route: {[p.tolist() for p in sim_node.waypoints]}")

    last_print_time = -1.0
    phase = "pick"
    completed_delivery = False
    try:
        while sim_node.running and sim_node.mj_data.time < args.max_time:
            pos_xy, target, dist, yaw_error, linear_vel, angular_vel = sim_node.drive_toward_next_waypoint(
                args.max_linear,
                args.max_angular,
            )
            obs, _, _, _, _ = sim_node.step(action)

            if sim_node.mj_data.time - last_print_time > 1.0:
                print(
                    f"t={sim_node.mj_data.time:5.2f}s "
                    f"wp={sim_node.waypoint_idx + 1}/{len(sim_node.waypoints)} "
                    f"pos=({pos_xy[0]: .2f}, {pos_xy[1]: .2f}) "
                    f"target=({target[0]: .2f}, {target[1]: .2f}) "
                    f"dist={dist:.2f} yaw_err={yaw_error:.2f} "
                    f"cmd=({linear_vel:.2f}, {angular_vel:.2f})"
                )
                last_print_time = sim_node.mj_data.time

            if sim_node.reached_target:
                if phase == "pick":
                    print("Reached picking zone and faced shelves. Continuing to delivery zone.")
                    sim_node.set_route(delivery_target_xy, delivery_waypoints, args.delivery_yaw)
                    phase = "delivery"
                    last_print_time = -1.0
                    continue
                else:
                    sim_node.stop_base()
                    for _ in range(20):
                        obs, _, _, _, _ = sim_node.step(action)
                    completed_delivery = True
                    break

            if not args.headless:
                time.sleep(0.001)

    finally:
        final_xy = np.array(obs["base_position"][:2], dtype=float)
        print(f"Final position: ({final_xy[0]:.3f}, {final_xy[1]:.3f})")
        print(f"Distance to delivery target: {np.linalg.norm(delivery_target_xy - final_xy):.3f} m")
        print(f"Final yaw error: {sim_node.final_yaw_error:.3f} rad")
        if not completed_delivery:
            print(f"Did not reach delivery target before max_time={args.max_time:.1f}s. Current phase: {phase}.")
        if hasattr(sim_node, "_cleanup_before_exit"):
            sim_node._cleanup_before_exit()


if __name__ == "__main__":
    main()
