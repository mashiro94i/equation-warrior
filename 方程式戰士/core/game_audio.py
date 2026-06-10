"""BGM／音效（assets/audio；檔案缺失或 pygame 錯誤時略過）。"""
from __future__ import annotations

import array as pyarray
import io
import random
import wave
from pathlib import Path

import pygame

_AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio"
_BGM_DIR = _AUDIO_DIR / "bgm"
_BGM_TRACK_EXTS = frozenset({".mp3", ".ogg", ".wav", ".flac"})
BGM_END_EVENT = getattr(pygame, "MUSIC_END", pygame.USEREVENT + 20)

_jump_sound: pygame.mixer.Sound | None = None
_shot_sound: pygame.mixer.Sound | None = None
_explosion_sound: pygame.mixer.Sound | None = None
_calc_effect_sound: pygame.mixer.Sound | None = None
_pickup_sound: pygame.mixer.Sound | None = None
_flip_sound: pygame.mixer.Sound | None = None
_fall_sound: pygame.mixer.Sound | None = None
_break_sound: pygame.mixer.Sound | None = None
_sin_stun_sound: pygame.mixer.Sound | None = None
_sin_wing_flap_sound: pygame.mixer.Sound | None = None
_sin_wing_half_speed_ready = False
_sin_attack_sound: pygame.mixer.Sound | None = None
_spike_hit_sound: pygame.mixer.Sound | None = None
_exp_enter_sound: pygame.mixer.Sound | None = None
_area_rampage_sounds: list[pygame.mixer.Sound] = []
_giant_crush_sound: pygame.mixer.Sound | None = None
_enemy_hurt_sound: pygame.mixer.Sound | None = None
_player_dead_sound: pygame.mixer.Sound | None = None
_player_hurt_sounds: list[pygame.mixer.Sound] = []
_monster_attack_sounds: list[pygame.mixer.Sound] = []
_underwater_bubbles: pygame.mixer.Sound | None = None
_underwater_channel: pygame.mixer.Channel | None = None
_underwater_active = False
_bubble_pop_sound: pygame.mixer.Sound | None = None
_bubble_repeat_channel: pygame.mixer.Channel | None = None
_bubble_repeat_active = False
_sfx_volume = 1.0
_initialized = False
_music_loaded = False
_bgm_paths: list[Path] = []
_bgm_last_path: Path | None = None
_bgm_volume_setting = 0.5
_BREAK_VOLUME_MULT = 0.45
_SIN_WING_FLAP_VOLUME_MULT = 2.0 / 5.0
_SIN_WING_FLAP_SPEED = 0.5
_EXP_ENTER_VOLUME_MULT = 1
_BGM_PLAYBACK_MULT = 0.25
_UNDERWATER_BUBBLES_VOLUME_MULT = 0.55 * 2
_BUBBLE_VOLUME_MULT = 2.0
_PICKUP_THROTTLE_MS = 90
_SPIKE_HIT_THROTTLE_MS = 120
_last_pickup_ms = 0
_last_spike_hit_ms = 0
_SCREEN_VIEW: pygame.Rect | None = None


def _screen_view() -> pygame.Rect:
    global _SCREEN_VIEW
    if _SCREEN_VIEW is None:
        from .constants import SCREEN_HEIGHT, SCREEN_WIDTH

        _SCREEN_VIEW = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
    return _SCREEN_VIEW


def rect_on_screen(rect) -> bool:
    """實體碰撞箱與玩家視野（螢幕）相交。"""
    if rect is None:
        return False
    return _screen_view().colliderect(rect)


def _sfx_allowed(at_rect=None) -> bool:
    """除 BGM 外，音效僅在 at_rect 位於視野內時播放；未傳 rect 視為允許。"""
    if at_rect is None:
        return True
    return rect_on_screen(at_rect)


