# Supermarket Sorting Task

本示例是一个自包含的超市分拣任务：MMK2 机器人从出发区导航到超市货架，抓取指定商品 `slot_D_L2_C2_yinlu`，再移动到配送桌并把商品放到桌面上。

任务代码、场景 MJCF、layout 和运行所需模型资产都放在 `examples/supermarket_sorting/` 下。`supermarket_sorting_server.py` 会在启动时自动把 `examples/supermarket_sorting/models` 设置为 `DISCOVERSE_ASSETS_DIR`，不需要手动配置模型路径。

## 目录

```text
examples/supermarket_sorting/
├── supermarket_sorting_server.py
├── supermarket_sorting_client.py
├── arm_kdl.py
├── mmk2_kdl.py
├── retail_competition_layout.json
├── mjcf/retail_competition.xml
└── models/
    ├── 3dgs/
    ├── meshes/
    ├── mjcf/
    └── textures/
```

## 推荐环境

- Ubuntu 22.04
- Python 3.10
- ROS2 Humble
- NVIDIA GPU + CUDA 11.8 或更高版本用于 3DGS 渲染
- 可显示图形窗口的桌面环境，或正确配置的远程 X11/EGL 环境

ROS2 Humble 主要面向 Ubuntu 22.04。Ubuntu 20.04 不建议作为新机器部署环境。

## 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y \
  git curl gnupg lsb-release software-properties-common \
  python3-pip python3-venv python3-dev build-essential \
  libgl1-mesa-dev libglew-dev libegl1-mesa-dev libgles2-mesa-dev \
  libglfw3-dev libglu1-mesa-dev libglm-dev libosmesa6-dev mesa-utils
```

## 2. 安装 ROS2 Humble

如果机器已经装好 ROS2 Humble，可以直接跳到下一节。

```bash
sudo add-apt-repository universe
sudo apt update
sudo apt install -y curl gnupg lsb-release

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y \
  ros-humble-desktop \
  ros-humble-rclpy \
  ros-humble-cv-bridge \
  ros-humble-tf2-ros \
  ros-humble-geometry-msgs \
  ros-humble-nav-msgs \
  ros-humble-sensor-msgs \
  ros-humble-std-msgs
```

每个新终端运行本任务前都需要加载 ROS2：

```bash
source /opt/ros/humble/setup.bash
```

## 3. 安装 Python 依赖

在仓库根目录执行：

```bash
cd /path/to/supermarket_sorting_task
source /opt/ros/humble/setup.bash

python3 -m venv --system-site-packages .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

# NVIDIA/CUDA 机器推荐先装 CUDA 版 PyTorch；CUDA 版本不一致时换成匹配本机的 PyTorch index。
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装 DISCOVERSE 核心和 3DGS 渲染依赖。依赖版本由仓库根目录 pyproject.toml 管理。
python -m pip install -e ".[gs]"
```

如果只想先验证 ROS2 和 MuJoCo 主流程，也可以先执行：

```bash
python -m pip install -e .
```

这种情况下 `supermarket_sorting_server.py` 仍可启动 MuJoCo 原生渲染；没有安装 `gaussian_renderer` 时，DISCOVERSE 会自动关闭 3DGS 渲染。

## 4. 验证环境

在仓库根目录执行：

```bash
cd /path/to/supermarket_sorting_task
source /opt/ros/humble/setup.bash
source .venv/bin/activate

python - <<'PY'
import numpy
import scipy
import mujoco
import rclpy
import cv_bridge
import tf2_ros
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import Float64MultiArray
from discoverse.robots_env.mmk2_base import MMK2Cfg

print("runtime imports ok")
PY
```

如果 `rclpy`、`cv_bridge` 或 ROS message 包导入失败，通常是没有执行 `source /opt/ros/humble/setup.bash`，或虚拟环境不是用 `--system-site-packages` 创建的。

如果 `mujoco`/OpenGL 报错，桌面环境优先使用：

```bash
export MUJOCO_GL=glfw
```

无显示器或远程服务器可尝试：

```bash
export MUJOCO_GL=egl
```

## 5. 运行任务

终端 A 启动 server：

```bash
cd /path/to/supermarket_sorting_task
source /opt/ros/humble/setup.bash
source .venv/bin/activate
export MUJOCO_GL=glfw

python examples/supermarket_sorting/supermarket_sorting_server.py
```

终端 B 启动 client：

```bash
cd /path/to/supermarket_sorting_task
source /opt/ros/humble/setup.bash
source .venv/bin/activate

python examples/supermarket_sorting/supermarket_sorting_client.py
```

client 当前执行固定流程：

```text
导航到货架 D -> 抓取 slot_D_L2_C2_yinlu -> 导航到配送桌 -> 放置到桌面
```

## ROS2 Topic

client 订阅：

```yaml
/slamware_ros_sdk_server_node/odom
/joint_states
```

client 发布：

```yaml
/cmd_vel
/spine_forward_position_controller/commands
/head_forward_position_controller/commands
/left_arm_forward_position_controller/commands
/right_arm_forward_position_controller/commands
```

