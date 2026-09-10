#!/usr/bin/env python3
"""livox_ros_driver2 用の設定ファイル(MID360_config.json)を生成する.

usage:
  python3 20_gen_config.py                      # LiDAR を自動検出して生成
  python3 20_gen_config.py 192.168.1.111        # IP 指定（機種は自動判別）
  python3 20_gen_config.py 192.168.1.111 192.168.1.50
  python3 20_gen_config.py 192.168.1.111 192.168.1.50 Mid360s   # 機種も明示

【重要】JSON のセクション名はデバイス種別そのもの
  Livox SDK2 はセクション名("MID360" / "Mid360s" など)から dev_type を決め、
  LiDAR の探索応答に入っている dev_type と一致しない場合、
  その応答を「ログも出さずに」捨てる。
  結果として ping は通り、ステータス通知も飛んでいるのに点群だけ来ない、
  という原因の分かりにくい症状になる。だからここは自動判別する。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from livox_detect import CFG_SECTION, DEV_TYPES, detect  # noqa: E402

SRC = os.path.expanduser(
    "~/livox_ws/src/livox_ros_driver2/config/MID360_config.json")
INSTALL = os.path.expanduser(
    "~/livox_ws/install/livox_ros_driver2/share/livox_ros_driver2/config/"
    "MID360_config.json")


def build(section, lidar_ip, host_ip):
    """ドライバが読む JSON を組み立てる."""
    return {
        # ドライバ自身が見る値。8 = livox_ros_driver2 内部の kLivoxLidarType で
        # デバイス種別とは別物なので、機種が変わっても 8 のままでよい
        "lidar_summary_info": {"lidar_type": 8},

        # ここのキー名がデバイス種別を決める（MID360 / Mid360s / HAP / Avia2）
        section: {
            # LiDAR 側のポート（機種によらず固定）
            "lidar_net_info": {
                "cmd_data_port": 56100,
                "push_msg_port": 56200,
                "point_data_port": 56300,
                "imu_data_port": 56400,
                "log_data_port": 56500,
            },
            # ホスト(PC)側のポート。LiDAR はここ宛にデータを送ってくる
            "host_net_info": {
                "cmd_data_ip": host_ip,   "cmd_data_port": 56101,
                "push_msg_ip": host_ip,   "push_msg_port": 56201,
                "point_data_ip": host_ip, "point_data_port": 56301,
                "imu_data_ip": host_ip,   "imu_data_port": 56401,
                "log_data_ip": "",        "log_data_port": 56501,
            },
        },

        "lidar_configs": [
            {
                "ip": lidar_ip,
                "pcl_data_type": 1,   # 1 = 直交座標(高精度)
                "pattern_mode": 0,    # 0 = 非繰り返しスキャン
                "extrinsic_parameter": {
                    "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                    "x": 0, "y": 0, "z": 0,
                },
            }
        ],
    }


def main():
    lidar_ip = sys.argv[1] if len(sys.argv) > 1 else None
    host_ip = sys.argv[2] if len(sys.argv) > 2 else "192.168.1.50"
    section = sys.argv[3] if len(sys.argv) > 3 else None

    if section is None:
        print(f"LiDAR を探索中 (ホスト {host_ip}) ...")
        try:
            lidars = detect(host_ip, duration=5.0)
        except RuntimeError as e:
            print(f"[NG] {e}")
            return 1
        if lidar_ip:
            lidars = [d for d in lidars if d["ip"] == lidar_ip] or lidars
        if not lidars:
            print("[NG] LiDAR が応答しません。")
            print("     sudo ~/livox_ws/tools/01_setup_net.sh を実行済みか、")
            print("     12V 電源が入っているかを確認してください。")
            return 1
        d = lidars[0]
        lidar_ip = d["ip"]
        section = d["section"]
        print(f"  検出: {d['model']} (dev_type={d['dev_type']}) "
              f"IP={d['ip']} SN={d['sn']}")
        if section is None:
            print(f"[NG] dev_type={d['dev_type']} に対応する設定セクション名が不明です。")
            return 1

    cfg = build(section, lidar_ip, host_ip)

    written = []
    for dest in (SRC, INSTALL):
        d = os.path.dirname(dest)
        if dest is INSTALL and not os.path.isdir(d):
            continue          # まだビルドしていない場合は install 側を飛ばす
        os.makedirs(d, exist_ok=True)
        with open(dest, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        written.append(dest)

    print(f"[OK] セクション名 \"{section}\" / LiDAR {lidar_ip} / ホスト {host_ip}")
    for w in written:
        print(f"     生成: {w}")
    if len(written) > 1:
        print("     ※ install 側にも直接書いたので再ビルド不要です")
    return 0


if __name__ == "__main__":
    sys.exit(main())