def _load_sound(path: Path) -> pygame.mixer.Sound | None:
    if not path.is_file():
        return None
    try:
        return pygame.mixer.Sound(str(path))
    except pygame.error:
        return None


def _resample_wav_file_stdlib(path: Path, speed: float) -> pygame.mixer.Sound | None:
    """無 numpy 時以 wave 線性重採樣（僅 16-bit PCM）。"""
    speed = max(0.05, float(speed))
    if abs(speed - 1.0) < 1e-6:
        return _load_sound(path)
    try:
        with wave.open(str(path), "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            comptype = wf.getcomptype()
            compname = wf.getcompname()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, OSError):
        return _load_sound(path)
    if sw != 2 or nch not in (1, 2):
        return _load_sound(path)

    samples = pyarray.array("h")
    samples.frombytes(raw)
    frame_count = len(samples) // nch
    new_frames = max(1, int(round(frame_count / speed)))
    out = pyarray.array("h")
    for i in range(new_frames):
        pos = i * speed
        i0 = int(pos)
        i1 = min(i0 + 1, frame_count - 1)
        frac = pos - i0
        for ch in range(nch):
            s0 = samples[i0 * nch + ch]
            s1 = samples[i1 * nch + ch]
            v = int(s0 * (1.0 - frac) + s1 * frac)
            out.append(max(-32768, min(32767, v)))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wout:
        wout.setnchannels(nch)
        wout.setsampwidth(sw)
        wout.setframerate(rate)
        wout.setcomptype(comptype, compname)
        wout.writeframes(out.tobytes())
    buf.seek(0)
    try:
        return pygame.mixer.Sound(file=buf)
    except pygame.error:
        return _load_sound(path)


def _load_sound_playback_speed(path: Path, speed: float) -> pygame.mixer.Sound | None:
    """調整播放速度（0.5 = 半速；1.0 = 原速）。"""
    if abs(speed - 1.0) < 1e-6:
        return _load_sound(path)
    try:
        import numpy as np

        snd = _load_sound(path)
        if snd is None:
            return None
        arr = pygame.sndarray.array(snd)
        sp = max(0.05, float(speed))
        n = int(arr.shape[0])
        new_n = max(1, int(round(n / sp)))
        x_old = np.arange(n, dtype=np.float64)
        x_new = np.linspace(0.0, float(n - 1), new_n)
        if arr.ndim == 1:
            resampled = np.interp(x_new, x_old, arr.astype(np.float64)).astype(arr.dtype)
        else:
            channels = [
                np.interp(x_new, x_old, arr[:, c].astype(np.float64))
                for c in range(arr.shape[1])
            ]
            resampled = np.stack(channels, axis=1).astype(arr.dtype)
        return pygame.sndarray.make_sound(resampled)
    except (ImportError, NotImplementedError, pygame.error, ValueError, TypeError):
        return _resample_wav_file_stdlib(path, speed)


def _discover_bgm_paths() -> list[Path]:
    paths: list[Path] = []
    seen_names: set[str] = set()
    if _BGM_DIR.is_dir():
        for path in sorted(_BGM_DIR.iterdir()):
            if path.is_file() and path.suffix.lower() in _BGM_TRACK_EXTS:
                key = path.name.lower()
                if key not in seen_names:
                    seen_names.add(key)
                    paths.append(path)
    legacy = _AUDIO_DIR / "music2.mp3"
    if legacy.is_file() and legacy.name.lower() not in seen_names:
        paths.append(legacy)
    return paths


def _load_wavs_from_dir(directory: Path) -> list[pygame.mixer.Sound]:
    out: list[pygame.mixer.Sound] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.wav")):
        snd = _load_sound(path)
        if snd is not None:
            out.append(snd)
    return out


