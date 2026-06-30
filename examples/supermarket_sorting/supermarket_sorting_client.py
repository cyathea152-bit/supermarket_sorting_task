#!/usr/bin/env python3
"""ROS2 client for the Supermarket Sorting Task.

Drive MMK2 to shelf D, pick slot_D_L2_C2_yinlu, and place it on the delivery
table. The client keeps a 19-d target_control, computes right-arm joints with
MMK2Kdl, and publishes to the controller command topics exposed by the server.

Subscribes:
  /slamware_ros_sdk_server_node/odom   (nav_msgs/Odometry)  base pose in world
  /joint_states                        (sensor_msgs/JointState) 17 joints
Publishes:
  /cmd_vel, /spine.../commands, /head.../commands,
  /{left,right}_arm_forward_position_controller/commands
"""
import math
import numpy as np
from scipy.spatial.transform import Rotation

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float64MultiArray
from collections import deque

from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from vision_msgs.msg import Detection3DArray

from discoverse.utils import step_func
from mmk2_kdl import MMK2Kdl

# ---- scene constants (world frame, +X east / +Y north). The object pose is NOT
#      hardcoded -- it comes purely from vision (/yinlu/detections). Navigation
#      waypoints below are task setup ("where the robot goes"), not object poses. ----
TABLE_ORIGIN = np.array([-1.92, -3.17, 0.0])     # delivery_table; top surface z~0.80
YAW_NORTH = math.pi / 2.0
YAW_SOUTH = -math.pi / 2.0

YELLOW_MID_Y = 2.475          # 抓取区两条黄线(y=1.70/3.25)正中
GRASP_BASE_X = 0.91           # 抓取列停靠 x(机器人去哪,非物体坐标);视觉再选正前方的 yinlu
GRASP_YAW = math.pi / 2.0     # 正北:base-creep 法,车直着开进去夹爪不侧偏
# 直行到黄线中点 -> 左转西行到货架列,停在黄线处(开阔区)部署胳膊,再 creep 进去
ROUTE_TO_SHELF = [[1.92, YELLOW_MID_Y], [GRASP_BASE_X, YELLOW_MID_Y]]
# 倒车退回黄线中点后,左转西行接避障下行路径
ROUTE_TO_TABLE = [[-0.35, YELLOW_MID_Y], [-0.35, -1.10], [-0.90, -1.10], [-0.90, -2.50], [-1.75, -2.50]]

# ---- manipulation params (verified via teleop on slot_D_L2_C2) ----
GRASP_ARM = "r"
HEAD_PITCH = -0.6
SLIDE_PRE, SLIDE_GRASP, SLIDE_LIFT = 0.11, 0.11, -0.04
GRIP_OPEN, GRIP_CLOSE = 1.0, 0.2   # 夹爪闭合度
# Grasp orientation found in teleop (zyx-euler a_rot). Works at GRASP_YAW, not north.
# Computed grasp orientation (north-facing): finger-close axis horizontal
# (straddles the vertical cylinder) + approach axis horizontal +Y (level entry).
# The arm is deployed in OPEN SPACE at the yellow line, then the BASE creeps the
# whole gripper straight into the shelf -- the arm never sweeps near the board.
GRASP_EULER = [-1.60, -1.60, -0.38]
# Gripper orientation in the FOOTPRINT frame for the verified grasp, expressed as a
# rotation matrix for MMK2Kdl (which takes the raw EE rotation, unlike MMK2FIK's
# "pick" action that pre-multiplies action_rot). This matrix is the FK rotation of
# the MMK2FIK solution for GRASP_EULER -- KDL round-trips it to the same physical pose.
GRASP_ROT = np.array([
    [ 0.93909533, -0.34348620,  0.01082593],
    [ 0.34365571,  0.93870412, -0.02711702],
    [-0.00084802,  0.02918586,  0.99957364],
])
GRASP_OFFSET = np.array([0.00, -0.01, 0.023])     # gripper vs object at grasp
# Open-space deploy pose & creep-stop, kept as OFFSETS from the PERCEIVED object so the
# grasp METHOD stays byte-identical to the original baseline while the target comes purely
# from vision. (Offsets measured from the original teleop-tuned constants.)
DEPLOY_OFFSET = np.array([-0.011, -0.315, 0.023]) # deploy further forward -> base stops further back -> elbow stays out of the shelf
CREEP_STOP_DY = 0.005                             # stop the creep when gripper reaches here (~object center, 居中夹取)

