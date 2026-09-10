# =============================================================================
#  Mid-360 動作確認用 launch ファイル
# =============================================================================
#
# 【launch ファイルとは？】
#   ROS 2 では普通、ノードを1個ずつ `ros2 run パッケージ名 実行ファイル名` で
#   起動します。しかし今回は
#       (1) livox_ros_driver2  ... LiDAR と通信して ROS トピックに流すドライバ
#       (2) mid360_check       ... それを受け取って判定する自作ノード
#       (3) rviz2              ... 点群を3D表示するビューア(任意)
#   の3つを同時に起動したい。こういう「まとめて起動する設定」を書くのが
#   launch ファイルです。Python で書けます。
#
# 【起動コマンド】
#   ros2 launch mid360_check mid360_check_launch.py
#   ros2 launch mid360_check mid360_check_launch.py rviz:=true duration:=15.0
#                            ~~~~~~~~~~~~~ ~~~~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~~~
#                            パッケージ名   launchファイル名        引数
#
#   ※ 引数は `名前:=値` の形（= ではなく := なので注意）
#
# 【使える引数】
#   user_config_path : MID360_config.json のパス（LiDAR の IP 設定など）
#   frame_id         : 点群に付ける座標系の名前 (既定 livox_frame)
#   publish_freq     : 点群を publish する周波数 [Hz] (既定 10.0)
#   duration         : 判定に使う計測秒数 (既定 10.0、0 で無限監視)
#   rviz             : true にすると RViz2 も起動
# =============================================================================

import os

# パッケージのインストール先(share ディレクトリ)のパスを取得する関数
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument   # 引数を定義する
from launch.conditions import IfCondition          # 条件付き起動に使う
from launch.substitutions import LaunchConfiguration  # 引数の値を参照する
from launch_ros.actions import Node                # ノードを1つ起動する指示
# 引数(文字列)を「この型のパラメータ」として渡すためのラッパ
from launch_ros.parameter_descriptions import ParameterValue

DRIVER_PKG = 'livox_ros_driver2'


def generate_launch_description():
    """ros2 launch から呼ばれる関数。起動したいものを詰めて返す."""

    # --- 設定ファイル・rviz 設定のパスを組み立てる -------------------------
    driver_share = get_package_share_directory(DRIVER_PKG)
    # 例: ~/livox_ws/install/livox_ros_driver2/share/livox_ros_driver2/config/MID360_config.json
    default_cfg = os.path.join(driver_share, 'config', 'MID360_config.json')
    rviz_cfg = os.path.join(get_package_share_directory('mid360_check'),
                            'rviz', 'mid360.rviz')

    # --- コマンドラインから渡せる引数の定義 --------------------------------
    # DeclareLaunchArgument('名前', default_value='既定値') で定義し、
    # LaunchConfiguration('名前') で値を参照します。
    args = [
        DeclareLaunchArgument('user_config_path', default_value=default_cfg,
                              description='MID360_config.json のパス'),
        DeclareLaunchArgument('frame_id', default_value='livox_frame',
                              description='点群に付ける座標系名'),
        DeclareLaunchArgument('publish_freq', default_value='10.0',
                              description='点群の publish 周波数 [Hz]'),
        DeclareLaunchArgument('duration', default_value='10.0',
                              description='判定に使う計測秒数 (0 で無限監視)'),
        DeclareLaunchArgument('rviz', default_value='false',
                              description='true なら RViz2 も起動'),
    ]

    # --- (1) Livox のドライバノード ----------------------------------------
    # これが LiDAR から UDP でデータを受け取り、
    # /livox/lidar と /livox/imu というトピックに流してくれます。
    livox = Node(
        package=DRIVER_PKG,                        # パッケージ名
        executable='livox_ros_driver2_node',       # 実行ファイル名
        name='livox_lidar_publisher',              # ノードにつける名前
        output='screen',                           # ログを端末に出す
        parameters=[{
            # 点群の出力形式。0 = 標準の sensor_msgs/PointCloud2
            #   1 にすると Livox 独自の CustomMsg になり、
            #   RViz でもこの判定ノードでも読めなくなるので 0 のままにすること
            'xfer_format': 0,
            # 複数台つないだときトピックを分けるか。0 = 1トピックにまとめる
            'multi_topic': 0,
            # データの供給元。0 = 実機の LiDAR（他は再生用など）
            'data_src': 0,
            # 点群を何 Hz で publish するか。10.0 なら 1スキャン約2万点
            # launch の引数は文字列なので、value_type=float を明示しないと
            # "10" が INTEGER と解釈されて型エラーになる
            'publish_freq': ParameterValue(
                LaunchConfiguration('publish_freq'), value_type=float),
            'output_data_type': 0,
            # 点群メッセージの header.frame_id。RViz の Fixed Frame と合わせる
            'frame_id': LaunchConfiguration('frame_id'),
            # LiDAR の IP / ホストの IP を書いた JSON ファイル
            'user_config_path': LaunchConfiguration('user_config_path'),
            'cmdline_input_bd_code': 'livox0000000001',
        }],
    )

    # --- (2) 自作の判定ノード ----------------------------------------------
    checker = Node(
        package='mid360_check',
        executable='check_node',       # setup.py の console_scripts で定義した名前
        name='mid360_check',
        output='screen',
        parameters=[{
            'duration': ParameterValue(
                LaunchConfiguration('duration'), value_type=float),
            'cloud_topic': '/livox/lidar',
            'imu_topic': '/livox/imu',
        }],
    )

    # --- (3) RViz2（rviz:=true のときだけ起動）-----------------------------
    # condition=IfCondition(...) を付けると、その値が true のときだけ起動します
    rviz = Node(
        package='rviz2', executable='rviz2', name='rviz2',
        arguments=['-d', rviz_cfg],    # -d で設定ファイルを読み込む
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    # 定義した引数と、起動したいノードをまとめて返す
    return LaunchDescription(args + [livox, checker, rviz])
