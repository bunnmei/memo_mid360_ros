# =============================================================================
#  ROS 2 環境を安全に読み込むための共通処理（各スクリプトから source される）
# =============================================================================
#  ROS の setup.bash は内部で未定義変数を参照するため、`set -u` が有効なままだと
#    /opt/ros/humble/setup.bash: line 8: AMENT_TRACE_SETUP_FILES: unbound variable
#  というエラーで止まる。読み込みの間だけ `set +u` にして回避する。
# =============================================================================

ros_source() {
  local f="$1"
  set +u
  # shellcheck disable=SC1090
  source "$f"
  set -u
}

# ROS 本体
ros_source /opt/ros/humble/setup.bash

# 自作ワークスペース（ビルド前は存在しないので、あるときだけ読む）
if [ -f "$HOME/livox_ws/install/setup.bash" ]; then
  ros_source "$HOME/livox_ws/install/setup.bash"
  LIVOX_WS_SOURCED=1
else
  LIVOX_WS_SOURCED=0
fi
