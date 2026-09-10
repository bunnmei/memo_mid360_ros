# Livox Mid-360S 動作確認 (ROS 2 Humble / Ubuntu 22.04)

> **ROS 2 が初めての方は [HOWTO.md](HOWTO.md) を読んでください。**
> 用語の説明・起動コマンド・確認用コマンドを丁寧に書いてあります。
> 本ファイルは環境情報と手順の要約です。

## 接続されている機体（実測で確定）

| 項目 | 値 |
|---|---|
| 機種 | **Livox Mid-360S**（Mid-360 ではない） |
| dev_type | **35**（Mid-360 は 9） |
| シリアル番号 | `ARMCP7E0031111` |
| LiDAR IP | `192.168.1.111` / cmd_port 56100 |
| JSON セクション名 | **`"Mid360s"`**（`"MID360"` ではない） |

> **最重要**: Livox SDK2 は設定 JSON の**セクション名**からデバイス種別を決め、
> LiDAR の探索応答に入っている `dev_type` と一致しない応答を
> **ログを一切出さずに捨てます**。
> セクション名を `"MID360"` にしていると
> 「ping は通る・ステータス通知も届く・なのに点群だけ来ない」
> という原因の非常に分かりにくい症状になります。
> `20_gen_config.py` はこれを自動判別して正しいセクション名で生成します。

## 動作確認の実測結果（PASS）

```
点群 : 10.90 Hz / 19999 点/msg / 距離 0.11〜45.49 m / 非有限点 0
IMU  : 203.64 Hz / |加速度| 0.993 g（重力を正しく検出）
```

## ネットワーク構成

| 項目 | 値 |
|---|---|
| 有線LAN | `enp1s0` = 192.168.1.210/24（家庭内LAN・デフォルトGW 192.168.1.1） |
| USB LAN | `enxc817f5600593` (QinHeng USB 10/100 LAN) ← Mid-360S 接続先 |
| ホストIP | `192.168.1.50` を USB LAN に付与 |

Mid-360S の IP は既存の家庭内LANと同一サブネットなので、`01_setup_net.sh` は
USB LAN に `noprefixroute` で IP を付け、**LiDAR 宛の /32 経路だけ**を
USB LAN に向けます。これでインターネット接続を維持したまま衝突を回避できます。

> 100BASE-TX の結線は M12 ピン **1,2,3,6** → RJ45 ピン **1,2,3,6**。
> ツイストペアは **1-2 で1ペア / 3-6 で1ペア** に必ず合わせること。

## 手順

```bash
# 0) 依存パッケージ（初回のみ）
~/livox_ws/tools/00_install_deps.sh

# 1) ホスト側ネットワーク設定（PC 再起動のたびに実行）
sudo ~/livox_ws/tools/01_setup_net.sh
#    -> "Link detected: yes" が出れば結線・電源はOK

# 2) LiDAR の IP と機種を特定
python3 ~/livox_ws/tools/10_find_lidar.py

# 3) 見つかった IP で経路を確定
sudo ~/livox_ws/tools/01_setup_net.sh 192.168.1.111
ping -c 3 192.168.1.111

# 4) 設定ファイル生成（機種は自動判別）
python3 ~/livox_ws/tools/20_gen_config.py

# 5) ビルド（初回のみ、10〜20分）
~/livox_ws/tools/30_build.sh

# 6) 動作確認の本番
~/livox_ws/tools/50_run_check.sh 15          # 15秒計測して PASS/FAIL 判定
~/livox_ws/tools/50_run_check.sh 15 rviz     # RViz2 で点群も表示（要 GUI 環境）
```

## 合格基準（`check_node` の判定）

| 項目 | 閾値 | 実機の実測値 |
|---|---|---|
| 点群レート | ≥ 5 Hz | 10.90 Hz |
| 点数 / メッセージ | ≥ 1000 | 19999 |
| 距離データ | 有効値あり | 0.11〜45.49 m |
| IMU レート | ≥ 100 Hz | 203.64 Hz |

PASS なら終了コード 0、FAIL なら 1 を返します。

## ファイル構成

```
~/livox_ws/
├── tools/
│   ├── _ros_env.sh            ROS 環境の読み込み（set -u 対策）
│   ├── 00_install_deps.sh     依存パッケージ導入（sudo）
│   ├── 01_setup_net.sh        USB LAN を UP + IP付与 + LiDAR宛/32経路（sudo）
│   ├── livox_detect.py        探索プロトコルの最小実装（機種判別の中核）
│   ├── 10_find_lidar.py       LiDAR の IP・機種・シリアルを特定
│   ├── 20_gen_config.py       MID360_config.json 生成（機種を自動判別）
│   ├── 30_build.sh            Livox-SDK2 + livox_ros_driver2 のビルド
│   ├── 31_rebuild_check.sh    mid360_check だけ高速再ビルド
│   ├── 40_udp_raw_check.py    ROS 無しで生UDP到達を確認
│   ├── 50_run_check.sh        ドライバ + 判定ノードを起動（メイン）
│   ├── 51_topic_only.sh       判定ノードのみ起動
│   ├── 52_record_bag.sh       rosbag2 記録
│   └── 99_cleanup.sh          居残りプロセスの停止
└── src/
    ├── livox_ros_driver2/     Livox 純正ドライバ
    └── mid360_check/          動作確認 ROS 2 パッケージ
```

## よくあるトラブル

| 症状 | 原因・対処 |
|---|---|
| **ping は通るのに点群が来ない／ドライバのログが `Init lds lidar success!` で止まる** | **設定 JSON のセクション名がデバイス種別と不一致**。`python3 tools/20_gen_config.py` で再生成する（自動判別） |
| 前回は動いたのに急に見つからない | ドライバの子プロセスが居残ってポート 56000 を専有している。`~/livox_ws/tools/99_cleanup.sh` |
| `Link detected: no` | 12V電源未投入 / M12結線ミス（1-2, 3-6 のペア）/ USBハブの給電不足 |
| `AMENT_TRACE_SETUP_FILES: unbound variable` | `set -u` のまま ROS の setup.bash を読むと出る。`tools/_ros_env.sh` 経由にする |
| `InvalidParameterTypeException ... 'INTEGER', expecting 'DOUBLE'` | `duration:=15` のように小数点なしで渡した。`15.0` にする（スクリプト経由なら自動補完） |
| RViz が `could not connect to display` | SSH/コンソール接続で GUI が無い。`ssh -X` にするか rosbag 記録して手元で再生 |
| IMU だけ来て点群が来ない | launch の `xfer_format` が 1 (CustomMsg) になっていないか確認 |
| RViz に何も出ない | Fixed Frame を `livox_frame` に、PointCloud2 の QoS Reliability を **Best Effort** に |
