# grasp_gen

Discoverse 仿真 → Zenoh 发布：Airbot 抓取场景 RGB/Depth 流。

```bash
cd examples/grasp_gen
python publish.py            # 默认渲染
python publish.py --use-gs   # 3DGS 高斯溅射渲染
```

## 发布 / 订阅

- **发布**：`env/{CAMERA_ID}/rgb` (jpeg)、`env/{CAMERA_ID}/depth` (zstd-float32)
- **订阅**：`robot/state/joint`、`gripper/sim_two_finger/state` → 控制仿真

## 依赖

- MJCF：`models/mjcf/manipulator/roombia/airplay_pick_blocks.xml`
- 3DGS（可选）：`models/3dgs/grasp_gen_obj/{scene,plate,bottle}.ply`
