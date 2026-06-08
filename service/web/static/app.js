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
const proSkeletonForm = document.querySelector("#pro-skeleton-form");
const previewLoadButton = document.querySelector("#preview-load-button");
const previewProSelect = document.querySelector("#preview-pro-select");
const previewUserSelect = document.querySelector("#preview-user-select");
const previewProSkeletonSelect = document.querySelector("#preview-pro-skeleton-select");
const previewPhaseSelect = document.querySelector("#preview-phase-select");
const previewStepSlider = document.querySelector("#preview-step-slider");
const previewCoordinateModeInputs = document.querySelectorAll('input[name="previewCoordinateMode"]');
const previewAlignmentModeInputs = document.querySelectorAll('input[name="previewAlignmentMode"]');
const previewPlayButton = document.querySelector("#preview-play-button");
const previewPrevButton = document.querySelector("#preview-prev-button");
const previewNextButton = document.querySelector("#preview-next-button");
const previewStepText = document.querySelector("#preview-step-text");
const previewScoreText = document.querySelector("#preview-score-text");
const previewFrameText = document.querySelector("#preview-frame-text");
const previewAlignmentText = document.querySelector("#preview-alignment-text");
const previewReleaseText = document.querySelector("#preview-release-text");
const previewSourceText = document.querySelector("#preview-source-text");
const previewVideoPanel = document.querySelector("#preview-video-panel");
const previewProVideoCard = document.querySelector('[data-video-card="pro"]');
const previewUserVideoCard = document.querySelector('[data-video-card="user"]');
const previewProVideo = document.querySelector("#preview-pro-video");
const previewUserVideo = document.querySelector("#preview-user-video");
const previewProVideoFrame = document.querySelector("#preview-pro-video-frame");
const previewUserVideoFrame = document.querySelector("#preview-user-video-frame");
const frameMapSummary = document.querySelector("#frame-map-summary");
const frameMap = document.querySelector("#frame-map");
const phaseSkeletonSummary = document.querySelector("#phase-skeleton-summary");
const phaseSkeletonGallery = document.querySelector("#phase-skeleton-gallery");
const fullComparisonSummary = document.querySelector("#full-comparison-summary");
const fullComparisonCanvas = document.querySelector("#full-comparison-canvas");
const fullComparisonContext = fullComparisonCanvas?.getContext("2d");
const fullComparisonPlayButton = document.querySelector("#full-comparison-play-button");
const fullComparisonSlider = document.querySelector("#full-comparison-slider");
const fullComparisonFrameText = document.querySelector("#full-comparison-frame-text");
const fullComparisonPhaseTrack = document.querySelector("#full-comparison-phase-track");
const alignmentSummary = document.querySelector("#alignment-summary");
const cockingStatusText = document.querySelector("#cocking-status-text");
const cockingTableBody = document.querySelector("#cocking-table-body");
const crop2ReviewLoadButton = document.querySelector("#crop2-review-load-button");
const crop2ReviewMaxFrames = document.querySelector("#crop2-review-max-frames");
const crop2ReviewStatus = document.querySelector("#crop2-review-status");
const crop2ReviewGrid = document.querySelector("#crop2-review-grid");
const skeletonCanvas = document.querySelector("#skeleton-canvas");
const skeletonContext = skeletonCanvas.getContext("2d");

let previewPayload = null;
let activePhaseIndex = 0;
let activeStepIndex = 0;
let activeCoordinateMode = "sourceNormalized";
let activeAlignmentMode = "fixed";
let stationaryFootAnchors = {};
let previewTimer = null;
let fullComparisonIndex = 0;
let fullComparisonTimer = null;
let crop2ReviewItems = [];
let crop2ReviewFrameIndexes = {};
let crop2ReviewTimers = {};
let crop2ReviewSharedBounds = null;
let dtwAlignmentCache = new WeakMap();

