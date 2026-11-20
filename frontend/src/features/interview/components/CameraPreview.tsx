"use client";

import { User } from "lucide-react";
import { type RefObject, useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

const SIZES = {
  // 장비 점검 화면 (700×440, 얼굴 안내 160×200)
  L: { frame: "aspect-[700/440]", guide: "h-50 w-40", icon: "size-15" },
  // 면접 화면 오른쪽 (332×220, 얼굴 안내 76×96)
  S: { frame: "aspect-[332/220]", guide: "h-24 w-19", icon: "size-7" },
} as const;

type CameraPreviewProps = {
  size: keyof typeof SIZES;
  label: string;
  /** 카메라 스트림. 없으면 어두운 배경과 얼굴 안내만 보여준다 */
  stream?: MediaStream | null;
  /** 캡처할 때 쓰는 video 요소 */
  videoRef?: RefObject<HTMLVideoElement | null>;
};

/**
 * 카메라 미리보기. 거울처럼 좌우를 뒤집어 보여 주고 점선으로 얼굴 자리를 안내한다.
 * 영상은 화면에만 보이고 녹화하지 않는다.
 */
export function CameraPreview({ size, label, stream, videoRef }: CameraPreviewProps) {
  const s = SIZES[size];
  const ownRef = useRef<HTMLVideoElement | null>(null);
  const ref = videoRef ?? ownRef;

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    video.srcObject = stream ?? null;
    if (stream) void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream, ref]);

  return (
    <div
      role="img"
      aria-label={label}
      className={cn("relative flex w-full items-center justify-center overflow-hidden rounded-card bg-dark", s.frame)}
    >
      <video
        ref={ref}
        muted
        playsInline
        autoPlay
        className={cn("absolute inset-0 size-full -scale-x-100 object-cover", !stream && "hidden")}
      />
      <div
        className={cn(
          "relative flex items-center justify-center rounded-full border-2 border-dashed",
          stream ? "border-white/70" : "border-grey-400",
          s.guide,
        )}
      >
        {!stream && <User aria-hidden className={cn("text-grey-500", s.icon)} strokeWidth={1.5} />}
      </div>
    </div>
  );
}
