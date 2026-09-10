# Livox Mid-360S + ROS 2 Humble セットアップ完全手順

ゼロから構築し直せるように、**何を・なぜ・どのコマンドで**行うかを順にまとめたものです。
用意済みのスクリプトを使う方法と、その中身（生のコマンド）を併記しています。

---

## 0. 全体像

### 何を作るのか

```
  Mid-360S ──UDP/LAN──> [livox_ros_driver2] ──/livox/lidar──> [mid360_check]  → PASS/FAIL
  192.168.1.111          (Livox純正ドライバ)  ──/livox/imu───>  (自作の判定ノード)
                                              └─────────────> [rviz2] → 3D表示
```

LiDAR は **UDP でひたすらデータを撒くだけの機器**です。ROS とは無関係に動きます。
`livox_ros_driver2` がその UDP を受け取って ROS 2 の「トピック」に変換し、
その先は普通の ROS 2 の世界になります。

### 作業は大きく4段階

| 段階 | 内容 | 頻度 |
|---|---|---|
| A. 配線 | M12 ケーブルと 12V 電源 | 最初だけ |
| B. ネットワーク | PC 側の IP と経路の設定 | **PC 再起動のたび** |
| C. ソフト構築 | ドライバのビルドと設定 | 最初だけ |
| D. 実行・確認 | 動作確認とデータ取得 | 毎回 |

### この環境の確定値

| 項目 | 値 | 備考 |
|---|---|---|
| OS | Ubuntu 22.04 Server | デスクトップ環境なし |
| ROS | Humble | `/opt/ros/humble` |
| **機種** | **Livox Mid-360S** | Mid-360 **ではない**（後述） |
| dev_type | 35 | Mid-360 は 9 |
| シリアル | `ARMCP7E0031111` | |
| LiDAR IP | `192.168.1.111` | |
| ホスト IP（LiDAR用） | `192.168.1.50` | USB LAN 側に付与 |
| USB LAN | `enxc817f5600593` | LiDAR 接続先 |
| 有線 LAN | `enp1s0` = `192.168.1.210` | 家庭内LAN・インターネット |
| デフォルトGW | `192.168.1.1` | |
| 作業ディレクトリ | `~/livox_ws` | |

---

## A. 配線

### A-1. M12 → RJ45 の結線

Mid-360S の M12 コネクタのうち、**Ethernet に使うのはピン 1, 2, 3, 6** です。
RJ45 の同じ番号のピンへ配線します。

```
M12 ピン 1 ──── RJ45 ピン 1  ┐ ペア1（撚り線を組にする）
M12 ピン 2 ──── RJ45 ピン 2  ┘
M12 ピン 3 ──── RJ45 ピン 3  ┐ ペア2
M12 ピン 6 ──── RJ45 ピン 6  ┘
```

**重要**: 100BASE-TX は差動信号なので、**1-2 で1組、3-6 で1組**の撚り対にすること。
ペアを跨いで結線すると、リンクが上がらないか、上がっても不安定になります。

### A-2. 電源

12V を接続します。通電すると内部モーターが回る音がします。
**音がしない場合は電源を疑ってください**（LAN 側をいくら調べても解決しません）。

### A-3. 確認

```bash
ip -br link show enxc817f5600593
```
`UP` になっていない場合は次の B-1 で起こします。

---

## B. ネットワーク設定（PC 再起動のたびに必要）

### B-0. なぜ設定が必要か

Mid-360S の工場出荷 IP は `192.168.1.111` で、**家庭内LAN（`enp1s0` = 192.168.1.210/24）と
同じサブネット**です。単純に USB LAN にも `192.168.1.x/24` を振ると、
Linux はどちらの NIC に送ればよいか判断できず、通信が壊れます。

そこで次の3点セットで回避します。

1. USB LAN の IP は `noprefixroute` で付ける（`/24` の経路を作らせない）
2. **LiDAR 宛の `/32` ホスト経路だけ**を USB LAN に向ける
3. `brd +` でブロードキャストアドレスを明示（Livox の探索はブロードキャストを使う）

