const form = document.querySelector("#analysis-form");
const output = document.querySelector("#output");
const schemaOutput = document.querySelector("#schema-output");
const statusText = document.querySelector("#status-text");
const schemaButton = document.querySelector("#schema-button");
const schemaCards = document.querySelector("#schema-cards");
const resultCards = document.querySelector("#result-cards");
const phasePanel = document.querySelector("#phase-panel");
const phaseTableBody = document.querySelector("#phase-table-body");
const schemaVersion = document.querySelector("#schema-version");
const schemaCamera = document.querySelector("#schema-camera");
const schemaScoreScale = document.querySelector("#schema-score-scale");
const schemaPhaseCount = document.querySelector("#schema-phase-count");
const schemaColumnCount = document.querySelector("#schema-column-count");
const overallScore = document.querySelector("#overall-score");
const topProId = document.querySelector("#top-pro-id");
const keypointsSize = document.querySelector("#keypoints-size");
const poseStatus = document.querySelector("#pose-status");
const videoSummary = document.querySelector("#video-summary");
const previewUploadForm = document.querySelector("#preview-upload-form");
const previewLoadButton = document.querySelector("#preview-load-button");
const previewProSelect = document.querySelector("#preview-pro-select");
const previewUserSelect = document.querySelector("#preview-user-select");
const previewPhaseSelect = document.querySelector("#preview-phase-select");
const previewStepSlider = document.querySelector("#preview-step-slider");
const previewPlayButton = document.querySelector("#preview-play-button");
const previewPrevButton = document.querySelector("#preview-prev-button");
const previewNextButton = document.querySelector("#preview-next-button");
const previewStepText = document.querySelector("#preview-step-text");
const previewScoreText = document.querySelector("#preview-score-text");
const previewFrameText = document.querySelector("#preview-frame-text");
const previewReleaseText = document.querySelector("#preview-release-text");
const previewSourceText = document.querySelector("#preview-source-text");
const frameMapSummary = document.querySelector("#frame-map-summary");
const frameMap = document.querySelector("#frame-map");
const cockingStatusText = document.querySelector("#cocking-status-text");
const cockingTableBody = document.querySelector("#cocking-table-body");
const skeletonCanvas = document.querySelector("#skeleton-canvas");
const skeletonContext = skeletonCanvas.getContext("2d");

let previewPayload = null;
let activePhaseIndex = 0;
let activeStepIndex = 0;
let previewTimer = null;

const defaultPreviewProVideo =
  "대한민국 야구 대표팀 우완투수 No.18 박준현 선수 불펜피칭 영상 x 2025 제32회 세계청소년야구선수권대회(18세 이하) 현장체크.mp4";
const defaultPreviewUserVideo = "y2.mp4";

const phaseClassNames = {
  windup: "phase-windup",
  leg_lift: "phase-leg-lift",
  stride: "phase-stride",
  acceleration: "phase-acceleration",
  follow_through: "phase-follow-through",
};

const jointEdges = [
  ["left_shoulder", "right_shoulder"],
  ["left_hip", "right_hip"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["left_ankle", "left_foot_index"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
  ["right_ankle", "right_foot_index"],
];

schemaButton.addEventListener("click", async () => {
  statusText.textContent = "스키마 확인 중";
  schemaOutput.hidden = true;
  schemaOutput.textContent = "{}";
  schemaCards.hidden = true;

  try {
    const response = await fetch("/api/schema");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "스키마 확인 실패");
    }
    statusText.textContent = "스키마 확인 완료";
    schemaOutput.hidden = false;
    schemaOutput.textContent = JSON.stringify(payload, null, 2);
    schemaCards.hidden = false;
    schemaVersion.textContent = payload.responseSchemaVersion || "-";
    schemaCamera.textContent = (payload.supportedCameraViews || []).join(", ") || "-";
    schemaScoreScale.textContent = payload.similarity?.scoreScale || "-";
    schemaPhaseCount.textContent = `${payload.similarity?.phases?.length || 0}`;
    schemaColumnCount.textContent = `${payload.keypointsCsvColumns?.length || 0}`;
  } catch (error) {
    statusText.textContent = "오류";
    schemaOutput.hidden = false;
    schemaOutput.textContent = JSON.stringify({ message: error.message }, null, 2);
  }
});

