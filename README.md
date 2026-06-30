# Supermarket Sorting Task

超市分拣比赛 ROS2 仿真环境。参赛者启动 server 后，通过 ROS2 话题订阅 RGB-D、里程计、关节状态，并发布控制指令驱动 MMK2 机器人完成货架抓取和桌面放置。

## 快速运行

宿主机需要 Docker、NVIDIA Driver、NVIDIA Container Toolkit 和 NVIDIA GPU。

```bash
docker pull crpi-1pzq998p9m7w0auy.cn-hangzhou.personal.cr.aliyuncs.com/challengecup/smart_retail_client:latest
```

允许容器显示图形窗口，并创建运行缓存：

```bash
xhost +local:docker
docker volume create supermarket_sorting_cache
```

启动 server：

```bash
docker run --rm -it \
  --gpus all \
  --network host \
  --ipc host \
  --name supermarket_sorting_server \
  -e DISPLAY=${DISPLAY} \
  -e ROS_DOMAIN_ID=99 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e MUJOCO_GL=glfw \
  -e SUPERMARKET_HEADLESS=0 \
  -e SUPERMARKET_ENABLE_RENDER=1 \
  -e SUPERMARKET_USE_GS=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v supermarket_sorting_cache:/root/.cache \
  crpi-1pzq998p9m7w0auy.cn-hangzhou.personal.cr.aliyuncs.com/challengecup/smart_retail_client:latest \
  bash -lc "python3 examples/supermarket_sorting/supermarket_sorting_server.py"
```

另开终端运行 baseline client：

```bash
docker run --rm -it \
  --network host \
  --ipc host \
  --name supermarket_sorting_baseline \
  -e ROS_DOMAIN_ID=99 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  crpi-1pzq998p9m7w0auy.cn-hangzhou.personal.cr.aliyuncs.com/challengecup/smart_retail_client:latest \
  bash -lc "python3 examples/supermarket_sorting/supermarket_sorting_client.py"
```

baseline 会执行固定流程：

```text
start zone -> shelf D -> pick slot_D_L2_C2_yinlu -> delivery table -> place
```

参赛者可以保留同一个 server，替换为自己的 ROS2 client。

停止容器：

```bash
docker stop supermarket_sorting_server
docker stop supermarket_sorting_baseline
```

## 主要脚本

```text
examples/supermarket_sorting/supermarket_sorting_server.py   # 启动 MuJoCo/ROS2 仿真 server
examples/supermarket_sorting/supermarket_sorting_client.py   # baseline 抓取 client
```

server 常用环境变量：

```text
ROS_DOMAIN_ID=99              server 和 client 必须一致
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
MUJOCO_GL=glfw                开启桌面可视化窗口
SUPERMARKET_HEADLESS=0        开启可视化界面
SUPERMARKET_USE_GS=1          启用 3D Gaussian Splatting 渲染
SUPERMARKET_ENABLE_RENDER=1   保持相机图像和深度图发布
```

`supermarket_sorting_cache` 用于保存运行时编译和缓存文件，避免每次启动容器都重新生成缓存。

## ROS2 话题

下表列出本场景 server 提供给参赛者使用的全部 ROS2 接口话题。`/rosout`、`/parameter_events` 等 ROS2 自动话题不属于比赛控制/观测接口。

### Server 发布

| Topic | Type | 说明 |
| --- | --- | --- |
| `/slamware_ros_sdk_server_node/odom` | `nav_msgs/msg/Odometry` | 机器人底盘位姿和速度。 |
| `/tf` | `tf2_msgs/msg/TFMessage` | 动态 TF，主要为 `odom -> base_link`。 |
| `/joint_states` | `sensor_msgs/msg/JointState` | 升降、头部、双臂和夹爪关节状态。 |
| `/head_camera/color/image_raw` | `sensor_msgs/msg/Image` | 头部 RGB 图像，`rgb8`，默认 640x480。 |
| `/head_camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` | 头部 RGB 相机内参。 |
| `/head_camera/aligned_depth_to_color/image_raw` | `sensor_msgs/msg/Image` | 头部深度图，对齐 RGB，`mono16`，单位毫米。 |
| `/head_camera/aligned_depth_to_color/camera_info` | `sensor_msgs/msg/CameraInfo` | 头部深度相机内参。 |
| `/left_camera/color/image_raw` | `sensor_msgs/msg/Image` | 左腕 RGB 图像，`rgb8`，默认 640x480。 |
| `/left_camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` | 左腕相机内参。 |
| `/right_camera/color/image_raw` | `sensor_msgs/msg/Image` | 右腕 RGB 图像，`rgb8`，默认 640x480。 |
| `/right_camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` | 右腕相机内参。 |
| `/slamware_ros_sdk_server_node/scan` | `sensor_msgs/msg/LaserScan` | 激光雷达扫描；默认超市场景未开启 lidar，因此默认不发布。 |

### Server 订阅

| Topic | Type | 控制格式 |
| --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 使用 `linear.x` 控制前进速度，`angular.z` 控制角速度。 |
| `/spine_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[slide_joint]` |
| `/head_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[head_yaw_joint, head_pitch_joint]` |
| `/left_arm_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[joint1, joint2, joint3, joint4, joint5, joint6, gripper]` |
| `/right_arm_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[joint1, joint2, joint3, joint4, joint5, joint6, gripper]` |

baseline 中 `gripper=1.0` 表示张开夹爪，`gripper=0.2` 是抓取 `slot_D_L2_C2_yinlu` 时使用的闭合命令。

`/joint_states` 关节顺序：

```text
slide_joint
head_yaw_joint
head_pitch_joint
left_arm_joint1
left_arm_joint2
left_arm_joint3
left_arm_joint4
left_arm_joint5
left_arm_joint6
left_arm_eef_gripper_joint
right_arm_joint1
right_arm_joint2
right_arm_joint3
right_arm_joint4
right_arm_joint5
right_arm_joint6
right_arm_eef_gripper_joint
```

## ROS2 调用示例

以下命令需要在与 server 相同 `ROS_DOMAIN_ID` 的容器内运行。

```bash
ros2 topic list
ros2 topic echo /slamware_ros_sdk_server_node/odom
ros2 topic hz /head_camera/color/image_raw
```

底盘前进：

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.10, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

底盘停止：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

升降和头部：

```bash
ros2 topic pub --once /spine_forward_position_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.10]}"

ros2 topic pub --once /head_forward_position_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.0, -0.6]}"
```

右臂张开/闭合夹爪：

```bash
ros2 topic pub --once /right_arm_forward_position_controller/commands \
  std_msgs/msg/Float64MultiArray \
  "{data: [0.0, -0.166, 0.032, 0.0, -1.571, -2.223, 1.0]}"

ros2 topic pub --once /right_arm_forward_position_controller/commands \
  std_msgs/msg/Float64MultiArray \
  "{data: [0.0, -0.166, 0.032, 0.0, -1.571, -2.223, 0.2]}"
```
