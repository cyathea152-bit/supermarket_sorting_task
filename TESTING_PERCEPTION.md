

# 现有方案测试文档 — yinlu 视觉抓取（坐标对齐验证）

本文档用于验证**当前已交付的感知→抓取链路**，重点是 **坐标对齐度**。

> 你现在要测的核心问题：相机检测出的 yinlu 世界坐标，和真值（ground truth）差多少毫米？
> 这决定了"视觉驱动抓取"能不能替代原来的硬编码坐标。

---

## 0. 现状总览（诚实清单）

| 组件 | 状态 | 说明 |
|---|---|---|
| 坐标桥（相机→世界变换） | ✅ 已验证 | 离线 round-trip 0.0mm，量化噪声后最坏 1.3mm |
| 感知节点 `yinlu_detect.py` | ✅ 已写 | 独立 ROS2 节点，发布 `/yinlu/detections`（世界系） |
| `gt` 后端（坐标验证用） | ✅ 已写 | 用真值投影，回算并打印逐瓶误差 |
| `blob` 后端（黑底场景） | ✅ 已写 | 黑底下非黑像素团 = 物体，无需模型 |
| client 接入（抓取逻辑不变） | ✅ 已写+编译通过 | 目标来源从硬编码改为视觉，缺失自动回退 GT |
| `yolo` 后端 + `yinlu.pt` 权重 | ✅ 已训练完成 | v0 权重，val mAP50=0.9949（仿真域，黑底域随机化） |

**测试覆盖：`gt`（坐标对齐）+ `blob`（黑底端到端）+ `yolo`（已训练，测试五）。**

---

## 测试一：离线坐标桥（30 秒，无需 Docker / GPU）

纯几何 + FK 数学验证，不依赖仿真。

```bash
cd /home/discover/supermarket_sorting_task/examples/supermarket_sorting
python3 perception/validate_cam_bridge.py
```

**期望输出结尾：**
```
RESULT: ALL PASS — coordinate bridge is correct.
```
目标瓶 `slot_D_L2_C2_yinlu` 两个机位都应 `in_frame`，`ideal_err 0.0000mm`，`quant_err < 1.3mm`。

---

## 测试二：在线坐标对齐（核心，需 Docker + GPU）★

这是**回答"坐标对齐度"的关键测试**。用 `gt` 后端：节点把每只 yinlu 的真值世界坐标投影到像素，再走完整的"采样真实深度→反投影→相机转世界"链路回算，打印**逐瓶 mm 级误差**。误差里包含了真实渲染深度的量化/噪声，比离线测试更接近真实抓取条件。

### 启动容器

> **镜像/容器说明**：固化镜像是 `supermarket_sorting_task:perception`（已含 `vision_msgs` + `ultralytics`，在 `:latest` 基础上装好 commit 得到）。**不要** `docker build`（会卡在重新拉 nvidia 基础镜像）。下面用镜像起一个常驻容器 `smkt_run`，server 和感知节点共用它。

```bash
# 起常驻容器（headless + GS + EGL，挂载源码，host 网络）
docker run -d --name smkt_run --gpus all --network host \
  -e ROS_DOMAIN_ID=99 -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e MUJOCO_GL=egl -e SUPERMARKET_HEADLESS=1 -e SUPERMARKET_USE_GS=1 -e SUPERMARKET_ENABLE_RENDER=1 \
  -v /home/discover/supermarket_sorting_task:/workspace/supermarket_sorting_task \
  -w /workspace/supermarket_sorting_task --entrypoint sleep \
  supermarket_sorting_task:perception infinity
```

> `SUPERMARKET_USE_GS=1` 很重要：坐标对齐要在真实 GS 深度下测，才有意义。
> 用完清理：`docker rm -f smkt_run`

### 终端 1 — server

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; python3 examples/supermarket_sorting/supermarket_sorting_server.py'
```

### 终端 2 — 感知节点（gt 后端）

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting/perception; python3 yinlu_detect.py --backend gt'
```