previewLoadButton.addEventListener("click", () => {
  loadSelectedSkeletonPreview();
});
previewUploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadSelectedSkeletonPreview();
});
previewPhaseSelect.addEventListener("change", () => {
  activePhaseIndex = Number(previewPhaseSelect.value || 0);
  activeStepIndex = firstScoredStep(activePreviewPhase());
  stopPreview();
  syncPreviewControls();
  renderSkeletonPreview();
});
previewStepSlider.addEventListener("input", () => {
  activeStepIndex = Number(previewStepSlider.value || 0);
  renderSkeletonPreview();
});
previewPrevButton.addEventListener("click", () => {
  movePreviewStep(-1);
});
previewNextButton.addEventListener("click", () => {
  movePreviewStep(1);
});
previewPlayButton.addEventListener("click", () => {
  if (previewTimer) {
    stopPreview();
    return;
  }
  startPreview();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusText.textContent = "분석 요청 중";
  output.textContent = "{}";
  resultCards.hidden = true;
  phasePanel.hidden = true;
  phaseTableBody.innerHTML = "";

  try {
    const data = new FormData(form);
    const targetDistanceM = Number(data.get("targetDistanceM") || 16);
    const releaseExtensionM = Number(data.get("releaseExtensionM") || 1.5);
    const metadata = {
      videoId: "user_video_upload",
      analysisType: "pro_similarity",
      pitchType: data.get("pitchType") || "직구",
      cameraView: "rear",
      maxFrames: data.get("maxFrames") ? Number(data.get("maxFrames")) : undefined,
      user: {
        videoId: "user_video_upload",
      },
      speed: {
        user: {
          targetDistanceM,
          releaseExtensionM,
          releaseFrame: optionalNumber(data.get("userReleaseFrame")),
          arrivalFrame: optionalNumber(data.get("userArrivalFrame")),
        },
      },
    };

    const requestBody = new FormData();
    requestBody.append("userVideo", data.get("userVideo"));
    requestBody.append("metadata", JSON.stringify(metadata));

    const response = await fetch("/api/analyze/similarity", {
      method: "POST",
      body: requestBody,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || payload.message || "분석 요청 실패");
    }
    statusText.textContent = "완료";
    output.textContent = JSON.stringify(payload, null, 2);
    resultCards.hidden = false;
    phasePanel.hidden = false;
    const topPlayer = payload.players?.[0];
    overallScore.textContent = topPlayer?.overallScore == null ? "-" : `${topPlayer.overallScore}`;
    topProId.textContent = topPlayer?.proId || "-";
    keypointsSize.textContent = formatCsvSize(payload.user_data?.skeleton_data);
    poseStatus.textContent = formatPoseStatus(payload);
    videoSummary.textContent = formatVideoSummary(payload.user_data);
    renderPhaseScores(topPlayer?.phaseScores || []);
  } catch (error) {
    statusText.textContent = "오류";
    output.textContent = JSON.stringify({ message: error.message }, null, 2);
  }
});

initializePreview();

