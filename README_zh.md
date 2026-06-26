# 超市分拣任务

本仓库基于 `huzhengju/shentoon_detection` 的 DISCOVERSE 裁剪架构，集成了一个自包含的 **超市分拣任务（Supermarket Sorting Task）**。

任务流程：MMK2 机器人从出发区导航到超市货架，抓取指定商品 `slot_D_L2_C2_yinlu`，再移动到配送桌并把商品放到桌面上。

## 入口

任务代码和资产位于：

```text
examples/supermarket_sorting/
```

完整安装、环境验证和运行命令见：

[examples/supermarket_sorting/README.md](examples/supermarket_sorting/README.md)

## 快速安装

推荐环境：

- Ubuntu 22.04
- Python 3.10
- ROS2 Humble
- NVIDIA GPU + CUDA 11.8 或更高版本用于 3DGS 渲染

安装 ROS2 Humble 后，在仓库根目录执行：

```bash
source /opt/ros/humble/setup.bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
python -m pip install -e ".[gs]"
```

环境验证：

```bash
source /opt/ros/humble/setup.bash
source .venv/bin/activate

python - <<'PY'
import mujoco
import rclpy
import cv_bridge
import tf2_ros
from discoverse.robots_env.mmk2_base import MMK2Cfg
print("runtime imports ok")
PY
```

启动 server：

```bash
source /opt/ros/humble/setup.bash
source .venv/bin/activate
export MUJOCO_GL=glfw
python examples/supermarket_sorting/supermarket_sorting_server.py
```

另开终端启动 client：

```bash
source /opt/ros/humble/setup.bash
source .venv/bin/activate
python examples/supermarket_sorting/supermarket_sorting_client.py
```

## 说明

- 任务自己的 MJCF、layout、mesh、texture、3DGS 资产都放在 `examples/supermarket_sorting/` 内。
- `supermarket_sorting_server.py` 会自动把 `examples/supermarket_sorting/models` 设置为 `DISCOVERSE_ASSETS_DIR`，不依赖用户额外设置模型路径。
- 红色半透明商品碰撞盒保持可见，配送桌保持可见；配送桌桌面接触参数已调软，用于减轻最终放置物体时的抖动。
- 本仓库保留 DISCOVERSE 的基础结构和 `pyproject.toml` 安装方式；超市分拣任务作为一个普通 example 运行。