これでインターネット（`enp1s0` 経由）を維持したまま LiDAR と通信できます。

### B-1. スクリプトで実行

```bash
sudo ~/livox_ws/tools/01_setup_net.sh              # まず IP だけ付与
python3 ~/livox_ws/tools/10_find_lidar.py          # LiDAR の IP と機種を特定
sudo ~/livox_ws/tools/01_setup_net.sh 192.168.1.111  # 経路まで確定
```

`Link detected: yes` が出れば配線と電源は正常です。
`no` の場合は A に戻って 12V 電源・M12 結線・USB ハブの給電を確認してください。

### B-2. スクリプトの中身（生のコマンド）

```bash
IFACE=enxc817f5600593
HOST_IP=192.168.1.50
LIDAR_IP=192.168.1.111

# 1) インタフェースを起こす
sudo ip link set $IFACE up

# 2) リンク（ケーブルが刺さって通信できているか）を確認
sudo ethtool $IFACE | grep -E "Link detected|Speed"

# 3) ARP flux 対策（同一サブネットに NIC が2枚あるときの定番設定）
sudo sysctl -w net.ipv4.conf.$IFACE.arp_ignore=1
sudo sysctl -w net.ipv4.conf.$IFACE.arp_announce=2
sudo sysctl -w net.ipv4.conf.$IFACE.rp_filter=2
sudo sysctl -w net.ipv4.conf.all.rp_filter=2

# 4) IP を付与。brd + と noprefixroute が要点
sudo ip addr flush dev $IFACE
sudo ip addr add $HOST_IP/24 brd + dev $IFACE noprefixroute

# 5) LiDAR 宛だけを USB LAN に向ける
sudo ip route replace $LIDAR_IP/32 dev $IFACE src $HOST_IP
```

> `ip addr add` は `ifconfig` と違い、**`brd +` を書かないとブロードキャストアドレスが
> 設定されません**。Livox の探索とステータス通知はブロードキャストで飛ぶため、
> これが無いと取りこぼす原因になります。

### B-3. 確認

```bash
ip -br addr show enxc817f5600593    # 192.168.1.50/24 が付いているか
ip route get 192.168.1.111          # dev enxc817f5600593 経由になっているか
ping -c 3 192.168.1.111             # 疎通確認
ip route | grep '^default'          # インターネット経路が enp1s0 のままか
```

---

## C. ソフトウェアの構築（最初の一度だけ）

### C-1. 依存パッケージ

```bash
~/livox_ws/tools/00_install_deps.sh
```

中身:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential cmake git \
  python3-colcon-common-extensions python3-rosdep \
  ros-humble-pcl-conversions ros-humble-pcl-ros \
  ros-humble-rviz2 ros-humble-rosbag2-storage-default-plugins \
  iproute2 iputils-ping net-tools tcpdump ethtool
```

`colcon` は ROS 2 のワークスペースをビルドするツールで、**これが無いと何も始まりません**。

### C-2. LiDAR の IP と「機種」を特定 ★最重要

```bash
python3 ~/livox_ws/tools/10_find_lidar.py
```

出力例:

```
[検出] 192.168.1.111
       機種        : Mid-360S  (dev_type=35)
       シリアル番号: ARMCP7E0031111
       JSON セクション名: "Mid360s"
