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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
