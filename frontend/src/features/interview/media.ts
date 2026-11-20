/**
 * 브라우저 녹음과 카메라 캡처. 녹음 파일과 캡처 이미지는 서버로 보낸 뒤 브라우저에 남기지 않는다.
 */

/** Transcribe가 받는 형식 가운데 이 브라우저가 녹음할 수 있는 것 (Chrome·Firefox는 webm, Safari는 mp4) */
const AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function canRecord(): boolean {
  return typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined";
}

export type AnswerRecorder = {
  /** 녹음을 끝내고 파일을 돌려준다. 여러 번 불러도 같은 파일이다. */
  stop: () => Promise<Blob>;
  /** 파일을 만들지 않고 그만둔다 */
  cancel: () => void;
};

/** 답변 녹음을 시작한다. 카메라가 함께 열려 있어도 소리만 녹음한다. */
export function startAnswerRecorder(stream: MediaStream): AnswerRecorder {
  const audioOnly = new MediaStream(stream.getAudioTracks());
  const mimeType = AUDIO_TYPES.find((type) => window.MediaRecorder.isTypeSupported(type));
  // 2분 답변이 업로드 한도(6MB)를 넘지 않게 음성에 충분한 낮은 비트레이트로 녹음한다
  const recorder = new window.MediaRecorder(audioOnly, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 32000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };

  let done: Promise<Blob> | null = null;
  recorder.start(1000);

  return {
    stop() {
      done ??= new Promise<Blob>((resolve) => {
        const finish = () => resolve(new Blob(chunks, { type: (recorder.mimeType || mimeType || "audio/webm").split(";")[0] }));
        if (recorder.state === "inactive") finish();
        else {
          recorder.onstop = finish;
          recorder.stop();
        }
      });
      return done;
    },
    cancel() {
      if (recorder.state !== "inactive") recorder.stop();
    },
  };
}

const FRAME_WIDTH = 640;
const FRAME_QUALITY = 0.72;

/** 지금 화면을 JPEG 한 장으로 만든다. 영상이 아직 안 나왔으면 null. */
export function captureFrame(video: HTMLVideoElement | null): Promise<Blob | null> {
  if (!video || video.videoWidth === 0 || video.videoHeight === 0) return Promise.resolve(null);
  const scale = Math.min(1, FRAME_WIDTH / video.videoWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const context = canvas.getContext("2d");
  if (!context) return Promise.resolve(null);
  // 미리보기는 거울처럼 뒤집어 보여 주지만 보내는 이미지는 뒤집지 않는다 (좌우 각도가 바뀌지 않게)
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", FRAME_QUALITY));
}

export function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
