#!/usr/bin/env python3
"""Livox LiDAR の探索と機種判別（Livox SDK2 の探索プロトコルの最小実装）.

なぜ必要か:
  Livox SDK2 は設定ファイルのセクション名（"MID360" / "Mid360s" など）から
  デバイス種別(dev_type)を決め、LiDAR の応答の dev_type と一致しない場合は
  「何のログも出さずに」その応答を捨てる。
  そのため機種を間違えると「ping は通るのに点群が来ない」という
  極めて分かりにくい症状になる。ここで実機の dev_type を先に確定させる。

単体実行:
  python3 livox_detect.py [HOST_IP]      # 既定 192.168.1.50
"""
import select
import socket
import struct
import sys
import time

DETECTION_PORT = 56000

# livox_lidar_def.h の LivoxLidarDeviceType
DEV_TYPES = {
    0: "Hub", 1: "Mid-40", 2: "Tele", 3: "Horizon", 6: "Mid-70",
    7: "Avia", 9: "Mid-360", 10: "Industrial HAP", 15: "PA",
    35: "Mid-360S", 38: "Avia2",
}

# dev_type -> 設定ファイル(JSON)のセクション名
# Livox-SDK2/sdk_core/parse_cfg_file.cpp の dev_type_map と一致させること
CFG_SECTION = {
    9: "MID360",
    35: "Mid360s",
    10: "HAP",
    38: "Avia2",
}


def crc16_ccitt(data: bytes, seed: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE。SDK は制御フレームの先頭18バイトに対して使う."""
    crc = seed
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_search(seq: int) -> bytes:
    """探索コマンド(cmd_id=0x0000)のフレームを組み立てる(24バイト).

      0    : sof 0xAA
      1    : version 0x00
      2-3  : length = 24
      4-7  : seq_num
      8-9  : cmd_id = 0x0000 (LidarSearch)
      10   : cmd_type = 0x00 (コマンド)
      11   : sender_type = 0x00 (ホスト)
      12-17: 予約
      18-19: 先頭18バイトの CRC16
      20-23: ペイロードの CRC32（ペイロード無しなので 0）
    """
    f = bytearray(24)
    f[0] = 0xAA
    f[1] = 0x00
    struct.pack_into("<H", f, 2, 24)
    struct.pack_into("<I", f, 4, seq & 0xFFFFFFFF)
    struct.pack_into("<H", f, 8, 0x0000)
    f[10] = 0x00
    f[11] = 0x00
    struct.pack_into("<H", f, 18, crc16_ccitt(bytes(f[:18])))
    struct.pack_into("<I", f, 20, 0)
    return bytes(f)


def parse_reply(data: bytes):
    """探索応答をパースして dict を返す。応答でなければ None.

    ペイロード(24バイト)は DetectionData 構造体:
      uint8 ret_code / uint8 dev_type / char sn[16] / uint8 lidar_ip[4] / uint16 cmd_port
    """
    if len(data) < 48 or data[0] != 0xAA:
        return None
    cmd_id = struct.unpack_from("<H", data, 8)[0]
    cmd_type = data[10]
    if cmd_id != 0x0000 or cmd_type != 0x01:   # 0x01 = ACK
        return None
    p = data[24:]
    if len(p) < 24 or p[0] != 0:               # ret_code != 0 は異常
        return None
    dev_type = p[1]
    return {
        "dev_type": dev_type,
        "model": DEV_TYPES.get(dev_type, f"不明(dev_type={dev_type})"),
        "section": CFG_SECTION.get(dev_type),
        "sn": p[2:18].split(b"\x00")[0].decode(errors="replace"),
        "ip": ".".join(str(x) for x in p[18:22]),
        "cmd_port": struct.unpack_from("<H", p, 22)[0],
    }


def detect(host_ip: str = "192.168.1.50", duration: float = 5.0):
    """探索ブロードキャストを撒いて、応答した LiDAR の一覧を返す.

    ソケットを2つ使う点が重要:
      tx : ホストIP に bind した 56000 番。ここから探索を送る。
           送信元ポートが 56000 でないと LiDAR は別ポートに返してしまう。
      rx : 0.0.0.0 の 56000 番。LiDAR の応答は 255.255.255.255 宛の
           ブロードキャストで返ってくるため、特定IPに bind した tx では
           受け取れない（SDK が detection_socket_ と
           detection_broadcast_socket_ の2つを持つのと同じ理由）。
    """
    def mk(bind_ip):
        so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        so.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        so.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        so.bind((bind_ip, DETECTION_PORT))
        return so

    try:
        tx = mk(host_ip)
    except OSError as e:
        raise RuntimeError(
            f"{host_ip}:{DETECTION_PORT} に bind できません ({e})\n"
            f"  - sudo ~/livox_ws/tools/01_setup_net.sh を実行済みか確認\n"
            f"  - livox のドライバ/サンプルが起動中なら停止してください "
            f"(pkill livox_ros_drive / pkill livox_lidar_qui)") from e
    try:
        rx = mk("0.0.0.0")
    except OSError as e:
        tx.close()
        raise RuntimeError(f"0.0.0.0:{DETECTION_PORT} に bind できません ({e})") from e

    found = {}
    seq = 0x3000
    deadline = time.time() + duration
    last_send = 0.0
    while time.time() < deadline:
        if time.time() - last_send > 0.5:
            try:
                tx.sendto(build_search(seq), ("255.255.255.255", DETECTION_PORT))
            except OSError:
                pass
            seq += 1
            last_send = time.time()
        ready, _, _ = select.select([tx, rx], [], [], 0.3)
        for so in ready:
            try:
                data, addr = so.recvfrom(65535)
            except OSError:
                continue
            if addr[0] == host_ip:      # 自分が撒いたブロードキャストの折り返し
                continue
            info = parse_reply(data)
            if info:
                found[info["ip"]] = info
    tx.close()
    rx.close()
    return list(found.values())


def main():
    host_ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.50"
    try:
        lidars = detect(host_ip)
    except RuntimeError as e:
        print(f"[NG] {e}")
        return 1
    if not lidars:
        print("[NG] 応答した LiDAR がありません")
        return 1
    for d in lidars:
        print(f"  IP       : {d['ip']}")
        print(f"  機種     : {d['model']}  (dev_type={d['dev_type']})")
        print(f"  シリアル : {d['sn']}")
        print(f"  設定名   : \"{d['section']}\"  <- JSON のセクション名はこれ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