def init_audio() -> None:
    global _initialized, _jump_sound, _shot_sound, _explosion_sound
    global _calc_effect_sound, _pickup_sound, _flip_sound, _fall_sound, _break_sound
    global _player_dead_sound, _player_hurt_sounds, _monster_attack_sounds, _underwater_bubbles
    global _sin_stun_sound, _sin_wing_flap_sound, _sin_wing_half_speed_ready, _sin_attack_sound
    global _spike_hit_sound
    global _exp_enter_sound, _area_rampage_sounds, _giant_crush_sound, _enemy_hurt_sound
    global _underwater_channel, _music_loaded, _bgm_paths
    global _bubble_pop_sound, _bubble_repeat_channel
    if _initialized:
        return
    _initialized = True
    _jump_sound = _load_sound(_AUDIO_DIR / "jump.wav")
    _shot_sound = _load_sound(_AUDIO_DIR / "shot.wav")
    _explosion_sound = _load_sound(_AUDIO_DIR / "explosion.wav")
    _calc_effect_sound = _load_sound(_AUDIO_DIR / "power_up.wav")
    _pickup_sound = _load_sound(_AUDIO_DIR / "pickup.wav")
    _flip_sound = _load_sound(_AUDIO_DIR / "flip.wav")
    _fall_sound = _load_sound(_AUDIO_DIR / "fall.wav")
    _break_sound = _load_sound(_AUDIO_DIR / "break.wav")
    _sin_stun_sound = _load_sound(_AUDIO_DIR / "sin_stun.wav")
    _sin_wing_flap_sound = _load_sound(_AUDIO_DIR / "sin_wing_flap.wav")
    _sin_wing_half_speed_ready = False
    _sin_attack_sound = _load_sound(_AUDIO_DIR / "sin_attack.wav")
    _spike_hit_sound = _load_sound(_AUDIO_DIR / "spike_hit.wav")
    _exp_enter_sound = _load_sound(_AUDIO_DIR / "exp_enter.wav")
    _area_rampage_sounds = _load_wavs_from_dir(_AUDIO_DIR / "angry")
    _giant_crush_sound = _load_sound(_AUDIO_DIR / "giant_crush.wav")
    _enemy_hurt_sound = _load_sound(_AUDIO_DIR / "enemy_hurt.wav")
    _player_dead_sound = _load_sound(_AUDIO_DIR / "player_dead.wav")
    _player_hurt_sounds = _load_wavs_from_dir(_AUDIO_DIR / "player_take_damage")
    _monster_attack_sounds = _load_wavs_from_dir(_AUDIO_DIR / "monster_attack")
    _underwater_bubbles = _load_sound(_AUDIO_DIR / "underwater_bubbles_loop.wav")
    if _underwater_bubbles is not None:
        _underwater_channel = pygame.mixer.Channel(7)
    _bubble_pop_sound = _load_sound(_AUDIO_DIR / "bubble_pop.mp3")
    if _bubble_pop_sound is None:
        _bubble_pop_sound = _load_sound(_AUDIO_DIR / "bubble_pop.wav")
    _bubble_repeat_channel = pygame.mixer.Channel(6)
    _BGM_DIR.mkdir(parents=True, exist_ok=True)
    _bgm_paths = _discover_bgm_paths()
    _music_loaded = len(_bgm_paths) > 0
    if _music_loaded:
        try:
            pygame.mixer.music.set_endevent(BGM_END_EVENT)
        except pygame.error:
            pass


def set_sfx_volume(volume: float) -> None:
    global _sfx_volume
    _sfx_volume = max(0.0, min(1.0, float(volume)))
    for snd in (
        _jump_sound,
        _shot_sound,
        _explosion_sound,
        _calc_effect_sound,
        _pickup_sound,
        _flip_sound,
        _fall_sound,
    ):
        if snd is not None:
            snd.set_volume(_sfx_volume)
    if _player_dead_sound is not None:
        _player_dead_sound.set_volume(_sfx_volume)
    if _enemy_hurt_sound is not None:
        _enemy_hurt_sound.set_volume(_sfx_volume)
    for snd in _player_hurt_sounds + _monster_attack_sounds:
        snd.set_volume(_sfx_volume)
    if _underwater_bubbles is not None and _underwater_active:
        _underwater_bubbles.set_volume(_sfx_volume * _UNDERWATER_BUBBLES_VOLUME_MULT)
    if _bubble_pop_sound is not None:
        _bubble_pop_sound.set_volume(_sfx_volume * _BUBBLE_VOLUME_MULT)
        if _bubble_repeat_active and _bubble_repeat_channel is not None:
            try:
                _bubble_repeat_channel.set_volume(_sfx_volume * _BUBBLE_VOLUME_MULT)
            except pygame.error:
                pass