const defaultPreviewProVideo = "김광현.mp4";
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
const scoreJoints = [
  "nose",
  "left_shoulder",
  "right_shoulder",
  "left_elbow",
  "right_elbow",
  "left_wrist",
  "right_wrist",
  "left_hip",
  "right_hip",
  "left_knee",
  "right_knee",
  "left_ankle",
  "right_ankle",
  "left_foot_index",
  "right_foot_index",
];
const scoreDistanceSigma = 0.55;
const goodFrameScoreThreshold = 78;
const badFrameScoreThreshold = 68;
const frameMarkerLimit = 3;

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
proSkeletonForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadSelectedProSkeletonPreview();
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
for (const input of previewCoordinateModeInputs) {
  input.addEventListener("change", () => {
    if (!input.checked) {
      return;
    }
    activeCoordinateMode = coordinateModeFromValue(input.value);
    clearDtwAlignmentCache();
    activeStepIndex = firstScoredStep(activePreviewPhase());
    syncPreviewControls();
    renderSkeletonPreview();
    renderPhaseSkeletonGallery(previewPayload);
    renderFullComparison(previewPayload);
    renderAlignmentSummary(previewPayload);
  });
}
for (const input of previewAlignmentModeInputs) {
  input.addEventListener("change", () => {
    if (!input.checked) {
      return;
    }
    activeAlignmentMode = alignmentModeFromValue(input.value);
    activeStepIndex = firstScoredStep(activePreviewPhase());
    syncPreviewControls();
    renderSkeletonPreview();
    renderPhaseSkeletonGallery(previewPayload);
    renderFullComparison(previewPayload);
    renderAlignmentSummary(previewPayload);
  });
}
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
fullComparisonPlayButton?.addEventListener("click", () => {
  if (fullComparisonTimer) {
    stopFullComparison();
    return;
  }
  startFullComparison();
});
fullComparisonSlider?.addEventListener("input", () => {
  stopFullComparison();
  fullComparisonIndex = Number(fullComparisonSlider.value || 0);
  renderFullComparisonFrame({ syncMainPreview: true });
});
if (fullComparisonPhaseTrack) {
  fullComparisonPhaseTrack.addEventListener("click", (event) => {
    const segment = event.target.closest("[data-full-frame-index]");
    if (!segment) {
      return;
    }
    stopFullComparison();
    fullComparisonIndex = Number(segment.dataset.fullFrameIndex || 0);
    renderFullComparisonFrame({ syncMainPreview: true });
  });
}
if (phaseSkeletonGallery) {
  phaseSkeletonGallery.addEventListener("click", (event) => {
    const card = event.target.closest("[data-phase-jump]");
    if (!card) {
      return;
    }
    activePhaseIndex = Number(card.dataset.phaseJump || 0);
    activeStepIndex = Number(card.dataset.sampleIndex || 0);
    stopPreview();
    syncPreviewControls();
    renderSkeletonPreview();
    skeletonCanvas.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}
crop2ReviewLoadButton?.addEventListener("click", () => {
  loadCrop2Review();
});
crop2ReviewGrid?.addEventListener("input", (event) => {
  const slider = event.target.closest("[data-crop2-slider]");
  if (!slider) {
    return;
  }
  const itemIndex = Number(slider.dataset.crop2Slider || 0);
  crop2ReviewFrameIndexes[itemIndex] = Number(slider.value || 0);
  renderCrop2ReviewFrame(itemIndex, { seekVideo: true });
});
crop2ReviewGrid?.addEventListener("click", (event) => {
  const playButton = event.target.closest("[data-crop2-play]");
  if (!playButton) {
    return;
  }
  const itemIndex = Number(playButton.dataset.crop2Play || 0);
  if (crop2ReviewTimers[itemIndex]) {
    stopCrop2ReviewTimer(itemIndex);
    return;
  }
  startCrop2ReviewTimer(itemIndex);
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
  const proSkeletonButton = proSkeletonForm.querySelector('button[type="submit"]');
  const isProSkeleton = options.mode === "proSkeleton";
  const hasFormData = Boolean(options.formData);
  const isUpload = hasFormData && !isProSkeleton;
  previewLoadButton.disabled = true;
  uploadButton.disabled = true;
  proSkeletonButton.disabled = true;
  previewLoadButton.textContent = isUpload || isProSkeleton ? "처리 중" : "불러오는 중";
  uploadButton.textContent = isUpload ? "분석 중" : "선택 영상으로 보기";
  proSkeletonButton.textContent = isProSkeleton ? "불러오는 중" : "DB skeleton 보기";
  renderPhaseSkeletonGallery(null);
  renderFullComparison(null);
  renderAlignmentSummary(null);
  drawPreviewPlaceholder(isUpload ? "업로드 영상 분석 중" : "skeleton 준비 중");
  try {
    const response = await fetch(options.endpoint || "/api/experiments/resampling-preview", {
      method: hasFormData ? "POST" : "GET",
      body: options.formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "미리보기 로드 실패");
    }
    previewPayload = payload;
    stationaryFootAnchors = buildStationaryFootAnchors(payload);
    clearDtwAlignmentCache();
    activePhaseIndex = 0;
    previewPhaseSelect.innerHTML = payload.phases
      .map((phase, index) => `<option value="${index}">${escapeHtml(phase.label || phase.phase)}</option>`)
      .join("");
    renderPreviewVideos(payload);
    activeStepIndex = firstScoredStep(activePreviewPhase());
    syncPreviewControls();
    renderCockingEvents(payload.cockingEvents);
    renderPhaseSkeletonGallery(payload);
    renderFullComparison(payload);
    renderAlignmentSummary(payload);
    renderFrameMap(payload);
    renderSkeletonPreview();
  } catch (error) {
    previewPayload = null;
    stationaryFootAnchors = {};
    clearDtwAlignmentCache();
    renderPreviewVideos(null);
    renderCockingEvents(null);
    renderFrameMap(null);
    renderPhaseSkeletonGallery(null);
    renderFullComparison(null);
    renderAlignmentSummary(null);
    drawPreviewPlaceholder(error.message);
  } finally {
    previewLoadButton.disabled = false;
    uploadButton.disabled = false;
    proSkeletonButton.disabled = false;
    previewLoadButton.textContent = "기본 조합 보기";
    uploadButton.textContent = "선택 영상으로 보기";
    proSkeletonButton.textContent = "DB skeleton 보기";
  }
}

async function initializePreview() {
  drawPreviewPlaceholder("미리보기 대기 중");
  await loadPreviewVideoOptions();
  await loadProSkeletonOptions();
  await loadSelectedSkeletonPreview();
}

async function loadSelectedSkeletonPreview() {
  const formData = new FormData(previewUploadForm);
  formData.append(
    "metadata",
    JSON.stringify({
      maxFrames: optionalNumber(formData.get("maxFrames")),
      proTrimStartSec: optionalNumber(formData.get("proTrimStartSec")),
      proTrimEndSec: optionalNumber(formData.get("proTrimEndSec")),
      userTrimStartSec: optionalNumber(formData.get("userTrimStartSec")),
      userTrimEndSec: optionalNumber(formData.get("userTrimEndSec")),
    })
  );
  await loadSkeletonPreview({ formData });
}

async function loadSelectedProSkeletonPreview() {
  const formData = new FormData(proSkeletonForm);
  await loadSkeletonPreview({
    endpoint: "/api/experiments/pro-skeleton-preview",
    formData,
    mode: "proSkeleton",
  });
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

async function loadProSkeletonOptions() {
  try {
    const response = await fetch("/api/experiments/pro-skeleton-options");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "DB skeleton 목록 로드 실패");
    }
    renderProSkeletonOptions(previewProSkeletonSelect, payload.players || [], "DB skeleton 없음");
  } catch (error) {
    renderProSkeletonOptions(previewProSkeletonSelect, [], error.message);
  }
}

async function loadCrop2Review() {
  const maxFrames = optionalNumber(crop2ReviewMaxFrames?.value) || 360;
  crop2ReviewLoadButton.disabled = true;
  crop2ReviewStatus.textContent = "crop2 skeleton 추출 중";
  crop2ReviewGrid.innerHTML = `<p class="empty-state">crop2 영상 분석 중...</p>`;
  stopAllCrop2ReviewTimers();
  try {
    const response = await fetch(`/api/experiments/crop2-skeletons?maxFrames=${encodeURIComponent(maxFrames)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "crop2 skeleton 로드 실패");
    }
    crop2ReviewItems = payload.items || [];
    crop2ReviewSharedBounds = buildCrop2ReviewSharedBounds(crop2ReviewItems);
    crop2ReviewFrameIndexes = Object.fromEntries(crop2ReviewItems.map((_, index) => [index, 0]));
    renderCrop2Review(payload);
  } catch (error) {
    crop2ReviewItems = [];
    crop2ReviewFrameIndexes = {};
    crop2ReviewSharedBounds = null;
    crop2ReviewStatus.textContent = "오류";
    crop2ReviewGrid.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  } finally {
    crop2ReviewLoadButton.disabled = false;
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

function renderProSkeletonOptions(select, players, emptyLabel) {
  select.innerHTML = "";
  if (!players.length) {
    select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    select.disabled = true;
    return;
  }
  select.disabled = false;
  select.innerHTML = players
    .map((player) => {
      const detail = [player.frameCount ? `${player.frameCount}f` : "", player.fps ? `${Number(player.fps).toFixed(2)}fps` : ""]
        .filter(Boolean)
        .join(" / ");
      const label = detail ? `${player.playerName || player.proId} (${detail})` : player.playerName || player.proId;
      return `<option value="${escapeHtml(player.id)}">${escapeHtml(label)}</option>`;
    })
    .join("");
}

function selectPreferredVideo(select, preferredId) {
  const preferred = String(preferredId || "").normalize("NFC");
  const option = Array.from(select.options).find((item) => item.value.normalize("NFC") === preferred);
  if (option) {
    select.value = option.value;
  }
}

function clearDtwAlignmentCache() {
  dtwAlignmentCache = new WeakMap();
}

function phasePreviewFrames(phase) {
  if (!phase?.samples?.length) {
    return [];
  }
  if (activeAlignmentMode !== "dtw" || isProSkeletonDataPreview(previewPayload)) {
    return fixedPhasePreviewFrames(phase);
  }
  return dtwAlignedPhaseFrames(phase);
}

function fixedPhasePreviewFrames(phase) {
  return (phase?.samples || []).map((sample, index) => ({
    alignmentPathLength: phase.samples.length,
    phase,
    proSampleIndex: index,
    sample,
    sampleIndex: index,
    userSampleIndex: index,
  }));
}

function dtwAlignedPhaseFrames(phase) {
  const cached = dtwAlignmentCache.get(phase);
  if (cached) {
    return cached;
  }
  const samples = phase.samples || [];
  if (samples.length < 2) {
    const fallback = fixedPhasePreviewFrames(phase);
    dtwAlignmentCache.set(phase, fallback);
    return fallback;
  }
  const path = buildDtwPath(phase);
  const resampledPath = resampleDtwPath(path, samples.length);
  const frames = resampledPath.map(([proIndex, userIndex], index) => {
    const proSample = samples[proIndex] || samples[0];
    const userSample = samples[userIndex] || samples[0];
    return {
      alignmentPathLength: path.length,
      phase,
      proSampleIndex: proIndex,
      sample: buildAlignedSample(proSample, userSample, index, samples.length, proIndex, userIndex, path.length),
      sampleIndex: index,
      userSampleIndex: userIndex,
    };
  });
  dtwAlignmentCache.set(phase, frames);
  return frames;
}

function buildDtwPath(phase) {
  const samples = phase.samples || [];
  const length = samples.length;
  const windowSize = Math.max(6, Math.ceil(length * 0.25));
  const costs = Array.from({ length }, () => Array(length).fill(Number.POSITIVE_INFINITY));
  const previous = Array.from({ length }, () => Array(length).fill(null));

  for (let proIndex = 0; proIndex < length; proIndex += 1) {
    const minUserIndex = Math.max(0, proIndex - windowSize);
    const maxUserIndex = Math.min(length - 1, proIndex + windowSize);
    for (let userIndex = minUserIndex; userIndex <= maxUserIndex; userIndex += 1) {
      const localCost = poseDistance(previewPoints(samples[proIndex], "pro"), previewPoints(samples[userIndex], "user"));
      if (!Number.isFinite(localCost)) {
        continue;
      }
      const candidates = [
        { cost: proIndex > 0 ? costs[proIndex - 1][userIndex] : Number.POSITIVE_INFINITY, pair: [proIndex - 1, userIndex] },
        { cost: userIndex > 0 ? costs[proIndex][userIndex - 1] : Number.POSITIVE_INFINITY, pair: [proIndex, userIndex - 1] },
        {
          cost: proIndex > 0 && userIndex > 0 ? costs[proIndex - 1][userIndex - 1] : Number.POSITIVE_INFINITY,
          pair: [proIndex - 1, userIndex - 1],
        },
      ];
      if (proIndex === 0 && userIndex === 0) {
        costs[proIndex][userIndex] = localCost;
        continue;
      }
      const best = candidates.reduce((currentBest, candidate) => (candidate.cost < currentBest.cost ? candidate : currentBest));
      if (!Number.isFinite(best.cost)) {
        continue;
      }
      costs[proIndex][userIndex] = localCost + best.cost;
      previous[proIndex][userIndex] = best.pair;
    }
  }

  if (!Number.isFinite(costs[length - 1][length - 1])) {
    return samples.map((_, index) => [index, index]);
  }

  const path = [];
  let proIndex = length - 1;
  let userIndex = length - 1;
  while (proIndex >= 0 && userIndex >= 0) {
    path.push([proIndex, userIndex]);
    const pair = previous[proIndex][userIndex];
    if (!pair) {
      break;
    }
    [proIndex, userIndex] = pair;
  }
  return path.reverse();
}

function resampleDtwPath(path, targetCount) {
  if (!path.length || targetCount <= 0) {
    return [];
  }
  if (targetCount === 1) {
    return [path[0]];
  }
  const result = [];
  for (let index = 0; index < targetCount; index += 1) {
    const sourceIndex = Math.round((index / (targetCount - 1)) * (path.length - 1));
    result.push(path[Math.max(0, Math.min(sourceIndex, path.length - 1))]);
  }
  return result;
}

function buildAlignedSample(proSample, userSample, stepIndex, stepCount, proSampleIndex, userSampleIndex, pathLength) {
  const score = poseScoreForPoints(proSample, userSample);
  return {
    alignment: {
      mode: "dtw",
      pathLength,
      proSampleIndex,
      userSampleIndex,
    },
    progress: stepIndex / Math.max(1, stepCount - 1),
    proDisplayPoints: proSample.proDisplayPoints,
    proFrame: proSample.proFrame,
    proPoints: proSample.proPoints,
    score,
    stepIndex,
    userDisplayPoints: userSample.userDisplayPoints,
    userFrame: userSample.userFrame,
    userPoints: userSample.userPoints,
  };
}

function syncPreviewControls() {
  const phase = activePreviewPhase();
  const maxStep = Math.max(0, (phasePreviewFrames(phase).length || 1) - 1);
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
  return phasePreviewFrames(phase)[activeStepIndex]?.sample || null;
}

function firstScoredStep(phase) {
  const index = phasePreviewFrames(phase).findIndex((item) => scoreForSample(item.sample) != null);
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

function startFullComparison() {
  const frames = fullComparisonFrames(previewPayload);
  if (!frames.length) {
    return;
  }
  stopPreview();
  fullComparisonPlayButton.textContent = "정지";
  fullComparisonTimer = window.setInterval(() => {
    fullComparisonIndex = fullComparisonIndex >= frames.length - 1 ? 0 : fullComparisonIndex + 1;
    renderFullComparisonFrame();
  }, 120);
}

function stopFullComparison() {
  if (fullComparisonTimer) {
    window.clearInterval(fullComparisonTimer);
    fullComparisonTimer = null;
  }
  if (fullComparisonPlayButton) {
    fullComparisonPlayButton.textContent = "전체 재생";
  }
}

function movePreviewStep(delta, options = {}) {
  const phase = activePreviewPhase();
  if (!phase) {
    return;
  }
  const maxStep = Math.max(0, phasePreviewFrames(phase).length - 1);
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
    updatePhaseSkeletonActiveState();
    return;
  }

  const bounds = computePhaseBounds(phase);
  const transform = buildCanvasTransform(bounds);
  const proPoints = previewPoints(sample, "pro");
  const userPoints = previewPoints(sample, "user");
  skeletonContext.clearRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  skeletonContext.fillStyle = "#fffdf8";
  skeletonContext.fillRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  drawPreviewGrid();
  if (isProSkeletonDataPreview(previewPayload)) {
    drawSkeleton(proPoints, transform, "#2368d9", 0.82);
    drawSkeletonLabel(proPoints, transform, previewPayload.sources?.playerName || "DB skeleton", "#2368d9", -12);
    drawDbSkeletonLegend(previewPayload.sources?.playerName || "DB skeleton");
  } else {
    drawSkeleton(proPoints, transform, "#2368d9", 0.78);
    drawSkeleton(userPoints, transform, "#d86b24", 0.78);
    drawSkeletonLabel(proPoints, transform, "선수(pro)", "#2368d9", -12);
    drawSkeletonLabel(userPoints, transform, "사용자(user)", "#d86b24", 14);
    drawLegend();
  }
  drawPreviewTitle(phase, sample);
  updatePreviewReadout(phase, sample);
  syncPreviewVideos(sample);
  renderFrameMap(previewPayload);
  updatePhaseSkeletonActiveState();
}

function isProSkeletonDataPreview(payload) {
  return payload?.sources?.mode === "pro_skeleton_data";
}

function previewPoints(sample, side) {
  const analysisPoints = side === "pro" ? sample?.proPoints : sample?.userPoints;
  const displayPoints = side === "pro" ? sample?.proDisplayPoints : sample?.userDisplayPoints;
  if (activeCoordinateMode === "sourceNormalized") {
    return anchorPointsToJoint(displayPoints || analysisPoints, stationaryFootAnchors[side]);
  }
  if (activeCoordinateMode === "display") {
    return displayPoints || analysisPoints;
  }
  const points = analysisPoints || displayPoints;
  if (activeCoordinateMode === "stationaryFoot") {
    return anchorPointsToJoint(points, stationaryFootAnchors[side]);
  }
  return points;
}

function coordinateModeFromValue(value) {
  if (value === "sourceNormalized" || value === "display" || value === "stationaryFoot") {
    return value;
  }
  return "analysis";
}

function alignmentModeFromValue(value) {
  return value === "dtw" ? "dtw" : "fixed";
}

function coordinateModeLabel() {
  if (activeCoordinateMode === "sourceNormalized") {
    return sourceNormalizedModeLabel();
  }
  if (activeCoordinateMode === "display") {
    return "원본-골반";
  }
  if (activeCoordinateMode === "stationaryFoot") {
    return stationaryFootModeLabel("분석+고정발");
  }
  return "분석 좌표";
}

function sourceNormalizedModeLabel() {
  return stationaryFootModeLabel("원본기반 정규화");
}

function stationaryFootModeLabel(prefix) {
  const proLabel = stationaryFootAnchors.pro?.label;
  const userLabel = stationaryFootAnchors.user?.label;
  if (proLabel && userLabel && !isProSkeletonDataPreview(previewPayload)) {
    return `${prefix}(선수 ${proLabel} / 사용자 ${userLabel})`;
  }
  if (proLabel) {
    return `${prefix}(${proLabel})`;
  }
  return prefix;
}

function alignmentModeLabel(sample) {
  if (activeAlignmentMode !== "dtw" || isProSkeletonDataPreview(previewPayload)) {
    return "Fixed step";
  }
  const alignment = sample?.alignment;
  if (!alignment) {
    return "DTW 정렬";
  }
  return `DTW 정렬(선수 ${alignment.proSampleIndex + 1} / 사용자 ${alignment.userSampleIndex + 1})`;
}

function anchorPointsToJoint(points, anchorConfig) {
  const primaryJoint = anchorConfig?.primaryJoint || "left_foot_index";
  const fallbackJoints = anchorConfig?.fallbackJoints || ["left_ankle"];
  const anchor = validPoint(points?.[primaryJoint]) || fallbackJoints.map((joint) => validPoint(points?.[joint])).find(Boolean);
  if (!anchor) {
    return points;
  }
  const anchored = {};
  for (const [joint, point] of Object.entries(points || {})) {
    if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y)) {
      anchored[joint] = point;
      continue;
    }
    anchored[joint] = {
      ...point,
      x: point.x - anchor.x,
      y: point.y - anchor.y,
    };
  }
  return anchored;
}

function buildStationaryFootAnchors(payload) {
  return {
    pro: detectStationaryFootAnchor(payload, "pro"),
    user: detectStationaryFootAnchor(payload, "user"),
  };
}

function detectStationaryFootAnchor(payload, side) {
  const candidates = ["left", "right"]
    .map((footSide) => ({
      footSide,
      score: stationaryFootScore(payload, side, footSide),
    }))
    .filter((candidate) => Number.isFinite(candidate.score))
    .sort((a, b) => a.score - b.score);
  const selected = candidates[0]?.footSide || "left";
  return {
    primaryJoint: `${selected}_foot_index`,
    fallbackJoints: [`${selected}_ankle`],
    footSide: selected,
    label: selected === "left" ? "왼발" : "오른발",
    score: candidates[0]?.score ?? null,
  };
}

function stationaryFootScore(payload, side, footSide) {
  const footScore = jointDisplayMotionScore(payload, side, `${footSide}_foot_index`);
  const ankleScore = jointDisplayMotionScore(payload, side, `${footSide}_ankle`);
  if (Number.isFinite(footScore) && Number.isFinite(ankleScore)) {
    return footScore * 0.65 + ankleScore * 0.35;
  }
  if (Number.isFinite(footScore)) {
    return footScore;
  }
  return ankleScore;
}

function jointDisplayMotionScore(payload, side, joint) {
  const points = [];
  for (const phase of payload?.phases || []) {
    for (const sample of phase.samples || []) {
      const displayPoints = side === "pro" ? sample.proDisplayPoints : sample.userDisplayPoints;
      const analysisPoints = side === "pro" ? sample.proPoints : sample.userPoints;
      const point = validPoint((displayPoints || analysisPoints)?.[joint]);
      if (point) {
        points.push(point);
      }
    }
  }
  if (points.length < 3) {
    return Number.POSITIVE_INFINITY;
  }

  let pathLength = 0;
  for (let index = 1; index < points.length; index += 1) {
    pathLength += pointDistance(points[index - 1], points[index]);
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const span = Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  return pathLength / Math.max(1, points.length - 1) + span * 0.35;
}

function pointDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function poseScoreForPoints(proSample, userSample) {
  return poseScore(previewPoints(proSample, "pro"), previewPoints(userSample, "user"));
}

function scoreForSample(sample) {
  if (!sample || isProSkeletonDataPreview(previewPayload)) {
    return sample?.score ?? null;
  }
  const dynamicScore = poseScore(previewPoints(sample, "pro"), previewPoints(sample, "user"));
  return dynamicScore ?? sample.score ?? null;
}

function formatSampleScore(sample) {
  const score = scoreForSample(sample);
  return score == null ? "-" : `${score}`;
}

function poseScore(proPoints, userPoints) {
  let weightedTotal = 0;
  let weightTotal = 0;
  for (const joint of scoreJoints) {
    const pro = validPoint(proPoints?.[joint]);
    const user = validPoint(userPoints?.[joint]);
    if (!pro || !user) {
      continue;
    }
    const distance = pointDistance(pro, user);
    const score = 100 * Math.exp(-0.5 * (distance / scoreDistanceSigma) ** 2);
    const weight = Math.sqrt(Math.max(0, Number(pro.confidence || 0)) * Math.max(0, Number(user.confidence || 0)));
    weightedTotal += score * weight;
    weightTotal += weight;
  }
  if (weightTotal <= 0) {
    return null;
  }
  return Math.round((weightedTotal / weightTotal) * 100) / 100;
}

function poseDistance(proPoints, userPoints) {
  let weightedTotal = 0;
  let weightTotal = 0;
  for (const joint of scoreJoints) {
    const pro = validPoint(proPoints?.[joint]);
    const user = validPoint(userPoints?.[joint]);
    if (!pro || !user) {
      continue;
    }
    const weight = Math.sqrt(Math.max(0, Number(pro.confidence || 0)) * Math.max(0, Number(user.confidence || 0)));
    weightedTotal += pointDistance(pro, user) * weight;
    weightTotal += weight;
  }
  return weightTotal > 0 ? weightedTotal / weightTotal : Number.POSITIVE_INFINITY;
}

function computePhaseBounds(phase) {
  const xs = [];
  const ys = [];
  for (const item of phasePreviewFrames(phase)) {
    collectPointBounds(previewPoints(item.sample, "pro"), xs, ys);
    collectPointBounds(previewPoints(item.sample, "user"), xs, ys);
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
  return buildCanvasTransformForCanvas(skeletonCanvas, bounds, 180, 180, 0.58);
}

function buildCanvasTransformForCanvas(canvas, bounds, horizontalPadding, verticalPadding, verticalAnchor) {
  const width = canvas.width;
  const height = canvas.height;
  const rangeX = Math.max(0.8, bounds.maxX - bounds.minX);
  const rangeY = Math.max(1.2, bounds.maxY - bounds.minY);
  const scale = Math.min((width - horizontalPadding) / rangeX, (height - verticalPadding) / rangeY);
  const midX = (bounds.minX + bounds.maxX) / 2;
  const midY = (bounds.minY + bounds.maxY) / 2;
  return {
    project(point) {
      return {
        x: width / 2 + (point.x - midX) * scale,
        y: height * verticalAnchor - (point.y - midY) * scale,
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

function drawDbSkeletonLegend(label) {
  drawLegendItem(label, "#2368d9", 44, 74);
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
  const frameCount = phasePreviewFrames(phase).length || phase.samples.length;
  skeletonContext.fillText(`${phase.label} ${activeStepIndex + 1}/${frameCount}`, 44, 42);
  skeletonContext.fillStyle = "#647067";
  skeletonContext.font = "16px Georgia, serif";
  const progress = `${Math.round((sample.progress || 0) * 100)}%`;
  skeletonContext.fillText(
    `progress ${progress} | score ${formatSampleScore(sample)} | ${coordinateModeLabel()} | ${alignmentModeLabel(sample)}`,
    44,
    skeletonCanvas.height - 28
  );
  skeletonContext.restore();
}

function renderFullComparison(payload) {
  stopFullComparison();
  const frames = fullComparisonFrames(payload);
  if (!fullComparisonCanvas || !fullComparisonContext || !fullComparisonSummary || !fullComparisonSlider) {
    return;
  }
  if (!frames.length) {
    fullComparisonIndex = 0;
    fullComparisonSlider.max = "0";
    fullComparisonSlider.value = "0";
    fullComparisonSummary.textContent = "-";
    fullComparisonFrameText.textContent = "-";
    fullComparisonPhaseTrack.innerHTML = `<p class="empty-state">전체 비교 영상 대기 중</p>`;
    drawFullComparisonPlaceholder("전체 비교 영상 대기 중");
    return;
  }
  fullComparisonIndex = Math.max(0, Math.min(fullComparisonIndex, frames.length - 1));
  fullComparisonSlider.max = `${frames.length - 1}`;
  fullComparisonSlider.value = `${fullComparisonIndex}`;
  fullComparisonSummary.textContent = `${frames.length} steps / ${coordinateModeLabel()} / ${alignmentModeLabel()}`;
  fullComparisonPhaseTrack.innerHTML = renderFullComparisonPhaseTrack(frames);
  renderFullComparisonFrame();
}

function renderAlignmentSummary(payload) {
  if (!alignmentSummary) {
    return;
  }
  if (!payload?.phases?.length) {
    alignmentSummary.innerHTML = `<p class="empty-state">정렬 실험 요약 대기 중</p>`;
    return;
  }
  if (isProSkeletonDataPreview(payload)) {
    alignmentSummary.innerHTML = `<p class="empty-state">DB skeleton 단독 보기에서는 DTW 비교가 없습니다.</p>`;
    return;
  }
  const rows = payload.phases.map((phase) => alignmentSummaryRow(phase)).join("");
  alignmentSummary.innerHTML = `
    <table class="alignment-summary-table">
      <thead>
        <tr>
          <th>Phase</th>
          <th>Fixed 평균</th>
          <th>DTW 평균</th>
          <th>차이</th>
          <th>최대 shift</th>
          <th>DTW path</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function alignmentSummaryRow(phase) {
  const fixedFrames = fixedPhasePreviewFrames(phase);
  const dtwFrames = dtwAlignedPhaseFrames(phase);
  const fixedScore = averageFrameScore(fixedFrames);
  const dtwScore = averageFrameScore(dtwFrames);
  const delta = Number.isFinite(fixedScore) && Number.isFinite(dtwScore) ? dtwScore - fixedScore : null;
  const maxShift = maxAlignmentShift(dtwFrames);
  const pathLength = dtwFrames[0]?.alignmentPathLength || phase.samples?.length || 0;
  return `
    <tr>
      <td>${escapeHtml(phase.label || phaseLabel(phase.phase))}</td>
      <td>${escapeHtml(formatAverageScore(fixedScore))}</td>
      <td>${escapeHtml(formatAverageScore(dtwScore))}</td>
      <td>${escapeHtml(formatScoreDelta(delta))}</td>
      <td>${escapeHtml(`${maxShift} step`)}</td>
      <td>${escapeHtml(`${pathLength}`)}</td>
    </tr>
  `;
}

function averageFrameScore(frames) {
  const scores = frames.map((item) => scoreForSample(item.sample)).filter((score) => Number.isFinite(score));
  if (!scores.length) {
    return Number.NaN;
  }
  return scores.reduce((total, score) => total + score, 0) / scores.length;
}

function maxAlignmentShift(frames) {
  if (!frames.length) {
    return 0;
  }
  return Math.max(...frames.map((item) => Math.abs((item.proSampleIndex || 0) - (item.userSampleIndex || 0))));
}

function formatAverageScore(score) {
  return Number.isFinite(score) ? score.toFixed(2) : "-";
}

function formatScoreDelta(delta) {
  if (!Number.isFinite(delta)) {
    return "-";
  }
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(2)}`;
}

function renderFullComparisonFrame(options = {}) {
  const frames = fullComparisonFrames(previewPayload);
  if (!frames.length || !fullComparisonCanvas || !fullComparisonContext || !fullComparisonSlider) {
    return;
  }
  fullComparisonIndex = Math.max(0, Math.min(fullComparisonIndex, frames.length - 1));
  const item = frames[fullComparisonIndex];
  const bounds = computePayloadBounds(previewPayload);
  const transform = buildCanvasTransformForCanvas(fullComparisonCanvas, bounds, 160, 150, 0.58);
  drawFullComparisonBackground();
  const proPoints = previewPoints(item.sample, "pro");
  const userPoints = previewPoints(item.sample, "user");
  if (isProSkeletonDataPreview(previewPayload)) {
    drawFullComparisonSkeleton(proPoints, transform, "#2368d9", 0.84);
  } else {
    drawFullComparisonSkeleton(proPoints, transform, "#2368d9", 0.78);
    drawFullComparisonSkeleton(userPoints, transform, "#d86b24", 0.78);
  }
  drawFullComparisonTitle(item, frames.length);
  fullComparisonSlider.value = `${fullComparisonIndex}`;
  fullComparisonFrameText.textContent = `${item.phase.label || phaseLabel(item.phase.phase)} ${item.sampleIndex + 1}/${phasePreviewFrames(item.phase).length} · ${fullComparisonIndex + 1}/${frames.length}`;
  updateFullComparisonPhaseTrack(item.phaseIndex);
  if (options.syncMainPreview) {
    activePhaseIndex = item.phaseIndex;
    activeStepIndex = item.sampleIndex;
    syncPreviewControls();
    renderSkeletonPreview();
  }
}

function fullComparisonFrames(payload) {
  const frames = [];
  for (const [phaseIndex, phase] of (payload?.phases || []).entries()) {
    for (const item of phasePreviewFrames(phase)) {
      const sample = item.sample;
      if (previewPoints(sample, "pro") || previewPoints(sample, "user")) {
        frames.push({ ...item, phaseIndex });
      }
    }
  }
  return frames;
}

function computePayloadBounds(payload) {
  const xs = [];
  const ys = [];
  for (const phase of payload?.phases || []) {
    for (const item of phasePreviewFrames(phase)) {
      collectPointBounds(previewPoints(item.sample, "pro"), xs, ys);
      collectPointBounds(previewPoints(item.sample, "user"), xs, ys);
    }
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

function drawFullComparisonPlaceholder(message) {
  drawFullComparisonBackground();
  fullComparisonContext.fillStyle = "#647067";
  fullComparisonContext.font = "700 22px Georgia, serif";
  fullComparisonContext.fillText(message, 44, 76);
}

function drawFullComparisonBackground() {
  fullComparisonContext.clearRect(0, 0, fullComparisonCanvas.width, fullComparisonCanvas.height);
  fullComparisonContext.fillStyle = "#fffdf8";
  fullComparisonContext.fillRect(0, 0, fullComparisonCanvas.width, fullComparisonCanvas.height);
  fullComparisonContext.save();
  fullComparisonContext.strokeStyle = "#eadfce";
  fullComparisonContext.lineWidth = 1;
  for (let x = 76; x < fullComparisonCanvas.width; x += 82) {
    fullComparisonContext.beginPath();
    fullComparisonContext.moveTo(x, 84);
    fullComparisonContext.lineTo(x, fullComparisonCanvas.height - 52);
    fullComparisonContext.stroke();
  }
  for (let y = 104; y < fullComparisonCanvas.height; y += 76) {
    fullComparisonContext.beginPath();
    fullComparisonContext.moveTo(46, y);
    fullComparisonContext.lineTo(fullComparisonCanvas.width - 46, y);
    fullComparisonContext.stroke();
  }
  fullComparisonContext.restore();
}

function drawFullComparisonSkeleton(points, transform, color, alpha) {
  fullComparisonContext.save();
  fullComparisonContext.lineCap = "round";
  fullComparisonContext.lineJoin = "round";
  fullComparisonContext.strokeStyle = color;
  fullComparisonContext.fillStyle = color;
  fullComparisonContext.globalAlpha = alpha;
  fullComparisonContext.lineWidth = 6;

  for (const [start, end] of jointEdges) {
    const startPoint = validPoint(points?.[start]);
    const endPoint = validPoint(points?.[end]);
    if (!startPoint || !endPoint) {
      continue;
    }
    const a = transform.project(startPoint);
    const b = transform.project(endPoint);
    fullComparisonContext.beginPath();
    fullComparisonContext.moveTo(a.x, a.y);
    fullComparisonContext.lineTo(b.x, b.y);
    fullComparisonContext.stroke();
  }

  for (const point of Object.values(points || {})) {
    const valid = validPoint(point);
    if (!valid) {
      continue;
    }
    const projected = transform.project(valid);
    fullComparisonContext.beginPath();
    fullComparisonContext.arc(projected.x, projected.y, 6.7, 0, Math.PI * 2);
    fullComparisonContext.fill();
  }
  fullComparisonContext.restore();
}

function drawFullComparisonTitle(item, frameCount) {
  fullComparisonContext.save();
  fullComparisonContext.fillStyle = "#17201b";
  fullComparisonContext.font = "700 26px Georgia, serif";
  fullComparisonContext.fillText(
    `${item.phase.label || phaseLabel(item.phase.phase)} ${item.sampleIndex + 1}/${phasePreviewFrames(item.phase).length}`,
    44,
    42
  );
  fullComparisonContext.fillStyle = "#647067";
  fullComparisonContext.font = "16px Georgia, serif";
  fullComparisonContext.fillText(
    `전체 ${fullComparisonIndex + 1}/${frameCount} | score ${formatSampleScore(item.sample)} | 선수 ${formatFrame(item.sample.proFrame)} / 사용자 ${formatFrame(item.sample.userFrame)} | ${alignmentModeLabel(item.sample)}`,
    44,
    fullComparisonCanvas.height - 28
  );
  fullComparisonContext.restore();
}

function renderFullComparisonPhaseTrack(frames) {
  const phaseGroups = [];
  for (const [index, frame] of frames.entries()) {
    const latest = phaseGroups[phaseGroups.length - 1];
    if (latest?.phaseIndex === frame.phaseIndex) {
      latest.count += 1;
      continue;
    }
    phaseGroups.push({
      phaseIndex: frame.phaseIndex,
      firstFrameIndex: index,
      count: 1,
      phase: frame.phase,
    });
  }
  return phaseGroups
    .map((group) => {
      const className = phaseClassNames[group.phase.phase] || "phase-unknown";
      const width = Math.max(3, (group.count / frames.length) * 100);
      return `
        <button
          type="button"
          class="full-phase-segment ${className}"
          style="width: ${width}%"
          data-full-frame-index="${group.firstFrameIndex}"
          data-full-phase-index="${group.phaseIndex}"
        >
          ${escapeHtml(group.phase.label || phaseLabel(group.phase.phase))}
        </button>
      `;
    })
    .join("");
}

function updateFullComparisonPhaseTrack(activePhaseIndexValue) {
  if (!fullComparisonPhaseTrack) {
    return;
  }
  for (const segment of fullComparisonPhaseTrack.querySelectorAll("[data-full-phase-index]")) {
    segment.classList.toggle("is-active", Number(segment.dataset.fullPhaseIndex) === activePhaseIndexValue);
  }
}

function renderPhaseSkeletonGallery(payload) {
  if (!phaseSkeletonGallery || !phaseSkeletonSummary) {
    return;
  }
  if (!payload?.phases?.length) {
    phaseSkeletonSummary.textContent = "-";
    phaseSkeletonGallery.innerHTML = `<p class="empty-state">phase skeleton 대기 중</p>`;
    return;
  }

  const proOnly = isProSkeletonDataPreview(payload);
  phaseSkeletonSummary.textContent = proOnly
    ? `${payload.phases.length}개 phase / DB skeleton / ${coordinateModeLabel()}`
    : `${payload.phases.length}개 phase / 선수 + 사용자 / ${coordinateModeLabel()} / ${alignmentModeLabel()}`;
  phaseSkeletonGallery.innerHTML = payload.phases
    .map((phase, phaseIndex) => renderPhaseSkeletonCard(phase, phaseIndex, proOnly))
    .join("");
  window.requestAnimationFrame(() => drawPhaseSkeletonCanvases(payload));
}

function renderPhaseSkeletonCard(phase, phaseIndex, proOnly) {
  const frames = phasePreviewFrames(phase);
  const sampleIndex = representativeSampleIndex(phase);
  const sample = frames[sampleIndex]?.sample || {};
  const label = phase.label || phaseLabel(phase.phase);
  const score = formatSampleScore(sample);
  const frameText = proOnly
    ? `선수 ${formatFrame(sample.proFrame)}`
    : `선수 ${formatFrame(sample.proFrame)} / 사용자 ${formatFrame(sample.userFrame)}`;
  const canvasNodes = (proOnly ? ["pro"] : ["pro", "user"])
    .map((side) => {
      const sideLabel = side === "pro" ? "선수(pro)" : "사용자(user)";
      return `
        <div class="phase-skeleton-side">
          <span>${sideLabel}</span>
          <canvas
            width="260"
            height="200"
            data-phase-skeleton-side="${side}"
            data-phase-index="${phaseIndex}"
            data-sample-index="${sampleIndex}"
            aria-label="${escapeHtml(label)} ${sideLabel} skeleton"
          ></canvas>
        </div>
      `;
    })
    .join("");
  const activeClass = phaseIndex === activePhaseIndex ? "is-active" : "";

  return `
    <button
      type="button"
      class="phase-skeleton-card ${activeClass}"
      data-phase-jump="${phaseIndex}"
      data-sample-index="${sampleIndex}"
      aria-label="${escapeHtml(label)} 대표 skeleton 보기"
    >
      <span class="phase-skeleton-card-head">
        <strong>${escapeHtml(label)}</strong>
        <em>${frames.length ? sampleIndex + 1 : 0}/${frames.length || 0}</em>
      </span>
      <span class="phase-skeleton-meta">score ${escapeHtml(score)} · ${escapeHtml(frameText)}</span>
      <span class="phase-skeleton-canvases">${canvasNodes}</span>
    </button>
  `;
}

function representativeSampleIndex(phase) {
  const frames = phasePreviewFrames(phase);
  if (!frames.length) {
    return 0;
  }
  const candidates = frames.filter((item) => scoreForSample(item.sample) != null);
  const pool = candidates.length ? candidates : frames;
  const centerIndex = (frames.length - 1) / 2;
  let best = pool[0];
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const candidate of pool) {
    const progress = Number(candidate.sample.progress);
    const distance = Number.isFinite(progress)
      ? Math.abs(progress - 0.5)
      : Math.abs(candidate.sampleIndex - centerIndex) / Math.max(1, centerIndex);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best.sampleIndex;
}

function drawPhaseSkeletonCanvases(payload) {
  if (!phaseSkeletonGallery) {
    return;
  }
  const canvases = phaseSkeletonGallery.querySelectorAll("canvas[data-phase-skeleton-side]");
  for (const canvas of canvases) {
    const phase = payload.phases?.[Number(canvas.dataset.phaseIndex)];
    const sample = phasePreviewFrames(phase)[Number(canvas.dataset.sampleIndex)]?.sample;
    const side = canvas.dataset.phaseSkeletonSide;
    const context = canvas.getContext("2d");
    drawMiniSkeletonBackground(context, canvas);
    if (!phase || !sample) {
      continue;
    }
    const bounds = computePhaseBounds(phase);
    const transform = buildMiniCanvasTransform(canvas, bounds);
    const points = previewPoints(sample, side);
    drawMiniSkeleton(context, points, transform, side === "pro" ? "#2368d9" : "#d86b24", 0.8);
  }
}

function drawMiniSkeletonBackground(context, canvas) {
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#fffdf8";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.save();
  context.strokeStyle = "#eadfce";
  context.lineWidth = 1;
  for (let x = 28; x < canvas.width; x += 46) {
    context.beginPath();
    context.moveTo(x, 20);
    context.lineTo(x, canvas.height - 16);
    context.stroke();
  }
  for (let y = 32; y < canvas.height; y += 44) {
    context.beginPath();
    context.moveTo(18, y);
    context.lineTo(canvas.width - 18, y);
    context.stroke();
  }
  context.restore();
}

function buildMiniCanvasTransform(canvas, bounds) {
  return buildCanvasTransformForCanvas(canvas, bounds, 46, 50, 0.58);
}

function drawMiniSkeleton(context, points, transform, color, alpha) {
  context.save();
  context.lineCap = "round";
  context.lineJoin = "round";
  context.strokeStyle = color;
  context.fillStyle = color;
  context.globalAlpha = alpha;
  context.lineWidth = 4;

  for (const [start, end] of jointEdges) {
    const startPoint = validPoint(points?.[start]);
    const endPoint = validPoint(points?.[end]);
    if (!startPoint || !endPoint) {
      continue;
    }
    const a = transform.project(startPoint);
    const b = transform.project(endPoint);
    context.beginPath();
    context.moveTo(a.x, a.y);
    context.lineTo(b.x, b.y);
    context.stroke();
  }

  for (const point of Object.values(points || {})) {
    const valid = validPoint(point);
    if (!valid) {
      continue;
    }
    const projected = transform.project(valid);
    context.beginPath();
    context.arc(projected.x, projected.y, 4.5, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
}

function updatePhaseSkeletonActiveState() {
  if (!phaseSkeletonGallery) {
    return;
  }
  for (const card of phaseSkeletonGallery.querySelectorAll("[data-phase-jump]")) {
    card.classList.toggle("is-active", Number(card.dataset.phaseJump) === activePhaseIndex);
  }
}

function updatePreviewReadout(phase, sample) {
  const frameCount = phasePreviewFrames(phase).length || phase.samples.length;
  previewStepText.textContent = `${activeStepIndex + 1} / ${frameCount}`;
  previewScoreText.textContent = formatSampleScore(sample);
  previewFrameText.textContent = `선수 ${formatFrame(sample.proFrame)} / 사용자 ${formatFrame(sample.userFrame)}`;
  if (previewAlignmentText) {
    previewAlignmentText.textContent = alignmentModeLabel(sample);
  }
  previewReleaseText.textContent = formatReleaseInfo(previewPayload?.releaseEvents);
  previewSourceText.textContent = formatPreviewSource(previewPayload);
}

function renderPreviewVideos(payload) {
  const proSource = payload?.videoSources?.pro || null;
  const userSource = isProSkeletonDataPreview(payload) ? null : payload?.videoSources?.user || null;
  setPreviewVideoSource(previewProVideoCard, previewProVideo, previewProVideoFrame, proSource);
  setPreviewVideoSource(previewUserVideoCard, previewUserVideo, previewUserVideoFrame, userSource);
  previewVideoPanel.hidden = !proSource && !userSource;
}

function setPreviewVideoSource(card, video, frameLabel, source) {
  if (!card || !video || !frameLabel) {
    return;
  }
  if (!source?.url) {
    card.hidden = true;
    frameLabel.textContent = "-";
    video.pause();
    video.removeAttribute("src");
    video.load();
    return;
  }
  card.hidden = false;
  if (video.getAttribute("src") !== source.url) {
    video.src = source.url;
    video.load();
  }
}

function syncPreviewVideos(sample) {
  if (!sample || previewVideoPanel.hidden) {
    return;
  }
  syncPreviewVideoToFrame("pro", previewProVideoCard, previewProVideo, previewProVideoFrame, sample.proFrame);
  syncPreviewVideoToFrame("user", previewUserVideoCard, previewUserVideo, previewUserVideoFrame, sample.userFrame);
}

function syncPreviewVideoToFrame(side, card, video, frameLabel, frame) {
  if (!card || card.hidden || !video || !frameLabel) {
    return;
  }
  const fps = Number(previewPayload?.videoMeta?.[side]?.fps);
  if (!Number.isFinite(frame) || !Number.isFinite(fps) || fps <= 0) {
    frameLabel.textContent = "-";
    return;
  }
  const seconds = Math.max(0, frame / fps);
  frameLabel.textContent = `${formatFrame(frame)}f / ${formatSecond(seconds)}s`;
  seekVideoToSecond(video, seconds);
}

function seekVideoToSecond(video, seconds) {
  if (!video.src) {
    return;
  }
  if (video.readyState < 1) {
    video.addEventListener("loadedmetadata", () => seekVideoToSecond(video, seconds), { once: true });
    return;
  }
  const duration = Number.isFinite(video.duration) ? video.duration : seconds;
  const target = Math.max(0, Math.min(seconds, duration));
  if (Math.abs(video.currentTime - target) > 0.04) {
    video.currentTime = target;
  }
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

function scoreMarkersForPayload(payload) {
  const scoredSamples = [];
  for (const phase of payload?.phases || []) {
    for (const sample of phase.samples || []) {
      const score = scoreForSample(sample);
      if (score == null) {
        continue;
      }
      scoredSamples.push({
        phase: phase.phase,
        label: phase.label || phase.phase,
        stepIndex: sample.stepIndex,
        proFrame: sample.proFrame,
        userFrame: sample.userFrame,
        score,
      });
    }
  }

  const good = scoredSamples
    .filter((sample) => sample.score >= goodFrameScoreThreshold)
    .sort((a, b) => b.score - a.score)
    .slice(0, frameMarkerLimit);
  const bad = scoredSamples
    .filter((sample) => sample.score <= badFrameScoreThreshold)
    .sort((a, b) => a.score - b.score)
    .slice(0, frameMarkerLimit);

  return {
    good: good.length ? good : scoredSamples.sort((a, b) => b.score - a.score).slice(0, 1),
    bad: bad.length ? bad : scoredSamples.sort((a, b) => a.score - b.score).slice(0, 1),
  };
}

function timelineMarkersForSide(side, payload) {
  const markers = [];
  const scoreMarkers = scoreMarkersForPayload(payload);
  for (const kind of ["good", "bad"]) {
    for (const marker of scoreMarkers[kind] || []) {
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
  for (const marker of payload.frameMarkers?.release || []) {
    const frame = Number(marker[`${side}Frame`]);
    if (!Number.isFinite(frame)) {
      continue;
    }
    markers.push({
      ...marker,
      kind: "release",
      frame,
      title: markerTitle("release", marker, frame),
    });
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
      const title = `${phase.label || phase.phase} ${formatFrame(frame)} / score ${formatSampleScore(sample)}`;
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
  const trimText = formatTrimInfo(payload?.previewTrim);
  const suffix = trimText ? ` | ${trimText}` : "";
  if (sources.mode === "uploaded_videos") {
    return `${sources.proVideo || "pro"} / ${sources.userVideo || "user"}${suffix}`;
  }
  if (sources.mode === "folder_videos") {
    return `${sources.proSource || "pro_data"}:${sources.proVideo || "pro"} / ${sources.userSource || "user_data"}:${sources.userVideo || "user"}${suffix}`;
  }
  if (sources.mode === "mixed_videos") {
    return `${sources.proSource || "pro"}:${sources.proVideo || "pro"} / ${sources.userSource || "user"}:${sources.userVideo || "user"}${suffix}`;
  }
  if (sources.mode === "pro_skeleton_data") {
    return `DB:${sources.playerName || sources.proId || "pro skeleton"}`;
  }
  return "기본 샘플";
}

function formatTrimInfo(trim) {
  const pro = trim?.pro;
  const user = trim?.user;
  const parts = [];
  if (pro?.enabled) {
    parts.push(`선수 ${formatSecond(pro.startSec)}~${formatSecond(pro.endSec)}s`);
  }
  if (user?.enabled) {
    parts.push(`사용자 ${formatSecond(user.startSec)}~${formatSecond(user.endSec)}s`);
  }
  return parts.join(" / ");
}

function formatSecond(value) {
  return Number.isFinite(value) ? Number(value).toFixed(2) : "-";
}

function renderCrop2Review(payload) {
  if (!crop2ReviewItems.length) {
    crop2ReviewStatus.textContent = "영상 없음";
    crop2ReviewGrid.innerHTML = `<p class="empty-state">pro_data/crop2 안에 검수할 영상이 없습니다.</p>`;
    return;
  }
  crop2ReviewStatus.textContent = `${crop2ReviewItems.length}개 영상 / ${payload.analysisMaxFrames || "-"}f 제한 / 원본기반 정규화`;
  crop2ReviewGrid.innerHTML = crop2ReviewItems.map((item, index) => renderCrop2ReviewCard(item, index)).join("");
  window.requestAnimationFrame(() => {
    for (let index = 0; index < crop2ReviewItems.length; index += 1) {
      renderCrop2ReviewFrame(index, { seekVideo: false });
    }
  });
}

function renderCrop2ReviewCard(item, index) {
  const frames = crop2ReviewFrames(item);
  const meta = item.videoMeta || {};
  const frameCount = Number(meta.frameCount);
  const fps = Number(meta.fps);
  const frameText = Number.isFinite(frameCount) ? `${frameCount}f` : "-";
  const fpsText = Number.isFinite(fps) ? `${fps.toFixed(2)}fps` : "-";
  const sourceUrl = item.videoSource?.url || "";
  const phaseNames = (item.phases || []).map((phase) => phase.label || phaseLabel(phase.phase)).join(" · ");
  const warningText = crop2WarningText(item);
  return `
    <article class="crop2-review-card" data-crop2-card="${index}">
      <header>
        <div>
          <strong>${escapeHtml(item.label || item.filename || `crop2 ${index + 1}`)}</strong>
          <span>${escapeHtml(frameText)} / ${escapeHtml(fpsText)} / ${frames.length} skeleton steps</span>
        </div>
        <em>원본기반 정규화</em>
      </header>
      <video src="${escapeHtml(sourceUrl)}" controls playsinline preload="metadata"></video>
      <canvas width="420" height="320" data-crop2-canvas="${index}" aria-label="${escapeHtml(item.label || item.filename)} skeleton"></canvas>
      <div class="crop2-review-controls">
        <button type="button" data-crop2-play="${index}">재생</button>
        <input type="range" min="0" max="${Math.max(0, frames.length - 1)}" value="0" data-crop2-slider="${index}" />
        <span data-crop2-readout="${index}">-</span>
      </div>
      <p class="crop2-review-phases">${escapeHtml(phaseNames || "phase 없음")}</p>
      ${warningText ? `<p class="crop2-review-warning">${escapeHtml(warningText)}</p>` : ""}
    </article>
  `;
}

function crop2WarningText(item) {
  const warnings = item.warnings?.pro || item.warnings || [];
  return Array.isArray(warnings) ? warnings.slice(0, 2).join(" / ") : "";
}

function crop2ReviewFrames(item) {
  const frames = [];
  for (const [phaseIndex, phase] of (item?.phases || []).entries()) {
    for (const [sampleIndex, sample] of (phase.samples || []).entries()) {
      if (crop2ReviewPoints(item, sample)) {
        frames.push({ phase, phaseIndex, sample, sampleIndex });
      }
    }
  }
  return frames;
}

function crop2ReviewPoints(_item, sample) {
  return sample?.proDisplayPoints || sample?.proPoints || null;
}

function renderCrop2ReviewFrame(itemIndex, options = {}) {
  const item = crop2ReviewItems[itemIndex];
  const frames = crop2ReviewFrames(item);
  const card = crop2ReviewGrid.querySelector(`[data-crop2-card="${itemIndex}"]`);
  const canvas = crop2ReviewGrid.querySelector(`canvas[data-crop2-canvas="${itemIndex}"]`);
  if (!item || !frames.length || !card || !canvas) {
    return;
  }
  const frameIndex = Math.max(0, Math.min(crop2ReviewFrameIndexes[itemIndex] || 0, frames.length - 1));
  crop2ReviewFrameIndexes[itemIndex] = frameIndex;
  const frame = frames[frameIndex];
  const context = canvas.getContext("2d");
  const bounds = crop2ReviewSharedBounds || buildCrop2ReviewSharedBounds([item]);
  const transform = buildCanvasTransformForCanvas(canvas, bounds, 58, 56, 0.58);
  drawMiniSkeletonBackground(context, canvas);
  drawMiniSkeleton(context, crop2ReviewPoints(item, frame.sample), transform, "#2368d9", 0.88);
  context.save();
  context.fillStyle = "#17201b";
  context.font = "700 18px Georgia, serif";
  context.fillText(`${frame.phase.label || phaseLabel(frame.phase.phase)} ${frame.sampleIndex + 1}/${frame.phase.samples.length}`, 18, 26);
  context.restore();
  updateCrop2ReviewControls(card, item, frame, frameIndex, frames.length, options);
}

function buildCrop2ReviewSharedBounds(items) {
  const xs = [];
  const ys = [];
  for (const item of items || []) {
    for (const frame of crop2ReviewFrames(item)) {
      collectPointBounds(crop2ReviewPoints(item, frame.sample), xs, ys);
    }
  }
  if (!xs.length || !ys.length) {
    return crop2ReviewDefaultBounds();
  }
  return expandBoundsToMinimumRange(
    {
      minX: percentile(xs, 0.02),
      maxX: percentile(xs, 0.98),
      minY: percentile(ys, 0.02),
      maxY: percentile(ys, 0.98),
    },
    { minRangeX: 4.8, minRangeY: 3.8 }
  );
}

function crop2ReviewDefaultBounds() {
  return { minX: -2.4, maxX: 2.4, minY: -1.9, maxY: 1.9 };
}

function expandBoundsToMinimumRange(bounds, ranges) {
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const rangeX = Math.max(ranges.minRangeX, bounds.maxX - bounds.minX);
  const rangeY = Math.max(ranges.minRangeY, bounds.maxY - bounds.minY);
  return {
    minX: centerX - rangeX / 2,
    maxX: centerX + rangeX / 2,
    minY: centerY - rangeY / 2,
    maxY: centerY + rangeY / 2,
  };
}

function percentile(values, ratio) {
  const sorted = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!sorted.length) {
    return 0;
  }
  const index = Math.max(0, Math.min(sorted.length - 1, Math.round((sorted.length - 1) * ratio)));
  return sorted[index];
}

function updateCrop2ReviewControls(card, item, frame, frameIndex, frameCount, options) {
  const slider = card.querySelector("[data-crop2-slider]");
  const readout = card.querySelector("[data-crop2-readout]");
  const video = card.querySelector("video");
  if (slider) {
    slider.value = `${frameIndex}`;
  }
  if (readout) {
    readout.textContent = `${frameIndex + 1}/${frameCount} · ${frame.phase.label || phaseLabel(frame.phase.phase)} · ${formatFrame(frame.sample.proFrame)}f`;
  }
  if (options.seekVideo && video) {
    const fps = Number(item.videoMeta?.fps);
    const frameNumber = Number(frame.sample.proFrame);
    if (Number.isFinite(fps) && fps > 0 && Number.isFinite(frameNumber)) {
      seekVideoToSecond(video, frameNumber / fps);
    }
  }
}

function startCrop2ReviewTimer(itemIndex) {
  stopAllCrop2ReviewTimers();
  const frames = crop2ReviewFrames(crop2ReviewItems[itemIndex]);
  if (!frames.length) {
    return;
  }
  const card = crop2ReviewGrid.querySelector(`[data-crop2-card="${itemIndex}"]`);
  const button = card?.querySelector("[data-crop2-play]");
  if (button) {
    button.textContent = "정지";
  }
  crop2ReviewTimers[itemIndex] = window.setInterval(() => {
    const nextIndex = (crop2ReviewFrameIndexes[itemIndex] || 0) + 1;
    crop2ReviewFrameIndexes[itemIndex] = nextIndex >= frames.length ? 0 : nextIndex;
    renderCrop2ReviewFrame(itemIndex, { seekVideo: true });
  }, 140);
}

function stopCrop2ReviewTimer(itemIndex) {
  if (crop2ReviewTimers[itemIndex]) {
    window.clearInterval(crop2ReviewTimers[itemIndex]);
    delete crop2ReviewTimers[itemIndex];
  }
  const button = crop2ReviewGrid.querySelector(`[data-crop2-play="${itemIndex}"]`);
  if (button) {
    button.textContent = "재생";
  }
}

function stopAllCrop2ReviewTimers() {
  for (const itemIndex of Object.keys(crop2ReviewTimers)) {
    stopCrop2ReviewTimer(Number(itemIndex));
  }
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
