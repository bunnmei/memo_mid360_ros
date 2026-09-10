# Mid-360S 動作確認 — ROS 2 はじめての人向けガイド

> 接続されている機体は実測の結果 **Livox Mid-360S**（dev_type 35、SN `ARMCP7E0031111`、
> IP `192.168.1.111`）でした。Mid-360 とは設定ファイルのセクション名が異なります。
> 詳細は [README.md](README.md) を参照。

## 0. まず知っておく ROS 2 の言葉（3つだけ）

| 言葉 | 意味 | 今回の例 |
|---|---|---|
| **ノード (node)** | 1つの小さなプログラム | ドライバ / 判定ノード / RViz |
| **トピック (topic)** | ノード同士をつなぐ名前付きの通信路 | `/livox/lidar`（点群）、`/livox/imu` |
| **パッケージ (package)** | ノードをまとめた単位。`ros2 run` の第1引数 | `livox_ros_driver2`、`mid360_check` |

今回の構成はこれだけです。

```
  Mid-360S ──UDP──> [livox_ros_driver2] ──/livox/lidar──> [mid360_check]  → PASS/FAIL
   (LAN)              (ドライバノード)   ──/livox/imu───>  (判定ノード)
                                         └─────────────> [rviz2] → 3D表示
```

## 1. 「source」は毎回必要（一番よくハマる所）

ROS 2 は、端末に「ROS のコマンドの場所」を教えてからでないと `ros2` が使えません。
**新しい端末を開くたび**に、毎回これを打ちます。

```bash
source /opt/ros/humble/setup.bash      # ROS 本体
source ~/livox_ws/install/setup.bash   # 自分で作ったパッケージ（ビルド後から有効）
```

毎回打つのが面倒なら、次の1行で `.bashrc` に登録できます（以後は自動）。

```bash
echo 'source /opt/ros/humble/setup.bash; [ -f ~/livox_ws/install/setup.bash ] && source ~/livox_ws/install/setup.bash' >> ~/.bashrc
```

> `tools/` の中の `.sh` スクリプトは **中で source を自分でやっている**ので、
> スクリプト経由なら source を意識しなくて大丈夫です。

## 2. 準備（上から順に1回ずつ）

```bash
# --- (a) 必要なソフトを入れる（初回のみ・数分） -------------------------
~/livox_ws/tools/00_install_deps.sh

# --- (b) LiDAR 用のネットワーク設定（PC を再起動するたびに実行）--------
sudo ~/livox_ws/tools/01_setup_net.sh
#   → "Link detected: yes" が出れば、電源と結線はOK
#   → "no" なら 12V電源 / M12ピン1,2,3,6の結線 / USBハブの給電 を確認

# --- (c) LiDAR の IP と「機種」を探す -----------------------------------
python3 ~/livox_ws/tools/10_find_lidar.py
#   → IP・機種(dev_type)・シリアル番号・JSONセクション名 が表示される
#     例: 192.168.1.111 / Mid-360S (dev_type=35) / "Mid360s"

# --- (d) 見つかった IP を設定に反映 --------------------------------------
sudo ~/livox_ws/tools/01_setup_net.sh 192.168.1.111
ping -c 3 192.168.1.111                     # 疎通確認
python3 ~/livox_ws/tools/20_gen_config.py   # 機種は自動判別されるので引数不要

# --- (e) ドライバをビルド（初回のみ・10〜20分かかります）---------------
~/livox_ws/tools/30_build.sh
```

## 3. 起動コマンド（ここが本番）

### 方法A: スクリプト1発（いちばん簡単・おすすめ）

```bash
~/livox_ws/tools/50_run_check.sh 15          # 15秒計測して PASS/FAIL 判定
~/livox_ws/tools/50_run_check.sh 15 rviz     # 3D表示(RViz2)も一緒に起動
```

### 方法B: ros2 launch を直接打つ（方法Aの中身はこれ）

```bash
source /opt/ros/humble/setup.bash
source ~/livox_ws/install/setup.bash

ros2 launch mid360_check mid360_check_launch.py
ros2 launch mid360_check mid360_check_launch.py duration:=15.0 rviz:=true
#          ~~~~~~~~~~~~ ~~~~~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~~~~
#          パッケージ名  launchファイル名          引数(名前:=値)
```

引数はこれだけあります（全部省略可）。

| 引数 | 既定値 | 意味 |
|---|---|---|
| `duration:=` | `10.0` | 判定に使う秒数。`0` にすると無限に監視だけ続ける |
| `rviz:=` | `false` | `true` で RViz2 を同時起動 |
| `publish_freq:=` | `10.0` | 点群を出す周波数[Hz] |
| `frame_id:=` | `livox_frame` | 点群の座標系名 |
| `user_config_path:=` | 自動 | MID360_config.json の場所 |

### 方法C: 端末を2つ開いて別々に動かす（デバッグ向き）

