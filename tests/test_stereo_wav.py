"""build_stereo_test_wav のWAV構造テスト。

macOS の `say` コマンドで音声を合成するため macos マーカーを付ける。
L/Rの振り分けが崩れるとステレオペアの左右確認が無意味になるので、
チャンネルごとの実データを検証する。
"""

import array
import shutil
import wave

import pytest

import bo

pytestmark = pytest.mark.macos


@pytest.fixture(scope="module")
def wav_path(tmp_path_factory) -> str:
    if shutil.which("say") is None:
        pytest.skip("macOS の say コマンドが無い")
    return bo.build_stereo_test_wav(str(tmp_path_factory.mktemp("stereo")))


@pytest.fixture(scope="module")
def channels(wav_path) -> tuple[list[int], list[int]]:
    with wave.open(wav_path) as w:
        frames = array.array("h", w.readframes(w.getnframes()))
    return list(frames[0::2]), list(frames[1::2])


def test_output_is_16bit_stereo(wav_path):
    with wave.open(wav_path) as w:
        assert w.getnchannels() == 2
        assert w.getsampwidth() == 2
        assert w.getframerate() > 0
        assert w.getnframes() > 0


def test_left_and_right_are_both_present(channels):
    left, right = channels
    assert any(left), "左チャンネルが無音"
    assert any(right), "右チャンネルが無音"


def test_left_speaks_before_right(channels):
    """左の発話が終わってから右が始まる(同時に鳴らない)。"""
    left, right = channels
    last_left = max(i for i, v in enumerate(left) if v != 0)
    first_right = min(i for i, v in enumerate(right) if v != 0)
    assert last_left < first_right


def test_channels_never_overlap(channels):
    """どのフレームでもL/Rの一方は必ず無音(片チャンネルずつ鳴る)。"""
    left, right = channels
    assert not any(l != 0 and r != 0 for l, r in zip(left, right))


def test_normalized_close_to_full_scale(channels):
    """sayの出力はピークが小さいので0.9まで正規化される。"""
    left, right = channels
    for samples in (left, right):
        peak = max(abs(v) for v in samples)
        assert peak > int(32767 * 0.8)
