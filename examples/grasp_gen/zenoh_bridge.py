"""
discoverse_zenoh_bridge.py

Discoverse/MuJoCo -> Zenoh bridge:
  - env/{camera_id}/rgb   : ImageData(jpeg)
  - env/{camera_id}/depth : ImageData(zstd-depth32 float32 meters)
  - env/{camera_id}/pcl   : raw bytes float32 (N,4) [x,y,z,packed_rgb_bits_as_float]
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

import cv2
import zstandard as zstd

import zenoh

from google.protobuf.timestamp_pb2 import Timestamp
from generated.image_pb2 import ImageData

import torch


# =========================
# Proto helpers
# =========================
def now_ts() -> Timestamp:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


def pack_image(
    fmt: str,
    data_bytes: bytes,
    width: int = 0,
    height: int = 0,
    channels: int = 0,
) -> bytes:
    return ImageData(
        format=fmt,
        data=data_bytes,
        width=width,
        height=height,
        channels=channels,
        timestamp=now_ts(),
    ).SerializeToString()


# =========================
# MuJoCo camera helpers
# =========================
def mj_intrinsics_from_fovy(
    sim,
    cam_id: int,
    height: int,
    width: int,
    principal_at_pixel_center: bool = True,
) -> Tuple[float, float, float, float]:
    """
    Approximate pinhole intrinsics from MuJoCo camera fovy.

    Returns fx, fy, cx, cy in pixel units.

    principal_at_pixel_center:
      - True : cx = W/2, cy = H/2 (pixel-center convention, pairs with u+0.5,v+0.5)
      - False: cx = (W-1)/2, cy = (H-1)/2 (pixel-index convention)
    """
    fovy_deg = float(sim.mj_model.cam_fovy[cam_id])
    fovy = np.deg2rad(fovy_deg)

    fy = 0.5 * float(height) / np.tan(fovy / 2.0)
    fx = fy * (float(width) / float(height))

    if principal_at_pixel_center:
        cx = float(width) * 0.5
        cy = float(height) * 0.5
    else:
        cx = (float(width) - 1.0) * 0.5
        cy = (float(height) - 1.0) * 0.5

    return fx, fy, cx, cy


def mj_world_from_cam(sim, cam_id: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    world_from_cam pose from MuJoCo runtime buffers.
    Returns:
      R_w_c: (3,3)
      t_w_c: (3,)
    """
    t_w_c = sim.mj_data.cam_xpos[cam_id].copy()
    R_w_c = sim.mj_data.cam_xmat[cam_id].copy().reshape(3, 3)  # row-major
    return R_w_c, t_w_c


# =========================
# Zenoh publisher
# =========================
@dataclass
class ZenohPubConfig:
    camera_id: str
    shm_mb: int = 256
    jpeg_quality: int = 85
    zstd_level: int = 1


class ZenohPub:
    def __init__(self, cfg: ZenohPubConfig):
        self.cfg = cfg
        self.session = zenoh.open(zenoh.Config())

        base = f"env/{cfg.camera_id}"
        self.pub_rgb = self.session.declare_publisher(
            f"{base}/rgb", congestion_control=zenoh.CongestionControl.DROP
        )
        self.pub_depth = self.session.declare_publisher(
            f"{base}/depth", congestion_control=zenoh.CongestionControl.DROP
        )
        self.pub_pcl = self.session.declare_publisher(
            f"{base}/pcl", congestion_control=zenoh.CongestionControl.DROP
        )

        self.cctx = zstd.ZstdCompressor(level=cfg.zstd_level)

    def _put(self, pub: zenoh.Publisher, payload: bytes) -> None:
        """直接 put bytes，不使用 SHM，避免 alloc 累积导致内存溢出"""
        pub.put(payload)

    def publish_rgb(self, rgb: np.ndarray) -> None:
        if rgb is None:
            return
        bgr = rgb[..., ::-1]
        ok, encoded = cv2.imencode(
            ".jpg",
            bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self.cfg.jpeg_quality)],
        )
        if not ok:
            return
        payload = pack_image("jpeg", encoded.tobytes())
        self._put(self.pub_rgb, payload)

    def publish_depth(self, depth_m: np.ndarray) -> None:
        if depth_m is None:
            return
        depth32 = depth_m.astype(np.float32, copy=False)
        compressed = self.cctx.compress(depth32.tobytes())
        payload = pack_image(
            "zstd-depth32",
            compressed,
            width=int(depth32.shape[1]),
            height=int(depth32.shape[0]),
            channels=1,
        )
        self._put(self.pub_depth, payload)

    def publish_pcl(self, pcl_bytes: bytes) -> None:
        if not pcl_bytes:
            return
        self._put(self.pub_pcl, pcl_bytes)


