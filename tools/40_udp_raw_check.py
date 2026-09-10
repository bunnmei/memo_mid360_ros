#!/usr/bin/env python3
"""ROS を使わずに Mid-360 の生 UDP データ到達を確認する（低レベル確認用）.

Livox SDK2 のハンドシェイク（0x0000 コマンド）を LiDAR の 56100 番へ送り、
点群 56301 / IMU 56401 にデータが返ってくるかを見る。
ドライバのビルド前でも「LiDAR が生きているか」を切り分けられる。

usage: python3 40_udp_raw_check.py <LIDAR_IP> [HOST_IP] [SECONDS]
"""
import socket
import struct
import sys
import threading
import time

CRC16_TAB = None


def crc16(data: bytes) -> int:
    """CCITT-FALSE 相当（Livox SDK2 のフレーム CRC16）."""
    crc = 0x4C49
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def build_frame(cmd_id: int, payload: bytes, seq: int = 1) -> bytes:
    """SDK2 の制御フレーム (24 byte ヘッダ + payload)."""
    sof = 0xAA
    version = 0x01
    length = 24 + len(payload)
    cmd_type = 0x00      # REQ
    sender_type = 0x00   # host
    resv = b"\x00" * 6
    head = struct.pack("<BBHIHBB6s", sof, version, length, seq, cmd_id,
                       cmd_type, sender_type, resv)
    head += struct.pack("<H", crc16(head))
    frame = head + payload
    frame += struct.pack("<I", crc32(payload)) if payload else struct.pack("<I", crc32(b""))
    return frame


class Counter:
    def __init__(self, name):
        self.name = name
        self.pkts = 0
        self.bytes = 0
        self.first = None
        self.last = None

    def add(self, n):
        self.pkts += 1
        self.bytes += n
        t = time.time()
        if self.first is None:
            self.first = t
        self.last = t

    def report(self):
        if self.pkts == 0:
            return f"  {self.name:<12} 受信なし"
        dur = max(1e-6, (self.last - self.first))
        return (f"  {self.name:<12} {self.pkts:6d} pkt  {self.bytes/1024:8.1f} KiB  "
                f"{self.pkts/dur:7.1f} pkt/s")


def recv_on(sock, counter, deadline):
    """既に bind 済みのソケットで受信数を数える（コマンド応答用）."""
    while time.time() < deadline:
        sock.settimeout(max(0.2, deadline - time.time()))
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            break
        except OSError:
            break
        counter.add(len(data))


def sink(port, counter, deadline, host_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    s.bind(("0.0.0.0", port))
    while time.time() < deadline:
        s.settimeout(max(0.2, deadline - time.time()))
        try:
            data, _ = s.recvfrom(65535)
        except socket.timeout:
            break
        except OSError:
            break
        counter.add(len(data))
    s.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    lidar_ip = sys.argv[1]
    host_ip = sys.argv[2] if len(sys.argv) > 2 else "192.168.1.50"
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

    print("=" * 66)
    print(f" 生 UDP 確認  LiDAR={lidar_ip}  HOST={host_ip}  {secs:.0f}s")
    print("=" * 66)

    counters = {
        "point 56301": Counter("point 56301"),
        "imu   56401": Counter("imu   56401"),
        "push  56201": Counter("push  56201"),
        "cmd   56101": Counter("cmd   56101"),
    }
    # 56101 は「ホストから LiDAR へコマンドを送るポート」で、LiDAR の応答も
    # 同じポートに返ってくる。1つのソケットで送受信するため sink には含めない。
    ports = {"point 56301": 56301, "imu   56401": 56401, "push  56201": 56201}

    deadline = time.time() + secs
    threads = []
    for name, port in ports.items():
        t = threading.Thread(target=sink,
                             args=(port, counters[name], deadline, host_ip),
                             daemon=True)
        t.start()
        threads.append(t)

    # --- コマンド用ソケット（送信 + 応答受信を兼ねる）---
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bound = False
    try:
        tx.bind((host_ip, 56101))
        bound = True
    except OSError as e:
        print(f"[警告] {host_ip}:56101 に bind できません ({e})。")
        print("       他の Livox プロセス(ドライバ等)が動いていないか確認してください。")
    if bound:
        # 同じソケットで LiDAR からの応答を数えるスレッドを回す
        t = threading.Thread(target=recv_on,
                             args=(tx, counters["cmd   56101"], deadline),
                             daemon=True)
        t.start()
        threads.append(t)

    # ハンドシェイク(0x0000)を LiDAR の cmd ポート 56100 へ毎秒投げる
    time.sleep(0.3)
    ip_parts = [int(x) for x in host_ip.split(".")]
    payload = struct.pack("<4B HHHHH", *ip_parts, 56101, 56201, 56301, 56401, 56501)
    frame = build_frame(0x0000, payload)
    for i in range(int(secs)):
        try:
            tx.sendto(frame, (lidar_ip, 56100))
        except OSError as e:
            print(f"[NG] 送信失敗: {e}")
            break
        time.sleep(1.0)

    for t in threads:
        t.join()
    tx.close()

    print()
    for name in counters:          # cmd 56101 も含めて全て表示する
        print(counters[name].report())
    print()
    if counters["point 56301"].pkts > 0:
        print("[OK] 点群 UDP が到達しています。LiDAR は正常に動作しています。")
        rc = 0
    elif counters["push  56201"].pkts > 0:
        print("[△] LiDAR は生きています（ステータス通知 push が届いています）。")
        print("     ただし点群ストリームは開始していません。点群の開始には")
        print("     Livox SDK2 による正式なハンドシェイクが必要なので、これは正常です。")
        print("     次はドライバ経由で確認してください:")
        print("       ~/livox_ws/tools/30_build.sh      # 未ビルドなら")
        print("       ~/livox_ws/tools/50_run_check.sh 15 rviz")
        rc = 0
    elif any(c.pkts for c in counters.values()):
        print("[△] 何らかの応答はありますが点群が来ていません。")
        print("     ~/livox_ws/tools/50_run_check.sh でドライバ経由で再確認してください。")
        rc = 0
    else:
        print("[NG] 一切データが来ていません。")
        print("     - ping " + lidar_ip + " が通るか")
        print("     - ホストIPが " + host_ip + " になっているか (ip -br addr)")
        print("     - ファイアウォール (sudo ufw status) が UDP を塞いでいないか")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
