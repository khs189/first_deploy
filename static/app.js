let jobId = document.body.dataset.jobId || "";
let pollingTimer = null;
let alertedComplete = false;

const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const uploadBtn = document.getElementById("uploadBtn");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const downloadBtn = document.getElementById("downloadBtn");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const statusBox = document.getElementById("statusBox");

function setStatus(text) {
  statusBox.textContent = text;
}

function applyJobState(job) {
  progressBar.value = job.percent;
  progressText.textContent = `${job.percent}% (${job.done}/${job.total})`;
  setStatus(job.message || "");

  startBtn.disabled = !job.can_start;
  stopBtn.disabled = !job.running;
  downloadBtn.disabled = !job.can_download;

  if (job.source_name) {
    fileName.textContent = job.source_name;
  }

  if (job.completed && !alertedComplete) {
    alertedComplete = true;
    alert("주소 정제가 완료되었습니다. 다운로드하세요.");
  }
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "요청 처리 중 오류가 발생했습니다.");
  }
  return data;
}

async function refreshStatus() {
  if (!jobId) {
    return;
  }
  try {
    const data = await fetchJSON(`/api/jobs/${jobId}/status`);
    applyJobState(data.job);
  } catch (err) {
    setStatus(err.message);
  }
}

function startPolling() {
  if (pollingTimer) {
    return;
  }
  pollingTimer = setInterval(refreshStatus, 1000);
}

function stopPolling() {
  if (!pollingTimer) {
    return;
  }
  clearInterval(pollingTimer);
  pollingTimer = null;
}

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("업로드할 xlsx 파일을 선택하세요.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  uploadBtn.disabled = true;
  setStatus("업로드 중...");
  alertedComplete = false;

  try {
    const data = await fetchJSON("/api/upload", {
      method: "POST",
      body: formData,
    });
    jobId = data.job.job_id;
    applyJobState(data.job);
    startPolling();
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  } finally {
    uploadBtn.disabled = false;
  }
});

startBtn.addEventListener("click", async () => {
  if (!jobId) {
    alert("먼저 파일을 업로드하세요.");
    return;
  }
  try {
    const data = await fetchJSON(`/api/jobs/${jobId}/start`, { method: "POST" });
    applyJobState(data.job);
    startPolling();
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  }
});

stopBtn.addEventListener("click", async () => {
  if (!jobId) {
    return;
  }
  try {
    const data = await fetchJSON(`/api/jobs/${jobId}/stop`, { method: "POST" });
    applyJobState(data.job);
    startPolling();
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  }
});

downloadBtn.addEventListener("click", () => {
  if (!jobId) {
    return;
  }
  window.location.href = `/api/jobs/${jobId}/download`;
});

window.addEventListener("beforeunload", () => {
  stopPolling();
});

if (jobId) {
  startPolling();
  refreshStatus();
} else {
  setStatus("파일을 업로드한 뒤 시작 버튼을 누르세요.");
  startBtn.disabled = true;
  stopBtn.disabled = true;
  downloadBtn.disabled = true;
}
