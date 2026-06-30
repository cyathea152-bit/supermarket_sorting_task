# Supermarket Sorting Task

超市分拣比赛 ROS2 仿真环境。启动 server 后，baseline 通过头部相机**视觉检测** yinlu 瓶子并驱动 MMK2 机器人完成货架抓取和桌面放置。

## 快速运行

宿主机需要 Docker、NVIDIA Driver、NVIDIA Container Toolkit 和 NVIDIA GPU。

本地构建镜像（含视觉感知依赖与权重）：

```bash
docker build -t supermarket_sorting_task:perception .
```

允许容器显示图形窗口，并创建运行缓存：

```bash
xhost +local:docker
docker volume create supermarket_sorting_cache
```

### 启动 server

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
  -e SUPERMARKET_RANDOMIZE=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v supermarket_sorting_cache:/root/.cache \
  supermarket_sorting_task:perception \
  bash -lc "source /opt/ros/humble/setup.bash && python3 examples/supermarket_sorting/supermarket_sorting_server.py"
```

> 需要可复现的随机结果时，再加一行 `-e SUPERMARKET_SEED=42`（任意数字）。

**随机摆放功能**：server 默认会将 45 个物品在货架格子里**随机打乱摆放**（每次启动物品位置不同），防止参赛者硬编码坐标。可通过环境变量控制：
- `SUPERMARKET_RANDOMIZE=0` — 关闭随机，使用固定布局（baseline 演示时需要）
- `SUPERMARKET_SEED=<数字>` — 指定随机种子，让随机结果可复现（调试/评测用）

### 启动 baseline（视觉抓取）

baseline 由两个进程组成：**感知节点**从头部相机检测 yinlu 并发布世界坐标到 `/yinlu/detections`，**控制 client** 订阅该坐标驱动机器人抓取。**baseline 需要固定布局**（`SUPERMARKET_RANDOMIZE=0`），因为它只检测导航目标列正前方的 yinlu；随机模式是给参赛者的挑战，需要自行实现全场搜索目标。

先启动 server（固定布局）：

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
  -e SUPERMARKET_RANDOMIZE=0 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v supermarket_sorting_cache:/root/.cache \
  supermarket_sorting_task:perception \
  bash -lc "source /opt/ros/humble/setup.bash && python3 examples/supermarket_sorting/supermarket_sorting_server.py"
```

再启动 baseline client：

```bash
docker run --rm -it \
  --gpus all \
  --network host \
  --ipc host \
  --name supermarket_sorting_baseline \
  -e ROS_DOMAIN_ID=99 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  supermarket_sorting_task:perception \
  bash -lc "source /opt/ros/humble/setup.bash; \
            python3 examples/supermarket_sorting/perception/yinlu_detect.py --backend yolo & \
            python3 examples/supermarket_sorting/supermarket_sorting_client.py"
```

baseline 流程：

```text
start zone -> shelf D -> 视觉锁定 yinlu -> creep 抓取 -> delivery table -> place
```

机器人不含硬编码物体坐标：导航到货架列后，从视觉检测中选取正前方的 yinlu 锁定为目标（12s 内未检测到则报错退出）。参赛者可以保留同一个 server，替换为自己的 ROS2 client。

停止容器：

```bash
docker stop supermarket_sorting_server
docker stop supermarket_sorting_baseline
```

## 主要脚本

```text
examples/supermarket_sorting/supermarket_sorting_server.py   # 启动 MuJoCo/ROS2 仿真 server
examples/supermarket_sorting/supermarket_sorting_client.py   # baseline 控制 client（视觉抓取）
examples/supermarket_sorting/perception/yinlu_detect.py      # 视觉感知节点，发布 /yinlu/detections
```

感知节点支持三种检测后端（`--backend`）：

```text
yolo   训练好的 YOLOv8 权重 perception/checkpoints/yinlu.pt（默认用于 baseline）
blob   无需权重，黑底场景用连通域检测
gt     用真值投影，打印逐瓶坐标对齐误差（验证相机->世界变换用）
```

server 常用环境变量：

```text
ROS_DOMAIN_ID=99                 server 和 baseline 必须一致
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
MUJOCO_GL=glfw                   开启桌面可视化窗口
SUPERMARKET_HEADLESS=0           开启可视化界面
SUPERMARKET_USE_GS=1             启用 3D Gaussian Splatting 渲染
SUPERMARKET_ENABLE_RENDER=1      保持相机图像和深度图发布
SUPERMARKET_RANDOMIZE=1          随机摆放 45 个物品（默认 1 开启；baseline 需设为 0）
SUPERMARKET_SEED=<数字>          指定随机种子，让随机结果可复现（可选）
```

`supermarket_sorting_cache` 用于保存运行时编译和缓存文件，避免每次启动容器都重新生成缓存。

## ROS2 话题

下表列出本场景的全部 ROS2 接口话题。`/rosout`、`/parameter_events` 等 ROS2 自动话题不属于比赛控制/观测接口。

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

### 感知节点发布（baseline 视觉）

| Topic | Type | 说明 |
| --- | --- | --- |
| `/yinlu/detections` | `vision_msgs/msg/Detection3DArray` | 检测到的 yinlu 瓶子，位姿为**世界坐标系**（`frame_id=world`）；client 订阅此话题获取抓取目标。 |
| `/yinlu/result_image` | `sensor_msgs/msg/Image` | 检测可视化叠加图（绿色框 + 世界坐标），`bgr8`，仅供调试。 |

### Server 订阅

| Topic | Type | 控制格式 |
| --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 使用 `linear.x` 控制前进速度，`angular.z` 控制角速度。 |
| `/spine_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[slide_joint]` |
| `/head_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[head_yaw_joint, head_pitch_joint]` |
| `/left_arm_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[joint1, joint2, joint3, joint4, joint5, joint6, gripper]` |
| `/right_arm_forward_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | `[joint1, joint2, joint3, joint4, joint5, joint6, gripper]` |

baseline 中 `gripper=1.0` 表示张开夹爪，`gripper=0.2` 是抓取 yinlu 时使用的闭合命令。

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

