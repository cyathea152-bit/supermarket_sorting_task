#!/usr/bin/env python3
"""Tkinter desktop launcher for robot simulation examples."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import queue
import re
import runpy
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from typing import Any, Dict, List, Optional, Tuple, Union


SCRIPT_DIR = Path(__file__).resolve().parent


def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return SCRIPT_DIR.parent


REPO_ROOT = get_runtime_root()
EXAMPLES_ROOT = REPO_ROOT / "examples"
MJCF_ROOT = REPO_ROOT / "models" / "mjcf"
DATA_ROOT = REPO_ROOT / "data"
APP_NAME = "机器人仿真智能控制系统"
APP_DIALOG_TITLE = "机器人仿真智能控制系统"
APP_CLASS_NAME = "RobotSimControl"
LOGO_IMAGE_PATH = REPO_ROOT / "scripts" / "assets" / "shentoon_robotstudio_logo.png"
WINDOW_ICON_PATH = REPO_ROOT / "scripts" / "assets" / "shentoon_window_icon.png"
WINDOW_ICON_XBM_PATH = REPO_ROOT / "scripts" / "assets" / "shentoon_window_icon.xbm"
LOG_LIMIT = 4000
FONT_FAMILY = "TkDefaultFont"
MONO_FONT_FAMILY = "TkFixedFont"
BASE_FONT = (FONT_FAMILY, 20)
LABEL_FONT = (FONT_FAMILY, 20)
TITLE_FONT = (FONT_FAMILY, 30, "bold")
BUTTON_FONT = (FONT_FAMILY, 20, "bold")
LIST_FONT = (FONT_FAMILY, 20)
LOG_FONT = (MONO_FONT_FAMILY, 20)

APP_BG = "#eef2f7"
PANEL_BG = "#ffffff"
PANEL_BORDER = "#d8e0ea"
TEXT_FG = "#172033"
MUTED_FG = "#667085"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
PRIMARY_PRESS = "#1e40af"
DANGER = "#dc2626"
DANGER_HOVER = "#fee2e2"
DANGER_PRESS = "#fecaca"
SOFT_BLUE = "#eff6ff"
SOFT_BLUE_PRESS = "#dbeafe"
INPUT_BG = "#f8fafc"
TREE_BG = "#fbfdff"
TREE_SELECTED = "#dbeafe"
LOG_BG = "#0f172a"
LOG_FG = "#e5e7eb"
LOG_INSERT = "#93c5fd"


def display_text(text: object) -> str:
    value = str(text)
    replacements = {
        "DISCOVERSE": APP_DIALOG_TITLE,
        "Discoverse": APP_DIALOG_TITLE,
        "discoverse": "robot-sim",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def apply_window_icon(window: tk.Toplevel) -> None:
    try:
        if WINDOW_ICON_XBM_PATH.exists():
            window.iconbitmap(default=f"@{WINDOW_ICON_XBM_PATH}")
        if WINDOW_ICON_PATH.exists():
            icon = tk.PhotoImage(file=str(WINDOW_ICON_PATH))
            window.iconphoto(True, icon)
            window.tk.call("wm", "iconphoto", window._w, "-default", icon)
            window._window_icon = icon  # type: ignore[attr-defined]
            window.after(120, lambda: window.iconphoto(True, icon))
    except tk.TclError:
        pass


def configure_cjk_fonts(root: tk.Tk) -> None:
    global FONT_FAMILY, MONO_FONT_FAMILY, BASE_FONT, LABEL_FONT, TITLE_FONT, BUTTON_FONT, LIST_FONT, LOG_FONT

    families = {family.lower(): family for family in tkfont.families(root=root)}
    preferred = (
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Source Han Sans CN",
        "Noto Sans SC",
        "HarmonyOS Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Heiti SC",
        "Nimbus Sans L",
    )
    mono_preferred = (
        "Noto Sans Mono CJK SC",
        "Source Han Mono SC",
        "WenQuanYi Zen Hei Mono",
        "WenQuanYi Micro Hei Mono",
        "Sarasa Mono SC",
        "JetBrains Mono",
        "Nimbus Mono L",
        "DejaVu Sans Mono",
    )

    FONT_FAMILY = next((families[name.lower()] for name in preferred if name.lower() in families), "TkDefaultFont")
    MONO_FONT_FAMILY = next((families[name.lower()] for name in mono_preferred if name.lower() in families), FONT_FAMILY)
    BASE_FONT = (FONT_FAMILY, 13)
    LABEL_FONT = (FONT_FAMILY, 12)
    TITLE_FONT = (FONT_FAMILY, 20, "bold")
    BUTTON_FONT = (FONT_FAMILY, 12, "bold")
    LIST_FONT = (FONT_FAMILY, 12)
    LOG_FONT = (MONO_FONT_FAMILY, 12)


@dataclass(frozen=True)
class ExampleInfo:
    id: str
    name: str
    group: str
    path: str


@dataclass(frozen=True)
class SceneInfo:
    id: str
    name: str
    group: str
    path: str


@dataclass(frozen=True)
class DatasetInfo:
    id: str
    name: str
    group: str
    path: str
    abs_path: Path
    videos: Tuple[Path, ...]
    files: int
    size_bytes: int
    modified_at: float


LaunchItem = Union[ExampleInfo, SceneInfo, DatasetInfo]


EXAMPLE_GROUP_PRIORITY = {
    "tasks_airbot_play": 0,
    "tasks_mmk2": 1,
}


def group_sort_key(group: str) -> Tuple[int, str]:
    return (EXAMPLE_GROUP_PRIORITY.get(group, len(EXAMPLE_GROUP_PRIORITY)), group)


def example_sort_key(example: ExampleInfo) -> Tuple[int, str, str]:
    group_rank, group_name = group_sort_key(example.group)
    return (group_rank, group_name, example.name)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def directory_stats(path: Path) -> Tuple[int, int]:
    files = 0
    total = 0
    if path.is_file():
        return 1, path.stat().st_size
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return files, total


EXCLUDED_DESKTOP_EXAMPLES = {
    # Optional hardware, ROS, CUDA/torch, 3DGS, external services, or CLI-only tools.
    "3dmouse/3dmouse.py",
    "active_slam/camera_view.py",
    "active_slam/mmk2_open_car.py",
    "force_control_data_collect_using_joy/robot_joy_controller.py",
    "force_control_data_collect_using_joy/test_joy_only.py",
    "grasp_gen/publish.py",
    "grasp_gen/subscribe_joint_state.py",
    "grasp_gen/zenoh_bridge.py",
    "force_control/impedance_control.py",
    "hardware_sim/client/airbotplay.py",
    "hardware_sim/client/manger.py",
    "hardware_sim/client/motor_client.py",
    "hardware_sim/client/transport.py",
    "hardware_sim/example/real_play_kbd_ctrl.py",
    "hardware_sim/example/real_play_pos_ctrl.py",
    "hardware_sim/example/real_play_pvt_swing.py",
    "hardware_sim/example/real_play_return_zero.py",
    "hardware_sim/example/real_play_test_init.py",
    "hardware_sim/example/real_play_test_interfaces.py",
    "mocap_ik/mink_arm_ik.py",
    "mocap_ik/mocap_ik_utils.py",
    "robots/airbot_play_cer.py",
    "robots/airbot_replay.py",
    "robots/airbot_replay_control.py",
    "robots/control_util.py",
    "robots/cooperative_control.py",
    "robots/franka_pick_fruit.py",
    "robots/mink_arm_ik.py",
    "robots/pid_control.py",
    "robots/quadrotor_logger.py",
    "robots/rm2_control.py",
    "robots/skyrover_on_car_base.py",
    "robots/ur5e_pick_fruit.py",
    "ros1/airbot_play_cam_ros1.py",
    "ros1/airbot_play_ros1_joy.py",
    "ros1/mmk2_joy_ros1_generate_policy.py",
    "ros1/mmk2_ros1.py",
    "ros1/mmk2_ros1_joy.py",
    "ros1/mmk2_teach_bag_ros1.py",
    "ros1/tok2_ros1.py",
    "ros2/airbot_play_ros2.py",
    "ros2/airbot_play_ros2_joy.py",
    "ros2/mmk2_joy_ros2_generate_policy.py",
    "ros2/mmk2_ros2.py",
    "ros2/mmk2_ros2_joy.py",
    "ros2/tok2_ros2.py",
    "sensor_lidar/mmk2_lidar_ros1.py",
    "sensor_lidar/mmk2_lidar_ros2.py",
    "tasks_airbot_play/block_bridge_place.py",
    "tasks_hand_arm/build_tower.py",
    "tasks_mmk2/gendata_from_json.py",
    "universal_tasks/universal_task_runtime.py",
    "robots/rm2_car.py",
    "robots/skyrover.py",
    "robots/skyrover_and_rm2car.py",
}


EXCLUDED_DESKTOP_SCENES = {
    # These scenes fail direct MuJoCo model loading in the lightweight package due to
    # missing assets, stale include paths, or invalid model definitions.
    "capture.xml",
    "cooperative_aerial_ground_sim.xml",
    "cooperative_multi_robot_sim.xml",
    "dex_hand/inspire_hand_arm/arm_mjcf/air_arm.xml",
    "dex_hand/inspire_hand_arm/hand_arm_bridge.xml",
    "dex_hand/inspire_hand_arm/hand_mjcf/inspire_right_hand.xml",
    "dex_hand/inspire_hand_arm/hand_with_arm.xml",
    "dex_hand/leaphand_sensor_env/leaphand_sensor.xml",
    "exhibition.xml",
    "exhibition_conference.xml",
    "grasp_apple.xml",
    "manipulator/franka_robotiq/panda_robotiq.xml",
    "manipulator/franka_robotiq/pick_fruit.xml",
    "manipulator/new_airbot_play/mjx_airbot_play.xml",
    "manipulator/new_airbot_play/sensor.xml",
    "manipulator/universal_robots_ur5e_robotiq/pick_fruit.xml",
    "manipulator/universal_robots_ur5e_robotiq/ur5e_robotiq.xml",
    "rm2_car_floor.xml",
    "skyrover_floor.xml",
    "skyrover_on_rm2_car.xml",
    "tok2_floor.xml",
}


class ProcessManager:
    def __init__(self, python: str) -> None:
        self.python = python
        self.process: Optional[subprocess.Popen[str]] = None
        self.command: List[str] = []
        self.example_id: Optional[str] = None
        self.started_at: Optional[float] = None
        self.returncode: Optional[int] = None
        self.logs: deque[Dict[str, Any]] = deque(maxlen=LOG_LIMIT)
        self.next_log_id = 0
        self.lock = threading.Lock()
        self.reader_thread: Optional[threading.Thread] = None
        self.waiter_thread: Optional[threading.Thread] = None

    def status(self) -> Dict[str, Any]:
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            if self.process is not None and not running:
                self.returncode = self.process.poll()
            return {
                "running": running,
                "pid": self.process.pid if self.process is not None else None,
                "returncode": self.returncode,
                "example_id": self.example_id,
                "command": self.command,
                "started_at": self.started_at,
            }

    def get_logs(self, since: int = 0) -> Dict[str, Any]:
        with self.lock:
            logs = [item for item in self.logs if item["id"] > since]
            latest = self.next_log_id - 1
        return {"logs": logs, "latest": latest}

    def start(
        self,
        example: ExampleInfo,
        python: str,
        common_args: Dict[str, Any],
        extra_args: str,
        env_lines: str,
    ) -> Dict[str, Any]:
        parsed_extra_args = shlex.split(extra_args or "")
        script_path = REPO_ROOT / example.path
        command = [python or self.python, str(script_path)]

        if common_args.get("auto"):
            command.append("--auto")
        if common_args.get("use_gs"):
            command.append("--use_gs")
        if common_args.get("data_idx") not in (None, ""):
            command.extend(["--data_idx", str(common_args["data_idx"])])
        if common_args.get("data_set_size") not in (None, ""):
            command.extend(["--data_set_size", str(common_args["data_set_size"])])
        command.extend(parsed_extra_args)

        return self.start_command(example.id, command, env_lines, cwd=REPO_ROOT)

    def start_command(
        self,
        target_id: str,
        command: List[str],
        env_lines: str = "",
        cwd: Path = REPO_ROOT,
    ) -> Dict[str, Any]:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("已有任务正在运行，请先停止当前任务。")

        env = os.environ.copy()
        env_extra = parse_env_lines(env_lines)
        env.update(env_extra)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("DISCOVERSE_ASSETS_DIR", str(REPO_ROOT / "models"))

        preexec_fn = os.setsid if hasattr(os, "setsid") else None
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=preexec_fn,
        )

        with self.lock:
            self.process = process
            self.command = command
            self.example_id = target_id
            self.started_at = time.time()
            self.returncode = None
            self.logs.clear()
            self.next_log_id = 0
            self._append_log_locked(f"$ {shlex.join(command)}")
            if env_extra:
                keys = ", ".join(sorted(env_extra))
                self._append_log_locked(f"# 已应用环境变量: {keys}")

        self.reader_thread = threading.Thread(target=self._read_output, args=(process,), daemon=True)
        self.waiter_thread = threading.Thread(target=self._wait_process, args=(process,), daemon=True)
        self.reader_thread.start()
        self.waiter_thread.start()
        return self.status()

    def stop(self) -> Dict[str, Any]:
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                process = None
            else:
                pid = process.pid
                self._append_log_locked(f"# 正在停止进程 {pid}...")

        if process is None:
            return self.status()

        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with self.lock:
                    self._append_log_locked(f"# 进程 {pid} 未退出，正在强制结束...")
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=5)
        except ProcessLookupError:
            pass

        with self.lock:
            self.returncode = process.poll()
        return self.status()

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                with self.lock:
                    self._append_log_locked(line.rstrip("\n"))
        finally:
            try:
                process.stdout.close()
            except Exception:
                pass

    def _wait_process(self, process: subprocess.Popen[str]) -> None:
        returncode = process.wait()
        with self.lock:
            self.returncode = returncode
            if returncode == 0:
                self._append_log_locked("# 任务已正常结束。")
            else:
                self._append_log_locked(f"# 任务异常退出，退出码: {returncode}。")

    def _append_log_locked(self, text: str) -> None:
        self.logs.append({"id": self.next_log_id, "time": time.time(), "text": text})
        self.next_log_id += 1


def scan_examples() -> List[ExampleInfo]:
    examples: List[ExampleInfo] = []
    if not EXAMPLES_ROOT.exists():
        return examples

    for path in sorted(EXAMPLES_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        rel_examples = path.relative_to(EXAMPLES_ROOT).as_posix()
        if rel_examples in EXCLUDED_DESKTOP_EXAMPLES:
            continue
        group = rel_examples.split("/", 1)[0] if "/" in rel_examples else "root"
        name = rel_examples[:-3]
        examples.append(ExampleInfo(id=rel_examples, name=name, group=group, path=rel))
    return sorted(examples, key=example_sort_key)


def scan_datasets() -> List[DatasetInfo]:
    datasets: List[DatasetInfo] = []
    if not DATA_ROOT.exists():
        return datasets

    for task_dir in sorted((path for path in DATA_ROOT.iterdir() if path.is_dir()), key=lambda p: p.name):
        episode_dirs = [
            path
            for path in task_dir.iterdir()
            if path.is_dir() and ((path / "obs_action.json").exists() or any(path.glob("cam_*.mp4")))
        ]
        if episode_dirs:
            targets = sorted(episode_dirs, key=lambda p: p.name)
        else:
            has_dataset_files = any(task_dir.glob("*.mp4")) or any(task_dir.glob("*.json")) or any(task_dir.glob("*.mjb"))
            targets = [task_dir] if has_dataset_files else []

        for target in targets:
            videos = tuple(sorted(target.rglob("*.mp4"), key=lambda p: p.name))
            files, size = directory_stats(target)
            try:
                modified_at = target.stat().st_mtime
            except OSError:
                modified_at = 0
            rel = target.relative_to(REPO_ROOT).as_posix()
            name = target.relative_to(DATA_ROOT).as_posix()
            datasets.append(
                DatasetInfo(
                    id=rel,
                    name=name,
                    group=task_dir.name,
                    path=rel,
                    abs_path=target,
                    videos=videos,
                    files=files,
                    size_bytes=size,
                    modified_at=modified_at,
                )
            )

    return sorted(datasets, key=lambda item: (-item.modified_at, item.group, item.name))


def parse_env_lines(text: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for lineno, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"第 {lineno} 行环境变量格式错误，应为 KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError(f"第 {lineno} 行环境变量格式错误，变量名不能为空")
        env[key] = value
    return env


def is_install_source(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "discoverse").is_dir()


def find_install_source() -> Path:
    bundled_source = REPO_ROOT / "installer_source"
    if is_install_source(bundled_source):
        return bundled_source
    if is_install_source(REPO_ROOT):
        return REPO_ROOT
    executable_path = Path(sys.executable).resolve()
    for parent in executable_path.parents:
        if is_install_source(parent):
            return parent
    return REPO_ROOT


def find_conda_executable() -> str:
    candidates = [
        os.environ.get("CONDA_EXE"),
        shutil.which("conda"),
    ]
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(str(Path(conda_prefix) / "bin" / "conda"))

    for base in (
        "~/miniconda3",
        "~/anaconda3",
        "~/mambaforge",
        "~/miniforge3",
        "/opt/conda",
        "/usr/local/anaconda3",
        "/usr/local/miniconda3",
    ):
        candidates.append(str(Path(os.path.expanduser(base)) / "bin" / "conda"))

    shell_candidate = find_conda_from_shell()
    if shell_candidate:
        candidates.append(shell_candidate)

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
    return "conda"


def find_conda_from_shell() -> Optional[str]:
    shell = os.environ.get("SHELL") or "/bin/bash"
    try:
        result = subprocess.run(
            [shell, "-lc", "command -v conda"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    candidate = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return candidate or None


class EnvironmentInstallerWindow(tk.Toplevel):
    ENV_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, master: "DesktopExamplesApp") -> None:
        super().__init__(master)
        self.master_app = master
        self.title(f"{APP_DIALOG_TITLE} 环境安装")
        apply_window_icon(self)
        self.geometry("980x700")
        self.minsize(860, 600)
        self.transient(master)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.install_thread: Optional[threading.Thread] = None
        self.current_process: Optional[subprocess.Popen[str]] = None
        self.cancel_requested = False

        self.conda_var = tk.StringVar(value=find_conda_executable())
        self.env_name_var = tk.StringVar(value="robot_sim")
        self.python_version_var = tk.StringVar(value="3.11")
        self.source_var = tk.StringVar(value=str(find_install_source()))
        self.status_var = tk.StringVar(value="就绪")

        self._build_layout()
        self._set_installing(False)
        self.after(120, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        container = ttk.Frame(self, style="Panel.TFrame", padding=14)
        container.grid(row=0, column=0, rowspan=4, sticky="nsew", padx=12, pady=12)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(8, weight=1)

        ttk.Label(container, text="环境安装", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        ttk.Label(container, text="Conda 可执行文件", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(container, textvariable=self.conda_var).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.detect_conda_button = AnimatedButton(
            container,
            text="自动识别",
            command=self._detect_conda,
            normal_bg=SOFT_BLUE,
            hover_bg="#dbeafe",
            press_bg=SOFT_BLUE_PRESS,
            fg=PRIMARY,
            disabled_bg="#f7f8fb",
        )
        self.detect_conda_button.grid(row=2, column=2, sticky="ew", pady=(0, 10), padx=(8, 0))

        ttk.Label(container, text="Conda 环境名", style="Panel.TLabel").grid(
            row=3, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Entry(container, textvariable=self.env_name_var).grid(row=4, column=0, sticky="ew", padx=(0, 12), pady=(0, 10))

        ttk.Label(container, text="Python 版本", style="Panel.TLabel").grid(row=3, column=1, sticky="w", pady=(0, 4))
        self.python_combo = ttk.Combobox(
            container,
            textvariable=self.python_version_var,
            values=("3.11", "3.12"),
            state="readonly",
            width=12,
        )
        self.python_combo.grid(row=4, column=1, sticky="w", pady=(0, 10))

        ttk.Label(container, text="安装源目录", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(container, textvariable=self.source_var, state="readonly").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(0, 10)
        )

        button_row = ttk.Frame(container, style="Panel.TFrame")
        button_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.install_button = AnimatedButton(
            button_row,
            text="安装",
            command=self._start_install,
            normal_bg=PRIMARY,
            hover_bg=PRIMARY_HOVER,
            press_bg=PRIMARY_PRESS,
        )
        self.install_button.pack(side=tk.LEFT, padx=(0, 8))
        self.cancel_button = AnimatedButton(
            button_row,
            text="取消",
            command=self._cancel_install,
            normal_bg="#fff1f2",
            hover_bg=DANGER_HOVER,
            press_bg=DANGER_PRESS,
            fg=DANGER,
            disabled_bg="#f7f8fb",
        )
        self.cancel_button.pack(side=tk.LEFT)
        ttk.Label(button_row, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.LEFT, padx=(16, 0))

        log_frame = ttk.Frame(container, style="Panel.TFrame")
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            background=LOG_BG,
            foreground=LOG_FG,
            insertbackground=LOG_INSERT,
            wrap="word",
            state="disabled",
            borderwidth=0,
            padx=12,
            pady=10,
            height=12,
            font=LOG_FONT,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _start_install(self) -> None:
        if self.install_thread and self.install_thread.is_alive():
            return
        try:
            conda = self.conda_var.get().strip()
            env_name = self.env_name_var.get().strip()
            python_version = self.python_version_var.get().strip()
            source = Path(self.source_var.get()).resolve()
            self._validate_inputs(conda, env_name, python_version, source)
        except RuntimeError as exc:
            messagebox.showerror(APP_DIALOG_TITLE, display_text(exc), parent=self)
            return

        self.cancel_requested = False
        self._clear_log()
        self._set_installing(True)
        self.status_var.set("正在安装")
        self.install_thread = threading.Thread(
            target=self._install_worker,
            args=(conda, env_name, python_version, source),
            daemon=True,
        )
        self.install_thread.start()

    def _detect_conda(self) -> None:
        self.conda_var.set(find_conda_executable())

    def _validate_inputs(self, conda: str, env_name: str, python_version: str, source: Path) -> None:
        if not conda:
            raise RuntimeError("请指定 Conda 可执行文件。")
        if not env_name:
            raise RuntimeError("请输入 Conda 环境名。")
        if env_name == "base":
            raise RuntimeError("请不要安装到 base 环境。")
        if not self.ENV_NAME_PATTERN.match(env_name):
            raise RuntimeError("环境名只能包含字母、数字、下划线、点和连字符。")
        if python_version not in {"3.11", "3.12"}:
            raise RuntimeError("请选择 Python 3.11 或 3.12。")
        if not is_install_source(source):
            raise RuntimeError(f"安装源目录不是有效的源码目录: {source}")

    def _install_worker(self, conda: str, env_name: str, python_version: str, source: Path) -> None:
        try:
            envs = self._list_conda_envs(conda)
            if env_name in envs:
                raise RuntimeError(f"Conda 环境已存在: {env_name}")

            self._log(f"Conda: {conda}")
            self._log(f"环境名: {env_name}")
            self._log(f"Python: {python_version}")
            self._log(f"安装源: {source}")
            self._run_command([conda, "create", "-y", "-n", env_name, f"python={python_version}"])
            self._run_command([conda, "run", "-n", env_name, "python", "-m", "pip", "install", "--upgrade", "pip"])
            self._run_command([conda, "run", "-n", env_name, "python", "-m", "pip", "install", "-e", str(source)])
            self._run_command(
                [
                    conda,
                    "run",
                    "-n",
                    env_name,
                    "python",
                    "-c",
                    "import discoverse, mujoco; print('运行库导入成功'); print('MuJoCo', mujoco.__version__)",
                ]
            )
            env_python = self._capture_command(
                [conda, "run", "-n", env_name, "python", "-c", "import sys; print(sys.executable)"]
            ).strip().splitlines()[-1]
            self.log_queue.put(("success", env_python))
        except Exception as exc:
            if self.cancel_requested:
                self.log_queue.put(("cancelled", "安装已取消。"))
            else:
                self.log_queue.put(("error", str(exc)))

    def _list_conda_envs(self, conda: str) -> set[str]:
        output = self._capture_command([conda, "env", "list", "--json"])
        data = json.loads(output)
        names: set[str] = set()
        details = data.get("envs_details") or {}
        for path, detail in details.items():
            name = detail.get("name") or Path(path).name
            names.add(name)
        for path in data.get("envs", []):
            names.add("base" if Path(path).name in {"miniconda3", "anaconda3"} else Path(path).name)
        return names

    def _capture_command(self, command: List[str]) -> str:
        self._log(f"$ {shlex.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.stdout:
            self._log(result.stdout.rstrip())
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败，退出码 {result.returncode}: {shlex.join(command)}")
        return result.stdout

    def _run_command(self, command: List[str]) -> None:
        self._log(f"$ {shlex.join(command)}")
        preexec_fn = os.setsid if hasattr(os, "setsid") else None
        self.current_process = subprocess.Popen(
            command,
            cwd=str(Path(self.source_var.get())),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=preexec_fn,
        )
        assert self.current_process.stdout is not None
        for line in self.current_process.stdout:
            self._log(line.rstrip("\n"))
        returncode = self.current_process.wait()
        self.current_process = None
        if self.cancel_requested:
            raise RuntimeError("安装已取消。")
        if returncode != 0:
            raise RuntimeError(f"命令执行失败，退出码 {returncode}: {shlex.join(command)}")

    def _cancel_install(self) -> None:
        self.cancel_requested = True
        process = self.current_process
        if process and process.poll() is None:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass

    def _log(self, text: str) -> None:
        self.log_queue.put(("log", text))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload + "\n")
                elif kind == "success":
                    self._append_log(f"\n安装完成。Python 路径: {payload}\n")
                    self.master_app.python_var.set(payload)
                    self.status_var.set("完成")
                    self._set_installing(False)
                elif kind == "cancelled":
                    self._append_log(f"\n{payload}\n")
                    self.status_var.set("已取消")
                    self._set_installing(False)
                elif kind == "error":
                    self._append_log(f"\n错误: {payload}\n")
                    self.status_var.set("失败")
                    self._set_installing(False)
        except queue.Empty:
            pass
        self.after(120, self._drain_log_queue)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        at_bottom = self.log_text.yview()[1] >= 0.98
        self.log_text.insert(tk.END, text)
        if at_bottom:
            self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _set_installing(self, installing: bool) -> None:
        self.install_button.set_enabled(not installing)
        self.cancel_button.set_enabled(installing)
        state = tk.DISABLED if installing else tk.NORMAL
        self.python_combo.configure(state="disabled" if installing else "readonly")
        for child in self.winfo_children():
            self._set_entry_state(child, state)

    def _set_entry_state(self, widget: tk.Widget, state: str) -> None:
        for child in widget.winfo_children():
            self._set_entry_state(child, state)
        if isinstance(widget, ttk.Entry) and str(widget.cget("state")) != "readonly":
            widget.configure(state=state)

    def _on_close(self) -> None:
        if self.install_thread and self.install_thread.is_alive():
            if not messagebox.askyesno(APP_DIALOG_TITLE, "安装仍在运行，是否取消并关闭？", parent=self):
                return
            self._cancel_install()
        self.destroy()


def scan_scenes() -> List[SceneInfo]:
    scenes: List[SceneInfo] = []
    if not MJCF_ROOT.exists():
        return scenes
    for path in sorted(MJCF_ROOT.rglob("*")):
        if path.suffix.lower() not in {".xml", ".mjb"}:
            continue
        if path.suffix.lower() == ".xml" and not _looks_like_mujoco_scene(path):
            continue
        rel = path.relative_to(MJCF_ROOT).as_posix()
        if rel in EXCLUDED_DESKTOP_SCENES:
            continue
        group = rel.split("/", 1)[0] if "/" in rel else "root"
        scenes.append(SceneInfo(id=rel, name=rel.rsplit(".", 1)[0], group=group, path=rel))
    return scenes


def _looks_like_mujoco_scene(path: Path) -> bool:
    try:
        for _event, element in ET.iterparse(path, events=("start",)):
            return element.tag == "mujoco"
    except ET.ParseError:
        return False
    return False


def prepare_worker_environment() -> None:
    os.chdir(REPO_ROOT)
    os.environ.setdefault("DISCOVERSE_ASSETS_DIR", str(REPO_ROOT / "models"))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    repo_text = str(REPO_ROOT)
    if repo_text not in sys.path:
        sys.path.insert(0, repo_text)


def run_example_worker(example_path: str, extra_args: List[str]) -> int:
    prepare_worker_environment()
    script_path = (REPO_ROOT / example_path).resolve()
    if not script_path.exists():
        raise RuntimeError(f"未找到示例: {example_path}")
    script_dir = str(script_path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    sys.argv = [str(script_path)] + extra_args
    rel_parts = Path(example_path).with_suffix("").parts
    if rel_parts and rel_parts[0] == "examples" and all(part.isidentifier() for part in rel_parts):
        try:
            runpy.run_module(".".join(rel_parts), run_name="__main__", alter_sys=True)
            return 0
        except ImportError:
            sys.argv = [str(script_path)] + extra_args
    runpy.run_path(str(script_path), run_name="__main__")
    return 0


def run_scene_worker(scene_path: str, extra_args: List[str]) -> int:
    prepare_worker_environment()
    mjcf_path = (MJCF_ROOT / scene_path).resolve()
    if not mjcf_path.exists():
        raise RuntimeError(f"未找到场景: {scene_path}")
    sys.argv = ["mujoco.viewer", f"--mjcf={mjcf_path}"] + extra_args
    runpy.run_module("mujoco.viewer", run_name="__main__", alter_sys=True)
    return 0


def run_self_check() -> int:
    prepare_worker_environment()
    for module_name in ("OpenGL.platform.egl", "OpenGL.platform.glx", "OpenGL.platform.osmesa"):
        importlib.import_module(module_name)
    import discoverse.envs  # noqa: F401
    import mujoco  # noqa: F401

    print(f"{APP_DIALOG_TITLE} 打包自检通过。")
    return 0


HELP_TEXT = """机器人仿真智能控制系统

