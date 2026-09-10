#!/usr/bin/env bash
# =============================================================================
#  居残っている Livox 関連プロセスを止める
#
#  ros2 launch を Ctrl+C 以外の方法（timeout や端末を閉じるなど）で終了すると、
#  ドライバの子プロセスだけが生き残って UDP ポート 56000 等を掴み続ける。
#  この状態だと次回起動しても「LiDAR が見つからない」ことになるので、
#  おかしいと思ったらまずこれを実行する。
#
#  注意: pkill -f は自分自身のコマンドラインにもマッチしてしまうため、
#        プロセス名(comm, 15文字に切り詰め)で指定している。
# =============================================================================
set -eo pipefail

found=0
for name in livox_ros_drive livox_lidar_qui; do
  if pgrep -x "$name" >/dev/null 2>&1; then
    echo "停止: $(pgrep -a -x "$name" | head -3)"
    pkill -x "$name" 2>/dev/null || true
    found=1
  fi
done
sleep 1
for name in livox_ros_drive livox_lidar_qui; do
  pkill -9 -x "$name" 2>/dev/null || true
done

if [ "$found" = "0" ]; then
  echo "居残りプロセスはありません"
else
  echo "停止しました"
fi

echo "--- Livox 用ポート(56000-56600)を掴んでいるソケット ---"
python3 - <<'PY'
n = 0
for line in open('/proc/net/udp').read().splitlines()[1:]:
    f = line.split()
    port = int(f[1].split(':')[1], 16)
    if 56000 <= port <= 56600:
        n += 1
        print(f"  port {port} がまだ使用中")
print("  なし（クリーン）" if n == 0 else f"  {n} 件残っています")
PY
