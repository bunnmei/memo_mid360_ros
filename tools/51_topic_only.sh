#!/usr/bin/env bash
# =============================================================================
#  判定ノードだけを起動する（ドライバを別端末で動かしている場合）
#  usage: ./51_topic_only.sh [計測秒数]
# =============================================================================
set -eo pipefail
source ~/livox_ws/tools/_ros_env.sh

if [ "$LIVOX_WS_SOURCED" != "1" ]; then
  echo "[NG] 先に ~/livox_ws/tools/30_build.sh でビルドしてください"
  exit 1
fi

exec ros2 run mid360_check check_node --ros-args -p duration:="${1:-10.0}"