这是一个面向机器人仿真示例、场景和数据采集流程的桌面入口。它把常用运行、环境安装、日志查看和数据集管理集中在一个窗口中，适合不想反复敲命令的使用场景。

主要功能

1. 示例运行
   在左侧选择“示例”，可以按分组浏览 examples 中可直接运行的示例。任务类示例会优先显示在列表前面。选择示例后，可以设置 Python 解释器、data_idx、data_set_size、--auto、--use_gs、额外命令行参数和环境变量，然后点击“启动”。

2. 场景打开
   在左侧选择“场景”，可以浏览可直接打开的 MuJoCo 场景。已知缺资源或路径错误、直接打开会报错的场景会在 app 中隐藏。

3. 环境安装
   点击“环境安装”，可以自动识别 Conda 路径，也可以手动填写 Conda 可执行文件。安装器支持创建 Conda 环境，并可选择环境名和 Python 版本。

4. 数据集管理
   运行任务示例后，采集结果通常保存在 data/任务名/编号/ 下。切换到“数据集”页面后，可以刷新数据集列表、打开数据目录、回放 cam_*.mp4 视频、删除单个视频或删除整个数据集。

5. 日志查看
   右侧日志区域会显示当前任务的命令输出和退出状态。退出码为 0 表示任务正常结束；非 0 表示异常退出，需要查看日志中的报错。

