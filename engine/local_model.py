"""Download and check local hearing/translation models in the user's local app-data cache.

The app carries runtimes, while Settings downloads each model separately. Pinned files are
checked against SHA-256 before use and interrupted downloads resume. Whisper turbo uses
cuBLAS; PhoWhisper, SenseVoice, NLLB and Qwen run on CPU. Source installs can use faster-whisper's
own turbo cache with the NVIDIA packages installed through requirements.txt.
"""
from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NAME = "Whisper"
BLOCK = 1 << 20
TRIES = 5                 # a connection that breaks this often in a row, without a byte arriving, ends it
WAITING = "downloading"   # unfinished downloads wait in this folder


class DownloadError(Exception):
    """The download did not finish; the message says why in plain words."""


class Stopped(DownloadError):
    """The user stopped it. What arrived so far is kept for the next time."""


@dataclass(frozen=True)
class Part:
    url: str
    size: int                 # bytes to download
    sha256: str               # of the download
    place: str = ""           # where it goes in the folder; or, for a zip:
    unzip: tuple[tuple[str, str, int], ...] = ()    # (name in the zip, where it goes, its size)

    @property
    def name(self) -> str:
        return self.url.rsplit("/", 1)[-1]

    def files(self) -> tuple[tuple[str, int], ...]:
        """(place, size) of every file this part leaves in the folder."""
        return tuple((place, size) for _, place, size in self.unzip) or ((self.place, self.size),)


_WHISPER = ("https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo/resolve/"
            "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/")
PARTS = (
    # of the 2 GB of NVIDIA libraries the source version installs, the model loads these two files
    Part("https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/"
         "nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl", 553162896,
         "623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661",
         unzip=(("nvidia/cublas/bin/cublas64_12.dll", "gpu/cublas64_12.dll", 102518272),
                ("nvidia/cublas/bin/cublasLt64_12.dll", "gpu/cublasLt64_12.dll", 668673536))),
    Part(_WHISPER + "config.json", 2263,
         "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e", "whisper/config.json"),
    Part(_WHISPER + "preprocessor_config.json", 340,
         "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711", "whisper/preprocessor_config.json"),
    Part(_WHISPER + "tokenizer.json", 2710337,
         "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd", "whisper/tokenizer.json"),
    Part(_WHISPER + "vocabulary.json", 1068114,
         "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1", "whisper/vocabulary.json"),
    Part(_WHISPER + "model.bin", 1617884929,
         "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da", "whisper/model.bin"),
)


# id: (display name, role, directory, runtime)
MODELS = {
    "large-v3-turbo": ("Whisper large-v3-turbo", "hearing", "whisper", "faster_whisper"),
    "sensevoice": ("SenseVoice Small", "hearing", "sensevoice", "sherpa_onnx"),
    "phowhisper-small": ("PhoWhisper Small", "hearing", "phowhisper-small", "faster_whisper"),
    "nllb-200-ct2": ("NLLB-200 · CTranslate2", "translating", "nllb", "ctranslate2"),
    "qwen3-1.7b-ct2": ("Qwen3 1.7B · INT8", "translating", "qwen3-1.7b", "ctranslate2"),
}
DESCRIPTIONS = {
    "large-v3-turbo": "English, Chinese, Cantonese, Vietnamese, Japanese and Korean. Fast NVIDIA GPU option for multilingual conversations; mixed-language sentences can still be misheard.",
    "sensevoice": "Chinese, Cantonese, English, Japanese and Korean; no Vietnamese. Lightweight CPU option with automatic language detection. Mixed-language accuracy varies.",
    "phowhisper-small": "Vietnamese specialist, trained on diverse Vietnamese accents. Runs on CPU without NVIDIA; may be slower than GPU turbo. Choose turbo for other languages or mixed-language conversations.",
    "nllb-200-ct2": "English, Chinese, Cantonese, Vietnamese, Japanese and Korean. Translation-focused CPU model; keep this as the low-latency starting choice.",
    "qwen3-1.7b-ct2": "English, Chinese, Cantonese, Vietnamese, Japanese and Korean. Small CPU language-model alternative, with thinking disabled. May be slower or less accurate than NLLB; compare your language pair.",
}
_MODEL_FILES = json.loads((Path(__file__).parent / "assets" / "local_models.json").read_text(encoding="utf-8"))
REMOVED_MODELS = {"large-v3": ("Whisper large-v3", "whisper-v3")}


def selected(role: str = "hearing") -> str:
    from . import services
    default = "large-v3-turbo" if role == "hearing" else "nllb-200-ct2"
    name = services.setting("local", "hear_model" if role == "hearing" else "translate_model")
    return name if name in MODELS and MODELS[name][1] == role else default


def select(model: str) -> str:
    from . import services
    role = MODELS[model][1]
    services.save("local", **{"hear_model" if role == "hearing" else "translate_model": model})
    return role


def parts(model: str | None = None) -> tuple[Part, ...]:
    model = model or selected()
    if model == "large-v3-turbo":
        return PARTS
    return tuple(Part(**part) for part in _MODEL_FILES[model])