def _play(sound: pygame.mixer.Sound | None) -> None:
    if sound is None:
        return
    try:
        sound.set_volume(_sfx_volume)
        sound.play()
    except pygame.error:
        pass


def _play_random(pool: list[pygame.mixer.Sound]) -> None:
    if not pool:
        return
    _play(random.choice(pool))


def _prune_enemy_sfx_channels(enemy) -> None:
    chs = getattr(enemy, "_sfx_channels", None)
    if not chs:
        enemy._sfx_channels = []
        return
    enemy._sfx_channels = [ch for ch in chs if ch.get_busy()]


def stop_enemy_sfx(enemy) -> None:
    """停止該怪物正在播放的音效。"""
    for ch in list(getattr(enemy, "_sfx_channels", ())):
        try:
            ch.stop()
        except pygame.error:
            pass
    enemy._sfx_channels = []


def _play_on_enemy(enemy, sound: pygame.mixer.Sound | None, volume: float | None = None) -> None:
    if sound is None:
        return
    if enemy is not None and not getattr(enemy, "is_alive", True):
        return
    vol = _sfx_volume if volume is None else float(volume)
    try:
        sound.set_volume(max(0.0, min(1.0, vol)))
        if enemy is None:
            sound.play()
            return
        _prune_enemy_sfx_channels(enemy)
        ch = pygame.mixer.find_channel(True)
        if ch is not None:
            ch.play(sound)
            enemy._sfx_channels.append(ch)
        else:
            sound.play()
    except pygame.error:
        pass


def _play_random_at_volume(pool: list[pygame.mixer.Sound], volume: float) -> None:
    if not pool:
        return
    snd = random.choice(pool)
    try:
        snd.set_volume(max(0.0, min(1.0, float(volume))))
        snd.play()
    except pygame.error:
        pass


def play_jump(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_jump_sound)


def play_shot(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_shot_sound)


def play_area_throw(at_rect=None) -> None:
    """發射／甩出面積。"""
    if not _sfx_allowed(at_rect):
        return
    _play(_shot_sound)


def play_explosion(at_rect=None) -> None:
    """放置微分／積分塊。"""
    if not _sfx_allowed(at_rect):
        return
    _play(_explosion_sound)


def play_calculus_place(at_rect=None) -> None:
    play_explosion(at_rect)


def play_pickup(at_rect=None) -> None:
    """拾取音效；短時間內合併，避免連續吃愛心等卡頓。"""
    global _last_pickup_ms
    if not _sfx_allowed(at_rect):
        return
    now_ms = pygame.time.get_ticks()
    if now_ms - _last_pickup_ms < _PICKUP_THROTTLE_MS:
        return
    _last_pickup_ms = now_ms
    _play(_pickup_sound)


def play_flip(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_flip_sound)


def play_calculus_effect(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_calc_effect_sound)


def play_power_up(at_rect=None) -> None:
    """power_up.wav：e^x 觸發、Sigmoid 切換等。"""
    if not _sfx_allowed(at_rect):
        return
    _play(_calc_effect_sound)