**期望输出（每帧逐瓶打印，节点静止时数字应稳定）：**
```
[yinlu_detect] yinlu_detect up; backend=gt
[slot_D_L2_C2_yinlu] world=[0.978 3.415 0.951] gt=[0.978 3.415 0.951] err=0.42mm
[slot_D_L1_C3_yinlu] world=[1.288 3.415 0.651] gt=[1.288 3.415 0.651] err=0.55mm
...
```

> **坐标对齐判据**：在画面内的 yinlu，`err` 应 **< 10mm**（实测多在 1~3mm）。
> 如果某瓶 `err` 突然几十 mm，多半是该像素深度采到了背景/空洞 —— 看它是否在画面边缘。

### 终端 3 — client（可选，看视觉锁定）

```bash
docker exec -it ss_test bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
cd /workspace/supermarket_sorting_task/examples/supermarket_sorting
python3 supermarket_sorting_client.py
```

机器人到货架、低头 dwell 1s 后，**期望看到锁定日志**（字符串与代码一致）：
```
[perception] target locked via vision: OBJECT=[0.978 3.415 0.951]  CREEP_STOP_Y=3.4200  buf_size=5
```
- `via vision` = 视觉成功锁定（buf 攒够 ≥5 帧）
- `via GT-fallback` = 检测不足，回退硬编码（不退化，但说明感知没跟上）

---

## 测试三：黑底场景端到端抓取（blob 后端）

YOLO 权重就绪前，黑底场景用 `blob` 后端即可端到端跑通（黑底上 yinlu 是非黑像素团，连通域分割很稳）。

终端 1（server）同测试二，**终端 2 换后端**：

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting/perception; python3 yinlu_detect.py --backend blob'
```

端到端抓取还需启动 client（终端 3）：

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting; python3 supermarket_sorting_client.py'
```

**期望效果**：机器人导航到货架 → 低头 → 视觉锁定 yinlu 世界坐标 → creep 进货架 → 夹取 → 抬起 → 倒车 → 导航到桌 → 放下。抓取动作与原 baseline **完全一致**，区别仅在目标来源是视觉而非硬编码。

> blob 后端会检测**画面内所有非黑物体**（不止 yinlu）。client 端靠 `TARGET_MATCH_RADIUS=0.20m` 过滤——只接受落在目标槽位 xy 半径 20cm 内的检测，所以多物体不影响锁定正确的那只。

### 可视化检测框

```bash
# 任意 exec 终端
ros2 run rqt_image_view rqt_image_view /yinlu/result_image
```
画面应看到 yinlu 上的绿色框 + 世界坐标文字。

---

## 测试四：话题级诊断

```bash
ros2 topic list | grep -E "yinlu|head_camera"   # 话题是否齐全
ros2 topic echo /yinlu/detections --once         # 看一帧检测内容（world 坐标）
ros2 topic hz   /yinlu/detections                # 频率应 ~24Hz（跟相机）
ros2 topic hz   /head_camera/color/image_raw     # 上游相机帧率
```

---

## 测试五：YOLO 后端验收（yinlu.pt 已训练完成）★

YOLO 权重已训出：`perception/checkpoints/yinlu.pt`（22.5MB，yolov8s 微调，val mAP50=0.9949）。

### 测试 A — 加载权重对样图出框（最快，不需 ROS）

```bash
docker exec smkt_run bash -lc 'cd /workspace/supermarket_sorting_task/examples/supermarket_sorting && MUJOCO_GL=egl python3 -c "
import sys; sys.path.insert(0,\"perception\")
import cv2, glob; from backends import YoloBackend
be=YoloBackend(\"perception/checkpoints/yinlu.pt\", conf_thresh=0.5)
img=cv2.imread(sorted(glob.glob(\"perception/dataset/images/val/*_v0.jpg\"))[0])
print(\"dets:\", be.detect(img,None,None,None))"'
```
**期望**：`[YoloBackend] loaded ...` + 若干 yinlu 框（conf>0.9）。

### 测试 B — 端到端 server + yolo 后端

