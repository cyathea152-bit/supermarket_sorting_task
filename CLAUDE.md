# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A trimmed **DISCOVERSE** robotics runtime (MuJoCo + optional 3D Gaussian Splatting) repackaged as the **Supermarket Sorting** competition (超市分拣比赛). A ROS2 *server* runs the MMK2 dual-arm mobile-manipulator simulation and exposes RGB-D / odometry / joint-state topics; a contestant's ROS2 *client* subscribes to those and publishes control commands to drive the robot to pick an item off a shelf and place it on the delivery table. The Python package is named `discoverse` (version in `discoverse/__init__.py`); the competition code lives under `examples/supermarket_sorting/`.

## Running (Docker is the supported path)

Requires NVIDIA GPU + driver + Container Toolkit. See `README.md` for the full pull/xhost/volume setup. Core loop:

- **Server** (loads scene, runs sim): `python3 examples/supermarket_sorting/supermarket_sorting_server.py`
- **Baseline client** (fixed pick-place demo): `python3 examples/supermarket_sorting/supermarket_sorting_client.py`

Build the image: `docker build -t supermarket_sorting .` (installs the package with `pip install -e ".[gs]"`, ROS2 Humble, CUDA 11.8 torch). `docker/entrypoint.sh` sources ROS and prepends `examples/supermarket_sorting` and `examples/ros2` to `PYTHONPATH` — both must be importable for the server/client to run.

`ROS_DOMAIN_ID` (default 99) **must match** between server and client. `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` is assumed.

### Server environment-variable switches

Read in `supermarket_sorting_server.py::env_flag`:
- `SUPERMARKET_HEADLESS` — 0 opens the GLFW window, 1 headless (Dockerfile default uses EGL + headless)
- `SUPERMARKET_USE_GS` — enable 3D Gaussian Splatting rendering
- `SUPERMARKET_ENABLE_RENDER` — keep camera color/depth topics publishing
- `MUJOCO_GL` — `glfw` for desktop window, `egl` for headless

### Tooling

`pyproject.toml` configures `black` (line-length 88), `isort` (black profile), and `pytest` (`testpaths=["tests"]`), but there is no `tests/` directory — there is currently no test suite to run. Optional dependency groups (`gs`, `lidar`, `act`, `ros`, `full`, …) are defined there; the competition needs `gs`.

## Architecture

### Simulation core (`discoverse/`)

Class inheritance is the key to understanding the runtime:

```
SimulatorBase (discoverse/envs/simulator.py)   # MuJoCo load/step/render, GLFW window, optional GSRendererMuJoCo
   └── MMK2Base (discoverse/robots_env/mmk2_base.py)   # MMK2 robot: 28 qpos / 19 ctrl, init pose, gs_model_dict
          └── MMK2ROS2 (examples/ros2/mmk2_ros2.py)    # also subclasses rclpy Node; the actual server node
```

- `SimulatorBase.__init__` resolves the MJCF path, loads the model, and (when `use_gaussian_renderer`) builds a `GSRendererMuJoCo` from `config.gs_model_dict`, downloading `.ply` models from HuggingFace if not found locally under `DISCOVERSE_ASSETS_DIR/3dgs/`.
- Config objects (`MMK2Cfg` etc.) subclass `BaseConfig` and carry MJCF path, `init_state`, camera ids, render settings, and the `gs_model_dict`.
- `DISCOVERSE_ASSETS_DIR` (env var, set by the server to `examples/supermarket_sorting/models`) overrides where assets/3dgs models are resolved from. Set in `discoverse/__init__.py`.

### Control vector

The whole robot is driven by a single **19-dim `target_control`** array. Layout (server `MMK2ROS2` slices it; client mirrors it as `tc`):

```
[0:2]   base [lin.x, ang.z]      [2:3] slide   [3:5] head [yaw,pitch]
[5:11]  left arm joints (6)      [11]  left gripper
[12:18] right arm joints (6)     [18]  right gripper
```

The server's main loop calls `exec_node.step(exec_node.target_control)`; ROS subscriber callbacks write into `target_control`, and `thread_pubros2topic(freq)` publishes sensor topics on a separate thread.

### Competition task (`examples/supermarket_sorting/`)

- `supermarket_sorting_server.py` — builds `MMK2Cfg`, rewrites the scene XML (replaces `__REPO_ROOT__` placeholder, writes `/tmp/retail_competition_ros2_runtime.xml`), binds each shelf object's 3DGS `.ply` from `retail_competition_layout.json`, sets the start pose, then spins `MMK2ROS2`.
- `supermarket_sorting_client.py` — baseline `PickPlaceClient`. A phase state-machine (`NAV_SHELF → DEPLOY → CREEP → CLOSE → LIFT → RETREAT → NAV_TABLE → PLACE → DONE`) drives the robot. Uses **world-frame ground-truth** object/table positions (hardcoded — swap for perception). Notable design choices baked into comments: the arm is posed in open space at the "yellow line" then the *base* creeps the gripper straight into the shelf (arm never sweeps near the board); `/cmd_vel` and joint commands are acceleration-/slew-limited (`ramp_twist`, `smooth_step`) to avoid teleport/jerk.
- `mmk2_kdl.py` / `arm_kdl.py` — `MMK2Kdl` forward/inverse kinematics used by the client to convert world targets into right-arm joints (footprint frame).
- `retail_competition_layout.json` — per-slot ground truth: `body` name, `object_kind`, `aruco_id`, `world_position`, `gs_ply`. The server reads this to populate `obj_list` and `gs_model_dict`.
- `mjcf/retail_competition.xml`, `models/` (3dgs, meshes, mjcf, textures) — the scene assets.

### ROS2 interface (contestant contract)

The full topic list is documented in `README.md`. Summary: server **publishes** `/slamware_ros_sdk_server_node/odom`, `/tf`, `/joint_states`, and `/head_camera`, `/left_camera`, `/right_camera` color/depth/camera_info; server **subscribes** `/cmd_vel`, and `Float64MultiArray` command topics for `/spine…`, `/head…`, `/left_arm…`, `/right_arm…_forward_position_controller/commands`. Arm command arrays are `[j1..j6, gripper]`; `gripper=1.0` open, `0.2` is the baseline's closed grip. `/joint_states` order is documented in both the README and the client's `JOINT_NAMES`.

## Notes when editing

- The server depends on `examples/ros2/mmk2_ros2.py` (added to `sys.path` at runtime). Changes to the MMK2 ROS2 node affect every ros2 example, not just this task.
- Scene XML is templated: edit `mjcf/retail_competition.xml` with the `__REPO_ROOT__` placeholder, not the generated `/tmp/...runtime.xml`.
- Git submodules (`.gitmodules`: ComfyUI, lerobot, MuJoCo-LiDAR, urdf2mjcf, XML-Editor, policies/act) back optional features and are excluded from the package build and from black/isort.


# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.