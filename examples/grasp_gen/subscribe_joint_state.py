# subscribe_joint_state.py
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import zenoh

import generated.gripper_2f_pb2 as gripper_pb


@dataclass
class JointState:
    q: np.ndarray  # (dof,)
    v: np.ndarray  # (dof,)


def decode_robot_state_joint(payload: bytes) -> JointState:
    """
    Decode payload from topic 'robot/state/joint'.

    Encoding (confirmed in exec_robot_comp.py):
      payload = np.concatenate([q, v]).astype(np.float32).tobytes()
    so payload is raw float32 vector of length 2*dof.
    """
    vec = np.frombuffer(payload, dtype=np.float32)
    if vec.size % 2 != 0:
        raise ValueError(f"Invalid payload float32 count={vec.size}, must be even.")
    dof = vec.size // 2
    q = vec[:dof].copy()
    v = vec[dof:].copy()
    return JointState(q=q, v=v)


class ArmGripperSubscriber:
    """
    Subscribe:
      - robot/state/joint              -> arm q[:6]
      - gripper/sim_two_finger/state   -> Gripper2FState.position (protobuf) -> gripper width

    Output action:
      action: (sim_nj,) usually (7,) = [arm6, gripper]
    """

    def __init__(
        self,
        arm_topic: str = "robot/state/joint",
        gripper_topic: str = "gripper/sim_two_finger/state",
        sim_nj: int = 7,
        gripper_ctrl_min: float = 0.0,
        gripper_ctrl_max: float = 0.04,
        invert_gripper: bool = False,  # 如果发现开合方向反了，改 True
    ):
        self.arm_topic = arm_topic
        self.gripper_topic = gripper_topic
        self.sim_nj = int(sim_nj)
        self.grip_min = float(gripper_ctrl_min)
        self.grip_max = float(gripper_ctrl_max)
        self.invert_gripper = bool(invert_gripper)

        self._lock = threading.Lock()
        self._latest_arm: Optional[JointState] = None
        self._latest_grip: float = 0.0  # width in [0,0.04]

        # eclipse-zenoh python binding：必须用 zenoh.Config()
        self._session = zenoh.open(zenoh.Config())
        self._sub_arm = self._session.declare_subscriber(self.arm_topic, self._on_arm)
        self._sub_grip = self._session.declare_subscriber(self.gripper_topic, self._on_gripper)

    def _on_arm(self, sample):
        """覆盖式更新：复用 _latest_arm 缓冲区，每次覆盖上次消息，不累积"""
        try:
            payload = bytes(sample.payload)
            vec = np.frombuffer(payload, dtype=np.float32)
            if vec.size % 2 != 0:
                return
            dof = vec.size // 2
            with self._lock:
                if self._latest_arm is None:
                    self._latest_arm = JointState(
                        q=vec[:dof].copy(), v=vec[dof:].copy()
                    )
                elif self._latest_arm.q.shape[0] == dof:
                    self._latest_arm.q[:] = vec[:dof]
                    self._latest_arm.v[:] = vec[dof:]
                else:
                    self._latest_arm = JointState(
                        q=vec[:dof].copy(), v=vec[dof:].copy()
                    )
        except Exception as e:
            print(f"[ArmGripperSubscriber] arm decode error: {e}")

    def _on_gripper(self, sample):
        try:
            payload = bytes(sample.payload)
            msg = gripper_pb.Gripper2FState()
            msg.ParseFromString(payload)

            # hal 里写的是 state.position = self._gripper._current_pos
            # 这里先按“position 就是宽度”处理：裁剪到 [0,0.04]
            width = float(msg.position)
            width = float(np.clip(width, self.grip_min, self.grip_max))

            if self.invert_gripper:
                width = self.grip_max - width

            with self._lock:
                self._latest_grip = width
        except Exception as e:
            print(f"[ArmGripperSubscriber] gripper decode error: {e}")

    def get_latest_action(self) -> Optional[np.ndarray]:
        """
        Return latest action (sim_nj,):
          - action[:6] from arm q[:6]
          - action[6] from gripper width
        """
        with self._lock:
            if self._latest_arm is None:
                return None

            q = self._latest_arm.q
            action = np.zeros((self.sim_nj,), dtype=np.float32)

            # arm
            arm_n = min(6, self.sim_nj, int(q.shape[0]))
            action[:arm_n] = q[:arm_n].astype(np.float32)

            # gripper
            if self.sim_nj >= 7:
                action[6] = np.float32(self._latest_grip)

            return action

    def get_latest_raw_arm(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        with self._lock:
            if self._latest_arm is None:
                return None
            return self._latest_arm.q.copy(), self._latest_arm.v.copy()

    def get_latest_gripper_width(self) -> float:
        with self._lock:
            return float(self._latest_grip)

    def close(self):
        try:
            self._sub_arm.undeclare()
        except Exception:
            pass
        try:
            self._sub_grip.undeclare()
        except Exception:
            pass
        try:
            self._session.close()
        except Exception:
            pass