终端 1（server）同测试二，**终端 2 换 yolo 后端**：

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting/perception; python3 yinlu_detect.py --backend yolo'
```
检查：`ros2 topic echo /yinlu/detections` 有世界坐标输出；`/yinlu/result_image` 有框。

> **v0 权重局限（重要）**：当前 3DGS 背景仍是黑底，训练靠域随机化（随机背景/光照）让模型学瓶子本体。mAP 0.99 是**仿真域内**成绩，对真实复杂背景的鲁棒性**未经验证**。真背景扫完后用 `gen_dataset.py` 重生成数据集 + `train_yolo.py` 重训一版即可，代码不动。

### 复现训练（可选）

```bash
# 必须带 --shm-size=16g，否则 YOLO dataloader 多进程 OOM
docker run --rm --gpus all --shm-size=16g \
  -v /home/discover/supermarket_sorting_task:/workspace/supermarket_sorting_task \
  -w /workspace/supermarket_sorting_task --entrypoint bash \
  supermarket_sorting_task:perception -lc \
  'export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting; \
   MUJOCO_GL=egl python3 perception/gen_dataset.py && \
   python3 perception/train_yolo.py --weights yolov8s.pt'
```
> 预训练 `yolov8s.pt` 已放在 `examples/supermarket_sorting/yolov8s.pt`（GitHub 下载超时，从 hf-mirror 拉的），**请保留**，重训免下载。

---

## 可视化模式：带 3D 仿真窗口（glfw + X11）

前面测试默认 **headless（无窗口）**——稳定、不依赖显示，适合验收看数据。
要**肉眼看 MuJoCo 3D 仿真窗口**（机器人 + 货架）并跑 YOLO，改用下面带显示的配置。

### 1) 宿主机放开显示权限（每次重启后做一次）

```bash
xhost +local:docker
```

### 2) 用带显示的配置重起容器

```bash
docker rm -f smkt_run

docker run -d --name smkt_run --gpus all --network host \
  -e ROS_DOMAIN_ID=99 -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e DISPLAY=$DISPLAY -e MUJOCO_GL=glfw \
  -e SUPERMARKET_HEADLESS=0 -e SUPERMARKET_USE_GS=1 -e SUPERMARKET_ENABLE_RENDER=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /home/discover/supermarket_sorting_task:/workspace/supermarket_sorting_task \
  -w /workspace/supermarket_sorting_task --entrypoint sleep \
  supermarket_sorting_task:perception infinity
```

> 与 headless 的关键差异：`MUJOCO_GL=glfw` + `SUPERMARKET_HEADLESS=0` + `DISPLAY` + 挂 `/tmp/.X11-unix`。

### 3) 终端 1 — server（弹出 3D 仿真窗口）

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; python3 examples/supermarket_sorting/supermarket_sorting_server.py'
```
等几秒（GS 编译 CUDA 扩展），弹出货架 + 机器人的 3D 窗口。

<!-- VIZ_MARKER -->

### 4) 终端 2 — YOLO 感知节点（最终结果）

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting/perception; python3 yinlu_detect.py --backend yolo'
```
预期：`[YoloBackend] loaded .../checkpoints/yinlu.pt`，随后 `/yinlu/detections` 持续发布检测到的 yinlu 世界坐标。
> `yolo` 后端打印**真实检测结果**，不打印 gt 误差（gt 误差是 `--backend gt` 专有）。

### 5) 终端 3 — client（机器人开始动）★

**server 和感知节点都不控制机器人，只有 client 发控制指令。** 不启动 client 机器人不会动。

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export PYTHONPATH=examples/supermarket_sorting:examples/ros2:$PYTHONPATH; cd examples/supermarket_sorting; python3 supermarket_sorting_client.py'
```

机器人流程：导航到货架 → 低头 → 视觉锁定 yinlu → creep 进货架 → 夹取 → 抬起 → 倒车 → 去桌子 → 放下。

到货架低头 dwell 1 秒后，预期打印（确认视觉接管）：
```
[perception] target locked via vision: OBJECT=[0.978 3.415 0.951]  CREEP_STOP_Y=3.4200  buf_size=5
```
- `via vision` = YOLO 检测成功锁定目标
- `via GT-fallback` = 检测没跟上，回退硬编码（机器人仍会动，但说明感知要调参）

### 6) 终端 4 — 确认 YOLO 在出框（文本，可选）

