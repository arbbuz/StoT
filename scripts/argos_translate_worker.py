import contextlib
import io
import json
import os
import sys

_ARGOS_TRANSLATE = None
_TRANSLATION_CACHE = {}


def write_response(payload: dict) -> None:
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def translate_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise RuntimeError("request must be a JSON object")

    if request.get("command") == "shutdown":
        return {"ok": True, "shutdown": True}

    packages_dir = request.get("packages_dir")
    if packages_dir:
        os.environ["ARGOS_PACKAGES_DIR"] = str(packages_dir)
    os.environ.setdefault("ARGOS_DEBUG", "0")
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")

    text = str(request.get("text", ""))
    from_code = str(request.get("from_code", "en"))
    to_code = str(request.get("to_code", "ru"))

    captured_stdout = io.StringIO()
    with contextlib.redirect_stdout(captured_stdout):
        translated = get_translation(from_code, to_code).translate(text)

    return {"ok": True, "text": translated}


def get_translation(from_code: str, to_code: str):
    global _ARGOS_TRANSLATE

    if _ARGOS_TRANSLATE is None:
        from argostranslate import translate as argos_translate

        _ARGOS_TRANSLATE = argos_translate

    key = (from_code, to_code)
    translation = _TRANSLATION_CACHE.get(key)
    if translation is None:
        translation = _ARGOS_TRANSLATE.get_translation_from_codes(from_code, to_code)
        if translation is None:
            raise RuntimeError(f"missing translation direction: {from_code}->{to_code}")
        _TRANSLATION_CACHE[key] = translation
    return translation


def handle_raw_request(raw_request: str) -> dict:
    request = json.loads(raw_request)
    response = translate_request(request)
    if isinstance(request, dict) and "id" in request:
        response["id"] = request["id"]
    return response


def run_persistent() -> int:
    for raw_line in sys.stdin.buffer:
        raw_request = raw_line.decode("utf-8").strip()
        if not raw_request:
            continue
        try:
            response = handle_raw_request(raw_request)
            write_response(response)
            if response.get("shutdown"):
                return 0
        except Exception as exc:
            write_response({"ok": False, "error": str(exc)})
    return 0


def run_once() -> int:
    try:
        raw_request = sys.stdin.buffer.read().decode("utf-8")
        write_response(handle_raw_request(raw_request))
        return 0
    except Exception as exc:
        write_response({"ok": False, "error": str(exc)})
        return 0


def main() -> int:
    if "--persistent" in sys.argv[1:]:
        return run_persistent()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
