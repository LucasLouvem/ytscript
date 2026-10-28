const form = document.getElementById("form");
const urlInput = document.getElementById("url");
const clearUrl = document.getElementById("clear-url");
const submit = document.getElementById("submit");
const errorBox = document.getElementById("error");
const transcriptList = document.getElementById("transcript");
const search = document.getElementById("search");
const charCount = document.getElementById("char-count");
const languageSelect = document.getElementById("language");
const formatSelect = document.getElementById("format");
const translateSelect = document.getElementById("translate-to");
const timestampsToggle = document.getElementById("timestamps");
const copyButton = document.getElementById("copy");
const downloadButton = document.getElementById("download");
const thumb = document.getElementById("thumb");
const thumbPlaceholder = document.getElementById("thumb-placeholder");
const videoTitle = document.getElementById("video-title");
const videoMeta = document.getElementById("video-meta");
const durationField = document.getElementById("duration");
const nativeLanguageField = document.getElementById("native-language");
const lineCount = document.getElementById("line-count");
const elapsed = document.getElementById("elapsed");

const EMPTY_MESSAGE = "A transcrição aparece aqui.";
const AUTO_LANGUAGE_LABEL = "Automático (pt-BR / pt)";
const NO_TRANSLATION_LABEL = "Não traduzir";
const PLACEHOLDER = "—";

let current = null;

function languageName(code) {
  try {
    return new Intl.DisplayNames(["pt-BR"], { type: "language" }).of(code) || code;
  } catch {
    return code;
  }
}

function formatDuration(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (value) => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

function formatViews(count) {
  const compact = new Intl.NumberFormat("pt-BR", { notation: "compact" }).format(count);
  return `${compact} visualizações`;
}

function formatDate(iso) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(iso));
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function setOptions(select, firstLabel, options, selected) {
  select.replaceChildren(new Option(firstLabel, ""));
  for (const { value, label } of options) {
    select.append(new Option(label, value));
  }
  select.value = options.some((option) => option.value === selected) ? selected : "";
}

function trackLabel(track) {
  const kind = track.is_generated ? "automática" : "manual";
  return `${languageName(track.language_code)} (${kind})`;
}

function renderOptions(data, requestedLanguage, requestedTranslation) {
  const languages = data.tracks.map((track) => ({
    value: track.language_code,
    label: trackLabel(track),
  }));
  setOptions(languageSelect, AUTO_LANGUAGE_LABEL, languages, requestedLanguage);

  const active = data.tracks.find((track) => track.language_code === data.transcript.language_code);
  const translations = (active ? active.translation_languages : []).map((item) => ({
    value: item.language_code,
    label: languageName(item.language_code),
  }));
  setOptions(translateSelect, NO_TRANSLATION_LABEL, translations, requestedTranslation);
  translateSelect.disabled = translations.length === 0;
}

function renderVideo(video) {
  if (!video) {
    thumb.hidden = true;
    thumbPlaceholder.hidden = false;
    videoTitle.textContent = "Dados do vídeo indisponíveis";
    videoMeta.textContent = PLACEHOLDER;
    durationField.textContent = PLACEHOLDER;
    nativeLanguageField.textContent = PLACEHOLDER;
    return;
  }
  const fallback = video.thumbnail_url.replace("maxresdefault", "mqdefault");
  const useFallback = () => {
    thumb.onload = null;
    thumb.onerror = null;
    thumb.src = fallback;
  };
  // Sem maxresdefault o YouTube responde 404 com um placeholder 120x90 que carrega como imagem.
  thumb.onload = () => {
    if (thumb.naturalWidth <= 120) useFallback();
  };
  thumb.onerror = useFallback;
  thumb.src = video.thumbnail_url;
  thumb.alt = video.title;
  thumb.hidden = false;
  thumbPlaceholder.hidden = true;
  videoTitle.textContent = video.title;
  videoMeta.textContent = [
    video.channel,
    formatViews(video.view_count),
    formatDate(video.published_at),
  ].join(" · ");
  durationField.textContent = formatDuration(video.duration_seconds);
  nativeLanguageField.textContent = video.native_language
    ? languageName(video.native_language)
    : PLACEHOLDER;
}