```

**なぜ機種の特定が最重要なのか**

Livox SDK2 は設定 JSON の**セクション名**（`"MID360"` / `"Mid360s"` など）から
デバイス種別を決め、LiDAR の探索応答に入っている `dev_type` と一致しない応答を
**ログを一切出さずに捨てます**（`device_manager.cpp` の無言 `return`）。

セクション名を間違えると、こうなります。

- `ping` は通る ✓
- ステータス通知も 1 Hz で届く ✓
- ドライバは `Init lds lidar success!` まで進む ✓
- **なのに点群だけ永久に来ない、エラーメッセージも一切出ない** ✗

原因の切り分けが極めて困難なので、必ず最初に機種を確定させてください。

### C-3. 設定ファイルの生成

```bash
python3 ~/livox_ws/tools/20_gen_config.py
```

機種を自動判別して `MID360_config.json` を生成します（引数は不要）。
生成先は `src/` と `install/` の両方なので、この後の再ビルドは不要です。

生成される内容の要点:

```json
{
  "lidar_summary_info": { "lidar_type": 8 },
  "Mid360s": {                                    ← ここがデバイス種別
    "lidar_net_info":  { "cmd_data_port": 56100, ... },
    "host_net_info":   { "cmd_data_ip": "192.168.1.50", "point_data_port": 56301, ... }
  },
  "lidar_configs": [ { "ip": "192.168.1.111", "pcl_data_type": 1, "pattern_mode": 0, ... } ]
}
```

| キー | 意味 |
|---|---|
| `lidar_summary_info.lidar_type: 8` | ドライバ内部の定数。デバイス種別とは無関係、常に 8 |
| セクション名 `"Mid360s"` | **これがデバイス種別**。Mid-360 なら `"MID360"` |
| `lidar_net_info` | LiDAR 側のポート。機種によらず固定 |
| `host_net_info` | PC 側のポート。LiDAR はここ宛にデータを送ってくる |
| `lidar_configs[].ip` | LiDAR の IP アドレス |
| `pcl_data_type: 1` | 直交座標（高精度） |
| `pattern_mode: 0` | 非繰り返しスキャン |

使用ポート一覧:

| 用途 | LiDAR 側 | PC 側 |
|---|---|---|
| 探索（ブロードキャスト） | 56000 | 56000 |
| コマンド | 56100 | 56101 |
| ステータス通知 | 56200 | 56201 |
| **点群データ** | 56300 | **56301** |
| **IMU データ** | 56400 | **56401** |
| ログ | 56500 | 56501 |

### C-4. ビルド

```bash
~/livox_ws/tools/30_build.sh
```

10〜20分かかります。中身は3段階です。

```bash
# 1) Livox-SDK2（LiDAR と UDP で通信する C++ ライブラリ）
git clone https://github.com/Livox-SDK/Livox-SDK2.git ~/livox_ws/Livox-SDK2
mkdir -p ~/livox_ws/Livox-SDK2/build && cd ~/livox_ws/Livox-SDK2/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install && sudo ldconfig

# 2) livox_ros_driver2（SDK2 を使って ROS トピックに流すドライバ）
git clone https://github.com/Livox-SDK/livox_ros_driver2.git \
          ~/livox_ws/src/livox_ros_driver2