# perception target selection (pure vision; NO hardcoded object pose):
# the robot navigates to the shelf column, then grasps the yinlu directly ahead.
# Selection uses only the robot's own footprint frame -- the detection with the
# smallest lateral offset, at a plausible forward shelf depth.
DETECT_MIN_SAMPLES = 5            # frames to accumulate before trusting the lock
DETECT_TIMEOUT = 12.0            # s; abort the run if no yinlu is locked within this
REACH_FWD_MIN, REACH_FWD_MAX = 0.3, 1.5   # m ahead of base: plausible shelf depth
REACH_LATERAL_MAX = 0.45         # m sideways: reject yinlu in other columns
CREEP_SPEED = 0.06                                # m/s forward while creeping into the shelf
CREEP_YAW_KP = 4.0                                # hold heading firmly so the creep goes dead straight
LIFT_AMOUNT = 0.05                                # 夹住后竖直抬起量(减小 slide),让物体离开隔板再倒车
CARRY_FP = np.array([0.40, 0.0, 1.0])             # 抱持姿态(footprint 系):夹爪收回约一半,贴近身体,导航不怼墙
# Placement: robot faces SOUTH at the table; arm must reach OUT over the table top
# (z~0.80) and set the object down. Offsets are world-frame (TABLE_ORIGIN z=0).
PLACE_LOWER_SLIDE = 0.20                          # 松爪前把升降平台降到此值(整体竖直下降),物体降到桌面附近再松

# JointState names (order documented by the server).
JOINT_NAMES = [
    "slide_joint", "head_yaw_joint", "head_pitch_joint",
    "left_arm_joint1", "left_arm_joint2", "left_arm_joint3", "left_arm_joint4", "left_arm_joint5", "left_arm_joint6", "left_arm_eef_gripper_joint",
    "right_arm_joint1", "right_arm_joint2", "right_arm_joint3", "right_arm_joint4", "right_arm_joint5", "right_arm_joint6", "right_arm_eef_gripper_joint",
]
INIT_ARM_L = [0.0, -0.166, 0.032, 0.0, 1.571, 2.223]
INIT_ARM_R = [0.0, -0.166, 0.032, 0.0, -1.571, -2.223]

# top-level phases
NAV_SHELF, DEPLOY, CREEP, CLOSE, LIFT, RETREAT, NAV_TABLE, PLACE, DONE = range(9)
PHASE_NAME = {NAV_SHELF: "nav->shelf", DEPLOY: "deploy-arm", CREEP: "creep-in", CLOSE: "close",
              LIFT: "lift", RETREAT: "retreat", NAV_TABLE: "nav->table", PLACE: "place", DONE: "done"}
RETREAT_SPEED = 0.20          # 倒车速度 m/s