常用流程

1. 首次使用时，先点击“环境安装”创建或确认运行环境。
2. 切到“示例”，选择任务示例，例如 tasks_airbot_play 或 tasks_mmk2。
3. 需要自动采集时勾选 --auto，并设置 data_idx、data_set_size。
4. 点击“启动”，等待任务结束。
5. 切到“数据集”，点击“刷新”，查看生成的数据和视频。

提示

- 回放视频会调用系统默认播放器；Linux 下通常依赖 xdg-open。
- 如果示例需要 GPU、ROS、硬件设备或额外模型，但当前机器没有对应环境，运行仍可能失败。
- 打包版 app 的数据目录位于 app 自身运行根目录下；源码版则使用仓库中的 data/ 目录。
- 删除数据集和视频会直接删除磁盘文件，请确认后再操作。
"""


class HelpWindow(tk.Toplevel):
    def __init__(self, master: "DesktopExamplesApp") -> None:
        super().__init__(master)
        self.title(f"{APP_DIALOG_TITLE} 帮助")
        apply_window_icon(self)
        self.geometry("900x720")
        self.minsize(760, 560)
        self.transient(master)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        container = ttk.Frame(self, style="Panel.TFrame", padding=14)
        container.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=12, pady=12)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(container, text="帮助", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))

        text_frame = ttk.Frame(container, style="Panel.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        help_text = tk.Text(
            text_frame,
            wrap="word",
            borderwidth=0,
            padx=12,
            pady=10,
            background=INPUT_BG,
            foreground=TEXT_FG,
            insertbackground=PRIMARY,
            font=BASE_FONT,
        )
        help_text.grid(row=0, column=0, sticky="nsew")
        help_text.insert("1.0", HELP_TEXT)
        help_text.configure(state="disabled")
        scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=help_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        help_text.configure(yscrollcommand=scroll.set)

        AnimatedButton(
            container,
            text="关闭",
            command=self.destroy,
            normal_bg=PRIMARY,
            hover_bg=PRIMARY_HOVER,
            press_bg=PRIMARY_PRESS,
        ).grid(row=2, column=0, sticky="e", pady=(12, 0))


class AnimatedButton(tk.Button):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command,
        normal_bg: str,
        hover_bg: str,
        press_bg: str,
        fg: str = "#ffffff",
        disabled_bg: str = "#edf0f5",
    ) -> None:
        super().__init__(
            master,
            text=text,
            command=command,
            background=normal_bg,
            foreground=fg,
            activebackground=press_bg,
            activeforeground=fg,
            borderwidth=0,
            cursor="hand2",
            disabledforeground="#8a95a6",
            font=BUTTON_FONT,
            highlightthickness=1,
            highlightbackground=normal_bg,
            highlightcolor=normal_bg,
            padx=20,
            pady=10,
            relief=tk.FLAT,
        )
        self.normal_bg = normal_bg
        self.hover_bg = hover_bg
        self.press_bg = press_bg
        self.enabled_fg = fg
        self.disabled_bg = disabled_bg
        self._animation_id: Optional[str] = None
        self._pulse_id: Optional[str] = None
        self._target_bg = normal_bg
        self.bind("<Enter>", lambda _event: self._animate_to(self.hover_bg))
        self.bind("<Leave>", lambda _event: self._animate_to(self.normal_bg))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _press(self, _event: tk.Event[tk.Button]) -> None:
        if self["state"] == tk.DISABLED:
            return
        self.configure(relief=tk.FLAT, padx=18, pady=9)
        self._animate_to(self.press_bg, steps=4)

    def _release(self, _event: tk.Event[tk.Button]) -> None:
        if self["state"] == tk.DISABLED:
            return
        self.configure(relief=tk.FLAT, padx=20, pady=10)
        self._animate_to(self.hover_bg, steps=5)

    def _animate_to(self, color: str, steps: int = 8) -> None:
        if self["state"] == tk.DISABLED:
            return
        if self._animation_id is not None:
            self.after_cancel(self._animation_id)
            self._animation_id = None
        self._target_bg = color
        start = self._hex_to_rgb(self.cget("background"))
        end = self._hex_to_rgb(color)
        self._step_color(start, end, 1, steps)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.configure(
                state=tk.NORMAL,
                background=self.normal_bg,
                foreground=self.enabled_fg,
                cursor="hand2",
                relief=tk.FLAT,
                highlightbackground=self.normal_bg,
                highlightcolor=self.normal_bg,
                padx=20,
                pady=10,
            )
        else:
            if self._animation_id is not None:
                self.after_cancel(self._animation_id)
                self._animation_id = None
            if self._pulse_id is not None:
                self.after_cancel(self._pulse_id)
                self._pulse_id = None
            self.configure(
                state=tk.DISABLED,
                background=self.disabled_bg,
                foreground="#8a95a6",
                cursor="arrow",
                relief=tk.FLAT,
                highlightbackground=self.disabled_bg,
                highlightcolor=self.disabled_bg,
            )

    def pulse(self) -> None:
        if self["state"] == tk.DISABLED:
            return
        self.configure(relief=tk.FLAT, padx=18, pady=9)
        self._animate_to(self.press_bg, steps=3)
        self._pulse_id = self.after(90, lambda: self.configure(relief=tk.FLAT, padx=20, pady=10))
        self.after(105, lambda: self._animate_to(self.normal_bg, steps=7))

    def _step_color(self, start: tuple[int, int, int], end: tuple[int, int, int], step: int, steps: int) -> None:
        ratio = step / steps
        color = tuple(round(start[index] + (end[index] - start[index]) * ratio) for index in range(3))
        hex_color = self._rgb_to_hex(color)
        self.configure(background=hex_color, highlightbackground=hex_color, highlightcolor=hex_color)
        if step < steps:
            self._animation_id = self.after(18, lambda: self._step_color(start, end, step + 1, steps))
        else:
            self._animation_id = None

    @staticmethod
    def _hex_to_rgb(color: str) -> tuple[int, int, int]:
        color = color.lstrip("#")
        return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(color: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*color)


class DesktopExamplesApp(tk.Tk):
    def __init__(self, python: str) -> None:
        super().__init__(className=APP_CLASS_NAME)
        configure_cjk_fonts(self)
        self.title(APP_NAME)
        apply_window_icon(self)
        self.geometry("1500x960")
        self.minsize(1280, 780)
        self.configure(background=APP_BG)

        self.manager = ProcessManager(python)
        self.examples = scan_examples()
        self.scenes = scan_scenes()
        self.datasets = scan_datasets()
        self.filtered_items: List[LaunchItem] = []
        self.selected_item: Optional[LaunchItem] = None
        self.selected_video: Optional[Path] = None
        self.latest_log_id = -1
        self.was_running = False

        self.mode_var = tk.StringVar(value="示例")
        self.search_var = tk.StringVar()
        self.group_var = tk.StringVar(value="全部分组")
        self.python_var = tk.StringVar(value=python)
        self.selected_var = tk.StringVar(value="")
        self.data_idx_var = tk.StringVar()
        self.data_set_size_var = tk.StringVar()
        self.auto_var = tk.BooleanVar(value=False)
        self.use_gs_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="空闲")
        self.pid_var = tk.StringVar(value="进程: -")
        self.exit_var = tk.StringVar(value="退出码: -")
        self.command_var = tk.StringVar(value="")
        self.dataset_path_var = tk.StringVar(value="未选择数据集")
        self.dataset_meta_var = tk.StringVar(value="")

        self._build_style()
        self._build_layout()
        self._bind_events()
        self._refresh_groups()
        self._refresh_items()
        self._refresh_status(schedule=True)
        self.after(250, lambda: self._poll_logs(schedule=True))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("TFrame", background=APP_BG)
        self.style.configure("Panel.TFrame", background=PANEL_BG, relief="solid", borderwidth=1)
        self.style.configure("TLabel", background=APP_BG, foreground=TEXT_FG, font=LABEL_FONT)
        self.style.configure("Panel.TLabel", background=PANEL_BG, foreground=TEXT_FG, font=LABEL_FONT)
        self.style.configure("Muted.TLabel", background=PANEL_BG, foreground=MUTED_FG, font=(FONT_FAMILY, 11))
        self.style.configure("Title.TLabel", background=PANEL_BG, foreground=TEXT_FG, font=TITLE_FONT)
        self.style.configure("TEntry", fieldbackground=INPUT_BG, foreground=TEXT_FG, font=BASE_FONT, padding=(10, 7))
        self.style.configure("TCombobox", fieldbackground=INPUT_BG, foreground=TEXT_FG, font=BASE_FONT, padding=(10, 7))
        self.style.configure("TCheckbutton", font=BASE_FONT, background=PANEL_BG, foreground=TEXT_FG)
        self.style.configure(
            "Treeview",
            font=LIST_FONT,
            rowheight=30,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TEXT_FG,
            borderwidth=0,
        )
        self.style.configure(
            "Treeview.Heading",
            background="#f1f5f9",
            foreground=TEXT_FG,
            font=(FONT_FAMILY, 12, "bold"),
            relief="flat",
        )
        self.style.map(
            "Treeview",
            background=[("selected", TREE_SELECTED)],
            foreground=[("selected", TEXT_FG)],
        )

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0, minsize=520)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, style="Panel.TFrame", padding=16)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(7, weight=1)

        self._build_logo(sidebar).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.env_setup_button = AnimatedButton(
            sidebar,
            text="环境安装",
            command=self._open_environment_setup,
            normal_bg=SOFT_BLUE,
            hover_bg="#dbeafe",
            press_bg=SOFT_BLUE_PRESS,
            fg=PRIMARY,
            disabled_bg="#f7f8fb",
        )
        self.env_setup_button.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.help_button = AnimatedButton(
            sidebar,
            text="帮助",
            command=self._open_help,
            normal_bg=PRIMARY,
            hover_bg=PRIMARY_HOVER,
            press_bg=PRIMARY_PRESS,
        )
        self.help_button.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(sidebar, text="模式", style="Panel.TLabel").grid(row=3, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(
            sidebar,
            textvariable=self.mode_var,
            values=("示例", "场景", "数据集"),
            state="readonly",
        )
        self.mode_combo.grid(row=4, column=0, sticky="ew", pady=(4, 8))
        ttk.Label(sidebar, text="搜索", style="Panel.TLabel").grid(row=5, column=0, sticky="w")
        search = ttk.Entry(sidebar, textvariable=self.search_var)
        search.grid(row=6, column=0, sticky="ew", pady=(4, 8))

        filter_row = ttk.Frame(sidebar, style="Panel.TFrame")
        filter_row.grid(row=7, column=0, sticky="nsew")
        filter_row.columnconfigure(0, weight=1)
        filter_row.rowconfigure(2, weight=1)
        ttk.Label(filter_row, text="分组", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.group_combo = ttk.Combobox(filter_row, textvariable=self.group_var, state="readonly")
        self.group_combo.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.item_list = ttk.Treeview(
            filter_row,
            columns=("name",),
            show="headings",
            selectmode="browse",
        )
        self.item_list.heading("name", text="名称", anchor="w")
        self.item_list.column("name", width=440, minwidth=220, stretch=True, anchor="w")
        self.item_list.grid(row=2, column=0, sticky="nsew")
        list_scroll_y = ttk.Scrollbar(filter_row, orient=tk.VERTICAL, command=self.item_list.yview)
        list_scroll_y.grid(row=2, column=1, sticky="ns")
        self.item_list.configure(yscrollcommand=list_scroll_y.set)
        self.count_label = ttk.Label(sidebar, text="0 / 0", style="Muted.TLabel")
        self.count_label.grid(row=8, column=0, sticky="ew", pady=(8, 0))

        content = ttk.Frame(self, style="Panel.TFrame", padding=16)
        content.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(5, weight=1, minsize=240)

        form = ttk.Frame(content, style="Panel.TFrame")
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self._add_labeled_entry(form, "Python 解释器", self.python_var, 0, 0)
        self._add_labeled_entry(form, "已选择项目", self.selected_var, 0, 2, readonly=True)
        self._add_labeled_entry(form, "data_idx", self.data_idx_var, 2, 0)
        self._add_labeled_entry(form, "data_set_size", self.data_set_size_var, 2, 2)

        checks = ttk.Frame(form, style="Panel.TFrame")
        checks.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(checks, text="--auto", variable=self.auto_var).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Checkbutton(checks, text="--use_gs", variable=self.use_gs_var).pack(side=tk.LEFT)

        ttk.Label(form, text="额外命令行参数", style="Panel.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )
        self.extra_args_text = ttk.Entry(form)
        self.extra_args_text.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        ttk.Label(form, text="环境变量", style="Panel.TLabel").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )
        self.env_text = tk.Text(
            form,
            height=4,
            wrap="none",
            undo=True,
            borderwidth=1,
            relief="solid",
            background=INPUT_BG,
            foreground=TEXT_FG,
            insertbackground=PRIMARY,
            highlightthickness=1,
            highlightbackground=PANEL_BORDER,
            highlightcolor=PRIMARY,
            font=LOG_FONT,
        )
        self.env_text.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        actions = ttk.Frame(content, style="Panel.TFrame")
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        self.start_button = AnimatedButton(
            actions,
            text="启动",
            command=self._start,
            normal_bg=PRIMARY,
            hover_bg=PRIMARY_HOVER,
            press_bg=PRIMARY_PRESS,
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = AnimatedButton(
            actions,
            text="停止",
            command=self._stop,
            normal_bg="#fff1f2",
            hover_bg=DANGER_HOVER,
            press_bg=DANGER_PRESS,
            fg=DANGER,
            disabled_bg="#f7f8fb",
        )
        self.stop_button.pack(side=tk.LEFT)

        status = ttk.Frame(content, style="Panel.TFrame")
        status.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        status.columnconfigure(3, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(status, textvariable=self.pid_var, style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 16))
        ttk.Label(status, textvariable=self.exit_var, style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 16))
        ttk.Label(status, textvariable=self.command_var, style="Muted.TLabel").grid(row=0, column=3, sticky="ew")

        self.dataset_panel = ttk.Frame(content, style="Panel.TFrame")
        self.dataset_panel.columnconfigure(0, weight=1)
        self.dataset_panel.rowconfigure(3, weight=1)

        dataset_header = ttk.Frame(self.dataset_panel, style="Panel.TFrame")
        dataset_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(dataset_header, text="数据集", style="Panel.TLabel").pack(side=tk.LEFT)
        AnimatedButton(
            dataset_header,
            text="刷新",
            command=self._refresh_datasets,
            normal_bg=SOFT_BLUE,
            hover_bg="#dbeafe",
            press_bg=SOFT_BLUE_PRESS,
            fg=PRIMARY,
        ).pack(side=tk.RIGHT)

        ttk.Label(self.dataset_panel, textvariable=self.dataset_path_var, style="Panel.TLabel").grid(
            row=1, column=0, sticky="ew", pady=(8, 2)
        )
        ttk.Label(self.dataset_panel, textvariable=self.dataset_meta_var, style="Muted.TLabel").grid(
            row=2, column=0, sticky="ew", pady=(0, 8)
        )
        self.video_list = ttk.Treeview(
            self.dataset_panel,
            columns=("video",),
            show="headings",
            selectmode="browse",
            height=4,
        )
        self.video_list.heading("video", text="视频", anchor="w")
        self.video_list.column("video", width=420, minwidth=180, stretch=True, anchor="w")
        self.video_list.grid(row=3, column=0, sticky="nsew")
        self.video_list.bind("<<TreeviewSelect>>", self._select_video)
        dataset_actions = ttk.Frame(self.dataset_panel, style="Panel.TFrame")
        dataset_actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        AnimatedButton(
            dataset_actions,
            text="打开目录",
            command=self._open_dataset_dir,
            normal_bg=SOFT_BLUE,
            hover_bg="#dbeafe",
            press_bg=SOFT_BLUE_PRESS,
            fg=PRIMARY,
        ).pack(side=tk.LEFT, padx=(0, 8))
        AnimatedButton(
            dataset_actions,
            text="回放视频",
            command=self._play_selected_video,
            normal_bg=PRIMARY,
            hover_bg=PRIMARY_HOVER,
            press_bg=PRIMARY_PRESS,
        ).pack(side=tk.LEFT, padx=(0, 8))
        AnimatedButton(
            dataset_actions,
            text="删除视频",
            command=self._delete_selected_video,
            normal_bg="#fff1f2",
            hover_bg=DANGER_HOVER,
            press_bg=DANGER_PRESS,
            fg=DANGER,
        ).pack(side=tk.LEFT, padx=(0, 8))
        AnimatedButton(
            dataset_actions,
            text="删除数据集",
            command=self._delete_selected_dataset,
            normal_bg="#fff1f2",
            hover_bg=DANGER_HOVER,
            press_bg=DANGER_PRESS,
            fg=DANGER,
        ).pack(side=tk.LEFT)

        log_header = ttk.Frame(content, style="Panel.TFrame")
        log_header.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(log_header, text="日志", style="Panel.TLabel").pack(side=tk.LEFT, pady=(0, 5))

        log_frame = ttk.Frame(content, style="Panel.TFrame")
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            background=LOG_BG,
            foreground=LOG_FG,
            insertbackground=LOG_INSERT,
            wrap="word",
            state="disabled",
            borderwidth=0,
            padx=12,
            pady=10,
            height=6,
            font=LOG_FONT,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _build_logo(self, parent: tk.Misc) -> tk.Canvas:
        logo = tk.Canvas(
            parent,
            height=76,
            background=PANEL_BG,
            borderwidth=0,
            highlightthickness=0,
        )
        if LOGO_IMAGE_PATH.exists():
            image = tk.PhotoImage(file=str(LOGO_IMAGE_PATH))
            target_width = 280
            factor = max(1, image.width() // target_width)
            image = image.subsample(factor, factor)
            logo.image = image  # type: ignore[attr-defined]
            logo.create_image(8, 34, image=image, anchor="w")
        else:
            logo.create_text(8, 32, text="Shentoon RobotStudio", anchor="w", font=(FONT_FAMILY, 20, "bold"), fill="#e60012")
        logo.create_line(8, 66, 152, 66, fill="#e60012", width=3)
        logo.create_line(166, 66, 250, 66, fill="#ff9d7a", width=3)
        return logo

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        readonly: bool = False,
    ) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row, column=column, sticky="w", padx=(0, 8), pady=(0, 4)
        )
        state = "readonly" if readonly else "normal"
        entry = ttk.Entry(parent, textvariable=variable, state=state)
        entry.grid(row=row + 1, column=column, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 4))

    def _bind_events(self) -> None:
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._switch_mode())
        self.search_var.trace_add("write", lambda *_args: self._refresh_items())
        self.group_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_items())
        self.item_list.bind("<<TreeviewSelect>>", self._select_item)

    def _open_environment_setup(self) -> None:
        for window in self.winfo_children():
            if isinstance(window, EnvironmentInstallerWindow):
                window.lift()
                window.focus_force()
                return
        EnvironmentInstallerWindow(self)

    def _open_help(self) -> None:
        for window in self.winfo_children():
            if isinstance(window, HelpWindow):
                window.lift()
                window.focus_force()
                return
        HelpWindow(self)

    def _refresh_datasets(self) -> None:
        self.datasets = scan_datasets()
        if self.mode_var.get() == "数据集":
            self.selected_item = None
            self.selected_var.set("")
            self.selected_video = None
            self.dataset_path_var.set("未选择数据集")
            self.dataset_meta_var.set("")
            self.video_list.delete(*self.video_list.get_children())
            self._refresh_groups()
            self._refresh_items()
        self._append_log("# 数据集列表已刷新。\n")

    def _safe_data_path(self, path: Path) -> Path:
        resolved = path.resolve()
        data_root = DATA_ROOT.resolve()
        if resolved != data_root and data_root not in resolved.parents:
            raise RuntimeError(f"拒绝操作 data 目录外的路径: {resolved}")
        return resolved

    def _open_path(self, path: Path) -> None:
        target = self._safe_data_path(path)
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            elif os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                raise RuntimeError("当前系统没有内置打开方式")
        except Exception as exc:
            messagebox.showerror(APP_DIALOG_TITLE, f"打开失败: {display_text(exc)}")

    def _selected_dataset(self) -> Optional[DatasetInfo]:
        return self.selected_item if isinstance(self.selected_item, DatasetInfo) else None

    def _open_dataset_dir(self) -> None:
        dataset = self._selected_dataset()
        if dataset is None:
            messagebox.showerror(APP_DIALOG_TITLE, "请先选择一个数据集。")
            return
        self._open_path(dataset.abs_path)

    def _play_selected_video(self) -> None:
        dataset = self._selected_dataset()
        if dataset is None:
            messagebox.showerror(APP_DIALOG_TITLE, "请先选择一个数据集。")
            return
        video = self.selected_video or (dataset.videos[0] if dataset.videos else None)
        if video is None:
            messagebox.showerror(APP_DIALOG_TITLE, "该数据集没有可回放的视频。")
            return
        self._open_path(video)

    def _delete_selected_video(self) -> None:
        video = self.selected_video
        if video is None:
            messagebox.showerror(APP_DIALOG_TITLE, "请先选择一个视频。")
            return
        video = self._safe_data_path(video)
        if not messagebox.askyesno(APP_DIALOG_TITLE, f"确认删除视频？\n{display_text(video)}"):
            return
        try:
            video.unlink()
        except OSError as exc:
            messagebox.showerror(APP_DIALOG_TITLE, f"删除视频失败: {display_text(exc)}")
            return
        self._append_log(f"# 已删除视频: {video}\n")
        self._refresh_datasets()

    def _delete_selected_dataset(self) -> None:
        dataset = self._selected_dataset()
        if dataset is None:
            messagebox.showerror(APP_DIALOG_TITLE, "请先选择一个数据集。")
            return
        target = self._safe_data_path(dataset.abs_path)
        if not messagebox.askyesno(APP_DIALOG_TITLE, f"确认删除整个数据集？\n{display_text(target)}"):
            return
        try:
            shutil.rmtree(target)
        except OSError as exc:
            messagebox.showerror(APP_DIALOG_TITLE, f"删除数据集失败: {display_text(exc)}")
            return
        self._append_log(f"# 已删除数据集: {target}\n")
        self._refresh_datasets()

    def _refresh_groups(self) -> None:
        groups = ["全部分组"] + sorted({item.group for item in self._active_items()}, key=group_sort_key)
        self.group_combo.configure(values=groups)
        self.group_var.set(groups[0])

    def _refresh_items(self) -> None:
        query = self.search_var.get().strip().lower()
        group = self.group_var.get()
        active_items = self._active_items()
        self.filtered_items = []
        self.item_list.delete(*self.item_list.get_children())
        for item in active_items:
            target = f"{item.name} {item.path}".lower()
            if group != "全部分组" and item.group != group:
                continue
            if query and query not in target:
                continue
            self.filtered_items.append(item)
            row_id = str(len(self.filtered_items) - 1)
            if isinstance(item, DatasetInfo):
                label = f"{item.name}    视频 {len(item.videos)}    {human_size(item.size_bytes)}"
            else:
                label = item.name
            self.item_list.insert("", tk.END, iid=row_id, values=(label,))
        self.count_label.configure(text=f"{len(self.filtered_items)} / {len(active_items)}")

    def _select_item(self, _event: tk.Event[ttk.Treeview]) -> None:
        selection = self.item_list.selection()
        if not selection:
            return
        self.selected_item = self.filtered_items[int(selection[0])]
        self.selected_var.set(self.selected_item.path)
        if isinstance(self.selected_item, DatasetInfo):
            self._show_dataset_detail(self.selected_item)

    def _show_dataset_detail(self, dataset: DatasetInfo) -> None:
        self.selected_video = None
        self.dataset_path_var.set(dataset.path)
        modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dataset.modified_at))
        self.dataset_meta_var.set(
            f"文件: {dataset.files}    大小: {human_size(dataset.size_bytes)}    视频: {len(dataset.videos)}    修改: {modified}"
        )
        self.video_list.delete(*self.video_list.get_children())
        for index, video in enumerate(dataset.videos):
            try:
                label = f"{video.name}    {human_size(video.stat().st_size)}"
            except OSError:
                label = video.name
            self.video_list.insert("", tk.END, iid=str(index), values=(label,))

    def _select_video(self, _event: tk.Event[ttk.Treeview]) -> None:
        dataset = self._selected_dataset()
        selection = self.video_list.selection()
        if dataset is None or not selection:
            self.selected_video = None
            return
        index = int(selection[0])
        self.selected_video = dataset.videos[index] if index < len(dataset.videos) else None

    def _active_items(self) -> List[LaunchItem]:
        mode = self.mode_var.get()
        if mode == "场景":
            return self.scenes
        if mode == "数据集":
            return self.datasets
        return self.examples

    def _switch_mode(self) -> None:
        self.selected_item = None
        self.selected_var.set("")
        self.selected_video = None
        self.search_var.set("")
        if self.mode_var.get() == "数据集":
            self.dataset_panel.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
            self.start_button.set_enabled(False)
            self.stop_button.set_enabled(False)
            self.dataset_path_var.set("未选择数据集")
            self.dataset_meta_var.set("")
            self.video_list.delete(*self.video_list.get_children())
        else:
            self.dataset_panel.grid_remove()
        self._refresh_groups()
        self._refresh_items()
        self._refresh_status()

    def _start(self) -> None:
        if self.mode_var.get() == "数据集":
            messagebox.showerror(APP_DIALOG_TITLE, "数据集页面不能启动任务，请切换到示例或场景。")
            return
        if self.selected_item is None:
            messagebox.showerror(APP_DIALOG_TITLE, "请先选择一个示例或场景。")
            return
        self.start_button.pulse()
        self._clear_log()
        self.latest_log_id = -1
        common_args: Dict[str, object] = {
            "auto": self.auto_var.get(),
            "use_gs": self.use_gs_var.get(),
            "data_idx": self.data_idx_var.get().strip(),
            "data_set_size": self.data_set_size_var.get().strip(),
        }
        try:
            if isinstance(self.selected_item, SceneInfo):
                self._start_scene(self.selected_item)
            else:
                self._start_example(self.selected_item, common_args)
        except (RuntimeError, ValueError, shlex.SplitError) as exc:
            messagebox.showerror(APP_DIALOG_TITLE, display_text(exc))
        self._refresh_status()
        self._poll_logs()

    def _start_example(self, example: ExampleInfo, common_args: Dict[str, object]) -> None:
        if self._use_internal_worker():
            command = [sys.executable, "--run-example", example.path]
            if common_args.get("auto"):
                command.append("--auto")
            if common_args.get("use_gs"):
                command.append("--use_gs")
            if common_args.get("data_idx") not in (None, ""):
                command.extend(["--data_idx", str(common_args["data_idx"])])
            if common_args.get("data_set_size") not in (None, ""):
                command.extend(["--data_set_size", str(common_args["data_set_size"])])
            command.extend(shlex.split(self.extra_args_text.get().strip()))
            self.manager.start_command(
                example.id,
                command,
                self.env_text.get("1.0", tk.END),
                cwd=REPO_ROOT,
            )
            return

        self.manager.start(
            example,
            self.python_var.get().strip() or sys.executable,
            common_args,
            self.extra_args_text.get().strip(),
            self.env_text.get("1.0", tk.END),
        )

    def _start_scene(self, scene: SceneInfo) -> None:
        if self._use_internal_worker():
            command = [sys.executable, "--run-scene", scene.path]
        else:
            python = self.python_var.get().strip() or sys.executable
            mjcf_path = (MJCF_ROOT / scene.path).resolve()
            command = [python, "-m", "mujoco.viewer", f"--mjcf={mjcf_path}"]
        command.extend(shlex.split(self.extra_args_text.get().strip()))
        self.manager.start_command(
            f"scene:{scene.id}",
            command,
            self.env_text.get("1.0", tk.END),
            cwd=MJCF_ROOT,
        )

    def _use_internal_worker(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    def _stop(self) -> None:
        self.stop_button.pulse()
        self.manager.stop()
        self._refresh_status()
        self._poll_logs()

    def _refresh_status(self, schedule: bool = False) -> None:
        status = self.manager.status()
        running = bool(status["running"])
        finished_now = self.was_running and not running
        self.was_running = running
        self.status_var.set("运行中" if running else "空闲")
        self.pid_var.set(f"进程: {status['pid'] or '-'}")
        returncode = status["returncode"]
        self.exit_var.set(f"退出码: {returncode if returncode is not None else '-'}")
        command = status["command"]
        self.command_var.set(display_text(shlex.join(command)) if command else "")
        self.start_button.set_enabled((not running) and self.mode_var.get() != "数据集")
        self.stop_button.set_enabled(running)
        if finished_now:
            self.datasets = scan_datasets()
            if self.mode_var.get() == "数据集":
                self._refresh_groups()
                self._refresh_items()
        if schedule:
            self.after(1000, lambda: self._refresh_status(schedule=True))

    def _poll_logs(self, schedule: bool = False) -> None:
        data = self.manager.get_logs(self.latest_log_id)
        logs = data["logs"]
        if logs:
            self._append_log("\n".join(item["text"] for item in logs) + "\n")
            self.latest_log_id = data["latest"]
        if schedule:
            self.after(300, lambda: self._poll_logs(schedule=True))

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        at_bottom = self.log_text.yview()[1] >= 0.98
        self.log_text.insert(tk.END, display_text(text))
        if at_bottom:
            self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.manager.status()["running"]:
            if not messagebox.askyesno(APP_DIALOG_TITLE, "仍有任务正在运行，是否停止并退出？"):
                return
            self.manager.stop()
        self.destroy()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"启动 {APP_DIALOG_TITLE} 桌面启动器。")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="用于运行示例的 Python 解释器，默认使用当前解释器",
    )
    parser.add_argument("--run-example", help=argparse.SUPPRESS)
    parser.add_argument("--run-scene", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    args, worker_args = parser.parse_known_args(argv)
    args.worker_args = worker_args
    return args

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    worker_args = args.worker_args
    if worker_args and worker_args[0] == "--":
        worker_args = worker_args[1:]
    if args.run_example:
        return run_example_worker(args.run_example, worker_args)
    if args.run_scene:
        return run_scene_worker(args.run_scene, worker_args)
    if args.self_check:
        return run_self_check()
    app = DesktopExamplesApp(args.python)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