def play_sin_stun(at_rect=None, enemy=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play_on_enemy(enemy, _sin_stun_sound)


def _ensure_sin_wing_half_speed() -> None:
    """啟動時先載原速；首次拍翅再重採樣為半速，避免開局黑屏過久。"""
    global _sin_wing_flap_sound, _sin_wing_half_speed_ready
    if _sin_wing_half_speed_ready:
        return
    _sin_wing_half_speed_ready = True
    slowed = _load_sound_playback_speed(
        _AUDIO_DIR / "sin_wing_flap.wav", _SIN_WING_FLAP_SPEED,
    )
    if slowed is not None:
        _sin_wing_flap_sound = slowed


def play_sin_wing_flap(at_rect=None, enemy=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _ensure_sin_wing_half_speed()
    if _sin_wing_flap_sound is None:
        return
    _play_on_enemy(
        enemy,
        _sin_wing_flap_sound,
        _sfx_volume * _SIN_WING_FLAP_VOLUME_MULT,
    )


def play_sin_attack(at_rect=None, enemy=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play_on_enemy(enemy, _sin_attack_sound)


def play_bubble_pop(at_rect=None) -> None:
    """次方 0 啵聲、Sigma 單發 0 等。"""
    if not _sfx_allowed(at_rect) or _bubble_pop_sound is None:
        return
    try:
        _bubble_pop_sound.set_volume(_sfx_volume * _BUBBLE_VOLUME_MULT)
        _bubble_pop_sound.play()
    except pygame.error:
        pass


def start_bubble_repeat(at_rect=None) -> None:
    """Sigma n=0 連發期間循環泡泡音，至 stop_bubble_repeat。"""
    global _bubble_repeat_active
    if not _sfx_allowed(at_rect) or _bubble_pop_sound is None or _bubble_repeat_channel is None:
        return
    _bubble_repeat_active = True
    try:
        _bubble_pop_sound.set_volume(_sfx_volume * _BUBBLE_VOLUME_MULT)
        _bubble_repeat_channel.set_volume(_sfx_volume * _BUBBLE_VOLUME_MULT)
        _bubble_repeat_channel.play(_bubble_pop_sound, loops=-1)
    except pygame.error:
        _bubble_repeat_active = False


def stop_bubble_repeat() -> None:
    global _bubble_repeat_active
    _bubble_repeat_active = False
    if _bubble_repeat_channel is not None:
        try:
            _bubble_repeat_channel.stop()
        except pygame.error:
            pass


def is_bubble_repeat_active() -> bool:
    return _bubble_repeat_active


def play_spike_hit(at_rect=None) -> None:
    """地刺受傷音效；短時間內合併，多怪同時踩刺時減輕卡頓。"""
    global _last_spike_hit_ms
    if not _sfx_allowed(at_rect):
        return
    now_ms = pygame.time.get_ticks()
    if now_ms - _last_spike_hit_ms < _SPIKE_HIT_THROTTLE_MS:
        return
    _last_spike_hit_ms = now_ms
    _play(_spike_hit_sound)


def play_exp_enter(at_rect=None, enemy=None) -> None:
    """e^x 首次出現在視野內。"""
    if not _sfx_allowed(at_rect) or _exp_enter_sound is None:
        return
    _play_on_enemy(
        enemy,
        _exp_enter_sound,
        _sfx_volume * _EXP_ENTER_VOLUME_MULT,
    )


def play_giant_crush(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_giant_crush_sound)


def play_area_rampage(at_rect=None, enemy=None) -> None:
    """65822 對面積暴走射擊。"""
    if not _sfx_allowed(at_rect):
        return
    if _area_rampage_sounds:
        _play_on_enemy(
            enemy,
            random.choice(_area_rampage_sounds),
        )
        return
    play_monster_attack(enemy)


def play_fall(at_rect=None) -> None:
    """長時間下墜或面積被積分往下推。"""
    if not _sfx_allowed(at_rect):
        return
    _play(_fall_sound)


def play_break(at_rect=None) -> None:
    """可破壞牆或面積碎裂。"""
    if not _sfx_allowed(at_rect):
        return
    if _break_sound is None:
        return
    try:
        _break_sound.set_volume(_sfx_volume * _BREAK_VOLUME_MULT)
        _break_sound.play()
    except pygame.error:
        pass


def play_player_death(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play(_player_dead_sound)


def play_player_hurt(at_rect=None) -> None:
    if not _sfx_allowed(at_rect):
        return
    _play_random(_player_hurt_sounds)


def play_enemy_hurt(at_rect=None, enemy=None) -> None:
    """怪物受傷。"""
    if not _sfx_allowed(at_rect):
        return
    _play_on_enemy(enemy, _enemy_hurt_sound)


def play_monster_attack(enemy=None) -> None:
    """怪物攻擊／發射。"""
    if not _monster_attack_sounds:
        return
    if enemy is not None and not getattr(enemy, "is_alive", True):
        return
    snd = random.choice(_monster_attack_sounds)
    _play_on_enemy(enemy, snd)


def play_monster_attack_if_visible(rect, enemy=None) -> None:
    """僅當攻擊發生在畫面內時播放一次攻擊音效。"""
    if not rect_on_screen(rect):
        return
    play_monster_attack(enemy)


def set_underwater_bubbles_active(active: bool) -> None:
    """畫面可見水下裝飾格時循環播放氣泡音，離開則停止。"""
    global _underwater_active
    if _underwater_bubbles is None or _underwater_channel is None:
        return
    if active:
        if not _underwater_active or not _underwater_channel.get_busy():
            try:
                _underwater_bubbles.set_volume(
                    _sfx_volume * _UNDERWATER_BUBBLES_VOLUME_MULT
                )
                _underwater_channel.play(_underwater_bubbles, loops=-1)
                _underwater_active = True
            except pygame.error:
                pass
        return
    if _underwater_active:
        try:
            _underwater_channel.stop()
        except pygame.error:
            pass
        _underwater_active = False


def set_bgm_volume(volume: float) -> None:
    """設定 BGM（設定滑桿值 × 1/4 為實際輸出）。"""
    global _bgm_volume_setting
    _bgm_volume_setting = max(0.0, min(1.0, float(volume)))
    if not _music_loaded:
        return
    try:
        effective = max(0.0, min(1.0, _bgm_volume_setting * _BGM_PLAYBACK_MULT))
        pygame.mixer.music.set_volume(effective)
    except pygame.error:
        pass


def play_random_bgm() -> None:
    """隨機播放一首 BGM（播完後由 handle_bgm_end_event 接下一首）。"""
    global _bgm_last_path
    if not _bgm_paths:
        return
    choices = [p for p in _bgm_paths if p != _bgm_last_path]
    if not choices:
        choices = list(_bgm_paths)
    path = random.choice(choices)
    _bgm_last_path = path
    try:
        pygame.mixer.music.load(str(path))
        set_bgm_volume(_bgm_volume_setting)
        pygame.mixer.music.play()
    except pygame.error:
        pass


def handle_bgm_end_event() -> None:
    """MUSIC_END：隨機播放下一首。"""
    if _music_loaded:
        play_random_bgm()


def start_bgm_loop(volume: float = 0.5) -> None:
    """開局隨機 BGM（非循環單曲）。"""
    global _bgm_volume_setting
    _bgm_volume_setting = max(0.0, min(1.0, float(volume)))
    if not _music_loaded:
        return
    play_random_bgm()


def stop_bgm() -> None:
    try:
        pygame.mixer.music.stop()
    except pygame.error:
        pass
    set_underwater_bubbles_active(False)


def stop_all_ambient() -> None:
    set_underwater_bubbles_active(False)


def stop_all_sfx() -> None:
    """停止所有音效通道（不含 BGM）。"""
    stop_bubble_repeat()
    set_underwater_bubbles_active(False)
    try:
        pygame.mixer.stop()
    except pygame.error:
        pass