function optionalNumber(value) {
  if (value === null || value === "") {
    return undefined;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function formatCsvSize(csvText) {
  if (!csvText) {
    return "-";
  }
  return `${formatBytes(csvText.length)}`;
}

function formatVideoSummary(userData) {
  if (!userData) {
    return "-";
  }
  const frameCount = userData.frame_count ?? "-";
  const fps = userData.fps == null ? "-" : Number(userData.fps).toFixed(2);
  return `${frameCount} / ${fps}`;
}

function formatBytes(byteCount) {
  if (byteCount < 1024) {
    return `${byteCount} B`;
  }
  if (byteCount < 1024 * 1024) {
    return `${(byteCount / 1024).toFixed(1)} KB`;
  }
  return `${(byteCount / (1024 * 1024)).toFixed(2)} MB`;
}

function formatPoseStatus(payload) {
  const frameCount = payload.user_data?.frame_count ?? "-";
  const playerCount = payload.players?.length ?? 0;
  return `사용자 ${frameCount} frames / Top ${playerCount}`;
}

function renderPhaseScores(phaseScores) {
  if (!phaseScores.length) {
    phaseTableBody.innerHTML = `<tr><td colspan="4">phaseScores가 없습니다.</td></tr>`;
    return;
  }
  phaseTableBody.innerHTML = phaseScores
    .map((phase) => {
      const userFrames = `${phase.userStartFrame ?? "-"} → ${phase.userEndFrame ?? "-"}`;
      const proFrames = `${phase.proStartFrame ?? "-"} → ${phase.proEndFrame ?? "-"}`;
      const score = phase.score == null ? "-" : phase.score;
      return `
        <tr>
          <td>${escapeHtml(phase.label || phase.phase || "-")}</td>
          <td>${score}</td>
          <td>${userFrames}</td>
          <td>${proFrames}</td>
        </tr>
      `;
    })
    .join("");
}

async function loadSkeletonPreview(options = {}) {
  const uploadButton = previewUploadForm.querySelector('button[type="submit"]');
  const isUpload = Boolean(options.formData);
  previewLoadButton.disabled = true;
  uploadButton.disabled = true;
  previewLoadButton.textContent = isUpload ? "처리 중" : "불러오는 중";
  uploadButton.textContent = isUpload ? "분석 중" : "업로드 영상으로 보기";
  drawPreviewPlaceholder(isUpload ? "업로드 영상 분석 중" : "skeleton 준비 중");
  try {
    const response = await fetch("/api/experiments/resampling-preview", {
      method: isUpload ? "POST" : "GET",
      body: options.formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "미리보기 로드 실패");
    }
    previewPayload = payload;
    activePhaseIndex = 0;
    previewPhaseSelect.innerHTML = payload.phases
      .map((phase, index) => `<option value="${index}">${escapeHtml(phase.label || phase.phase)}</option>`)
      .join("");
    activeStepIndex = firstScoredStep(activePreviewPhase());
    syncPreviewControls();
    renderCockingEvents(payload.cockingEvents);
    renderFrameMap(payload);
    renderSkeletonPreview();
  } catch (error) {
    previewPayload = null;
    renderCockingEvents(null);
    renderFrameMap(null);
    drawPreviewPlaceholder(error.message);
  } finally {
    previewLoadButton.disabled = false;
    uploadButton.disabled = false;
    previewLoadButton.textContent = "기본 조합 보기";
    uploadButton.textContent = "선택 영상으로 보기";
  }
}

async function initializePreview() {
  drawPreviewPlaceholder("미리보기 대기 중");
  await loadPreviewVideoOptions();
  await loadSelectedSkeletonPreview();
}

async function loadSelectedSkeletonPreview() {
  const formData = new FormData(previewUploadForm);
  formData.append("metadata", JSON.stringify({ maxFrames: optionalNumber(formData.get("maxFrames")) }));
  await loadSkeletonPreview({ formData });
}

async function loadPreviewVideoOptions() {
  try {
    const response = await fetch("/api/experiments/video-options");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "영상 목록 로드 실패");
    }
    renderVideoOptions(previewProSelect, payload.proVideos || [], "pro_data 영상 없음");
    renderVideoOptions(previewUserSelect, payload.userVideos || [], "user_data 영상 없음");
    selectPreferredVideo(previewProSelect, defaultPreviewProVideo);
    selectPreferredVideo(previewUserSelect, defaultPreviewUserVideo);
  } catch (error) {
    renderVideoOptions(previewProSelect, [], error.message);
    renderVideoOptions(previewUserSelect, [], error.message);
  }
}

function renderVideoOptions(select, videos, emptyLabel) {
  select.innerHTML = "";
  if (!videos.length) {
    select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    select.disabled = true;
    return;
  }
  select.disabled = false;
  select.innerHTML = videos
    .map((video) => `<option value="${escapeHtml(video.id)}">${escapeHtml(video.label || video.filename)}</option>`)
    .join("");
}

function selectPreferredVideo(select, preferredId) {
  const option = Array.from(select.options).find((item) => item.value === preferredId);
  if (option) {
    select.value = preferredId;
  }
}

