"""Simple web UI and service manager for Fluke 187 serial simulators."""

from __future__ import annotations

import argparse
import html
import json
import threading
import time
import traceback
import urllib.parse
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

from fluke187_simulator import (
    DEFAULT_RANDOM_PROFILES,
    Fluke187Simulator,
    ReadingMode,
)


MAX_LOG_ENTRIES = 100


@dataclass
class SerialServiceConfig:
    port: str
    baudrate: int = 9600
    timeout: float = 1.0
    reading_mode: ReadingMode = ReadingMode.FIXED
    random_profile_name: str = "voltage_dc"
    seed: Optional[int] = None


@dataclass
class SerialServiceRecord:
    id: int
    config: SerialServiceConfig
    status: str = "starting"
    started_at: float = field(default_factory=time.time)
    stopped_at: Optional[float] = None
    last_activity_at: Optional[float] = None
    request_count: int = 0
    response_count: int = 0
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    thread: Optional[threading.Thread] = field(default=None, repr=False)

    def append_log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.logs.append(f"{timestamp} {message}")
        if len(self.logs) > MAX_LOG_ENTRIES:
            del self.logs[: len(self.logs) - MAX_LOG_ENTRIES]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "port": self.config.port,
            "baudrate": self.config.baudrate,
            "timeout": self.config.timeout,
            "reading_mode": self.config.reading_mode.value,
            "random_profile_name": self.config.random_profile_name,
            "seed": self.config.seed,
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_activity_at": self.last_activity_at,
            "request_count": self.request_count,
            "response_count": self.response_count,
            "error": self.error,
            "logs": list(self.logs),
        }


