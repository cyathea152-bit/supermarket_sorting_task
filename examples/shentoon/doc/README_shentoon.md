# Shentoon MMK2 Tasks

本文档总结当前仓库中和 Shentoon 场景相关的 MMK2 任务、场景文件、导航流程和 ROS2 数据发布方式。

## 文件索引

主要文件：

- `examples/shentoon/mjcf/shentoon1.xml`：Shentoon 3DGS 查看器默认使用的场景。
- `examples/shentoon/mjcf/shentoon2.xml`：当前导航和 ROS2 发布使用的仓库货架场景。
- `examples/shentoon/view_shentoon_3dgs.py`：Shentoon 场景查看器，支持 3DGS 对象模型。
- `examples/shentoon/shentoon2_nav_to_shelf.py`：MMK2 底盘导航任务，从起点经过障碍区域，到达 picking zone，再前往 delivery zone。
- `examples/shentoon/shentoon2_mmk2_ros2.py`：Shentoon2 场景的 ROS2 发布节点，发布底盘里程计、关节状态、相机图像、TF 和 RViz Marker。

## Shentoon2 场景

`shentoon2.xml` 是一个 10m x 10m 的仓库任务场景，坐标系使用 MuJoCo 世界坐标，ROS2 中对应 `odom` frame。

关键区域：

- 起点：`start_zone`，中心约为 `(-3.8, -3.8)`。
- 拣货区：`picking_zone`，中心约为 `(-1.55, -0.45)`，机器人到达后默认面向货架方向。
- 货架区：4 组标准货架，位于场景北侧，包含货架层板、物品和 ArUco 样式占位标记。
- 障碍区：`dynamic_obstacle_zone`，包含静态障碍箱。
- 放置区：`delivery_zone`，中心约为 `(3.65, 3.55)`，导航目标默认使用可到达点 `(3.55, 3.12)`。
- 路线围挡：`route_corridor_walls`，用于挡住非路线空白区域，同时保留起点、障碍区、货架区和放置区之间的可通行路线。

场景内置相机：

- `overview`
- `shelf_aisle`
- `delivery_zone`
- 机器人自身相机由 MMK2 模型提供，ROS2 脚本中使用 camera id：`head=3`、`left_arm=4`、`right_arm=5`。

## 导航任务

运行导航 demo：

```bash
cd /home/hunter/shentoon_detection
conda activate p7
python examples/shentoon/shentoon2_nav_to_shelf.py
```

无窗口运行：

```bash
python examples/shentoon/shentoon2_nav_to_shelf.py --headless
```

默认任务流程：

1. 从 `start_zone` 出发，初始位置 `(-3.8, -3.8)`。
2. 经过障碍区域和中间路径点。
3. 到达 `picking_zone`，目标点 `(-1.55, -0.45)`。
4. 在 `picking_zone` 调整 yaw，默认 `pick-yaw = pi/2`，面向货架方向。
5. 继续前往 `delivery_zone`，默认目标点 `(3.55, 3.12)`。
6. 到达放置区后调整最终 yaw，默认 `delivery-yaw = pi/2`。

常用参数：

```bash
python examples/shentoon/shentoon2_nav_to_shelf.py --headless \
  --pick-target=-1.55,-0.45 \
  --delivery-target=3.55,3.12 \
  --max-time 100
```

路径点参数使用分号分隔：

```bash
python examples/shentoon/shentoon2_nav_to_shelf.py --headless \
  --pick-waypoints="-1.9,-3.25;0.35,-3.10;2.45,-2.75;2.35,0.10" \
  --delivery-waypoints="-0.35,-1.70;2.55,-1.45;3.15,0.85;3.45,2.50"
```

导航实现说明：

- 底盘控制是基于已知世界坐标的 waypoint 追踪。
- 线速度和角速度被转换为左右轮目标速度。
- `PIDarray` 根据左右轮目标速度和实际轮速输出轮子控制力。
- 当前 demo 不是 SLAM 或全局路径规划器，而是固定场景中的坐标导航测试。

## 3DGS 查看器

查看 Shentoon 场景：

```bash
cd /home/hunter/shentoon_detection
conda activate p7
python examples/shentoon/view_shentoon_3dgs.py
```

查看 `shentoon2.xml`：

```bash
python examples/shentoon/view_shentoon_3dgs.py --mjcf examples/shentoon/mjcf/shentoon2.xml
```

关闭 3DGS，仅使用 MuJoCo 渲染：

```bash
python examples/shentoon/view_shentoon_3dgs.py --no-gs --mjcf examples/shentoon/mjcf/shentoon2.xml
```

只加载指定 3DGS 物体：

```bash
python examples/shentoon/view_shentoon_3dgs.py --only drill,hat
```

注意：如果启用 3DGS 且本地缺少模型，可能需要 Hugging Face 登录或设置 `HUGGINGFACE_HUB_TOKEN`。纯 MuJoCo 查看请使用 `--no-gs`。

## ROS2 发布节点

启动 Shentoon2 ROS2 发布节点：