```bash
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp; \
   ros2 topic echo /yinlu/detections --once'
```

### 看检测框叠加图（可选，需装 rqt）

精简镜像**未装 rqt**。要看 `/yinlu/result_image` 的绿色检测框：

```bash
docker exec smkt_run bash -lc 'apt-get update && apt-get install -y ros-humble-rqt-image-view'
docker exec -it smkt_run bash -lc \
  'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp; \
   rqt_image_view /yinlu/result_image'
```
> MuJoCo 仿真窗口（server）**不需要** rqt，直接能看；rqt 只用于看检测框叠加图。

### 可视化常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `ros2: command not found` | 该 shell 没 source ROS | 命令第一句必须 `source /opt/ros/humble/setup.bash` |
| 看不到任何窗口但有数据 | 用的是 headless 配置 | 按本节用 `MUJOCO_GL=glfw` + `HEADLESS=0` 重起 |
| 仿真窗口弹不出来 | X11 通道未通 | 宿主机先 `xhost +local:docker`；确认挂了 `/tmp/.X11-unix` 且 `-e DISPLAY=$DISPLAY` |
| `rqt_image_view` 找不到 | 镜像未装 rqt | 按上方 `apt-get install ros-humble-rqt-image-view` |

---

## 可调参数速查（都在 `supermarket_sorting_client.py` 顶部）

| 参数 | 默认 | 含义 | 何时调 |
|---|---|---|---|
| `DETECT_DWELL` | `1.0` s | DEPLOY 低头后等待检测累积的时间 | 锁定常走 GT-fallback → 调大 |
| `DETECT_MIN_SAMPLES` | `5` | 信任视觉所需最少帧数 | 帧率低/抖动大 → 调小到 3 |
| `TARGET_MATCH_RADIUS` | `0.20` m | 接受检测的 xy 半径 | 锁错相邻瓶 → 调小 |
| `CREEP_STOP_DY` | `0.005` m | creep 停止点相对物体 y 的偏移 | 夹深/夹浅 → 微调 |
| `DEPLOY_OFFSET` | `(-0.011,-0.315,0.023)` | 部署位相对物体的偏移 | **抓取姿态相关，非必要勿动** |

感知节点 blob 后端参数在 `perception/backends.py::BlobBackend.__init__`（`min_area` / `value_thr` / `depth_max` 等）。

---

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 节点不打印检测 | 没收到相机/深度/odom | `ros2 topic hz` 查上游；确认 `SUPERMARKET_ENABLE_RENDER=1` |
| `gt` 误差几十 mm | 像素深度采到背景/空洞 | 看该瓶是否在画面边缘；正常瓶应 <10mm |
| client 总是 `GT-fallback` | dwell 内没攒够 5 帧 | 调大 `DETECT_DWELL` 或调小 `DETECT_MIN_SAMPLES` |
| `ModuleNotFoundError: vision_msgs` | 镜像未重建 | 重新 `docker build`（已加 `ros-humble-vision-msgs`） |
| `No module named discoverse` | PYTHONPATH 未含 examples | 用 entrypoint 启动，或确认在容器内 `/workspace/...` 下运行 |
| 节点报 GS/CUDA 错 | `--gpus all` 未传 | 检查 `docker run` 的 `--gpus all` |

---

## 当前交付状态（实事求是）

| 组件 | 状态 | 验证方式 |
|---|---|---|
| 坐标桥（数学） | ✅ 已验证 0.00mm | 测试一（离线） |
| 坐标桥（真实深度） | ⏳ 待你测 | 测试二（`gt` 后端） |
| blob 后端端到端 | ⏳ 待你测 | 测试三 |
| client 视觉接入 | ✅ 已写+编译通过 | 测试二/三日志 |
| **YOLO 权重 yinlu.pt** | ✅ 已训练（v0） | 测试五 A/B（val mAP50=0.9949） |

> 三个后端都就绪：`gt` 测坐标对齐、`blob` 测黑底端到端、`yolo` 用训好的 `yinlu.pt`。
> YOLO 是 v0（黑底域随机化），真背景扫完后用同套脚本重训一版即可。
