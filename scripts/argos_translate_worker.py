import contextlib
import io
import json
import os
import sys


def write_response(payload: dict) -> None:
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        raw_request = sys.stdin.buffer.read().decode("utf-8")
        request = json.loads(raw_request)
        if not isinstance(request, dict):
            raise RuntimeError("request must be a JSON object")

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
            from argostranslate import translate as argos_translate

            translated = argos_translate.translate(text, from_code, to_code)

        write_response({"ok": True, "text": translated})
        return 0
    except Exception as exc:
        write_response({"ok": False, "error": str(exc)})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