def model_folder(model: str | None = None) -> Path:
    return folder() / MODELS[model or selected()][2]


def folder() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "local-model"


def gb(count: float) -> str:
    return f"{count / 2**30:.1f} GB"


def _has(part: Part, root: Path) -> bool:
    try:
        return all((root / place).stat().st_size == size for place, size in part.files())
    except OSError:
        return False


def ready(root: Path | None = None, *, model: str | None = None) -> bool:
    """Every file is in place (each was checked when it arrived)."""
    root = root or folder()
    return all(_has(part, root) for part in parts(model))


def size(model: str | None = None) -> int:
    """Bytes of the whole download."""
    return sum(part.size for part in parts(model))


def arrived(root: Path | None = None, *, model: str | None = None) -> int:
    """Bytes that are here already: whole parts, and the start of one that broke off."""
    root = root or folder()
    model = model or selected()
    waiting = root / WAITING if model == "large-v3-turbo" else root / WAITING / model
    count = 0
    for part in parts(model):
        if _has(part, root):
            count += part.size
        else:
            try:
                count += min((waiting / part.name).stat().st_size, part.size)
            except OSError:
                pass
    return count


def _owned_files(model: str) -> list[Path]:
    """Only this model's installed files and partial downloads, never shared GPU libraries."""
    root = folder().absolute()
    if model in REMOVED_MODELS:
        directory = REMOVED_MODELS[model][1]
        names = ("config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json", "model.bin")
        return [root / directory / name for name in names] + [root / WAITING / model / name for name in names]
    directory = MODELS[model][2]  # Reject unknown model IDs before touching the filesystem.
    waiting = root / WAITING if model == "large-v3-turbo" else root / WAITING / model
    files = []
    for part in parts(model):
        owned = [place for place, _ in part.files() if Path(place).parts[0] == directory]
        if owned:
            files.extend(root / place for place in owned)
            files.append(waiting / part.name)
    return files


def has_files(model: str) -> bool:
    return any(path.exists() or path.is_symlink() for path in _owned_files(model))


def delete(model: str) -> None:
    """Remove app-managed weights/partials; callers must stop downloads first."""
    files = _owned_files(model)
    try:
        root = folder().resolve()
        # Validate every target before deleting any file, including junctions and symlinks.
        for path in files:
            relative = path.relative_to(folder().absolute())
            expected = root / relative
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or resolved != expected or path.is_symlink():
                raise DownloadError("Model files point outside their expected folder; nothing was deleted")
    except (OSError, RuntimeError, ValueError) as error:
        raise DownloadError(f"Could not check model file paths; nothing was deleted: {error}") from error
    try:
        if model == "large-v3-turbo":
            # Explicit deletion must not trigger faster-whisper's automatic cache download.
            root.mkdir(parents=True, exist_ok=True)
            (root / "whisper.deleted").touch()
        for path in files:
            path.unlink(missing_ok=True)
        for parent in {path.parent for path in files}:
            try:
                parent.rmdir()  # Only empty folders; other models and unknown files stay intact.
            except OSError:
                pass
    except OSError as error:
        raise DownloadError(f"Could not delete model files. Stop using the model and try again: {error}") from error


# ---- can it run here? ----------------------------------------------------------------------

def installed(model: str | None = None) -> bool:
    """Whether this copy includes the chosen model's runtime."""
    return importlib.util.find_spec(MODELS[model or selected()][3]) is not None


@lru_cache(maxsize=1)
def nvidia_card() -> bool:
    """NVIDIA's driver is installed (it brings nvcuda.dll), as required for local Whisper."""
    try:
        ctypes.WinDLL("nvcuda.dll")
    except (OSError, AttributeError):      # AttributeError: not Windows
        return False
    return True


def gpu_folders() -> list[str]:
    """The folders that hold cuBLAS: the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12 or
    PyTorch (from source), and this download."""
    folders = []
    for package, sub in (("nvidia.cublas", "bin"), ("nvidia.cudnn", "bin"), ("torch", "lib")):
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            spec = None
        for location in (spec.submodule_search_locations or []) if spec else []:
            place = Path(location) / sub
            if place.is_dir():
                folders.append(str(place))
    if _has(PARTS[0], folder()):
        folders.append(str(folder() / "gpu"))
    return folders


def missing(model: str | None = None) -> str:
    """What the selected model lacks before it can run."""
    model = model or selected()
    if not installed(model):
        return "this copy has no Local Model runtime: install its dependencies or choose an online service in Settings → Models"
    if model == "large-v3-turbo":
        if not nvidia_card():
            return "the Local Model needs an NVIDIA graphics card, and this PC has none"
        if gpu_folders() and not (folder() / "whisper.deleted").exists():
            return ""  # Existing source installs let faster-whisper fetch its cached model.
    if not ready(model=model):
        return "the Local Model is not downloaded yet (Settings → Models)"
    return ""


# ---- the download --------------------------------------------------------------------------