function outputText() {
  if (!current) return "";
  if (formatSelect.value === "srt") return current.srt;
  if (formatSelect.value === "md") return current.markdown;
  if (timestampsToggle.checked) return current.text;
  return current.segments
    .map((segment) => segment.text.trim())
    .filter(Boolean)
    .join("\n");
}

const FILE_TYPES = { txt: "text/plain", srt: "text/plain", md: "text/markdown" };

// SRT e Markdown já saem do servidor com timestamps; só o .txt respeita o toggle.
function fixedTimestamps() {
  return formatSelect.value !== "txt";
}

function renderSegments() {
  const segments = current ? current.segments : [];
  const term = search.value.trim().toLowerCase();
  const visible = term ? segments.filter((s) => s.text.toLowerCase().includes(term)) : segments;
  const showTimestamps = fixedTimestamps() || timestampsToggle.checked;
  transcriptList.replaceChildren();
  if (visible.length === 0) {
    const item = document.createElement("li");
    item.className = "empty";
    item.textContent = segments.length ? "Nenhum trecho encontrado." : EMPTY_MESSAGE;
    transcriptList.append(item);
  }
  for (const segment of visible) {
    const item = document.createElement("li");
    if (showTimestamps) {
      const time = document.createElement("span");
      time.className = "time";
      time.textContent = `[${segment.timestamp}]`;
      item.append(time);
    }
    const text = document.createElement("span");
    text.textContent = segment.text;
    item.append(text);
    transcriptList.append(item);
  }
  charCount.textContent = `${outputText().length.toLocaleString("pt-BR")} caracteres`;
  timestampsToggle.disabled = fixedTimestamps() || !current;
}

function resetResult() {
  current = null;
  search.value = "";
  search.disabled = true;
  copyButton.disabled = true;
  downloadButton.disabled = true;
  lineCount.textContent = PLACEHOLDER;
  elapsed.textContent = PLACEHOLDER;
  renderSegments();
}

async function requestTranscript() {
  errorBox.hidden = true;
  submit.disabled = true;
  submit.textContent = "Transcrevendo...";
  const requestedLanguage = languageSelect.value;
  const requestedTranslation = translateSelect.value;
  const body = { url: urlInput.value.trim() };
  if (requestedLanguage) body.language = requestedLanguage;
  if (requestedTranslation) body.translate_to = requestedTranslation;
  const startedAt = performance.now();
  try {
    const response = await fetch("/api/transcripts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      resetResult();
      showError(`${data.message} ${data.action}`);
      return;
    }
    current = data;
    search.value = "";
    search.disabled = false;
    copyButton.disabled = false;
    downloadButton.disabled = false;
    renderOptions(data, requestedLanguage, requestedTranslation);
    renderVideo(data.video);
    renderSegments();
    lineCount.textContent = String(data.segments.length);
    elapsed.textContent = `${Math.round((performance.now() - startedAt) / 1000)} segundos`;
  } catch {
    resetResult();
    showError("Não foi possível falar com o servidor. Verifique se ele está rodando.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Transcrever";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  requestTranscript();
});

for (const select of [languageSelect, translateSelect]) {
  select.addEventListener("change", () => {
    if (current && urlInput.value.trim()) requestTranscript();
  });
}

for (const control of [formatSelect, timestampsToggle]) {
  control.addEventListener("change", renderSegments);
}

search.addEventListener("input", renderSegments);

clearUrl.addEventListener("click", () => {
  urlInput.value = "";
  urlInput.focus();
});

copyButton.addEventListener("click", () => {
  navigator.clipboard.writeText(outputText());
});

downloadButton.addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([outputText()], { type: FILE_TYPES[formatSelect.value] }));
  link.download = `transcricao.${formatSelect.value}`;
  link.click();
  URL.revokeObjectURL(link.href);
});