```bash
cd /home/hunter/shentoon_detection
conda activate p7
source /opt/ros/jazzy/setup.zsh
export ROS_DOMAIN_ID=99
unset RMW_IMPLEMENTATION
export MUJOCO_GL=egl

python examples/shentoon/shentoon2_mmk2_ros2.py --headless
```

如果系统已经安装 CycloneDDS，也可以使用：

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

未安装时不要设置该变量，否则会出现 `librmw_cyclonedds_cpp.so` 找不到的问题。

发布 topic：

- `/joint_states`：MMK2 升降、头部、左右臂和夹爪关节状态。
- `/slamware_ros_sdk_server_node/odom`：底盘里程计，`odom -> base_link`。
- `/tf`：`odom -> base_link`，以及 `base_link -> head_camera/left_camera/right_camera`。
- `/head_camera/color/image_raw`：头部 RGB 图像，编码 `rgb8`。
- `/head_camera/aligned_depth_to_color/image_raw`：头部深度图，编码 `mono16`，单位毫米。
- `/head_camera/color/camera_info`：头部 RGB 相机内参。
- `/head_camera/aligned_depth_to_color/camera_info`：头部深度相机内参。
- `/left_camera/color/image_raw`：左臂末端 RGB 图像。
- `/left_camera/color/camera_info`：左臂末端相机内参。
- `/right_camera/color/image_raw`：右臂末端 RGB 图像。
- `/right_camera/color/camera_info`：右臂末端相机内参。
- `/mujoco_scene`：RViz MarkerArray，用于显示场景区域、墙、货架、机器人底盘和相机位置。

订阅 topic：

- `/cmd_vel`：底盘速度控制。
- `/spine_forward_position_controller/commands`：升降关节位置命令。
- `/head_forward_position_controller/commands`：头部 yaw/pitch 位置命令。
- `/left_arm_forward_position_controller/commands`：左臂 6 关节加夹爪命令。
- `/right_arm_forward_position_controller/commands`：右臂 6 关节加夹爪命令。

当前 `--lidar` 参数尚未实现，使用会直接报错。

## ROS2 数据检查

另开终端检查 ROS2 数据：

```bash
source /opt/ros/jazzy/setup.zsh
export ROS_DOMAIN_ID=99
unset RMW_IMPLEMENTATION

ros2 node list
ros2 topic list
ros2 topic echo /joint_states --once
ros2 topic echo /slamware_ros_sdk_server_node/odom --once
ros2 topic hz /head_camera/color/image_raw
```

如果 topic list 为空，优先检查：

- 发布节点是否仍在运行。
- RViz/ros2 命令终端是否也设置了同一个 `ROS_DOMAIN_ID`。
- `RMW_IMPLEMENTATION` 是否两边一致。
- zsh 终端应使用 `source /opt/ros/jazzy/setup.zsh`，不要 source `setup.bash`。

## RViz 查看

启动 RViz：

```bash
source /opt/ros/jazzy/setup.zsh
export ROS_DOMAIN_ID=99
unset RMW_IMPLEMENTATION
rviz2
```

RViz 配置：

- `Global Options -> Fixed Frame` 设置为 `odom`。
- 添加 `TF`。
- 添加 `MarkerArray`，topic 选择 `/mujoco_scene`。
- 添加 `Odometry`，topic 选择 `/slamware_ros_sdk_server_node/odom`。
- 添加 `Image`，topic 可选：
  - `/head_camera/color/image_raw`
  - `/head_camera/aligned_depth_to_color/image_raw`
  - `/left_camera/color/image_raw`
  - `/right_camera/color/image_raw`

说明：

- 当前 ROS2 节点没有发布完整 URDF，也没有 `/robot_description`，所以 RViz 的 `RobotModel` 不会显示完整机器人模型。
- `/mujoco_scene` 是为 RViz 直观检查补充的 MarkerArray，可看到起点、拣货区、放置区、围挡、货架和机器人底盘位置。
- 如果加了 MarkerArray 仍看不到，点击 RViz 顶部的 Reset，或按 `F` 聚焦；机器人初始位置约为 `(-3.8, -3.8)`。

## 常见问题

`setup.bash` 报找不到 `setup.sh`：

zsh 中使用：

```bash
source /opt/ros/jazzy/setup.zsh
```

不要在 zsh 里 source `setup.bash`。

`librmw_cyclonedds_cpp.so` 找不到：

说明系统未安装 CycloneDDS RMW。先用默认 FastDDS：

```bash
unset RMW_IMPLEMENTATION
```

或者安装：

```bash
sudo apt update
sudo apt install ros-jazzy-rmw-cyclonedds-cpp
```

`gladLoadGL error` 或无窗口渲染失败：

无窗口运行时设置：

```bash
export MUJOCO_GL=egl
```

导航提前退出：

适当增大 `--max-time`，当前默认值为 `100.0` 秒。

3DGS 启动提示 Hugging Face 未登录：

如果只是看场景或跑导航，用 `--no-gs` 或不启用 3DGS。需要 3DGS 模型时再执行 Hugging Face 登录或设置 token。