```bash
# --- 端末1: ドライバだけ起動 ---
source /opt/ros/humble/setup.bash && source ~/livox_ws/install/setup.bash
ros2 launch livox_ros_driver2 rviz_MID360_launch.py

# --- 端末2: 判定ノードだけ起動 ---
~/livox_ws/tools/51_topic_only.sh 15
# 中身: ros2 run mid360_check check_node --ros-args -p duration:=15.0
#            ~~~ ~~~~~~~~~~~~ ~~~~~~~~~~
#            run パッケージ名  実行ファイル名
```

### 止め方

どのコマンドも **`Ctrl` + `C`** で止まります（`duration` を指定した場合は自動で終了します）。

## 4. 自分で中身を覗くための ros2 コマンド

ドライバが動いている状態で、**別の端末**から打ちます（source を忘れずに）。

```bash
ros2 node list                    # 動いているノードの一覧
ros2 topic list                   # トピックの一覧 → /livox/lidar が出るはず
ros2 topic hz /livox/lidar        # 点群が何Hzで来ているか  → 約 10 Hz
ros2 topic hz /livox/imu          # IMU の周波数            → 約 200 Hz
ros2 topic bw /livox/lidar        # 通信量                  → 数 MB/s
ros2 topic info /livox/lidar -v   # メッセージ型と QoS の詳細
ros2 topic echo /livox/imu        # IMU の中身を垂れ流し表示（Ctrl-C で止める）

ros2 topic echo /livox/lidar --field width   # 1メッセージの点数だけ表示
```

> `ros2 topic echo /livox/lidar` をそのまま打つと点群2万点が文字で流れて
> 端末が固まります。点群は `--field` を付けるか RViz で見てください。

### 3D で見る

```bash
rviz2 -d ~/livox_ws/install/mid360_check/share/mid360_check/rviz/mid360.rviz
```

RViz で点群が出ないときは、左のパネルで
- **Fixed Frame** が `livox_frame` になっているか
- PointCloud2 の **Reliability Policy** が `Best Effort` になっているか

を確認してください（この2つが原因の9割です）。

### 記録して後から見る

```bash
~/livox_ws/tools/52_record_bag.sh 10          # 10秒間 rosbag2 に記録
ros2 bag play ~/livox_ws/bags/mid360_XXXXXX   # 記録を再生（LiDARなしで再現できる）
```

## 5. 出力の読み方

```
[INFO] [mid360_check]: [  5.0s] cloud    50 個 ( 10.0 Hz) / imu    987 個 ( 200.1 Hz)
```
1秒ごとの途中経過です。`cloud` が 0 のままなら通信できていません。

最後に出るレポートの見どころ:

| 行 | 正常な値 | ここが変なら |
|---|---|---|
| 点群 レート | 約 10 Hz | 0 Hz → 通信できていない |
| 平均点数/msg | 約 20000 | 極端に少ない → `publish_freq` が高すぎる |
| 距離レンジ | 0.1〜70 m 程度 | 全部同じ距離 → 窓や壁に密着していないか |
| IMU レート | 約 200 Hz | 0 Hz → ドライバ設定を確認 |
| \|加速度\| | 約 1.0 (単位 g) | 0 → IMU が動いていない |

最後の `判定: PASS` が出れば Mid-360 は正常です。

## 6. ハマりやすい2大トラブル

### (1) ping は通るのに点群が来ない

ドライバのログが `Init lds lidar success!` で止まり、`ros2 topic list` に
`/livox/lidar` が出てこない場合、**設定 JSON のセクション名が機種と合っていません**。

Livox SDK2 はセクション名（`"MID360"` / `"Mid360s"` など）からデバイス種別を決め、
LiDAR の応答に入っている `dev_type` と一致しない応答を **エラーlog も出さずに捨てます**。
そのため「通信はできているのにデータだけ来ない」という切り分けづらい状態になります。

```bash
python3 ~/livox_ws/tools/10_find_lidar.py    # 機種を確認
python3 ~/livox_ws/tools/20_gen_config.py    # 正しいセクション名で再生成（自動判別）
```

### (2) 前は動いたのに急に見つからなくなった

`ros2 launch` を Ctrl+C 以外（端末を閉じる、`timeout` で殺すなど）で終了すると、
ドライバの子プロセスだけが生き残って UDP ポート 56000 を掴み続けます。
この状態では次に起動しても LiDAR を発見できません。

```bash
~/livox_ws/tools/99_cleanup.sh    # 居残りプロセスを停止してポートを確認
```

## 7. 困ったときのコマンド

```bash
ip -br addr                                   # IPアドレスの確認
sudo ethtool enxc817f5600593 | grep Link      # LANケーブルのリンク確認
ping 192.168.1.1XX                            # LiDAR と通信できるか
sudo ufw status                               # ファイアウォールが塞いでいないか
python3 ~/livox_ws/tools/40_udp_raw_check.py 192.168.1.111 192.168.1.50 10
                                              # ROS を使わず生UDPで確認（切り分け用）
python3 ~/livox_ws/tools/livox_detect.py      # 機種・シリアルだけを素早く確認
~/livox_ws/tools/99_cleanup.sh                # 居残りプロセスの停止
```

その他の症状別対処は `~/livox_ws/README.md` の「よくあるトラブル」を参照。
