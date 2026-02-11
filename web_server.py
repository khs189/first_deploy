from __future__ import annotations

import configparser
import io
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from app.api_client import call_juso_api, verify_credentials
from app.excel_io import collect_target_rows, load_sheet
from app.normalize import (
    build_road_address_and_zip,
    normalize_region_prefix,
    prepare_api_keyword,
    split_base_detail,
)


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "runtime" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MSG_COMPLETE = "주소 정제가 완료되었습니다. 다운로드하세요."


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(BASE_DIR / "config.ini", encoding="utf-8")
    return cfg


@dataclass
class JobState:
    job_id: str
    owner: str
    source_name: str
    wb: object
    ws: object
    targets: list[int]
    total: int
    done: int = 0
    running: bool = False
    completed: bool = False
    stopped: bool = False
    error: str = ""
    message: str = "파일 업로드 완료. 시작 버튼을 누르세요."
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    wb_lock: threading.Lock = field(default_factory=threading.Lock)
    worker: Optional[threading.Thread] = None

    def to_dict(self) -> dict:
        with self.lock:
            done = self.done
            total = self.total
            running = self.running
            completed = self.completed
            stopped = self.stopped
            error = self.error
            message = self.message
            source_name = self.source_name

        percent = int((done / total) * 100) if total > 0 else 0
        can_download = done > 0
        can_start = (not running) and (done < total) and (not error)
        return {
            "job_id": self.job_id,
            "source_name": source_name,
            "done": done,
            "total": total,
            "percent": percent,
            "running": running,
            "completed": completed,
            "stopped": stopped,
            "error": error,
            "message": message,
            "can_download": can_download,
            "can_start": can_start,
        }


app = Flask(__name__)
initial_cfg = load_config()
app.secret_key = initial_cfg.get("web", "secret_key", fallback="change-this-secret-in-production")

jobs: Dict[str, JobState] = {}
jobs_lock = threading.Lock()
user_latest_job: Dict[str, str] = {}


def current_user() -> Optional[str]:
    user = session.get("user")
    if isinstance(user, str) and user:
        return user
    return None


def get_user_job(user: str, job_id: str) -> Optional[JobState]:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None or job.owner != user:
        return None
    return job


@app.get("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))


@app.get("/login")
def login_page():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html", error="")


@app.post("/login")
def login_action():
    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    ok, message = verify_credentials(load_config(), username, password)
    if not ok:
        return render_template("login.html", error=message), 401

    session["user"] = username
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout_action():
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/app")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    job_id = user_latest_job.get(user, "")
    return render_template("app.html", username=user, job_id=job_id)


@app.post("/api/upload")
def upload_file():
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"ok": False, "message": "업로드할 파일을 선택하세요."}), 400

    filename = secure_filename(uploaded.filename)
    if not filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "message": "xlsx 파일만 업로드할 수 있습니다."}), 400

    with jobs_lock:
        previous = user_latest_job.get(user)
        if previous and previous in jobs and jobs[previous].running:
            return jsonify({"ok": False, "message": "진행 중인 작업이 있습니다. 먼저 중지하거나 완료하세요."}), 409

    saved_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{filename}"
    uploaded.save(saved_path)

    try:
        wb, ws = load_sheet(str(saved_path))
        targets = collect_target_rows(ws, start_row=2)
    except Exception as exc:
        return jsonify({"ok": False, "message": f"엑셀 파일을 읽지 못했습니다: {exc}"}), 400

    if not targets:
        return jsonify({"ok": False, "message": "A열에 정제할 주소가 없습니다."}), 400

    job_id = uuid.uuid4().hex
    job = JobState(
        job_id=job_id,
        owner=user,
        source_name=filename,
        wb=wb,
        ws=ws,
        targets=targets,
        total=len(targets),
        message=f"업로드 완료. 정제 대상 {len(targets)}건",
    )

    with jobs_lock:
        jobs[job_id] = job
        user_latest_job[user] = job_id

    return jsonify({"ok": True, "message": job.message, "job": job.to_dict()})


@app.post("/api/jobs/<job_id>/start")
def start_job(job_id: str):
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401

    job = get_user_job(user, job_id)
    if job is None:
        return jsonify({"ok": False, "message": "작업을 찾을 수 없습니다."}), 404

    response_message = "작업 상태를 확인하세요."
    with job.lock:
        if job.running:
            response_message = "이미 작업이 진행 중입니다."
        elif job.done >= job.total:
            job.completed = True
            job.message = MSG_COMPLETE
            response_message = MSG_COMPLETE
        elif job.error:
            return jsonify({"ok": False, "message": f"오류 상태입니다: {job.error}"}), 400
        else:
            job.stop_event.clear()
            job.running = True
            job.stopped = False
            job.message = "변환 진행 중..."
            job.worker = threading.Thread(target=run_job_worker, args=(job,), daemon=True)
            job.worker.start()
            response_message = "작업을 시작했습니다."

    return jsonify({"ok": True, "message": response_message, "job": job.to_dict()})


