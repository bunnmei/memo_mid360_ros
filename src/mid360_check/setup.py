# =============================================================================
#  mid360_check パッケージのビルド設定 (ament_python 形式)
# =============================================================================
#  ROS 2 の Python パッケージは、この setup.py に
#    - どの Python モジュールを含めるか
#    - どのファイルをインストール先(share/)にコピーするか
#    - どのコマンド名で実行できるようにするか
#  を書きます。`colcon build` がこれを読んでビルドします。
# =============================================================================
from glob import glob

from setuptools import setup

package_name = 'mid360_check'

setup(
    name=package_name,
    version='0.1.0',
    # このディレクトリ配下の Python モジュールをパッケージとして含める
    packages=[package_name],

    # インストール時にコピーするファイル。(コピー先, [コピー元]) の並び。
    # launch ファイルや rviz 設定は share/ に置かないと ros2 launch から見つかりません。
    data_files=[
        # ROS に「このパッケージが存在する」と登録するためのマーカー
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/rviz', glob('rviz/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='humi',
    maintainer_email='frenchpress090@gmail.com',
    description='Livox Mid-360 の動作確認用ノード',
    license='MIT',

    # ここが重要:
    #   'コマンド名 = モジュールのパス:関数名'
    # と書くと  ros2 run mid360_check check_node  で
    # mid360_check/check_node.py の main() が呼ばれるようになります。
    entry_points={
        'console_scripts': [
            'check_node = mid360_check.check_node:main',
        ],
    },
)