# =========================
# GPU RGBD -> PCL
# =========================
class GpuPclProjector:
    """
    GPU projector (torch only):
      - Build per-pixel rays from intrinsics
      - depth_is_range=False : depth is Z depth in camera frame (ray.z == 1)
      - depth_is_range=True  : depth is range along the ray (normalize(ray) * depth)
      - Convert OpenCV camera axis -> MuJoCo/OpenGL axis if needed
      - cam -> world by MuJoCo cam_xmat / cam_xpos
      - Optional world_translation (only translation, no rotation)
    """

    def __init__(
        self,
        stride: int = 1,
        max_depth: float = 4.0,
        device: str = "cuda",
        flip_y: bool = False,
        opencv_to_mujoco: bool = True,
        depth_is_range: bool = False,  # 你已验证 False 正确
        principal_at_pixel_center: bool = True,  # ✅默认用像素中心约定
        world_translation: Tuple[float, float, float] = (0.0, 0.0, 0.0),  # ✅只加平移微调入口
        debug: bool = False,
    ):
        self.stride = int(stride)
        self.max_depth = float(max_depth)
        self.device = torch.device(device)

        self.flip_y = bool(flip_y)
        self.opencv_to_mujoco = bool(opencv_to_mujoco)
        self.depth_is_range = bool(depth_is_range)
        self.principal_at_pixel_center = bool(principal_at_pixel_center)

        self.world_translation = np.array(world_translation, dtype=np.float32).reshape(3)
        self.debug = bool(debug)

        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")

        # OpenCV: x right, y down, z forward
        # MuJoCo/OpenGL cam: x right, y up, z backward (looks along -z)
        self._A_cv_to_mj = np.diag([1.0, -1.0, -1.0]).astype(np.float32)

    def _prep(self, rgb: np.ndarray, depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.flip_y:
            rgb = np.ascontiguousarray(np.flipud(rgb))
            depth = np.ascontiguousarray(np.flipud(depth))
        else:
            rgb = np.ascontiguousarray(rgb)
            depth = np.ascontiguousarray(depth)
        depth = depth.astype(np.float32, copy=False)
        return rgb, depth

    @torch.no_grad()
    def rgbd_to_pcl_numpy(self, sim, cam_id: int, rgb: np.ndarray, depth: np.ndarray) -> np.ndarray:
        if rgb is None or depth is None:
            return np.zeros((0, 4), dtype=np.float32)

        rgb, depth = self._prep(rgb, depth)

        s = self.stride
        depth_s = np.ascontiguousarray(depth[::s, ::s], dtype=np.float32)
        rgb_s = np.ascontiguousarray(rgb[::s, ::s, :], dtype=np.uint8)

        Hs, Ws = depth_s.shape
        H, W = depth.shape

        # ✅ 关键：内参使用原始分辨率，不要简单除 s
        fx, fy, cx, cy = mj_intrinsics_from_fovy(
            sim, cam_id, H, W, principal_at_pixel_center=self.principal_at_pixel_center
        )

        R_w_c, t_w_c = mj_world_from_cam(sim, cam_id)

        if self.debug:
            print("[PCL] depth min/max:", float(depth_s.min()), float(depth_s.max()))
            print("[PCL] fx,fy,cx,cy:", fx, fy, cx, cy)
            print("[PCL] stride:", s, "depth_is_range:", self.depth_is_range)
            print("[PCL] principal_at_pixel_center:", self.principal_at_pixel_center)
            print("[PCL] world_translation:", self.world_translation.tolist())

        depth_t = torch.from_numpy(depth_s).to(self.device)  # (Hs,Ws)
        rgb_t = torch.from_numpy(rgb_s).to(self.device)      # (Hs,Ws,3)

        valid = torch.isfinite(depth_t) & (depth_t > 1e-6) & (depth_t < self.max_depth)
        if not bool(valid.any()):
            return np.zeros((0, 4), dtype=np.float32)

        # (u_s, v_s) in downsample grid
        v_s, u_s = torch.meshgrid(
            torch.arange(Hs, device=self.device, dtype=torch.float32),
            torch.arange(Ws, device=self.device, dtype=torch.float32),
            indexing="ij",
        )

        # ✅ 映射回原图像素坐标，并使用像素中心 u+0.5, v+0.5
        # 对 stride=1 也同样正确
        u_full = u_s * float(s) + 0.5
        v_full = v_s * float(s) + 0.5

        x = (u_full - float(cx)) / float(fx)
        y = (v_full - float(cy)) / float(fy)
        z = torch.ones_like(x)

        ray = torch.stack([x, y, z], dim=-1)  # (Hs,Ws,3)

        if self.depth_is_range:
            ray = ray / torch.clamp(torch.linalg.norm(ray, dim=-1, keepdim=True), min=1e-8)

        d = depth_t[..., None]
        pts_cv = ray * d  # (Hs,Ws,3) in OpenCV cam coords
        pts_cv = pts_cv[valid]
        cols = rgb_t[valid].to(torch.int32)

        if self.opencv_to_mujoco:
            A = torch.from_numpy(self._A_cv_to_mj).to(self.device)
            pts_c = pts_cv @ A.T
        else:
            pts_c = pts_cv

        R = torch.from_numpy(R_w_c.astype(np.float32)).to(self.device)
        t = torch.from_numpy(t_w_c.astype(np.float32)).to(self.device)

        pts_w = (pts_c @ R.T) + t[None, :]

        # ✅ 仅平移微调入口（world frame）
        if float(np.linalg.norm(self.world_translation)) > 0.0:
            tw = torch.from_numpy(self.world_translation).to(self.device)
            pts_w = pts_w + tw[None, :]

        rgb32 = (cols[:, 0] << 16) | (cols[:, 1] << 8) | cols[:, 2]
        rgbf = rgb32.view(torch.float32)

        out = torch.cat([pts_w, rgbf[:, None]], dim=1).contiguous()
        return out.cpu().numpy()

    @torch.no_grad()
    def rgbd_to_pcl_bytes(self, sim, cam_id: int, rgb: np.ndarray, depth: np.ndarray) -> bytes:
        arr = self.rgbd_to_pcl_numpy(sim, cam_id, rgb, depth)
        return arr.tobytes() if arr.size else b""


# =========================
# PCL save to PLY (debug)
# =========================
DEBUG_PCL_DIR = "debug_pcl"
_pcl_save_counter = 0


def save_pcl_bytes_to_ply(pcl_bytes: bytes, ply_path: str) -> None:
    """Write raw float32 (N,4) [x,y,z,packed_rgb] to .ply file."""
    if not pcl_bytes or len(pcl_bytes) % 16 != 0:
        return
    n = len(pcl_bytes) // 16
    pcl_np = np.frombuffer(pcl_bytes, dtype=np.float32).reshape(n, 4)
    col4 = np.ascontiguousarray(pcl_np[:, 3].astype(np.float32))
    rgb32 = np.frombuffer(col4.tobytes(), dtype=np.uint32)
    r, g, b = (rgb32 >> 16) & 0xFF, (rgb32 >> 8) & 0xFF, rgb32 & 0xFF
    with open(ply_path, "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex %d\n" % n)
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for i in range(n):
            f.write("%.6f %.6f %.6f %d %d %d\n" % (pcl_np[i, 0], pcl_np[i, 1], pcl_np[i, 2], r[i], g[i], b[i]))


# =========================
# Convenience functions
# =========================
def publish_rgb_depth(
    pubs: ZenohPub,
    rgb: Optional[np.ndarray],
    depth: Optional[np.ndarray],
) -> None:
    if rgb is not None:
        pubs.publish_rgb(rgb)
    if depth is not None:
        pubs.publish_depth(depth)


def publish_pcl(
    pubs: ZenohPub,
    projector: GpuPclProjector,
    sim,
    cam_id: int,
    rgb: Optional[np.ndarray],
    depth: Optional[np.ndarray],
    save_to_disk: bool = False,
) -> None:
    if rgb is None or depth is None:
        return
    pcl_bytes = projector.rgbd_to_pcl_bytes(sim, cam_id, rgb, depth)
    if not pcl_bytes:
        return
    pubs.publish_pcl(pcl_bytes)
    if save_to_disk:
        global _pcl_save_counter
        os.makedirs(DEBUG_PCL_DIR, exist_ok=True)
        ply_path = os.path.join(DEBUG_PCL_DIR, f"pcl_{_pcl_save_counter:06d}.ply")
        save_pcl_bytes_to_ply(pcl_bytes, ply_path)
        _pcl_save_counter += 1