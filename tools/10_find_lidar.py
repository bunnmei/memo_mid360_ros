#!/usr/bin/env python3
"""LiDAR を探して IP と「機種」を特定する（ROS 不要）.

Livox SDK2 と同じ探索プロトコルで問い合わせるので、
IP だけでなく dev_type（機種）とシリアル番号まで分かる。

機種の特定が重要な理由:
  SDK は設定 JSON のセクション名から dev_type を決め、LiDAR の応答の
  dev_type と一致しない応答を「ログも出さずに」捨てる。
  そのため機種を取り違えると
    「ping は通る・ステータス通知も届く・なのに点群だけ来ない」
  という原因の分かりにくい症状になる。

usage:
  python3 10_find_lidar.py [HOST_IP]     # 既定 192.168.1.50
"""
import os
import re
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from livox_detect import detect  # noqa: E402

SUBNET = os.environ.get("LIDAR_SUBNET", "192.168.1")
LIDAR_IFACE = os.environ.get("LIDAR_IFACE", "enxc817f5600593")
HOST_RANGE = range(100, 200)


def ping_sweep(iface=None):
    """保険のための ping スイープ（探索に応答しない場合の生存確認用）."""
    results = []

    def ping(ip):
        cmd = ["ping", "-c", "1", "-W", "1", "-n"]
        if iface:
            cmd += ["-I", iface]
        cmd.append(ip)
        if subprocess.run(cmd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            results.append(ip)

    ts = [threading.Thread(target=ping, args=(f"{SUBNET}.{n}",), daemon=True)
          for n in HOST_RANGE]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return results


def main():
    host_ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.50"
    print("=" * 68)
    print(" Livox LiDAR 探索")
    print("=" * 68)
    print(f"[1/2] SDK と同じ探索コマンドを {SUBNET}.255 帯にブロードキャスト "
          f"(ホスト {host_ip}) ...")

    try:
        lidars = detect(host_ip, duration=5.0)
    except RuntimeError as e:
        print(f"  [NG] {e}")
        lidars = []

    if lidars:
        print()
        for d in lidars:
            print(f"  [検出] {d['ip']}")
            print(f"         機種        : {d['model']}  (dev_type={d['dev_type']})")
            print(f"         シリアル番号: {d['sn']}")
            print(f"         cmd_port    : {d['cmd_port']}")
            print(f"         JSON セクション名: \"{d['section']}\"")
        print()
        print("=" * 68)
        d = lidars[0]
        print("[OK] 次のステップ:")
        print(f"  sudo ~/livox_ws/tools/01_setup_net.sh {d['ip']}")
        print(f"  python3 ~/livox_ws/tools/20_gen_config.py {d['ip']} {host_ip}")
        print("  ~/livox_ws/tools/50_run_check.sh 15")
        return 0

    # 探索に応答が無い場合、そもそも通信できているのかを ping で切り分ける
    print("  応答なし")
    print()
    print(f"[2/2] {LIDAR_IFACE} 経由で ping スイープ (生存確認) ...")
    alive = ping_sweep(LIDAR_IFACE)
    neigh = subprocess.run(["ip", "neigh"], capture_output=True, text=True).stdout
    for ip in sorted(alive, key=lambda x: int(x.split(".")[-1])):
        m = re.search(rf"^{re.escape(ip)}\s+dev\s+(\S+).*?lladdr\s+(\S+)", neigh, re.M)
        dev, mac = (m.group(1), m.group(2)) if m else ("?", "?")
        print(f"  [応答] {ip}  dev={dev}  mac={mac}")
    if not alive:
        print("  応答なし")

    print()
    print("=" * 68)
    if alive:
        print("[△] ping は通るが探索に応答しません。考えられる原因:")
        print("    - livox のドライバやサンプルが起動中でポート 56000 を専有している")
        print("      -> pkill livox_ros_drive ; pkill livox_lidar_qui")
        print(f"    - ホストIP が {host_ip} になっていない (ip -br addr で確認)")
    else:
        print("[NG] LiDAR が見つかりませんでした。確認してください:")
        print("  - 12V 電源が入っているか（起動すると内部モータの回転音がする）")
        print("  - sudo ~/livox_ws/tools/01_setup_net.sh を実行済みか")
        print("  - USB LAN アダプタが Link detected: yes になっているか")
        print("  - M12 ピン 1,2,3,6 の結線（1-2 / 3-6 でツイストペアを組むこと）")
        print("  - 別サブネットに変更済みの機体なら LIDAR_SUBNET=192.168.x を指定")
    return 1


if __name__ == "__main__":
    sys.exit(main())
