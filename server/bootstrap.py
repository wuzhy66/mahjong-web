"""加载随仓库保存的杭州规则与公开观测编码。"""
import sys
from pathlib import Path
VENDOR = Path(__file__).resolve().parent / 'vendor'
sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(VENDOR / 'mahjong/hangzhou-mahjong'))
from mahjong.engine_compat import install
install()
