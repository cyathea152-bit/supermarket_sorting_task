#!/usr/bin/env bash
set -e

source /opt/ros/humble/setup.bash

export PYTHONPATH="/workspace/supermarket_sorting_task/examples/supermarket_sorting:/workspace/supermarket_sorting_task/examples/ros2:${PYTHONPATH:-}"

exec "$@"
