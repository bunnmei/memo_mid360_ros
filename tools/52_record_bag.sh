#!/usr/bin/env bash
# =============================================================================
#  動作確認の証跡として rosbag2 に記録する
#  usage: ./52_record_bag.sh [記録秒数]
# =============================================================================
set -eo pipefail
source ~/livox_ws/tools/_ros_env.sh

if [ "$LIVOX_WS_SOURCED" != "1" ]; then
  echo "[NG] 先に ~/livox_ws/tools/30_build.sh でビルドしてください"
  exit 1
fi

OUT=~/livox_ws/bags/mid360_$(date +%Y%m%d_%H%M%S)
mkdir -p ~/livox_ws/bags
echo "記録先: $OUT"
timeout "${1:-10}" ros2 bag record -o "$OUT" /livox/lidar /livox/imu || true
ros2 bag info "$OUT"