function syncPreviewControls() {
  const phase = activePreviewPhase();
  const maxStep = Math.max(0, (phase?.samples?.length || 1) - 1);
  activeStepIndex = Math.max(0, Math.min(activeStepIndex, maxStep));
  previewPhaseSelect.value = `${activePhaseIndex}`;
  previewStepSlider.max = `${maxStep}`;
  previewStepSlider.value = `${activeStepIndex}`;
}

function activePreviewPhase() {
  return previewPayload?.phases?.[activePhaseIndex] || null;
}

function activePreviewSample() {
  const phase = activePreviewPhase();
  return phase?.samples?.[activeStepIndex] || null;
}

function firstScoredStep(phase) {
  const index = (phase?.samples || []).findIndex((sample) => sample.score != null);
  return index >= 0 ? index : 0;
}

function startPreview() {
  if (!activePreviewPhase()) {
    return;
  }
  previewPlayButton.textContent = "정지";
  previewTimer = window.setInterval(() => {
    movePreviewStep(1, { wrap: true });
  }, 150);
}

function stopPreview() {
  if (previewTimer) {
    window.clearInterval(previewTimer);
    previewTimer = null;
  }
  previewPlayButton.textContent = "재생";
}

function movePreviewStep(delta, options = {}) {
  const phase = activePreviewPhase();
  if (!phase) {
    return;
  }
  const maxStep = Math.max(0, phase.samples.length - 1);
  const next = activeStepIndex + delta;
  if (options.wrap) {
    activeStepIndex = next > maxStep ? 0 : next < 0 ? maxStep : next;
  } else {
    activeStepIndex = Math.max(0, Math.min(next, maxStep));
  }
  previewStepSlider.value = `${activeStepIndex}`;
  renderSkeletonPreview();
}

function renderSkeletonPreview() {
  const phase = activePreviewPhase();
  const sample = activePreviewSample();
  if (!phase || !sample) {
    drawPreviewPlaceholder("표시할 skeleton이 없습니다");
    return;
  }

  const bounds = computePhaseBounds(phase);
  const transform = buildCanvasTransform(bounds);
  const proPoints = sample.proDisplayPoints || sample.proPoints;
  const userPoints = sample.userDisplayPoints || sample.userPoints;
  skeletonContext.clearRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  skeletonContext.fillStyle = "#fffdf8";
  skeletonContext.fillRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  drawPreviewGrid();
  drawSkeleton(proPoints, transform, "#2368d9", 0.78);
  drawSkeleton(userPoints, transform, "#d86b24", 0.78);
  drawSkeletonLabel(proPoints, transform, "선수(pro)", "#2368d9", -12);
  drawSkeletonLabel(userPoints, transform, "사용자(user)", "#d86b24", 14);
  drawLegend();
  drawPreviewTitle(phase, sample);
  updatePreviewReadout(phase, sample);
  renderFrameMap(previewPayload);
}

function computePhaseBounds(phase) {
  const xs = [];
  const ys = [];
  for (const sample of phase.samples || []) {
    collectPointBounds(sample.proDisplayPoints || sample.proPoints, xs, ys);
    collectPointBounds(sample.userDisplayPoints || sample.userPoints, xs, ys);
  }
  if (!xs.length || !ys.length) {
    return { minX: -1, maxX: 1, minY: -1.7, maxY: 1.3 };
  }
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function collectPointBounds(points, xs, ys) {
  for (const point of Object.values(points || {})) {
    if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y) || Number(point.confidence || 0) < 0.05) {
      continue;
    }
    xs.push(point.x);
    ys.push(point.y);
  }
}

function buildCanvasTransform(bounds) {
  const width = skeletonCanvas.width;
  const height = skeletonCanvas.height;
  const rangeX = Math.max(0.8, bounds.maxX - bounds.minX);
  const rangeY = Math.max(1.2, bounds.maxY - bounds.minY);
  const scale = Math.min((width - 180) / rangeX, (height - 180) / rangeY);
  const midX = (bounds.minX + bounds.maxX) / 2;
  const midY = (bounds.minY + bounds.maxY) / 2;
  return {
    project(point) {
      return {
        x: width / 2 + (point.x - midX) * scale,
        y: height * 0.58 - (point.y - midY) * scale,
      };
    },
  };
}

