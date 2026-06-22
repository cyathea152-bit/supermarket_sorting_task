import argparse
import os
import threading

import mujoco
import numpy as np
import rclpy
import tf2_ros
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from sensor_msgs.msg import CameraInfo, Image, JointState, LaserScan
from scipy.spatial.transform import Rotation
from visualization_msgs.msg import Marker, MarkerArray

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

from discoverse.robots_env.mmk2_base import MMK2Base, MMK2Cfg
from discoverse.utils import PIDarray, camera2k


class Shentoon2MMK2ROS2(MMK2Base, Node):
    target_control = np.zeros(19)

    def __init__(self, config):
        self.tctr_base = self.target_control[:2]
        self.tctr_slide = self.target_control[2:3]
        self.tctr_head = self.target_control[3:5]
        self.tctr_left_arm = self.target_control[5:11]
        self.tctr_lft_gripper = self.target_control[11:12]
        self.tctr_right_arm = self.target_control[12:18]
        self.tctr_rgt_gripper = self.target_control[18:19]

        MMK2Base.__init__(self, config)
        Node.__init__(self, "shentoon2_mmk2_mujoco_node")

        self.pid_base_vel = PIDarray(
            kps=np.array([7.5, 7.5]),
            kis=np.array([0.0, 0.0]),
            kds=np.array([0.0, 0.0]),
            integrator_maxs=np.array([5.0, 5.0]),
        )
        self.init_topic_publisher()
        self.init_topic_subscriber()

        self.camera_ids = {
            "head": self.camera_id("head_cam"),
            "left_arm": self.camera_id("lft_handeye"),
            "right_arm": self.camera_id("rgt_handeye"),
        }
        print("MMK2 camera ids:", self.camera_ids)
        self.print_ros2_startup_help()

    def print_ros2_startup_help(self):
        published_topics = [
            "/joint_states",
            "/slamware_ros_sdk_server_node/odom",
            "/tf",
            "/head_camera/color/image_raw",
            "/head_camera/aligned_depth_to_color/image_raw",
            "/head_camera/color/camera_info",
            "/head_camera/aligned_depth_to_color/camera_info",
            "/left_camera/color/image_raw",
            "/left_camera/color/camera_info",
            "/right_camera/color/image_raw",
            "/right_camera/color/camera_info",
            "/mujoco_scene",
        ]
        if self.config.lidar_s2_sim:
            published_topics.append("/slamware_ros_sdk_server_node/scan")

        print("\nROS2 publisher is ready.")
        print(f"  node: /{self.get_name()}")
        print(f"  ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '<unset>')}")
        print(f"  RMW_IMPLEMENTATION={os.environ.get('RMW_IMPLEMENTATION', '<unset>')}")
        print("  RViz Fixed Frame: odom")
        print("  Published topics:")
        for topic in published_topics:
            print(f"    {topic}")
        print("")

    def init_topic_subscriber(self):
        self.cmd_vel_suber = self.create_subscription(Twist, "/cmd_vel", self.cmd_vel_callback, 5)
        self.spine_cmd_suber = self.create_subscription(Float64MultiArray, "/spine_forward_position_controller/commands", self.cmd_spine_callback, 5)
        self.head_cmd_suber = self.create_subscription(Float64MultiArray, "/head_forward_position_controller/commands", self.cmd_head_callback, 5)
        self.left_arm_cmd_suber = self.create_subscription(Float64MultiArray, "/left_arm_forward_position_controller/commands", self.cmd_left_arm_callback, 5)
        self.right_arm_cmd_suber = self.create_subscription(Float64MultiArray, "/right_arm_forward_position_controller/commands", self.cmd_right_arm_callback, 5)

    def cmd_vel_callback(self, msg):
        self.tctr_base[0] = (msg.linear.x - msg.angular.z * self.wheel_distance) / self.wheel_radius
        self.tctr_base[1] = (msg.linear.x + msg.angular.z * self.wheel_distance) / self.wheel_radius

    def cmd_spine_callback(self, msg):
        if len(msg.data) == 1:
            self.tctr_slide[:] = msg.data[:]
        else:
            self.get_logger().error("Spine command length error")

    def cmd_head_callback(self, msg):
        if len(msg.data) == 2:
            self.tctr_head[:] = msg.data[:]
        else:
            self.get_logger().error("Head command length error")

    def cmd_left_arm_callback(self, msg):
        if len(msg.data) == 7:
            self.tctr_left_arm[:] = msg.data[:6]
            self.tctr_lft_gripper[:] = msg.data[6:]
        else:
            self.get_logger().error("Left arm command length error")

    def cmd_right_arm_callback(self, msg):
        if len(msg.data) == 7:
            self.tctr_right_arm[:] = msg.data[:6]
            self.tctr_rgt_gripper[:] = msg.data[6:]
        else:
            self.get_logger().error("Right arm command length error")

    def resetState(self):
        super().resetState()
        self.pid_base_vel.reset()
        self.target_control[:] = self.init_joint_ctrl[:]

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

    def camera_id(self, name):
        cam_id = mujoco.mj_name2id(self.mj_model, mujoco.mjtObj.mjOBJ_CAMERA, name)
        if cam_id < 0:
            raise ValueError(f"Camera not found in MJCF: {name}")
        return cam_id

    def make_camera_info(self, cam_id, frame_id):
        info = CameraInfo()
        info.width = self.config.render_set["width"]
        info.height = self.config.render_set["height"]
        info.header.frame_id = frame_id
        info.k = camera2k(
            self.mj_model.cam_fovy[cam_id] * np.pi / 180.0,
            self.config.render_set["width"],
            self.config.render_set["height"],
        ).flatten().tolist()
        return info

    def init_topic_publisher(self):
        self.tf_broadcaster = tf2_ros.TransformBroadcaster(self)

        self.joint_state_puber = self.create_publisher(JointState, "/joint_states", 5)
        self.joint_state = JointState()
        self.joint_state.name = [
            "slide_joint", "head_yaw_joint", "head_pitch_joint",
            "left_arm_joint1", "left_arm_joint2", "left_arm_joint3", "left_arm_joint4", "left_arm_joint5", "left_arm_joint6", "left_arm_eef_gripper_joint",
            "right_arm_joint1", "right_arm_joint2", "right_arm_joint3", "right_arm_joint4", "right_arm_joint5", "right_arm_joint6", "right_arm_eef_gripper_joint",
        ]
        self.joint_state.position = self.sensor_qpos[2:].tolist()
        self.joint_state.velocity = self.sensor_qvel[2:].tolist()
        self.joint_state.effort = self.sensor_force[2:].tolist()

        self.odom_puber = self.create_publisher(Odometry, "/slamware_ros_sdk_server_node/odom", 5)
        self.odom_msg = Odometry()
        self.odom_msg.header.frame_id = "odom"
        self.odom_msg.child_frame_id = "base_link"

        if self.config.lidar_s2_sim:
            self.lidar_s2_puber = self.create_publisher(LaserScan, "/slamware_ros_sdk_server_node/scan", 1)
        self.scene_marker_puber = self.create_publisher(MarkerArray, "/mujoco_scene", 1)

        self.head_color_puber = self.create_publisher(Image, "/head_camera/color/image_raw", 2)
        self.head_color_info_puber = self.create_publisher(CameraInfo, "/head_camera/color/camera_info", 2)
        self.head_depth_puber = self.create_publisher(Image, "/head_camera/aligned_depth_to_color/image_raw", 2)
        self.head_depth_info_puber = self.create_publisher(CameraInfo, "/head_camera/aligned_depth_to_color/camera_info", 2)
        self.left_color_puber = self.create_publisher(Image, "/left_camera/color/image_raw", 2)
        self.left_color_info_puber = self.create_publisher(CameraInfo, "/left_camera/color/camera_info", 2)
        self.right_color_puber = self.create_publisher(Image, "/right_camera/color/image_raw", 2)
        self.right_color_info_puber = self.create_publisher(CameraInfo, "/right_camera/color/camera_info", 2)

        self.head_color_info = self.make_camera_info(self.config.head_cam_id, "head_camera")
        self.head_depth_info = self.make_camera_info(self.config.head_cam_id, "head_camera")
        self.left_color_info = self.make_camera_info(self.config.left_arm_cam_id, "left_camera")
        self.right_color_info = self.make_camera_info(self.config.right_arm_cam_id, "right_camera")
        self.create_timer(1.0, self.publish_camera_info)

    def publish_camera_info(self):
        stamp = self.get_clock().now().to_msg()
        for info in (self.head_color_info, self.head_depth_info, self.left_color_info, self.right_color_info):
            info.header.stamp = stamp
        self.head_color_info_puber.publish(self.head_color_info)
        self.head_depth_info_puber.publish(self.head_depth_info)
        self.left_color_info_puber.publish(self.left_color_info)
        self.right_color_info_puber.publish(self.right_color_info)

    def thread_pubros2topic(self, freq=30):
        rate = self.create_rate(freq)
        while rclpy.ok() and self.running:
            time_stamp = self.get_clock().now().to_msg()

            self.joint_state.header.stamp = time_stamp
            self.joint_state.position = self.sensor_qpos[2:].tolist()
            self.joint_state.velocity = self.sensor_qvel[2:].tolist()
            self.joint_state.effort = self.sensor_force[2:].tolist()
            self.joint_state_puber.publish(self.joint_state)

            self.odom_msg.header.stamp = time_stamp
            self.odom_msg.pose.pose.position.x = self.sensor_base_position[0]
            self.odom_msg.pose.pose.position.y = self.sensor_base_position[1]
            self.odom_msg.pose.pose.position.z = self.sensor_base_position[2]
            self.odom_msg.pose.pose.orientation.w = self.sensor_base_orientation[0]
            self.odom_msg.pose.pose.orientation.x = self.sensor_base_orientation[1]
            self.odom_msg.pose.pose.orientation.y = self.sensor_base_orientation[2]
            self.odom_msg.pose.pose.orientation.z = self.sensor_base_orientation[3]
            self.odom_msg.twist.twist.linear.x = self.sensor_base_linear_vel[0]
            self.odom_msg.twist.twist.linear.y = self.sensor_base_linear_vel[1]
            self.odom_msg.twist.twist.linear.z = self.sensor_base_linear_vel[2]
            self.odom_msg.twist.twist.angular.x = self.sensor_base_gyro[0]
            self.odom_msg.twist.twist.angular.y = self.sensor_base_gyro[1]
            self.odom_msg.twist.twist.angular.z = self.sensor_base_gyro[2]
            self.odom_puber.publish(self.odom_msg)

            self.publish_base_tf(time_stamp)
            self.publish_camera_tfs(time_stamp)
            self.publish_camera_images(time_stamp)
            self.publish_scene_markers(time_stamp)
            rate.sleep()

    def publish_scene_markers(self, time_stamp):
        markers = MarkerArray()
        marker_id = 0

        def add_box(name, pos, scale, color, frame_id="odom"):
            nonlocal marker_id
            marker = Marker()
            marker.header.stamp = time_stamp
            marker.header.frame_id = frame_id
            marker.ns = name
            marker.id = marker_id
            marker_id += 1
            marker.type = Marker.CUBE
            marker.action = Marker.ADD
            marker.pose.position.x = float(pos[0])
            marker.pose.position.y = float(pos[1])
            marker.pose.position.z = float(pos[2])
            marker.pose.orientation.w = 1.0
            marker.scale.x = float(scale[0])
            marker.scale.y = float(scale[1])
            marker.scale.z = float(scale[2])
            marker.color.r = float(color[0])
            marker.color.g = float(color[1])
            marker.color.b = float(color[2])
            marker.color.a = float(color[3])
            markers.markers.append(marker)

        def add_text(name, text, pos, color=(1.0, 1.0, 1.0, 1.0), frame_id="odom"):
            nonlocal marker_id
            marker = Marker()
            marker.header.stamp = time_stamp
            marker.header.frame_id = frame_id
            marker.ns = name
            marker.id = marker_id
            marker_id += 1
            marker.type = Marker.TEXT_VIEW_FACING
            marker.action = Marker.ADD
            marker.pose.position.x = float(pos[0])
            marker.pose.position.y = float(pos[1])
            marker.pose.position.z = float(pos[2])
            marker.pose.orientation.w = 1.0
            marker.scale.z = 0.28
            marker.color.r = float(color[0])
            marker.color.g = float(color[1])
            marker.color.b = float(color[2])
            marker.color.a = float(color[3])
            marker.text = text
            markers.markers.append(marker)

        # Warehouse zones and route boundaries in the same world coordinates as odom.
        add_box("floor", (0.0, 0.0, -0.01), (10.0, 10.0, 0.01), (0.18, 0.18, 0.18, 0.25))
        add_box("start_zone", (-3.8, -3.8, 0.01), (1.5, 1.5, 0.02), (0.1, 0.75, 0.3, 0.55))
        add_text("start_label", "start", (-3.8, -3.8, 0.25), (0.3, 1.0, 0.45, 1.0))
        add_box("picking_zone", (-1.55, -0.45, 0.02), (4.7, 2.0, 0.03), (0.1, 0.35, 0.9, 0.38))
        add_text("picking_label", "picking_zone", (-1.55, -0.45, 0.35), (0.35, 0.65, 1.0, 1.0))
        add_box("delivery_zone", (3.65, 3.55, 0.02), (1.0, 1.0, 0.03), (0.95, 0.15, 0.1, 0.55))
        add_text("delivery_label", "delivery_zone", (3.65, 3.55, 0.35), (1.0, 0.35, 0.25, 1.0))

        wall_color = (0.7, 0.7, 0.72, 0.85)
        for name, pos, scale in (
            ("north_wall", (0.0, 5.0, 0.75), (10.0, 0.06, 1.5)),
            ("south_wall", (0.0, -5.0, 0.75), (10.0, 0.06, 1.5)),
            ("west_wall", (-5.0, 0.0, 0.75), (0.06, 10.0, 1.5)),
            ("east_wall", (5.0, 0.0, 0.75), (0.06, 10.0, 1.5)),
            ("route_wall_south_aisle_north", (-2.05, -2.35, 0.75), (4.5, 0.06, 1.5)),
            ("route_wall_south_aisle_south", (-1.35, -4.35, 0.75), (4.9, 0.06, 1.5)),
            ("route_wall_obstacle_east_lower", (4.0, -1.55, 0.75), (0.06, 3.0, 1.5)),
            ("route_wall_obstacle_west_lower", (-1.35, -2.05, 0.75), (0.06, 0.9, 1.5)),
            ("route_wall_pick_north", (1.35, 1.05, 0.75), (1.3, 0.06, 1.5)),
            ("route_wall_pick_south", (-0.2, -2.55, 0.75), (0.9, 0.06, 1.5)),
            ("route_wall_delivery_west", (2.45, 2.30, 0.75), (0.06, 2.3, 1.5)),
            ("route_wall_delivery_east", (4.20, 1.70, 0.75), (0.06, 3.5, 1.5)),
            ("route_wall_delivery_south", (3.95, -0.15, 0.75), (0.44, 0.06, 1.5)),
        ):
            add_box(name, pos, scale, wall_color)

        for idx, shelf_x in enumerate((-3.35, -1.8, -0.25), start=1):
            add_box(f"shelf_{idx}", (shelf_x, 1.25, 0.75), (1.25, 0.5, 1.5), (0.72, 0.62, 0.32, 0.85))
        add_box("shelf_4", (-3.35, 2.45, 0.75), (1.25, 0.5, 1.5), (0.72, 0.62, 0.32, 0.85))
        add_text("shelf_label", "shelves", (-1.8, 1.9, 1.75), (1.0, 0.85, 0.35, 1.0))

        # Robot and camera markers. The base marker follows odometry; camera markers use TF frames.
        add_box("mmk2_base", (0.0, 0.0, 0.18), (0.55, 0.42, 0.36), (0.0, 0.7, 1.0, 0.9), frame_id="base_link")
        add_text("base_label", "base_link", (0.0, 0.0, 0.65), (0.4, 0.85, 1.0, 1.0), frame_id="base_link")
        add_box("head_camera_marker", (0.0, 0.0, 0.0), (0.10, 0.06, 0.06), (0.0, 1.0, 0.45, 0.9), frame_id="head_camera")
        add_box("left_camera_marker", (0.0, 0.0, 0.0), (0.08, 0.05, 0.05), (1.0, 0.55, 0.1, 0.9), frame_id="left_camera")
        add_box("right_camera_marker", (0.0, 0.0, 0.0), (0.08, 0.05, 0.05), (1.0, 0.25, 0.65, 0.9), frame_id="right_camera")

        self.scene_marker_puber.publish(markers)

    def publish_base_tf(self, time_stamp):
        trans_msg = self._tf_msg
        trans_msg.header.stamp = time_stamp
        trans_msg.transform.translation.x = self.sensor_base_position[0]
        trans_msg.transform.translation.y = self.sensor_base_position[1]
        trans_msg.transform.translation.z = self.sensor_base_position[2]
        trans_msg.transform.rotation.w = self.sensor_base_orientation[0]
        trans_msg.transform.rotation.x = self.sensor_base_orientation[1]
        trans_msg.transform.rotation.y = self.sensor_base_orientation[2]
        trans_msg.transform.rotation.z = self.sensor_base_orientation[3]
        self.tf_broadcaster.sendTransform(trans_msg)

    def publish_camera_tfs(self, time_stamp):
        for cam_id, frame_id in (
            (self.config.head_cam_id, "head_camera"),
            (self.config.left_arm_cam_id, "left_camera"),
            (self.config.right_arm_cam_id, "right_camera"),
        ):
            msg = TransformStamped()
            msg.header.stamp = time_stamp
            msg.header.frame_id = "base_link"
            msg.child_frame_id = frame_id
            cam_tmat = np.eye(4)
            cam = self.mj_data.camera(self.mj_model.camera(cam_id).name)
            cam_tmat[:3, :3] = np.array(cam.xmat).reshape((3, 3))
            cam_tmat[:3, 3] = cam.xpos

            base_tmat = np.eye(4)
            base_tmat[:3, :3] = Rotation.from_quat(self.sensor_base_orientation[[1, 2, 3, 0]]).as_matrix()
            base_tmat[:3, 3] = self.sensor_base_position
            rel_tmat = np.linalg.inv(base_tmat) @ cam_tmat
            quat = Rotation.from_matrix(rel_tmat[:3, :3]).as_quat()

            msg.transform.translation.x = rel_tmat[0, 3]
            msg.transform.translation.y = rel_tmat[1, 3]
            msg.transform.translation.z = rel_tmat[2, 3]
            msg.transform.rotation.x = quat[0]
            msg.transform.rotation.y = quat[1]
            msg.transform.rotation.z = quat[2]
            msg.transform.rotation.w = quat[3]
            self.tf_broadcaster.sendTransform(msg)

    @property
    def _tf_msg(self):
        if not hasattr(self, "_base_tf_msg"):
            self._base_tf_msg = TransformStamped()
            self._base_tf_msg.header.frame_id = "odom"
            self._base_tf_msg.child_frame_id = "base_link"
        return self._base_tf_msg

    def publish_camera_images(self, time_stamp):
        head_id = self.config.head_cam_id
        left_id = self.config.left_arm_cam_id
        right_id = self.config.right_arm_cam_id

        head_color = self.array_to_image(self.obs["img"][head_id], "rgb8")
        head_color.header.stamp = time_stamp
        head_color.header.frame_id = "head_camera"
        self.head_color_puber.publish(head_color)

        head_depth_mm = np.array(np.clip(self.obs["depth"][head_id] * 1e3, 0, 65535), dtype=np.uint16)
        head_depth = self.array_to_image(head_depth_mm, "mono16")
        head_depth.header.stamp = time_stamp
        head_depth.header.frame_id = "head_camera"
        self.head_depth_puber.publish(head_depth)

        left_color = self.array_to_image(self.obs["img"][left_id], "rgb8")
        left_color.header.stamp = time_stamp
        left_color.header.frame_id = "left_camera"
        self.left_color_puber.publish(left_color)
        
        right_color = self.array_to_image(self.obs["img"][right_id], "rgb8")
        right_color.header.stamp = time_stamp
        right_color.header.frame_id = "right_camera"
        self.right_color_puber.publish(right_color)

    @staticmethod
    def array_to_image(array, encoding):
        array = np.ascontiguousarray(array)
        msg = Image()
        msg.height = int(array.shape[0])
        msg.width = int(array.shape[1])
        msg.encoding = encoding
        msg.is_bigendian = 0
        channels = 1 if array.ndim == 2 else int(array.shape[2])
        msg.step = int(array.shape[1] * channels * array.dtype.itemsize)
        msg.data = array.tobytes()
        return msg


