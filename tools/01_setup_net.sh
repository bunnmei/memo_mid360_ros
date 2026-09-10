#!/usr/bin/env bash
# Mid-360 用のホストネットワーク設定（sudo 必要 / PC再起動のたびに実行）
#
# 状況:
#   enp1s0          = 家庭内LAN 192.168.1.210/24 (インターネット / デフォルトGW)
#   enxc817f56005xx = USB LAN アダプタ。ここに Mid-360 が直結されている
#
# Mid-360 のデフォルトIPは 192.168.1.1XX/24 で enp1s0 と同一サブネットのため、
# 普通に /24 を振ると経路が衝突する。そこで
#   * USB NIC には noprefixroute でIPだけ付与（/24経路を作らない）
#   * LiDAR 宛の /32 ホスト経路だけを USB NIC に向ける
#   * ARP flux 防止のため arp_ignore/arp_announce を設定
# とすることで、インターネット(enp1s0)を維持したまま LiDAR と通信できる。
set -euo pipefail

IFACE="${IFACE:-enxc817f5600593}"   # USB LAN アダプタ
HOST_IP="${HOST_IP:-192.168.1.50}"  # Livox 標準のホストIP
LIDAR_IP="${1:-}"                   # 例: ./01_setup_net.sh 192.168.1.180

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "[NG] インタフェース $IFACE が見つかりません。'ip -br addr' で名前を確認して IFACE=... を指定してください。"
  exit 1
fi

echo "== $IFACE を UP =="
sudo ip link set "$IFACE" up
sleep 2

# リンク（ケーブル/結線）確認
if command -v ethtool >/dev/null; then
  LINK=$(sudo ethtool "$IFACE" | awk -F': ' '/Link detected/{print $2}')
  SPEED=$(sudo ethtool "$IFACE" | awk -F': ' '/Speed/{print $2}')
  echo "   Link detected: ${LINK:-unknown}   Speed: ${SPEED:-unknown}"
  if [ "${LINK:-no}" != "yes" ]; then
    echo
    echo "[NG] リンクが上がっていません。以下を確認してください:"
    echo "     - Mid-360 の 12V 電源が入っているか (通電すると内部モータの回転音がする)"
    echo "     - M12 <-> RJ45 の結線: M12ピン 1,2,3,6 -> RJ45ピン 1,2,3,6 (1-2で1ペア, 3-6で1ペア)"
    echo "     - USB ハブ / LAN アダプタが給電不足になっていないか"
    exit 1
  fi
fi

echo "== ARP flux 対策 =="
sudo sysctl -qw "net.ipv4.conf.${IFACE}.arp_ignore=1"
sudo sysctl -qw "net.ipv4.conf.${IFACE}.arp_announce=2"
sudo sysctl -qw "net.ipv4.conf.${IFACE}.rp_filter=2"
sudo sysctl -qw net.ipv4.conf.all.rp_filter=2

echo "== $IFACE に $HOST_IP を付与 (noprefixroute) =="
sudo ip addr flush dev "$IFACE"
# brd + を必ず付ける:
#   ip addr add は ifconfig と違い、明示しないとブロードキャストアドレスを
#   設定しない。Livox の探索・ステータス通知はブロードキャストで飛ぶため、
#   これが無いと取りこぼす原因になる。
sudo ip addr add "${HOST_IP}/24" brd + dev "$IFACE" noprefixroute

if [ -n "$LIDAR_IP" ]; then
  echo "== LiDAR ${LIDAR_IP} への /32 経路を $IFACE に向ける =="
  sudo ip route replace "${LIDAR_IP}/32" dev "$IFACE" src "$HOST_IP"
else
  echo "== LiDAR IP 未指定: 経路は追加しません（家庭内LANの通信を壊さないため）=="
  echo "   次に  python3 ~/livox_ws/tools/10_find_lidar.py  で LiDAR の IP を特定し、"
  echo "   その IP を引数にして本スクリプトを再実行してください:"
  echo "     sudo ~/livox_ws/tools/01_setup_net.sh 192.168.1.1XX"
fi

echo
echo "== 結果 =="
ip -br addr show "$IFACE"
ip route | grep -E "$IFACE" | head -5
echo "  ... (default route は enp1s0 のまま維持されています)"
ip route | grep '^default'
echo
echo "[OK] ホスト側ネットワーク設定完了"