function drawSkeleton(points, transform, color, alpha) {
  skeletonContext.save();
  skeletonContext.lineCap = "round";
  skeletonContext.lineJoin = "round";
  skeletonContext.strokeStyle = color;
  skeletonContext.fillStyle = color;
  skeletonContext.globalAlpha = alpha;
  skeletonContext.lineWidth = 7;

  for (const [start, end] of jointEdges) {
    const startPoint = validPoint(points?.[start]);
    const endPoint = validPoint(points?.[end]);
    if (!startPoint || !endPoint) {
      continue;
    }
    const a = transform.project(startPoint);
    const b = transform.project(endPoint);
    skeletonContext.beginPath();
    skeletonContext.moveTo(a.x, a.y);
    skeletonContext.lineTo(b.x, b.y);
    skeletonContext.stroke();
  }

  for (const point of Object.values(points || {})) {
    const valid = validPoint(point);
    if (!valid) {
      continue;
    }
    const projected = transform.project(valid);
    skeletonContext.beginPath();
    skeletonContext.arc(projected.x, projected.y, 7.5, 0, Math.PI * 2);
    skeletonContext.fill();
  }
  skeletonContext.restore();
}

function validPoint(point) {
  if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
    return null;
  }
  if (Number(point.confidence || 0) < 0.05) {
    return null;
  }
  return point;
}

function drawSkeletonLabel(points, transform, label, color, offsetX) {
  const projectedPoints = Object.values(points || {})
    .map((point) => validPoint(point))
    .filter(Boolean)
    .map((point) => transform.project(point));
  if (!projectedPoints.length) {
    return;
  }
  const centerX = projectedPoints.reduce((total, point) => total + point.x, 0) / projectedPoints.length;
  const topY = Math.min(...projectedPoints.map((point) => point.y));
  skeletonContext.save();
  skeletonContext.font = "700 16px Georgia, serif";
  skeletonContext.fillStyle = color;
  skeletonContext.fillText(label, centerX + offsetX, Math.max(92, topY - 12));
  skeletonContext.restore();
}

function drawPreviewGrid() {
  skeletonContext.save();
  skeletonContext.strokeStyle = "#eadfce";
  skeletonContext.lineWidth = 1;
  for (let x = 80; x < skeletonCanvas.width; x += 80) {
    skeletonContext.beginPath();
    skeletonContext.moveTo(x, 96);
    skeletonContext.lineTo(x, skeletonCanvas.height - 54);
    skeletonContext.stroke();
  }
  for (let y = 116; y < skeletonCanvas.height; y += 80) {
    skeletonContext.beginPath();
    skeletonContext.moveTo(48, y);
    skeletonContext.lineTo(skeletonCanvas.width - 48, y);
    skeletonContext.stroke();
  }
  skeletonContext.restore();
}

function drawLegend() {
  drawLegendItem("선수(pro)", "#2368d9", 44, 74);
  drawLegendItem("사용자(user)", "#d86b24", 144, 74);
}

function drawLegendItem(label, color, x, y) {
  skeletonContext.save();
  skeletonContext.fillStyle = color;
  skeletonContext.beginPath();
  skeletonContext.arc(x, y - 5, 7, 0, Math.PI * 2);
  skeletonContext.fill();
  skeletonContext.fillStyle = "#3d473f";
  skeletonContext.font = "700 16px Georgia, serif";
  skeletonContext.fillText(label, x + 14, y);
  skeletonContext.restore();
}

function drawPreviewTitle(phase, sample) {
  skeletonContext.save();
  skeletonContext.fillStyle = "#17201b";
  skeletonContext.font = "700 28px Georgia, serif";
  skeletonContext.fillText(`${phase.label} ${activeStepIndex + 1}/${phase.samples.length}`, 44, 42);
  skeletonContext.fillStyle = "#647067";
  skeletonContext.font = "16px Georgia, serif";
  const progress = `${Math.round((sample.progress || 0) * 100)}%`;
  skeletonContext.fillText(`progress ${progress} | score ${sample.score ?? "-"}`, 44, skeletonCanvas.height - 28);
  skeletonContext.restore();
}

