#!/usr/bin/env python3
# =============================================================================
#  Livox Mid-360 動作確認ノード
# =============================================================================
#
# 【このファイルは何？】
#   ROS 2 の「ノード(node)」と呼ばれるプログラムです。
#   ROS 2 では、複数の小さなプログラム(ノード)が「トピック(topic)」という
#   名前付きの通信路を通じてデータをやり取りします。
#
#       [livox_ros_driver2 ノード]                [このノード]
#        LiDAR から UDP で受信          /livox/lidar   点群を受け取って
#        → ROS のメッセージに変換  ──────────────→  レート・点数を集計
#                                       /livox/imu
#                                  ──────────────→  PASS / FAIL を判定
#
#   データを送る側を「パブリッシャ(publisher)」、
#   受け取る側を「サブスクライバ(subscriber)」と呼びます。
#   このノードは受け取る側(サブスクライバ)だけを持っています。
#
# 【起動方法】
#   ドライバごとまとめて起動（推奨）:
#       ~/livox_ws/tools/50_run_check.sh 15
#   このノードだけを起動（ドライバが別端末で動いている場合）:
#       ros2 run mid360_check check_node --ros-args -p duration:=15.0
#
# 【パラメータ】 --ros-args -p 名前:=値  で起動時に変更できます
#   duration      判定に使う計測秒数 (既定 10.0 / 0 にすると無限に監視だけ続ける)
#   cloud_topic   点群トピック名     (既定 /livox/lidar)
#   imu_topic     IMU トピック名     (既定 /livox/imu)
#   min_cloud_hz  点群レートの合格ライン (既定 5.0 Hz)
#   min_imu_hz    IMU レートの合格ライン (既定 100.0 Hz)
#   min_points    1スキャンあたり点数の合格ライン (既定 1000)
#
# 【終了コード】 PASS なら 0 / FAIL なら 1 を返します（自動テストに使えます）
# =============================================================================

import math
import sys
import time

import numpy as np
import rclpy                      # ROS 2 の Python ライブラリ本体
from rclpy.node import Node       # ノードの基底クラス
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rcl_interfaces.msg import ParameterDescriptor
from sensor_msgs.msg import Imu, PointCloud2   # 使うメッセージ型


# -----------------------------------------------------------------------------
#  PointCloud2 メッセージをほどくためのヘルパ
# -----------------------------------------------------------------------------
# PointCloud2 は「点群をバイト列(1本の長いバイナリ)で持つ」メッセージです。
# 中身の並び方は msg.fields に「x は先頭から 0 バイト目に float32」…という
# 形で書かれているので、それを読んで numpy の型に変換します。
#
# PointField.datatype の番号 → numpy の型 の対応表
_DTYPES = {
    1: np.int8,   2: np.uint8,   3: np.int16,   4: np.uint16,
    5: np.int32,  6: np.uint32,  7: np.float32, 8: np.float64,
}


def cloud_to_xyz(msg: PointCloud2):
    """PointCloud2 メッセージを (点数, 3) の xyz 座標配列に変換する.

    Livox の点群は 1点あたり 26 バイトで
        x(4) y(4) z(4) intensity(4) tag(1) line(1) timestamp(8)
    のように並んでいます。この関数は msg.fields の情報から
    numpy の「構造体型(structured dtype)」を組み立てて一括で読み出します。
    （1点ずつ Python のループで読むと遅すぎて間に合わないため）
    """
    names = {f.name: f for f in msg.fields}
    # x, y, z が無い点群は扱えないので諦める
    if not {'x', 'y', 'z'} <= names.keys():
        return None

    dt = []       # numpy の dtype を組み立てるリスト
    offset = 0    # 今どこまで読んだか（バイト位置）
    for f in sorted(msg.fields, key=lambda f: f.offset):
        # フィールドの間に隙間(パディング)があれば、その分をダミーで埋める
        if f.offset > offset:
            dt.append((f'_pad{offset}', np.uint8, f.offset - offset))
            offset = f.offset
        np_t = _DTYPES.get(f.datatype)
        if np_t is None:          # 未知の型が来たら諦める
            return None
        count = max(1, f.count)
        dt.append((f.name, np_t, count) if count > 1 else (f.name, np_t))
        offset += np.dtype(np_t).itemsize * count

    # 1点の全長(point_step)より短ければ、末尾にもパディングを足す
    if msg.point_step > offset:
        dt.append((f'_pad{offset}', np.uint8, msg.point_step - offset))

    # バイト列を一気に構造体配列として解釈する
    arr = np.frombuffer(bytes(msg.data), dtype=np.dtype(dt))
    # x, y, z だけ取り出して (N, 3) の配列に組み直す
    return np.stack([arr['x'].astype(np.float64).ravel(),
                     arr['y'].astype(np.float64).ravel(),
                     arr['z'].astype(np.float64).ravel()], axis=1)