def build_config(args):
    cfg = MMK2Cfg()
    cfg.mjcf_file_path = "mjcf/tasks_mmk2/shentoon2.xml"
    cfg.use_gaussian_renderer = args.use_gs
    cfg.lidar_s2_sim = args.lidar
    cfg.sync = not args.headless
    cfg.headless = args.headless
    cfg.enable_render = True
    cfg.render_set = {
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
    }

    cfg.head_cam_id = 3
    cfg.left_arm_cam_id = 4
    cfg.right_arm_cam_id = 5
    cfg.obs_rgb_cam_id = [cfg.head_cam_id, cfg.left_arm_cam_id, cfg.right_arm_cam_id]
    cfg.obs_depth_cam_id = [cfg.head_cam_id]
    cfg.init_state["base_position"] = [-3.8, -3.8, 0.0]
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Publish shentoon2 MMK2 state and cameras over ROS2.")
    parser.add_argument("--headless", action="store_true", help="Run without opening a MuJoCo window.")
    parser.add_argument("--use-gs", action="store_true", help="Enable Gaussian renderer if assets are available.")
    parser.add_argument("--lidar", action="store_true", help="Also publish /slamware_ros_sdk_server_node/scan.")
    parser.add_argument("--pub-fps", type=float, default=24.0, help="ROS2 sensor publish frequency.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--max-time", type=float, default=0.0, help="Optional simulated seconds before exit. 0 means run forever.")
    args = parser.parse_args()
    if args.lidar:
        raise NotImplementedError("--lidar is not implemented in this shentoon2 ROS2 publisher yet.")

    rclpy.init()
    sim_node = Shentoon2MMK2ROS2(build_config(args))
    sim_node.reset()

    spin_thread = threading.Thread(target=lambda: rclpy.spin(sim_node), daemon=True)
    spin_thread.start()

    threads = []
    if sim_node.config.lidar_s2_sim:
        threads.append(threading.Thread(target=sim_node.thread_publidartopic, args=(12,), daemon=True))
    threads.append(threading.Thread(target=sim_node.thread_pubros2topic, args=(args.pub_fps,), daemon=True))
    for thread in threads:
        thread.start()

    try:
        while rclpy.ok() and sim_node.running:
            sim_node.step(sim_node.target_control)
            if args.max_time > 0.0 and sim_node.mj_data.time >= args.max_time:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sim_node.running = False
        for thread in threads:
            thread.join(timeout=1.0)
        sim_node.destroy_node()
        rclpy.shutdown()
        spin_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