function updatePreviewReadout(phase, sample) {
  previewStepText.textContent = `${activeStepIndex + 1} / ${phase.samples.length}`;
  previewScoreText.textContent = sample.score == null ? "-" : `${sample.score}`;
  previewFrameText.textContent = `선수 ${formatFrame(sample.proFrame)} / 사용자 ${formatFrame(sample.userFrame)}`;
  previewReleaseText.textContent = formatReleaseInfo(previewPayload?.releaseEvents);
  previewSourceText.textContent = formatPreviewSource(previewPayload);
}

function formatFrame(value) {
  return Number.isFinite(value) ? Number(value).toFixed(1) : "-";
}

function formatReleaseInfo(releaseEvents) {
  const pro = releaseEvents?.pro;
  const user = releaseEvents?.user;
  if (!pro && !user) {
    return "-";
  }
  return `선수 ${formatFrame(pro?.frame)}(${formatReleaseMethod(pro)}) / 사용자 ${formatFrame(user?.frame)}(${formatReleaseMethod(user)})`;
}

function formatReleaseMethod(event) {
  if (!event) {
    return "-";
  }
  return event.method === "ball_exit_midpoint_v1" ? "공" : "손목";
}

function renderFrameMap(payload) {
  if (!frameMap || !frameMapSummary) {
    return;
  }
  if (!payload?.phases?.length) {
    frameMapSummary.textContent = "-";
    frameMap.innerHTML = `<p class="empty-state">프레임 맵 대기 중</p>`;
    return;
  }

  frameMapSummary.textContent = formatFrameMapSummary(payload);
  frameMap.innerHTML = ["pro", "user"]
    .map((side) => renderFrameMapSide(side, payload))
    .join("");
}

function formatFrameMapSummary(payload) {
  const pro = frameRangeForSide(payload, "pro");
  const user = frameRangeForSide(payload, "user");
  return `선수 ${formatFrameRange(pro)} / 사용자 ${formatFrameRange(user)}`;
}

function formatFrameRange(range) {
  const total = Number.isFinite(range.totalFrameCount) ? `${range.totalFrameCount}f` : `${formatFrame(range.maxFrame)}f`;
  return `${total}`;
}

function renderFrameMapSide(side, payload) {
  const label = side === "pro" ? "선수(pro)" : "사용자(user)";
  const range = frameRangeForSide(payload, side);
  const markers = timelineMarkersForSide(side, payload);
  const activeFrame = activePreviewSample()?.[`${side}Frame`];
  const intervals = Object.entries(payload.phaseDetection?.[side]?.intervals || {});
  const phaseBands = intervals
    .map(([phaseName, interval]) => renderPhaseBand(phaseName, interval, range))
    .join("");
  const markerNodes = markers
    .map((marker) => renderTimelineMarker(marker, range))
    .join("");
  const activeMarker = Number.isFinite(activeFrame)
    ? `<span class="current-frame-marker" style="left: ${framePercent(activeFrame, range)}%" title="${label} 현재 ${formatFrame(activeFrame)}"></span>`
    : "";
  const chips = renderFrameChips(side, payload, markers, activeFrame);

  return `
    <article class="frame-map-row">
      <header class="frame-map-row-head">
        <strong>${label}</strong>
        <span>${formatFrame(range.minFrame)} → ${formatFrame(range.maxFrame)}</span>
      </header>
      <div class="frame-track" aria-label="${label} phase timeline">
        ${renderFrameTicks(range)}
        ${phaseBands}
        ${markerNodes}
        ${activeMarker}
      </div>
      <div class="frame-chip-strip" aria-label="${label} resampled frames">
        ${chips || `<span class="empty-state">프레임 없음</span>`}
      </div>
    </article>
  `;
}

