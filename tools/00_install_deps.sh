#!/usr/bin/env bash
# Mid-360 動作確認に必要な依存パッケージのインストール（sudo 必要 / 実行は1回だけでOK）
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  build-essential cmake git \
  python3-colcon-common-extensions python3-rosdep \
  ros-humble-pcl-conversions ros-humble-pcl-ros \
  ros-humble-rviz2 ros-humble-rosbag2-storage-default-plugins \
  iproute2 iputils-ping net-tools tcpdump ethtool

# rosdep 初期化（既に済んでいればスキップ）
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init
fi
rosdep update || true

echo
echo "[OK] 依存パッケージのインストール完了"