def wrap_to_pi(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


class PickPlaceClient(Node):
    def __init__(self):
        super().__init__("supermarket_sorting_client")
        self.kdl = MMK2Kdl()   # unified FK + analytical-grade IK (matches MMK2FIK on this mjcf)

        # target_control: [base_lin, base_ang, slide, head_yaw, head_pitch,
        #                  l_arm(6), l_grip, r_arm(6), r_grip]
        self.tc = np.zeros(19)
        self.tc[5:11] = INIT_ARM_L
        self.tc[11] = GRIP_OPEN
        self.tc[12:18] = INIT_ARM_R
        self.tc[18] = GRIP_OPEN

        # smoothed command actually published for slide/head/arms/grippers (idx 2..18):
        # step_func slews `action` toward `tc` so a new IK target never snaps (fixes 瞬移).
        # base velocity (idx 0,1) is NOT smoothed here -- it has its own accel ramp.
        self.action = self.tc.copy()
        self.joint_move_ratio = np.ones(19)
        self.tc_prev = self.tc.copy()
        self.joint_slew = 1.2            # rad/s (and grip-units/s) for the fastest joint

        # latest feedback
        self.base_xy = None
        self.base_yaw = 0.0
        self.jpos = None          # dict name->pos
        self.jvel = None

        # nav/phase state
        self.phase = NAV_SHELF
        self.nav_idx = 0
        self.nav_mode = "turn"
        self.sub_idx = 0
        self.sub_entered = False
        self.deploy_set = False
        self.carry_set = False
        self.place_sub = 0
        self.state_t0 = self.now()
        self.arm_target_set = False

        # ---- perception: target locked PURELY from /yinlu/detections (world frame) ----
        # No hardcoded object pose. OBJECT_WORLD/DEPLOY_WORLD/CREEP_STOP_Y stay None until a
        # yinlu is detected and locked at DEPLOY; the run aborts if none is seen within
        # DETECT_TIMEOUT. CREEP_STOP_Y/DEPLOY_WORLD are then derived via the grasp offsets.
        self.OBJECT_WORLD = None
        self.DEPLOY_WORLD = None
        self.CREEP_STOP_Y = None
        self.det_buf = deque(maxlen=30)   # recent detections of the yinlu directly ahead (world xyz)
        self.target_locked = False

        # gains
        self.pos_tol, self.turn_tol = 0.06, 0.03
        self.max_lin, self.max_ang = 0.45, 1.2
        # velocity ramping (acceleration limits) so /cmd_vel never jumps -> smooth motion
        self.rate_hz = 50.0
        self.dt = 1.0 / self.rate_hz
        self.max_lin_acc, self.max_ang_acc = 0.8, 5.0   # m/s^2, rad/s^2
        self.des_lin = self.des_ang = 0.0               # desired (from controller)
        self.cur_lin = self.cur_ang = 0.0               # ramped (actually published)

        # io
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 5)
        self.spine_pub = self.create_publisher(Float64MultiArray, "/spine_forward_position_controller/commands", 5)
        self.head_pub = self.create_publisher(Float64MultiArray, "/head_forward_position_controller/commands", 5)
        self.larm_pub = self.create_publisher(Float64MultiArray, "/left_arm_forward_position_controller/commands", 5)
        self.rarm_pub = self.create_publisher(Float64MultiArray, "/right_arm_forward_position_controller/commands", 5)
        self.create_subscription(Odometry, "/slamware_ros_sdk_server_node/odom", self.odom_cb, 10)
        self.create_subscription(JointState, "/joint_states", self.js_cb, 10)
        self.create_subscription(Detection3DArray, "/yinlu/detections", self.det_cb, 10)

        self.timer = self.create_timer(self.dt, self.tick)
        self.last_log = 0.0
        self.get_logger().info("pick-place client up; waiting for odom + joint_states...")

    # ---- ros helpers ----
    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def odom_cb(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        self.base_xy = np.array([p.x, p.y])
        self.base_yaw = Rotation.from_quat([q.x, q.y, q.z, q.w]).as_euler("xyz")[2]

    def js_cb(self, msg):
        self.jpos = {n: msg.position[i] for i, n in enumerate(msg.name) if i < len(msg.position)}
        self.jvel = {n: msg.velocity[i] for i, n in enumerate(msg.name) if i < len(msg.velocity)}

    def det_cb(self, msg):
        """Accumulate the yinlu directly ahead of the parked base (world frame).

        Pure vision -- there is NO prior object pose. Among all yinlu detections we
        keep the one most directly ahead of the robot (smallest lateral offset in the
        footprint frame, at a plausible forward shelf depth). Because the robot has
        navigated to the target shelf column, that bottle is the intended target.
        Selection uses only the robot's own frame, never a hardcoded object coordinate.
        """
        if self.target_locked or self.base_xy is None:
            return
        best, best_lat = None, REACH_LATERAL_MAX
        for det in msg.detections:
            if not det.results:
                continue
            pos = det.results[0].pose.pose.position
            pw = np.array([pos.x, pos.y, pos.z])
            fp = self.world_to_footprint(pw)   # fp[0]=forward (ahead), fp[1]=lateral (left+)
            fwd, lat = fp[0], abs(fp[1])
            if fwd < REACH_FWD_MIN or fwd > REACH_FWD_MAX:
                continue                       # wrong depth: floor, far shelf, etc.
            if lat < best_lat:
                best_lat, best = lat, pw       # most centered bottle wins
        if best is not None:
            self.det_buf.append(best)

    def _lock_target(self):
        """Lock OBJECT_WORLD from the accumulated detections. Returns True once locked.

        Called from DEPLOY before posing the arm. No fallback: if fewer than
        DETECT_MIN_SAMPLES have arrived it returns False and DEPLOY keeps waiting
        (until DETECT_TIMEOUT, then the run aborts).
        """
        if len(self.det_buf) < DETECT_MIN_SAMPLES:
            return False
        arr = np.array(list(self.det_buf))
        self.OBJECT_WORLD = np.median(arr, axis=0)
        self.DEPLOY_WORLD  = self.OBJECT_WORLD + DEPLOY_OFFSET
        self.CREEP_STOP_Y  = self.OBJECT_WORLD[1] + CREEP_STOP_DY
        self.target_locked = True
        self.get_logger().info(
            f"[perception] yinlu locked from vision: "
            f"OBJECT={np.round(self.OBJECT_WORLD,3)}  "
            f"CREEP_STOP_Y={self.CREEP_STOP_Y:.4f}  samples={len(self.det_buf)}")
        return True

    @property
    def slide_meas(self):
        return self.jpos.get("slide_joint", self.tc[2])

    @property
    def rarm_meas(self):
        return np.array([self.jpos.get(f"right_arm_joint{i+1}", self.tc[12 + i]) for i in range(6)])

    # ---- frames ----
    def world_to_footprint(self, p_world):
        d = np.array(p_world, dtype=float) - np.array([self.base_xy[0], self.base_xy[1], 0.0])
        c, s = math.cos(-self.base_yaw), math.sin(-self.base_yaw)
        return np.array([c * d[0] - s * d[1], s * d[0] + c * d[1], d[2]])

    def footprint_to_world(self, fp):
        c, s = math.cos(self.base_yaw), math.sin(self.base_yaw)
        return np.array([self.base_xy[0] + c * fp[0] - s * fp[1],
                         self.base_xy[1] + s * fp[0] + c * fp[1], fp[2]])

    def arm_to(self, world_pos, rot=GRASP_ROT):
        """Set right-arm joints so the gripper reaches a world position with the grasp
        orientation, via MMK2Kdl IK (footprint frame). IK failures leave the arm held."""
        fp = self.world_to_footprint(world_pos)
        T = np.eye(4)
        T[:3, :3] = rot
        T[:3, 3] = fp
        ref = np.zeros(7)
        ref[0] = float(self.tc[2])
        ref[1:] = self.rarm_meas
        sols = self.kdl.inverse_kinematics(T_left=None, T_right=T, ref_pos=ref, target_height=float(self.tc[2]))
        if sols:
            self.tc[12:18] = np.asarray(sols[0])[1:7]
            self.arm_target_set = True
        else:
            self.get_logger().warn(f"IK unreachable: world={np.round(world_pos, 3)} fp={np.round(fp, 3)} (arm holds)")

    def ee_world(self):
        """Actual gripper endpoint in world via MMK2Kdl forward kinematics (measured joints)."""
        _, T = self.kdl.forward_kinematics(np.concatenate([[float(self.slide_meas)], self.rarm_meas]), index="right")
        return self.footprint_to_world(T[:3, 3])

    # ---- smoothing ----
    def smooth_step(self):
        """Slew `action[2:19]` toward `tc[2:19]` so a freshly-set joint target ramps in
        instead of snapping (the cause of grasp 瞬移). When the target changes,
        normalize per-joint speed by the largest delta so all joints
        arrive together; then step_func each toward its target every tick."""
        if not np.allclose(self.tc[2:19], self.tc_prev[2:19]):
            dif = np.abs(self.action[2:19] - self.tc[2:19])
            self.joint_move_ratio[2:19] = dif / (np.max(dif) + 1e-6)
            self.joint_move_ratio[2] *= 0.3   # 升降放慢到 1/3: 放置时物体轻放下, 不砸桌面引发晃动
            self.tc_prev[:] = self.tc
        step = self.joint_slew * self.dt
        for i in range(2, 19):
            self.action[i] = step_func(self.action[i], self.tc[i], self.joint_move_ratio[i] * step)

    # ---- publishing ----
    def publish(self):
        tw = Twist()
        tw.linear.x = float(self.tc[0])
        tw.angular.z = float(self.tc[1])
        self.cmd_vel_pub.publish(tw)
        self.spine_pub.publish(Float64MultiArray(data=[float(self.action[2])]))
        self.head_pub.publish(Float64MultiArray(data=[float(self.action[3]), float(self.action[4])]))
        self.larm_pub.publish(Float64MultiArray(data=[float(x) for x in self.action[5:11]] + [float(self.action[11])]))
        self.rarm_pub.publish(Float64MultiArray(data=[float(x) for x in self.action[12:18]] + [float(self.action[18])]))

    # ---- navigation ----
    def set_twist(self, lin, ang):
        self.des_lin = float(np.clip(lin, -self.max_lin, self.max_lin))
        self.des_ang = float(np.clip(ang, -self.max_ang, self.max_ang))

    def ramp_twist(self):
        """Acceleration-limit the published velocity so /cmd_vel changes smoothly."""
        dl = np.clip(self.des_lin - self.cur_lin, -self.max_lin_acc * self.dt, self.max_lin_acc * self.dt)
        da = np.clip(self.des_ang - self.cur_ang, -self.max_ang_acc * self.dt, self.max_ang_acc * self.dt)
        self.cur_lin += dl
        self.cur_ang += da
        self.tc[0], self.tc[1] = self.cur_lin, self.cur_ang

    def follow_route(self, route, final_yaw):
        if self.nav_idx < len(route):
            target = np.array(route[self.nav_idx], dtype=float)
            delta = target - self.base_xy
            dist = float(np.linalg.norm(delta))
            yaw_err = wrap_to_pi(math.atan2(delta[1], delta[0]) - self.base_yaw)
            if self.nav_mode == "turn":
                self.set_twist(0.0, 2.2 * yaw_err)
                if abs(yaw_err) < self.turn_tol:
                    self.nav_mode = "drive"
            else:
                if dist < self.pos_tol:
                    self.nav_idx += 1
                    self.nav_mode = "turn"
                    self.set_twist(0.0, 0.0)
                else:
                    # Steering: deadband when nearly aligned, and FREEZE near the
                    # waypoint (bearing blows up there) -> long straights stay dead
                    # straight with no angular twitch.
                    if abs(yaw_err) < 0.05 or dist < 0.25:
                        ang = 0.0
                    else:
                        ang = 2.2 * yaw_err
                    align = max(0.0, math.cos(yaw_err))
                    self.set_twist(1.0 * dist * align, ang)
            return False
        yaw_err = wrap_to_pi(final_yaw - self.base_yaw)
        self.set_twist(0.0, 1.8 * yaw_err)
        if abs(yaw_err) < self.turn_tol:
            self.set_twist(0.0, 0.0)
            return True
        return False

    def reset_nav(self):
        self.nav_idx = 0
        self.nav_mode = "turn"

    # ---- manipulation step gating (joint-space convergence + dwell) ----
    def action_done(self, dwell=0.4):
        if self.now() - self.state_t0 < dwell:
            return False
        slide_ok = abs(self.slide_meas - self.tc[2]) < 0.02
        arm_ok = (not self.arm_target_set) or np.max(np.abs(self.rarm_meas - self.tc[12:18])) < 0.05
        return slide_ok and arm_ok

    def enter_sub(self):
        self.sub_entered = True
        self.state_t0 = self.now()
        self.arm_target_set = False

    def run_sub(self, setter, n_states):
        if not self.sub_entered:
            setter(self.sub_idx)
            self.enter_sub()
        if self.action_done():
            self.sub_idx += 1
            self.sub_entered = False
        return self.sub_idx >= n_states

    # ---- main 30 Hz tick ----
    def tick(self):
        if self.base_xy is None or self.jpos is None:
            return

        if self.phase == NAV_SHELF:
            if self.follow_route(ROUTE_TO_SHELF, GRASP_YAW):
                self.phase, self.deploy_set = DEPLOY, False
                self.state_t0 = self.now()   # start the detection dwell window fresh
        elif self.phase == DEPLOY:
            # 在黄线开阔处把胳膊摆成抓取姿态(张爪、抓取高度、水平),手臂全程不再动
            self.set_twist(0.0, 0.0)
            if not self.deploy_set:
                # Aim head/slide so the shelf is in view, accumulate /yinlu/detections,
                # then lock the target PURELY from vision and pose the arm. No hardcoded
                # fallback: if no yinlu is seen within DETECT_TIMEOUT, abort the run.
                self.tc[4] = HEAD_PITCH
                self.tc[2] = SLIDE_GRASP
                self.tc[18] = GRIP_OPEN
                if self._lock_target():
                    self.arm_to(self.DEPLOY_WORLD)
                    self.deploy_set = True
                    self.state_t0 = self.now()
                elif self.now() - self.state_t0 > DETECT_TIMEOUT:
                    self.get_logger().fatal(
                        f"no yinlu detected within {DETECT_TIMEOUT:.0f}s "
                        f"(samples={len(self.det_buf)}); aborting. Is the perception node "
                        f"(yinlu_detect.py) running and publishing /yinlu/detections?")
                    raise SystemExit(1)
            if self.deploy_set and self.action_done():
                self.phase = CREEP
        elif self.phase == CREEP:
            # 保持胳膊不动,车直着往前开,把整个夹爪平移送到物体处
            ee = self.ee_world()
            if ee[1] < self.CREEP_STOP_Y:
                self.set_twist(CREEP_SPEED, CREEP_YAW_KP * wrap_to_pi(GRASP_YAW - self.base_yaw))
            else:
                self.set_twist(0.0, 0.0)
                self.phase = CLOSE
                self.state_t0 = self.now()
        elif self.phase == CLOSE:
            self.set_twist(0.0, 0.0)
            self.tc[18] = GRIP_CLOSE
            if self.now() - self.state_t0 > 0.8:
                self.phase = LIFT
        elif self.phase == LIFT:
            # 竖直抬起(减小 slide,胸部上移),让物体离开隔板,胳膊关节保持不动
            self.set_twist(0.0, 0.0)
            self.tc[2] = SLIDE_GRASP - LIFT_AMOUNT
            if abs(self.slide_meas - self.tc[2]) < 0.02:
                self.phase = RETREAT
        elif self.phase == RETREAT:
            # 倒车(保持抓取朝向)退回黄线中点,object 还夹在手里
            yaw_err = wrap_to_pi(GRASP_YAW - self.base_yaw)
            if self.base_xy[1] > YELLOW_MID_Y + self.pos_tol:
                self.set_twist(-RETREAT_SPEED, 1.0 * yaw_err)
            else:
                self.set_twist(0.0, 0.0)
                self.phase = NAV_TABLE
                self.reset_nav()
        elif self.phase == NAV_TABLE:
            if self.follow_route(ROUTE_TO_TABLE, YAW_SOUTH):
                self.phase, self.place_sub = PLACE, 0
                self.state_t0 = self.now()
        elif self.phase == PLACE:
            self.set_twist(0.0, 0.0)
            if self.place_sub == 0:
                # 先把升降平台整体降下来,物体随之竖直下降到桌面附近(手臂关节不动)
                self.tc[2] = PLACE_LOWER_SLIDE
                if abs(self.slide_meas - PLACE_LOWER_SLIDE) < 0.02:
                    self.place_sub = 1
                    self.state_t0 = self.now()
            else:
                # 到位后松爪,物体落桌
                self.tc[18] = GRIP_OPEN
                if self.now() - self.state_t0 > 1.0:
                    self.phase = DONE
        else:
            self.set_twist(0.0, 0.0)

        self.ramp_twist()
        self.smooth_step()
        self.publish()

        if self.now() - self.last_log > 1.0:
            ee = self.ee_world()
            obj = self.OBJECT_WORLD
            obj_str = (f"({obj[0]:.3f},{obj[1]:.3f},{obj[2]:.3f})"
                       if obj is not None else "unlocked")
            self.get_logger().info(
                f"phase={PHASE_NAME[self.phase]} sub={self.sub_idx} "
                f"base=({self.base_xy[0]:.2f},{self.base_xy[1]:.2f}) yaw={self.base_yaw:.2f} slide={self.slide_meas:.3f} "
                f"gripper=({ee[0]:.3f},{ee[1]:.3f},{ee[2]:.3f}) "
                f"obj={obj_str} locked={self.target_locked}")
            self.last_log = self.now()


def main():
    rclpy.init()
    node = PickPlaceClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