@app.post("/api/jobs/<job_id>/stop")
def stop_job(job_id: str):
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401

    job = get_user_job(user, job_id)
    if job is None:
        return jsonify({"ok": False, "message": "작업을 찾을 수 없습니다."}), 404

    response_message = "이미 중지 상태입니다."
    with job.lock:
        if job.running:
            job.stop_event.set()
            job.message = "중지 요청됨. 현재 요청 처리 후 멈춥니다."
            response_message = "중지 요청을 보냈습니다."

    return jsonify({"ok": True, "message": response_message, "job": job.to_dict()})


@app.get("/api/jobs/<job_id>/status")
def status_job(job_id: str):
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401

    job = get_user_job(user, job_id)
    if job is None:
        return jsonify({"ok": False, "message": "작업을 찾을 수 없습니다."}), 404

    return jsonify({"ok": True, "job": job.to_dict()})


@app.get("/api/jobs/<job_id>/download")
def download_job(job_id: str):
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401

    job = get_user_job(user, job_id)
    if job is None:
        return jsonify({"ok": False, "message": "작업을 찾을 수 없습니다."}), 404

    with job.lock:
        done = job.done
        total = job.total

    if done <= 0:
        return jsonify({"ok": False, "message": "다운로드할 변환 결과가 없습니다."}), 400

    with job.wb_lock:
        output = io.BytesIO()
        job.wb.save(output)
        output.seek(0)

    filename = "output.xlsx" if done >= total else "output_partial.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def run_job_worker(job: JobState) -> None:
    try:
        cfg = load_config()
        api_url = cfg.get("juso", "api_url")
        confm_key = cfg.get("juso", "confm_key")
        sleep_seconds = cfg.getfloat("juso", "sleep_seconds", fallback=0.08)
        first_sort = cfg.get("juso", "first_sort", fallback="location")
    except Exception as exc:
        with job.lock:
            job.running = False
            job.error = str(exc)
            job.message = f"오류 발생: {exc}"
        return

    try:
        while True:
            with job.lock:
                if job.done >= job.total:
                    job.running = False
                    job.completed = True
                    job.stopped = False
                    job.message = MSG_COMPLETE
                    return
                if job.stop_event.is_set():
                    job.running = False
                    job.stopped = True
                    if job.done > 0:
                        job.message = "중지되었습니다. 현재까지 변환한 데이터를 다운로드할 수 있습니다."
                    else:
                        job.message = "중지되었습니다."
                    return
                row_index = job.done
                row = job.targets[row_index]

            col_b, col_c, col_d = process_row(job.ws, row, api_url, confm_key, first_sort, job.wb_lock)

            with job.wb_lock:
                job.ws[f"B{row}"] = col_b
                job.ws[f"C{row}"] = col_c
                job.ws[f"D{row}"] = col_d

            with job.lock:
                job.done += 1
                job.message = f"변환 진행 중... {job.done}/{job.total}"

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    except Exception as exc:
        with job.lock:
            job.running = False
            job.error = str(exc)
            job.message = f"오류 발생: {exc}"


def process_row(
    ws,
    row: int,
    api_url: str,
    confm_key: str,
    first_sort: str,
    wb_lock: threading.Lock,
) -> tuple[str, str, str]:
    with wb_lock:
        raw_value = ws[f"A{row}"].value
    raw = "" if raw_value is None else str(raw_value).strip()

    base, original_detail = split_base_detail(raw)
    keyword = prepare_api_keyword(base)
    if len(keyword) < 2:
        return raw, "실패:검색어짧음", ""

    try:
        data = call_juso_api(api_url, confm_key, keyword, first_sort=first_sort)
        common = data.get("results", {}).get("common", {})
        err = common.get("errorCode")
        if err != "0":
            return raw, f"실패:{err}:{common.get('errorMessage')}", ""

        juso_list = data.get("results", {}).get("juso", [])
        if not juso_list:
            return raw, "실패:검색결과없음", ""

        addr, zip_no = build_road_address_and_zip(juso_list[0], original_detail)
        addr = normalize_region_prefix(addr)
        return addr, "성공", zip_no
    except Exception as exc:
        return raw, f"실패:예외:{type(exc).__name__}", ""


if __name__ == "__main__":
    cfg = load_config()
    host = cfg.get("web", "host", fallback="0.0.0.0")
    port = cfg.getint("web", "port", fallback=8000)
    debug = cfg.getboolean("web", "debug", fallback=True)
    app.run(host=host, port=port, debug=debug)