# -----------------------------------------------------------------------------
#  本体のノードクラス
# -----------------------------------------------------------------------------
class Mid360Check(Node):
    """点群と IMU を購読して、受信状況を集計・判定するノード."""

    def __init__(self):
        # 'mid360_check' がこのノードの名前。ros2 node list に出てくる名前です
        super().__init__('mid360_check')

        # --- パラメータの宣言 ---------------------------------------------
        # ROS 2 では、起動時に外から変えられる値を「パラメータ」として宣言します。
        # declare_parameter('名前', 既定値) で宣言し、get_parameter で読みます。
        #
        # 既定値 10.0 は DOUBLE 型なので、そのままだと duration:=15 のように
        # 小数点なしで渡された瞬間に
        #   InvalidParameterTypeException: ... of type 'INTEGER', expecting 'DOUBLE'
        # で落ちてしまう。dynamic_typing=True にすると int でも float でも
        # 受け付けられるようになるので、数値パラメータには全部これを付ける。
        # （読み出し側は下で float()/int() に変換している）
        any_type = ParameterDescriptor(dynamic_typing=True)

        self.declare_parameter('duration', 10.0, any_type)
        self.declare_parameter('cloud_topic', '/livox/lidar')
        self.declare_parameter('imu_topic', '/livox/imu')
        self.declare_parameter('min_cloud_hz', 5.0, any_type)
        self.declare_parameter('min_imu_hz', 100.0, any_type)
        self.declare_parameter('min_points', 1000, any_type)

        g = self.get_parameter
        self.duration = float(g('duration').value)
        self.cloud_topic = g('cloud_topic').value
        self.imu_topic = g('imu_topic').value
        self.min_cloud_hz = float(g('min_cloud_hz').value)
        self.min_imu_hz = float(g('min_imu_hz').value)
        self.min_points = int(g('min_points').value)

        # --- QoS(通信品質)の設定 -------------------------------------------
        # ROS 2 では通信の性質を QoS で指定します。
        #   RELIABLE    : 届くまで再送する(確実だが遅延・詰まりが起きうる)
        #   BEST_EFFORT : 落ちても再送しない(センサデータ向け。Livox はこちら)
        # ここを間違えると「トピックはあるのに受信できない」現象が起きるので、
        # センサ側と合わせて BEST_EFFORT にしておきます。
        qos = QoSProfile(depth=20,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)

        # --- サブスクライバの作成 ------------------------------------------
        # create_subscription(メッセージ型, トピック名, 呼ばれる関数, QoS)
        # データが届くたびに第3引数の関数(コールバック)が自動で呼ばれます。
        self.create_subscription(PointCloud2, self.cloud_topic, self.on_cloud, qos)
        self.create_subscription(Imu, self.imu_topic, self.on_imu, qos)

        # --- 集計用の変数 ---------------------------------------------------
        self.t0 = time.time()      # 計測開始時刻
        self.c_n = 0               # 点群メッセージの受信数
        self.c_first = None        # 最初に点群を受けた時刻
        self.c_last = None         # 最後に点群を受けた時刻
        self.c_points = []         # 各メッセージの点数
        self.c_frame = None        # frame_id (座標系の名前)
        self.c_fields = None       # 点群に入っている項目名
        self.rng_min = math.inf    # 観測された最短距離
        self.rng_max = 0.0         # 観測された最長距離
        self.nan_pts = 0           # 無効値(NaN/inf)の点数
        self.total_pts = 0         # 総点数

        self.i_n = 0               # IMU メッセージの受信数
        self.i_first = None
        self.i_last = None
        self.acc = []              # 加速度のログ
        self.gyr = []              # 角速度のログ

        # get_logger().info(...) は ROS のログ出力。端末に [INFO] 付きで出ます
        self.get_logger().info(
            f'計測開始: cloud={self.cloud_topic} imu={self.imu_topic} '
            f'duration={self.duration if self.duration > 0 else "∞"}s')

        # 1秒ごとに tick() を呼ぶタイマー（途中経過の表示と、終了判定に使う）
        self.create_timer(1.0, self.tick)

    # ------------------------------------------------------------------
    #  コールバック: メッセージが届くたびに ROS が自動で呼んでくれる
    # ------------------------------------------------------------------
    def on_cloud(self, msg: PointCloud2):
        """点群(/livox/lidar)を1メッセージ受け取ったときの処理."""
        t = time.time()
        if self.c_first is None:
            self.c_first = t
        self.c_last = t
        self.c_n += 1

        # 点数 = 幅 x 高さ。Livox は height=1 の「並び順のない点群」なので width が点数
        n = msg.width * msg.height
        self.c_points.append(n)
        self.c_frame = msg.header.frame_id
        if self.c_fields is None:
            self.c_fields = [f.name for f in msg.fields]

        # 距離の統計をとる（LiDAR が本当に測距できているかの確認）
        xyz = cloud_to_xyz(msg)
        if xyz is not None and len(xyz):
            bad = ~np.isfinite(xyz).all(axis=1)   # NaN や inf を含む点
            self.nan_pts += int(bad.sum())
            good = xyz[~bad]
            if len(good):
                d = np.linalg.norm(good, axis=1)  # 原点からの距離
                d = d[d > 1e-3]                   # 原点ちょうどの点(無効点)は除く
                if len(d):
                    self.rng_min = min(self.rng_min, float(d.min()))
                    self.rng_max = max(self.rng_max, float(d.max()))
            self.total_pts += len(xyz)

    def on_imu(self, msg: Imu):
        """IMU(/livox/imu)を1メッセージ受け取ったときの処理."""
        t = time.time()
        if self.i_first is None:
            self.i_first = t
        self.i_last = t
        self.i_n += 1
        self.acc.append((msg.linear_acceleration.x,
                         msg.linear_acceleration.y,
                         msg.linear_acceleration.z))
        self.gyr.append((msg.angular_velocity.x,
                         msg.angular_velocity.y,
                         msg.angular_velocity.z))

    # ------------------------------------------------------------------
    #  1秒ごとの処理
    # ------------------------------------------------------------------
    def tick(self):
        el = time.time() - self.t0     # 経過秒数
        self.get_logger().info(
            f'[{el:5.1f}s] cloud {self.c_n:5d} 個 ({self.hz(self.c_n, self.c_first, self.c_last):5.1f} Hz) / '
            f'imu {self.i_n:6d} 個 ({self.hz(self.i_n, self.i_first, self.i_last):6.1f} Hz)')

        # 指定秒数に達したらレポートを出して終了する
        # （SystemExit を投げると main() 側の spin ループから抜けられる）
        if self.duration > 0 and el >= self.duration:
            self.report()
            raise SystemExit(0 if self.passed else 1)

    @staticmethod
    def hz(n, first, last):
        """受信数と最初/最後の時刻から周波数[Hz]を求める."""
        if n < 2 or first is None or last is None or last <= first:
            return 0.0
        # n個のメッセージの間隔は (n-1) 個なので n-1 で割る
        return (n - 1) / (last - first)

    # ------------------------------------------------------------------
    #  最終レポート
    # ------------------------------------------------------------------
    def report(self):
        c_hz = self.hz(self.c_n, self.c_first, self.c_last)
        i_hz = self.hz(self.i_n, self.i_first, self.i_last)
        avg_pts = float(np.mean(self.c_points)) if self.c_points else 0.0

        line = '=' * 68
        print('\n' + line)
        print(' Livox Mid-360 動作確認レポート')
        print(line)
        print(f' 計測時間            : {time.time() - self.t0:.1f} s')
        print()
        print(f' [点群] topic        : {self.cloud_topic}')
        print(f'        メッセージ数 : {self.c_n}')
        print(f'        レート       : {c_hz:.2f} Hz   (閾値 {self.min_cloud_hz} Hz)')
        print(f'        平均点数/msg : {avg_pts:.0f}     (閾値 {self.min_points})')
        print(f'        frame_id     : {self.c_frame}')
        print(f'        fields       : {self.c_fields}')
        if self.rng_max > 0:
            print(f'        距離レンジ   : {self.rng_min:.2f} m 〜 {self.rng_max:.2f} m')
        print(f'        非有限点     : {self.nan_pts} / {self.total_pts}')
        print()
        print(f' [IMU]  topic        : {self.imu_topic}')
        print(f'        メッセージ数 : {self.i_n}')
        print(f'        レート       : {i_hz:.2f} Hz   (閾値 {self.min_imu_hz} Hz)')
        if self.acc:
            a = np.array(self.acc)
            g = np.array(self.gyr)
            am = a.mean(axis=0)
            gm = g.mean(axis=0)
            print(f'        加速度 平均  : x={am[0]:+.3f} y={am[1]:+.3f} z={am[2]:+.3f}')
            print(f'        角速度 平均  : x={gm[0]:+.4f} y={gm[1]:+.4f} z={gm[2]:+.4f} [rad/s]')
            # 静止していれば重力だけが見えるはず。
            # 大きさが約 1 なら単位は g、約 9.8 なら m/s^2（Livox は g で出す）
            norm = float(np.linalg.norm(am))
            unit = 'g' if norm < 3.0 else 'm/s^2'
            print(f'        |加速度|     : {norm:.3f}  (単位はおそらく {unit})')
        print(line)

        # --- 合否チェック項目 ---
        checks = [
            ('点群を受信している', self.c_n > 0),
            (f'点群レート >= {self.min_cloud_hz} Hz', c_hz >= self.min_cloud_hz),
            (f'点数/msg >= {self.min_points}', avg_pts >= self.min_points),
            ('有効な距離データがある', self.rng_max > 0.05),
            ('IMU を受信している', self.i_n > 0),
            (f'IMU レート >= {self.min_imu_hz} Hz', i_hz >= self.min_imu_hz),
        ]
        for name, ok in checks:
            print(f'  [{"OK" if ok else "NG"}] {name}')
        self.passed = all(ok for _, ok in checks)
        print(line)
        if self.passed:
            print(' 判定: PASS — Mid-360 は正常に動作しています')
        else:
            print(' 判定: FAIL — 下のヒントを確認してください')
            if self.c_n == 0 and self.i_n == 0:
                print('   * トピックが来ていません。ドライバが起動しているか確認:')
                print('     ros2 topic list | grep livox')
                print('   * MID360_config.json の lidar ip / host ip が実機と一致しているか')
                print('   * ping <LIDAR_IP> が通るか')
            elif self.c_n == 0:
                print('   * IMU は来ているのに点群が無い場合、xfer_format の設定違い')
                print('     (CustomMsg 出力の launch を使っていないか) を確認')
            elif avg_pts < self.min_points:
                print('   * 点数が少ない: publish_freq が高すぎる / pattern_mode を確認')
        print(line + '\n')
        sys.stdout.flush()


# -----------------------------------------------------------------------------
#  エントリポイント
# -----------------------------------------------------------------------------
# setup.py の console_scripts に登録してあるので
#   ros2 run mid360_check check_node
# と打つとこの main() が呼ばれます。
def main():
    rclpy.init()               # ROS 2 の初期化（最初に必ず呼ぶ）
    node = Mid360Check()       # ノードを作る
    node.passed = False
    try:
        # spin() は「メッセージが来たらコールバックを呼ぶ」を延々と続ける関数。
        # ここでプログラムが待機状態になります。Ctrl-C か SystemExit で抜けます。
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        # duration=0(無限監視)で Ctrl-C されたときも、集計結果を出してあげる
        if node.c_n == 0 and node.i_n == 0 and node.duration <= 0:
            node.report()
    finally:
        code = 0 if getattr(node, 'passed', False) else 1
        node.destroy_node()    # ノードの後片付け
        try:
            rclpy.shutdown()   # ROS 2 の終了処理
        except Exception:
            pass
    sys.exit(code)


if __name__ == '__main__':
    main()