def download(progress=lambda done, total: None, stop=lambda: False, http=None,
             root: Path | None = None, wait=time.sleep, model: str | None = None) -> None:
    """Fetches the parts that are missing. `progress(done, total)` is told the bytes that are
    here; when `stop()` turns true the download ends with Stopped. Any other reason it can't
    finish is a DownloadError."""
    root = root or folder()
    model = model or selected()
    waiting = root / WAITING if model == "large-v3-turbo" else root / WAITING / model
    total = size(model)
    todo = [part for part in parts(model) if not _has(part, root)]
    done = total - sum(part.size for part in todo)
    try:
        waiting.mkdir(parents=True, exist_ok=True)
        _check_room(todo, waiting)
        if http is None and todo:
            import httpx
            http = httpx.Client(timeout=httpx.Timeout(20, read=30), follow_redirects=True)
        for part in todo:
            file = waiting / part.name
            _fetch(http, part, file, lambda have: progress(done + have, total), stop, wait)
            if _sha256(file, stop) != part.sha256:
                file.unlink()
                raise DownloadError(f"{part.name} arrived damaged and was thrown away; download again")
            _put(part, file, root)
            done += part.size
            progress(done, total)
        try:
            waiting.rmdir()
        except OSError:
            pass
    except (OSError, zipfile.BadZipFile) as error:
        raise DownloadError(f"the files could not be written: {error}") from error


def _check_room(todo: list[Part], waiting: Path) -> None:
    """A zip needs room for itself and for what comes out of it."""
    need = 0
    for part in todo:
        try:
            have = (waiting / part.name).stat().st_size
        except OSError:
            have = 0
        need += max(part.size - have, 0) + sum(size for _, _, size in part.unzip)
    free = shutil.disk_usage(waiting).free
    if free < need:
        drive = waiting.drive or str(waiting)
        raise DownloadError(f"not enough free space on {drive}: {gb(need)} are needed, {gb(free)} are free")


def _fetch(http, part: Part, file: Path, progress, stop, wait) -> None:
    """Downloads `part` into `file`, continuing after what is already there."""
    url = part.url
    mirror = ("https://hf-mirror.com/" + url.removeprefix("https://huggingface.co/")
              if url.startswith("https://huggingface.co/") else "")
    failures = 0
    while True:
        if stop():
            raise Stopped("stopped")
        host = url.split("/")[2]
        have = file.stat().st_size if file.exists() else 0
        if have > part.size:
            file.unlink()                       # not this file's beginning: start over
            have = 0
        if have == part.size:
            return
        before, problem = have, "it sent nothing"
        try:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with http.stream("GET", url, headers=headers) as answer:
                if answer.status_code == 200:
                    have = 0                    # the server sends everything again
                elif answer.status_code != 206:
                    if mirror and url != mirror:
                        logging.getLogger(__name__).warning(
                            "%s refused %s (HTTP %s); trying hf-mirror.com", host, part.name, answer.status_code)
                        url = mirror
                        continue
                    raise DownloadError(f"{host} refused the download (error {answer.status_code})")
                try:
                    out = open(file, "ab" if have else "wb")
                except OSError as error:
                    raise DownloadError(f"the files could not be written: {error}") from error
                with out:
                    for block in answer.iter_bytes(BLOCK):
                        if stop():
                            raise Stopped("stopped")
                        try:
                            out.write(block)
                        except OSError as error:
                            raise DownloadError(f"the files could not be written: {error}") from error
                        have += len(block)
                        progress(have)
            if have > part.size:
                file.unlink()
                raise DownloadError(f"{part.name} arrived with the wrong size and was thrown away; download again")
        except DownloadError:
            raise
        except Exception as error:              # the connection broke: go on from where it was
            problem = str(error) or type(error).__name__
        if stop():
            raise Stopped("stopped")
        if have >= part.size:
            continue
        if mirror and url != mirror:
            logging.getLogger(__name__).warning(
                "%s download of %s interrupted; trying hf-mirror.com", host, part.name)
            url = mirror
            continue
        failures = 0 if have > before else failures + 1
        if failures >= TRIES:
            raise DownloadError(f"the connection to {host} keeps breaking ({problem}); "
                                "download again to continue from here")
        wait(2 * max(failures, 1))


def _sha256(file: Path, stop) -> str:
    digest = hashlib.sha256()
    with open(file, "rb") as source:
        for block in iter(lambda: source.read(BLOCK), b""):
            if stop():
                raise Stopped("stopped")
            digest.update(block)
    return digest.hexdigest()


def _put(part: Part, file: Path, root: Path) -> None:
    """Moves a checked download to its place. Of a zip, only the files named in `unzip` stay."""
    if not part.unzip:
        target = root / part.place
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(file, target)
        return
    with zipfile.ZipFile(file) as archive:
        for name, place, _ in part.unzip:
            target = root / place
            target.parent.mkdir(parents=True, exist_ok=True)
            half = target.with_name(target.name + ".part")
            with archive.open(name) as source, open(half, "wb") as out:
                shutil.copyfileobj(source, out, BLOCK)
            os.replace(half, target)
    file.unlink()
    if not _has(part, root):
        raise DownloadError(f"{part.name} does not hold the files it should; download again")