function frameRangeForSide(payload, side) {
  const frames = [];
  const videoFrameCount = Number(payload.videoMeta?.[side]?.frameCount);
  if (Number.isFinite(videoFrameCount) && videoFrameCount > 0) {
    frames.push(0, videoFrameCount - 1);
  }

  const clip = payload.clipMeta?.[side] || {};
  pushFinite(frames, clip.startFrame);
  pushFinite(frames, clip.endFrame);

  const intervals = Object.values(payload.phaseDetection?.[side]?.intervals || {});
  for (const interval of intervals) {
    pushFinite(frames, interval.startFrame);
    pushFinite(frames, interval.endFrame);
  }

  for (const phase of payload.phases || []) {
    for (const sample of phase.samples || []) {
      pushFinite(frames, sample[`${side}Frame`]);
    }
  }

  const release = payload.releaseEvents?.[side] || {};
  pushFinite(frames, release.beforeFrame);
  pushFinite(frames, release.frame);
  pushFinite(frames, release.exitFrame);

  if (!frames.length) {
    return { minFrame: 0, maxFrame: 1, totalFrameCount: null };
  }
  const minFrame = Math.min(...frames);
  const maxFrame = Math.max(...frames);
  return {
    minFrame,
    maxFrame: Math.max(maxFrame, minFrame + 1),
    totalFrameCount: Number.isFinite(videoFrameCount) && videoFrameCount > 0 ? Math.round(videoFrameCount) : null,
  };
}

function pushFinite(values, value) {
  const number = Number(value);
  if (Number.isFinite(number)) {
    values.push(number);
  }
}

function renderFrameTicks(range) {
  const tickPercents = [0, 25, 50, 75, 100];
  return tickPercents
    .map((percent) => {
      const frame = range.minFrame + (range.maxFrame - range.minFrame) * (percent / 100);
      return `
        <span class="frame-tick" style="left: ${percent}%"></span>
        <span class="frame-tick-label" style="left: ${percent}%">${formatFrame(frame)}</span>
      `;
    })
    .join("");
}

function renderPhaseBand(phaseName, interval, range) {
  const start = Number(interval.startFrame);
  const end = Number(interval.endFrame);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return "";
  }
  const left = framePercent(Math.min(start, end), range);
  const right = framePercent(Math.max(start, end), range);
  const width = Math.max(0.6, right - left);
  const label = interval.label || phaseLabel(phaseName);
  const className = phaseClassNames[phaseName] || "phase-unknown";
  return `
    <span class="phase-band ${className}" style="left: ${left}%; width: ${width}%;" title="${escapeHtml(label)} ${formatFrame(start)}-${formatFrame(end)}">
      ${escapeHtml(label)}
    </span>
  `;
}

function timelineMarkersForSide(side, payload) {
  const markers = [];
  for (const kind of ["good", "bad", "release"]) {
    for (const marker of payload.frameMarkers?.[kind] || []) {
      const frame = Number(marker[`${side}Frame`]);
      if (!Number.isFinite(frame)) {
        continue;
      }
      markers.push({
        ...marker,
        kind,
        frame,
        title: markerTitle(kind, marker, frame),
      });
    }
  }
  return markers;
}

function markerTitle(kind, marker, frame) {
  const label = marker.label || marker.phase || "";
  const score = Number.isFinite(Number(marker.score)) ? ` / score ${marker.score}` : "";
  const prefix = kind === "good" ? "잘한 프레임" : kind === "bad" ? "못한 프레임" : "릴리즈";
  return `${prefix} ${label} ${formatFrame(frame)}${score}`;
}

function renderTimelineMarker(marker, range) {
  return `
    <span
      class="frame-marker marker-${marker.kind}"
      style="left: ${framePercent(marker.frame, range)}%"
      title="${escapeHtml(marker.title)}"
    ></span>
  `;
}

function renderFrameChips(side, payload, markers, activeFrame) {
  const chips = [];
  for (const phase of payload.phases || []) {
    const phaseClass = phaseClassNames[phase.phase] || "phase-unknown";
    for (const sample of phase.samples || []) {
      const frame = Number(sample[`${side}Frame`]);
      if (!Number.isFinite(frame)) {
        continue;
      }
      const markerKind = markerKindForFrame(markers, frame);
      const activeClass = sameFrame(frame, activeFrame) ? "is-active" : "";
      const markerClass = markerKind ? `has-${markerKind}` : "";
      const title = `${phase.label || phase.phase} ${formatFrame(frame)} / score ${sample.score ?? "-"}`;
      chips.push(
        `<span class="frame-chip ${phaseClass} ${markerClass} ${activeClass}" title="${escapeHtml(title)}">${formatCompactFrame(frame)}</span>`
      );
    }
  }
  return chips.join("");
}

