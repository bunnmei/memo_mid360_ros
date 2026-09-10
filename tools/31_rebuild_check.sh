#!/usr/bin/env bash
# =============================================================================
#  mid360_check パッケージだけを素早く再ビルドする
#
#  check_node.py や launch ファイルを編集したときはこれを実行する。
#  30_build.sh は Livox 純正の build.sh を呼ぶ都合で install/ を全消しして
#  フルビルド（10分前後）になるため、自作パッケージの修正にはこちらを使う。
# =============================================================================
set -eo pipefail
source ~/livox_ws/tools/_ros_env.sh
cd ~/livox_ws
colcon build --packages-select mid360_check
echo
echo "[OK] 再ビルド完了。新しい端末を開くか、下記を実行して反映してください:"
echo "     source ~/livox_ws/install/setup.bash"
