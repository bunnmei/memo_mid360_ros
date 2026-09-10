#!/usr/bin/env bash
# =============================================================================
#  Mid-360 動作確認の本体（ドライバ起動 + 判定ノード）
#
#  usage: ./50_run_check.sh [計測秒数] [rviz]
#    例:  ./50_run_check.sh              10秒計測
#         ./50_run_check.sh 15           15秒計測
#         ./50_run_check.sh 15 rviz      15秒計測 + RViz2 で3D表示
#  止めるときは Ctrl+C
# =============================================================================
set -eo pipefail

DUR="${1:-10.0}"
# ROS のパラメータは型に厳密で、"15" は INTEGER、"15.0" は DOUBLE と解釈される。
# duration は DOUBLE なので、小数点が無ければ付けておく。
case "$DUR" in
  *.*) ;;
  *)   DUR="${DUR}.0" ;;
esac

RVIZ="false"; [ "${2:-}" = "rviz" ] && RVIZ="true"

source ~/livox_ws/tools/_ros_env.sh

if [ "$LIVOX_WS_SOURCED" != "1" ]; then
  echo "[NG] ~/livox_ws/install が見つかりません。先にビルドしてください:"
  echo "     ~/livox_ws/tools/30_build.sh"
  exit 1
fi

# RViz2 は GUI なので、画面(X)が無い環境では起動できない。
# SSH やコンソールログインだと DISPLAY が空になる。
if [ "$RVIZ" = "true" ] && [ -z "${DISPLAY:-}" ]; then
  echo "[警告] DISPLAY が未設定のため RViz2 は起動できません（SSH/コンソール接続と思われます）。"
  echo "       点群の数値チェックはこのまま実行されます。3D で見たい場合は:"
  echo "         - PC のデスクトップ画面上のターミナルから実行する"
  echo "         - ssh -X もしくは ssh -Y で接続し直す"
  echo "         - 記録して手元の PC で再生する: ~/livox_ws/tools/52_record_bag.sh 10"
  echo
  RVIZ="false"
fi

export RCUTILS_COLORIZED_OUTPUT=1
exec ros2 launch mid360_check mid360_check_launch.py \
     duration:="$DUR" rviz:="$RVIZ"
