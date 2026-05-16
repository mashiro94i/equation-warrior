"""BGM／音效（assets/audio；檔案缺失或 pygame 錯誤時略過）。"""
from __future__ import annotations

import random
from pathlib import Path

import pygame

_AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio"

_jump_sound: pygame.mixer.Sound | None = None
_shot_sound: pygame.mixer.Sound | None = None
_explosion_sound: pygame.mixer.Sound | None = None
_calc_effect_sound: pygame.mixer.Sound | None = None
_pickup_sound: pygame.mixer.Sound | None = None
_flip_sound: pygame.mixer.Sound | None = None
_fall_sound: pygame.mixer.Sound | None = None
_break_sound: pygame.mixer.Sound | None = None
_player_dead_sound: pygame.mixer.Sound | None = None
_player_hurt_sounds: list[pygame.mixer.Sound] = []
_monster_attack_sounds: list[pygame.mixer.Sound] = []
_sfx_volume = 1.0
_initialized = False
_music_loaded = False
_BREAK_VOLUME_MULT = 0.45


def _load_sound(path: Path) -> pygame.mixer.Sound | None:
    if not path.is_file():
        return None
    try:
        return pygame.mixer.Sound(str(path))
    except pygame.error:
        return None


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
    global _player_dead_sound, _player_hurt_sounds, _monster_attack_sounds, _music_loaded
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
    _player_dead_sound = _load_sound(_AUDIO_DIR / "player_dead.wav")
    _player_hurt_sounds = _load_wavs_from_dir(_AUDIO_DIR / "player_take_damage")
    _monster_attack_sounds = _load_wavs_from_dir(_AUDIO_DIR / "monster_attack")
    mp = _AUDIO_DIR / "music2.mp3"
    if mp.is_file():
        try:
            pygame.mixer.music.load(str(mp))
            _music_loaded = True
        except pygame.error:
            _music_loaded = False


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
    for snd in _player_hurt_sounds + _monster_attack_sounds:
        snd.set_volume(_sfx_volume)


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


def play_jump() -> None:
    _play(_jump_sound)


def play_shot() -> None:
    _play(_shot_sound)


def play_area_throw() -> None:
    """發射／甩出面積。"""
    _play(_shot_sound)


def play_explosion() -> None:
    """放置微分／積分塊。"""
    _play(_explosion_sound)


def play_calculus_place() -> None:
    play_explosion()


def play_pickup() -> None:
    _play(_pickup_sound)


def play_flip() -> None:
    _play(_flip_sound)


def play_calculus_effect() -> None:
    _play(_calc_effect_sound)


def play_fall() -> None:
    """長時間下墜或面積被積分往下推。"""
    _play(_fall_sound)


def play_break() -> None:
    """可破壞牆或面積碎裂。"""
    if _break_sound is None:
        return
    try:
        _break_sound.set_volume(_sfx_volume * _BREAK_VOLUME_MULT)
        _break_sound.play()
    except pygame.error:
        pass


def play_player_death() -> None:
    _play(_player_dead_sound)


def play_player_hurt() -> None:
    _play_random(_player_hurt_sounds)


def play_monster_attack() -> None:
    _play_random(_monster_attack_sounds)


def start_bgm_loop(volume: float = 0.5) -> None:
    if not _music_loaded:
        return
    try:
        pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
        pygame.mixer.music.play(-1)
    except pygame.error:
        pass


def stop_bgm() -> None:
    try:
        pygame.mixer.music.stop()
    except pygame.error:
        pass