class SerialServiceManager:
    """Starts and tracks simulator workers, one per active serial port."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[int, SerialServiceRecord] = {}
        self._next_id = 1

    def list_records(self) -> List[dict]:
        with self._lock:
            return [record.to_dict() for record in self._records.values()]

    def reserved_ports(self) -> set[str]:
        with self._lock:
            return {record.config.port for record in self._records.values()}

    def active_ports(self) -> set[str]:
        with self._lock:
            return {
                record.config.port
                for record in self._records.values()
                if record.status in {"starting", "running"}
            }

    def available_ports(self) -> List[str]:
        ports = list_serial_ports()
        reserved = self.reserved_ports()
        return [port for port in ports if port not in reserved]

    def start_service(self, config: SerialServiceConfig) -> SerialServiceRecord:
        if not config.port:
            raise ValueError("port is required")

        with self._lock:
            if config.port in self.active_ports():
                raise ValueError(f"{config.port} is already running")

            record = SerialServiceRecord(id=self._next_id, config=config)
            self._next_id += 1
            thread = threading.Thread(
                target=self._run_service,
                args=(record,),
                name=f"fluke187-{record.id}-{config.port}",
                daemon=True,
            )
            record.thread = thread
            self._records[record.id] = record
            record.append_log("service queued")
            thread.start()
            return record

    def stop_service(self, record_id: int) -> SerialServiceRecord:
        record = self._get_record(record_id)
        with self._lock:
            if record.status in {"stopped", "error"}:
                return record
            record.status = "stopping"
            record.stop_event.set()
            record.append_log("stop requested")
        return record

    def delete_service(self, record_id: int) -> None:
        record = self._get_record(record_id)
        with self._lock:
            if record.status in {"starting", "running", "stopping"}:
                raise ValueError("stop the service before deleting it")
            del self._records[record_id]

    def _get_record(self, record_id: int) -> SerialServiceRecord:
        with self._lock:
            try:
                return self._records[record_id]
            except KeyError as exc:
                raise ValueError("service was not found") from exc

    def _run_service(self, record: SerialServiceRecord) -> None:
        try:
            import serial  # type: ignore
        except ImportError:
            with self._lock:
                record.status = "error"
                record.error = "pyserial is required. Install it with: pip install pyserial"
                record.stopped_at = time.time()
                record.append_log(record.error)
            return

        simulator = Fluke187Simulator(
            reading_mode=record.config.reading_mode,
            random_profile_name=record.config.random_profile_name,
            seed=record.config.seed,
        )

        try:
            with serial.Serial(
                port=record.config.port,
                baudrate=record.config.baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=record.config.timeout,
            ) as conn:
                with self._lock:
                    record.status = "running"
                    record.append_log("service started")

                while not record.stop_event.is_set():
                    response = simulator.serve_once(conn)
                    if response is None:
                        continue
                    with self._lock:
                        record.request_count += 1
                        record.response_count += 1
                        record.last_activity_at = time.time()
                        record.append_log(f"response: {response.strip()}")

        except Exception as exc:  # worker must capture serial/runtime errors for UI visibility
            with self._lock:
                record.status = "error"
                record.error = str(exc)
                record.stopped_at = time.time()
                record.append_log("error: " + str(exc))
                record.append_log(traceback.format_exc().splitlines()[-1])
            return

        with self._lock:
            record.status = "stopped"
            record.stopped_at = time.time()
            record.append_log("service stopped")


def list_serial_ports() -> List[str]:
    """Return serial device names when pyserial is installed, otherwise an empty list."""

    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []

    return sorted(port.device for port in list_ports.comports())


MANAGER = SerialServiceManager()


class FlukeWebHandler(BaseHTTPRequestHandler):
    server_version = "Fluke187Web/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_index())
            return
        if parsed.path == "/api/state":
            self._send_json(api_state())
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/services":
                payload = self._read_json()
                record = MANAGER.start_service(parse_config(payload))
                self._send_json(record.to_dict(), HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/services/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 3:
                    record_id = int(parts[2])
                    record = MANAGER.stop_service(record_id)
                    self._send_json(record.to_dict())
                    return
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        try:
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "services"]:
                MANAGER.delete_service(int(parts[2]))
                self._send_json({"ok": True})
                return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def parse_config(payload: dict) -> SerialServiceConfig:
    seed_value = payload.get("seed")
    return SerialServiceConfig(
        port=str(payload.get("port", "")).strip(),
        baudrate=int(payload.get("baudrate", 9600)),
        timeout=float(payload.get("timeout", 1.0)),
        reading_mode=ReadingMode(payload.get("reading_mode", ReadingMode.FIXED.value)),
        random_profile_name=str(payload.get("random_profile_name", "voltage_dc")),
        seed=int(seed_value) if str(seed_value).strip() else None,
    )


def api_state() -> dict:
    return {
        "records": MANAGER.list_records(),
        "available_ports": MANAGER.available_ports(),
        "reading_modes": [mode.value for mode in ReadingMode],
        "random_profiles": sorted(DEFAULT_RANDOM_PROFILES.keys()),
    }


def render_index() -> str:
    profiles = "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
        for name in sorted(DEFAULT_RANDOM_PROFILES.keys())
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fluke 187 Simulator Services</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f6f8fb; color: #1f2937; }}
header {{ margin-bottom: 1rem; }}
table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px #0002; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: .65rem; text-align: left; vertical-align: top; }}
th {{ background: #eef2ff; }}
tr.editor {{ background: #fbfdff; }}
input, select, button {{ padding: .4rem; }}
button {{ cursor: pointer; }}
.status-running {{ color: #047857; font-weight: 700; }}
.status-error {{ color: #b91c1c; font-weight: 700; }}
.status-stopped {{ color: #6b7280; font-weight: 700; }}
.log {{ white-space: pre-wrap; max-height: 12rem; overflow: auto; font-family: ui-monospace, monospace; font-size: .85rem; }}
.notice {{ color: #6b7280; }}
.actions {{ display: flex; gap: .35rem; flex-wrap: wrap; }}
</style>
</head>
<body>
<header>
<h1>Fluke 187 Simulator Services</h1>
<p class="notice">複数のシリアルポートでサービスを開始・停止できます。稼働中または履歴に残るポートは新規選択肢から除外されます。</p>
</header>
<table>
<thead><tr><th>ID</th><th>シリアルポート</th><th>設定</th><th>状態</th><th>通信</th><th>操作 / 詳細</th></tr></thead>
<tbody id="records"></tbody>
<tbody><tr class="editor"><td>新規</td><td><select id="port"></select><br><input id="manualPort" placeholder="手入力 COM3 / /dev/ttyUSB0"></td><td>
<label>baud <input id="baudrate" type="number" value="9600"></label><br>
<label>timeout <input id="timeout" type="number" step="0.1" value="1.0"></label><br>
<label>mode <select id="reading_mode"><option>fixed</option><option>random</option></select></label><br>
<label>profile <select id="random_profile_name">{profiles}</select></label><br>
<label>seed <input id="seed" type="number" placeholder="任意"></label>
</td><td colspan="2" class="notice">新規サービス設定は末尾のこの行からのみ追加できます。</td><td><button id="start">開始</button></td></tr></tbody>
</table>
<script>
const recordsEl = document.getElementById('records');
const portEl = document.getElementById('port');
function fmt(ts) {{ return ts ? new Date(ts * 1000).toLocaleString() : '-'; }}
function esc(value) {{ return String(value ?? '').replace(/[&<>\"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c])); }}
async function load() {{
  const state = await fetch('/api/state').then(r => r.json());
  portEl.innerHTML = state.available_ports.map(p => `<option value="${{esc(p)}}">${{esc(p)}}</option>`).join('');
  if (!portEl.innerHTML) portEl.innerHTML = '<option value="">検索結果なし（手入力可）</option>';
  recordsEl.innerHTML = state.records.map(r => `
    <tr>
      <td>${{r.id}}</td><td>${{esc(r.port)}}</td>
      <td>${{r.baudrate}} baud<br>${{r.timeout}} sec<br>${{esc(r.reading_mode)}} / ${{esc(r.random_profile_name)}}<br>seed: ${{r.seed ?? '-'}}</td>
      <td class="status-${{r.status}}">${{esc(r.status)}}<br><small>開始: ${{fmt(r.started_at)}}<br>停止: ${{fmt(r.stopped_at)}}</small>${{r.error ? `<br><strong>${{esc(r.error)}}</strong>` : ''}}</td>
      <td>requests: ${{r.request_count}}<br>responses: ${{r.response_count}}<br>last: ${{fmt(r.last_activity_at)}}</td>
      <td><div class="actions"><button onclick="stopService(${{r.id}})" ${{['stopped','error'].includes(r.status) ? 'disabled' : ''}}>停止</button><button onclick="deleteService(${{r.id}})" ${{['starting','running','stopping'].includes(r.status) ? 'disabled' : ''}}>削除</button></div><details><summary>ログ</summary><div class="log">${{esc(r.logs.join('\n'))}}</div></details></td>
    </tr>`).join('');
}}
async function startService() {{
  const manual = document.getElementById('manualPort').value.trim();
  const payload = {{
    port: manual || portEl.value,
    baudrate: document.getElementById('baudrate').value,
    timeout: document.getElementById('timeout').value,
    reading_mode: document.getElementById('reading_mode').value,
    random_profile_name: document.getElementById('random_profile_name').value,
    seed: document.getElementById('seed').value,
  }};
  const res = await fetch('/api/services', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(payload)}});
  if (!res.ok) alert((await res.json()).error || 'start failed');
  await load();
}}
async function stopService(id) {{ await fetch(`/api/services/${{id}}`, {{method:'POST'}}); await load(); }}
async function deleteService(id) {{ const res = await fetch(`/api/services/${{id}}`, {{method:'DELETE'}}); if (!res.ok) alert((await res.json()).error); await load(); }}
document.getElementById('start').addEventListener('click', startService);
load(); setInterval(load, 3000);
</script>
</body>
</html>"""


def run_web_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), FlukeWebHandler)
    print(f"Serving Fluke 187 simulator UI on http://{host}:{port}")
    httpd.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fluke 187 simulator web UI")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_web_server(args.host, args.port)


if __name__ == "__main__":
    main()