# 3) ワークスペース全体をビルド
cd ~/livox_ws/src/livox_ros_driver2
./build.sh humble
```

> **注意**: 純正の `build.sh` は先頭で `build/` `install/` を `rm -rf` するため、
> 実行するたびにフルビルドになります。自作パッケージだけ直したときは
> `~/livox_ws/tools/31_rebuild_check.sh`（数秒）を使ってください。

---

## D. 実行と確認

### D-0. `source` は毎回必要

ROS 2 は端末に「コマンドの場所」を教えてからでないと `ros2` が使えません。
**新しい端末を開くたび**に必要です。

```bash
source /opt/ros/humble/setup.bash      # ROS 本体
source ~/livox_ws/install/setup.bash   # 自分のワークスペース
```

毎回打つのが面倒なら `.bashrc` に登録します。

```bash
echo 'source /opt/ros/humble/setup.bash; [ -f ~/livox_ws/install/setup.bash ] && source ~/livox_ws/install/setup.bash' >> ~/.bashrc
```

> `tools/` 配下の `.sh` は中で `source` 済みなので、スクリプト経由なら意識不要です。
> なお ROS の `setup.bash` は `set -u`（未定義変数をエラー化）と相性が悪く、
> `AMENT_TRACE_SETUP_FILES: unbound variable` で落ちます。
> スクリプト内では `tools/_ros_env.sh` 経由で読み込んでいます。

### D-1. 動作確認（メイン）

```bash
~/livox_ws/tools/50_run_check.sh 15          # 15秒計測して PASS/FAIL 判定
~/livox_ws/tools/50_run_check.sh 15 rviz     # RViz2 で3D表示も
```

止めるときは `Ctrl` + `C`。

中身は `ros2 launch` 1本です。

```bash
ros2 launch mid360_check mid360_check_launch.py duration:=15.0 rviz:=true
#          ~~~~~~~~~~~~ ~~~~~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~~~~
#          パッケージ名  launchファイル名          引数（= ではなく :=）
```

| 引数 | 既定値 | 意味 |
|---|---|---|
| `duration:=` | `10.0` | 判定に使う秒数。`0` で無限監視 |
| `rviz:=` | `false` | `true` で RViz2 も起動 |
| `publish_freq:=` | `10.0` | 点群を出す周波数 [Hz] |
| `frame_id:=` | `livox_frame` | 点群の座標系名 |

> 引数は **`名前:=値`**（`:=`）です。また `duration:=15` のように小数点を省くと
> ROS は INTEGER と解釈して型エラーになります。スクリプト経由なら自動補完されます。

### D-2. 正常時の値

```
点群 : 10.9 Hz / 約 20000 点/msg / 距離 0.1〜60 m / 非有限点 0
IMU  : 203 Hz / |加速度| 約 1.0 g（静止時は重力のみ）
判定 : PASS
```

| 項目 | 閾値 | 実測 |
|---|---|---|
| 点群レート | ≥ 5 Hz | 10.84〜10.90 Hz |
| 点数/メッセージ | ≥ 1000 | 19996〜19999 |
| 距離レンジ | 有効値あり | 0.10〜59.67 m |
| IMU レート | ≥ 100 Hz | 203.03〜203.64 Hz |

PASS なら終了コード 0、FAIL なら 1 を返します。

### D-3. 自分で中身を覗く ros2 コマンド

ドライバ起動中に、**別の端末**から（`source` を忘れずに）。

```bash
ros2 node list                    # 動いているノード一覧
ros2 topic list                   # トピック一覧 → /livox/lidar が出るはず
ros2 topic hz /livox/lidar        # 点群の周波数 → 約 10 Hz
ros2 topic hz /livox/imu          # IMU の周波数 → 約 200 Hz
ros2 topic bw /livox/lidar        # 通信量 → 数 MB/s
ros2 topic info /livox/lidar -v   # メッセージ型と QoS の詳細
ros2 topic echo /livox/imu        # IMU の中身を表示（Ctrl-C で停止）
ros2 topic echo /livox/lidar --field width   # 1メッセージの点数だけ
```

> `ros2 topic echo /livox/lidar` を素で打つと2万点が文字で流れて端末が固まります。
> 点群は `--field` を付けるか RViz で見てください。

### D-4. 記録して後から見る

```bash
~/livox_ws/tools/52_record_bag.sh 10          # 10秒間 rosbag2 に記録
ros2 bag play ~/livox_ws/bags/mid360_XXXXXX   # 再生（LiDAR 無しで再現できる）
ros2 bag info ~/livox_ws/bags/mid360_XXXXXX   # 中身の確認
```

---

## E. RViz を Windows に表示する（SSH 経由）

Ubuntu Server 側に画面は不要です。X11 は「描画を要求する側（X クライアント = `rviz2`）」と
「実際に表示する側（X サーバ = 手元の Windows）」が分離しているためです。

### E-1. サーバ側の条件（確認済み）

```bash
grep -i X11Forwarding /etc/ssh/sshd_config   # X11Forwarding yes
command -v xauth                             # /usr/bin/xauth
```

### E-2. Windows 側は WSL2 から SSH する

```powershell
wsl                              # PowerShell から WSL に入る
ssh -X humi@192.168.1.210
echo $DISPLAY                    # localhost:10.0 のように出れば成功
```

WSLg が X サーバと `DISPLAY` を自動で用意します。**追加設定は不要**です。

> PowerShell から直接 `ssh -X` しても動きません。Windows の OpenSSH クライアントは
> **Windows 側に `DISPLAY` が無いと `-X` を黙って無効化する**ためです。
> VcXsrv 等を使う場合は、事前に `$env:DISPLAY = "127.0.0.1:0"` の設定が必要になります。

### E-3. 動作確認

```bash
sudo apt install -y x11-apps
xeyes                                        # ウィンドウが Windows 側に出れば成功
~/livox_ws/tools/50_run_check.sh 15 rviz     # RViz で点群を表示
```

WSLg は GLX を GPU にパススルーするため、`rviz2` は **OpenGL 4.5** で動きます。
VcXsrv や Xming のような間接 GLX に頼る X サーバでは重くなりますが、WSLg では問題ありません。

RViz で点群が見えないときは左パネルで:
- **Fixed Frame** が `livox_frame` になっているか
- PointCloud2 の **Reliability Policy** が `Best Effort` になっているか

（同梱の `mid360.rviz` では設定済みです）

---

## F. 頻度別まとめ

### 最初の一度だけ

```bash
~/livox_ws/tools/00_install_deps.sh
~/livox_ws/tools/30_build.sh
```

### PC 再起動のたび

```bash
sudo ~/livox_ws/tools/01_setup_net.sh 192.168.1.111
```

### 毎回

```bash
~/livox_ws/tools/50_run_check.sh 15 rviz
```

### 設定を変えたとき

```bash
python3 ~/livox_ws/tools/20_gen_config.py        # LiDAR の IP や機種が変わった
~/livox_ws/tools/31_rebuild_check.sh             # check_node.py や launch を編集した
```

---

## G. トラブルシューティング

### G-1. ping は通るのに点群が来ない ★最頻出

**症状**: ドライバのログが `Init lds lidar success!` で止まり、
`ros2 topic list` に `/livox/lidar` が出てこない。エラーも出ない。

**原因**: 設定 JSON のセクション名がデバイス種別と不一致（C-2 参照）。

```bash
python3 ~/livox_ws/tools/10_find_lidar.py    # 機種を確認
python3 ~/livox_ws/tools/20_gen_config.py    # 正しいセクション名で再生成
```

### G-2. 前は動いたのに急に見つからない

**原因**: `ros2 launch` を `Ctrl+C` 以外（端末を閉じる、`timeout` で殺す等）で
終了すると、ドライバの**子プロセスだけが生き残って UDP ポート 56000 を掴み続けます**。
この状態では次に起動しても LiDAR を発見できません。

```bash
~/livox_ws/tools/99_cleanup.sh    # 居残りプロセスを停止してポートを確認
```

> `pkill -f livox` は**自分自身のコマンドラインにもマッチして自滅する**ので、
> プロセス名で指定してください（`pkill -x livox_ros_drive`）。

### G-3. その他

| 症状 | 原因・対処 |
|---|---|
| `Link detected: no` | 12V電源未投入 / M12結線ミス（1-2, 3-6 のペア）/ USBハブの給電不足 |
| `AMENT_TRACE_SETUP_FILES: unbound variable` | `set -u` のまま ROS の setup.bash を読んだ。`tools/_ros_env.sh` 経由にする |
| `InvalidParameterTypeException ... 'INTEGER', expecting 'DOUBLE'` | `duration:=15` と小数点なしで渡した。`15.0` にする |
| `could not connect to display` | `DISPLAY` 未設定。WSL から `ssh -X` で入り直す（E 参照） |
| `colcon: command not found` | `00_install_deps.sh` が未実行 |
| IMU だけ来て点群が来ない | launch の `xfer_format` が 1 (CustomMsg) になっていないか |
| RViz に何も出ない | Fixed Frame = `livox_frame`、QoS = Best Effort を確認 |
| インターネットが切れた | `ip route \| grep default` が `enp1s0` 経由か確認。B-2 を再実行 |

### G-4. 切り分けの順序

上から順に潰していくと原因が絞れます。

```bash
# 1) 物理層 — ケーブルと電源
sudo ethtool enxc817f5600593 | grep "Link detected"     # yes か

