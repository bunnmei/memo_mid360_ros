#!/usr/bin/env bash
# =============================================================================
#  Livox-SDK2 + livox_ros_driver2 の取得とビルド
#
#  usage: ~/livox_ws/tools/30_build.sh
#         FORCE_SDK=1 ~/livox_ws/tools/30_build.sh   # SDK2 も強制再ビルド
#
#  SDK2 が既に /usr/local にインストール済みならスキップするので、
#  2回目以降は sudo なしで実行できます。
# =============================================================================
set -eo pipefail

WS=~/livox_ws
SDK_DIR=$WS/Livox-SDK2
DRV_DIR=$WS/src/livox_ros_driver2

# ROS 環境を読み込む（set -u 対策込み）
source ~/livox_ws/tools/_ros_env.sh

# ---------------------------------------------------------------------------
#  1. Livox-SDK2（LiDAR と UDP で通信する C++ ライブラリ）
# ---------------------------------------------------------------------------
if [ -f /usr/local/lib/liblivox_lidar_sdk_shared.so ] && [ "${FORCE_SDK:-0}" != "1" ]; then
  echo "== Livox-SDK2 はインストール済みのためスキップ =="
  echo "   (再ビルドしたい場合は FORCE_SDK=1 を付けて実行)"
else
  if [ ! -d "$SDK_DIR/.git" ]; then
    echo "== Livox-SDK2 を clone =="
    rm -rf "$SDK_DIR"
    git clone https://github.com/Livox-SDK/Livox-SDK2.git "$SDK_DIR"
  fi
  echo "== Livox-SDK2 をビルド / インストール（sudo のパスワードを聞かれます）=="
  mkdir -p "$SDK_DIR/build"
  cd "$SDK_DIR/build"
  cmake .. -DCMAKE_BUILD_TYPE=Release
  make -j"$(nproc)"
  sudo make install
  sudo ldconfig
fi

# ---------------------------------------------------------------------------
#  2. livox_ros_driver2（SDK2 を使って ROS トピックに流すドライバ）
# ---------------------------------------------------------------------------
# 注意: ディレクトリの有無ではなく build.sh の有無で判定する。
#       20_gen_config.py が先に config/ を作っている場合があり、
#       ディレクトリ判定だと clone がスキップされてしまうため。
if [ ! -f "$DRV_DIR/build.sh" ]; then
  echo "== livox_ros_driver2 を clone =="
  TMP=$(mktemp -d)
  git clone https://github.com/Livox-SDK/livox_ros_driver2.git "$TMP/livox_ros_driver2"
  mkdir -p "$DRV_DIR"
  # -n (no-clobber) なので、20_gen_config.py が生成済みの
  # MID360_config.json があればそれを上書きせずに残す
  cp -a -n "$TMP/livox_ros_driver2/." "$DRV_DIR/"
  rm -rf "$TMP"
  chmod +x "$DRV_DIR/build.sh"
  echo "   -> clone 完了"
fi

# 生成済み設定ファイルの中身を確認して表示（IP が正しいか目視できるように）
CFG="$DRV_DIR/config/MID360_config.json"
if [ -f "$CFG" ]; then
  echo "== 使用する設定: $CFG =="
  grep -E '"ip"|"cmd_data_ip"' "$CFG" | sed 's/^/   /'
fi

# ---------------------------------------------------------------------------
#  3. colcon build（ROS 2 のワークスペースをビルド）
# ---------------------------------------------------------------------------
if ! command -v colcon >/dev/null 2>&1; then
  echo
  echo "[NG] colcon が見つかりません。ROS 2 のワークスペースをビルドするツールです。"
  echo "     先に依存パッケージを入れてください（sudo のパスワードを聞かれます）:"
  echo "       ~/livox_ws/tools/00_install_deps.sh"
  echo "     その後もう一度 30_build.sh を実行してください。"
  exit 1
fi

echo "== ワークスペースをビルド =="
# 注意: livox_ros_driver2 付属の build.sh は先頭で
#       build/ devel/ install/ を rm -rf するため、毎回フルビルドになります
cd "$DRV_DIR"
# 付属の build.sh が package_ROS2.xml -> package.xml のコピーと
# colcon build（ワークスペース全体）をやってくれる
./build.sh humble

echo
echo "[OK] ビルド完了"
echo "     次: ~/livox_ws/tools/50_run_check.sh 15 rviz"