function markerKindForFrame(markers, frame) {
  const release = markers.find((marker) => marker.kind === "release" && sameFrame(marker.frame, frame));
  if (release) {
    return "release";
  }
  const bad = markers.find((marker) => marker.kind === "bad" && sameFrame(marker.frame, frame));
  if (bad) {
    return "bad";
  }
  const good = markers.find((marker) => marker.kind === "good" && sameFrame(marker.frame, frame));
  return good ? "good" : "";
}

function sameFrame(a, b) {
  if (!Number.isFinite(Number(a)) || !Number.isFinite(Number(b))) {
    return false;
  }
  return Math.abs(Number(a) - Number(b)) <= 0.51;
}

function framePercent(frame, range) {
  const span = Math.max(1, range.maxFrame - range.minFrame);
  const percent = ((Number(frame) - range.minFrame) / span) * 100;
  return Math.max(0, Math.min(100, percent));
}

function formatCompactFrame(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return `${Math.round(number)}`;
}

function phaseLabel(phase) {
  const labels = {
    windup: "와인드업",
    leg_lift: "레그 리프트",
    stride: "스트라이드",
    acceleration: "가속",
    follow_through: "팔로스루",
  };
  return labels[phase] || phase || "-";
}

function renderCockingEvents(cockingEvents) {
  const pro = cockingEvents?.pro || {};
  const user = cockingEvents?.user || {};
  const rows = [
    {
      label: "얼리 코킹",
      key: "earlyCocking",
      fallbackMetric: "팔꿈치 후방 proxy",
    },
    {
      label: "레이트 코킹",
      key: "lateCocking",
      fallbackMetric: "팔꿈치-어깨 거리",
    },
  ];
  cockingStatusText.textContent = [pro.status, user.status].filter(Boolean).join(" / ") || "-";
  cockingTableBody.innerHTML = rows
    .map((row) => {
      const proEvent = pro[row.key] || {};
      const userEvent = user[row.key] || {};
      const metricName = proEvent.metricName || userEvent.metricName || row.fallbackMetric;
      return `
        <tr>
          <td>${row.label}</td>
          <td>${formatFrame(proEvent.frame)}</td>
          <td>${formatFrame(userEvent.frame)}</td>
          <td>${formatMetricName(metricName)}</td>
        </tr>
      `;
    })
    .join("");
}

function formatMetricName(metricName) {
  const labels = {
    throwing_elbow_lateral_offset_from_shoulder: "팔꿈치가 어깨 기준 가장 뒤로 간 프레임",
    throwing_elbow_shoulder_distance: "팔꿈치-어깨 거리가 최대인 프레임",
  };
  return labels[metricName] || metricName || "-";
}

function formatPreviewSource(payload) {
  const sources = payload?.sources || {};
  if (sources.mode === "uploaded_videos") {
    return `${sources.proVideo || "pro"} / ${sources.userVideo || "user"}`;
  }
  if (sources.mode === "folder_videos") {
    return `${sources.proSource || "pro_data"}:${sources.proVideo || "pro"} / ${sources.userSource || "user_data"}:${sources.userVideo || "user"}`;
  }
  if (sources.mode === "mixed_videos") {
    return `${sources.proSource || "pro"}:${sources.proVideo || "pro"} / ${sources.userSource || "user"}:${sources.userVideo || "user"}`;
  }
  return "기본 샘플";
}

function drawPreviewPlaceholder(message) {
  skeletonContext.clearRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  skeletonContext.fillStyle = "#fffdf8";
  skeletonContext.fillRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  skeletonContext.fillStyle = "#647067";
  skeletonContext.font = "700 26px Georgia, serif";
  skeletonContext.fillText(message, 44, 62);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