# 2) ネットワーク層 — IP と経路
ip -br addr show enxc817f5600593                        # 192.168.1.50/24 か
ping -c 3 192.168.1.111                                 # 応答するか

# 3) Livox プロトコル層 — 機種と探索（ROS 不要）
~/livox_ws/tools/99_cleanup.sh                          # 先に居残りを消す
python3 ~/livox_ws/tools/livox_detect.py                # 機種が出るか
python3 ~/livox_ws/tools/40_udp_raw_check.py 192.168.1.111 192.168.1.50 10

# 4) ROS 層 — トピック
ros2 topic list | grep livox
ros2 topic hz /livox/lidar
```

---

## H. ファイル一覧

```
~/livox_ws/
├── SETUP_GUIDE.md          このファイル（通しの手順書）
├── README.md               環境情報と手順の要約
├── HOWTO.md                ROS 2 初心者向けガイド
├── tools/
│   ├── _ros_env.sh             ROS 環境の読み込み（set -u 対策）
│   ├── 00_install_deps.sh      依存パッケージ導入（sudo・初回のみ）
│   ├── 01_setup_net.sh         USB LAN を UP + IP付与 + /32経路（sudo・毎起動）
│   ├── livox_detect.py         探索プロトコルの最小実装（機種判別の中核）
│   ├── 10_find_lidar.py        LiDAR の IP・機種・シリアルを特定
│   ├── 20_gen_config.py        設定 JSON 生成（機種を自動判別）
│   ├── 30_build.sh             SDK2 + ドライバのビルド（初回のみ）
│   ├── 31_rebuild_check.sh     mid360_check だけ高速再ビルド
│   ├── 40_udp_raw_check.py     ROS 無しで生 UDP 到達を確認
│   ├── 50_run_check.sh         ドライバ + 判定ノードを起動 ★メイン
│   ├── 51_topic_only.sh        判定ノードのみ起動
│   ├── 52_record_bag.sh        rosbag2 記録
│   └── 99_cleanup.sh           居残りプロセスの停止
├── Livox-SDK2/             Livox 純正 SDK（C++ ライブラリ）
└── src/
    ├── livox_ros_driver2/  Livox 純正 ROS 2 ドライバ
    │   └── config/MID360_config.json    ← 20_gen_config.py が生成
    └── mid360_check/       自作の動作確認パッケージ
        ├── mid360_check/check_node.py       判定ノード本体
        ├── launch/mid360_check_launch.py    まとめて起動する設定
        └── rviz/mid360.rviz                 RViz の表示設定
```

---

## I. 用語集

| 用語 | 意味 |
|---|---|
| **ノード (node)** | ROS 2 の 1 プログラム。今回はドライバ・判定ノード・RViz の3つ |
| **トピック (topic)** | ノード同士をつなぐ名前付きの通信路。`/livox/lidar` など |
| **パッケージ (package)** | ノードをまとめた単位。`ros2 run` の第1引数 |
| **ワークスペース** | パッケージを置いてビルドする作業場。ここでは `~/livox_ws` |
| **colcon** | ROS 2 のビルドツール |
| **launch ファイル** | 複数ノードをまとめて起動する Python の設定 |
| **QoS** | 通信品質の設定。センサは `Best Effort`（落ちても再送しない） |
| **frame_id** | 座標系の名前。RViz の Fixed Frame と一致させる |
| **PointCloud2** | ROS 標準の点群メッセージ型 |
| **dev_type** | Livox のデバイス種別番号。Mid-360=9、**Mid-360S=35** |
