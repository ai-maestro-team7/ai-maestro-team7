import { User } from "lucide-react";
import { cn } from "@/lib/cn";

const SIZES = {
  // 장비 점검 화면 (700×440, 얼굴 안내 160×200)
  L: { frame: "aspect-[700/440]", guide: "h-50 w-40", icon: "size-15" },
  // 면접 화면 오른쪽 (332×220, 얼굴 안내 76×96)
  S: { frame: "aspect-[332/220]", guide: "h-24 w-19", icon: "size-7" },
} as const;

/**
 * 카메라 미리보기 자리. 시연에서는 카메라를 켜지 않고 어두운 배경과 점선 얼굴 안내만 보여준다.
 * 얼굴 이미지는 만들거나 저장하지 않는다.
 */
export function CameraPreview({ size, label }: { size: keyof typeof SIZES; label: string }) {
  const s = SIZES[size];
  return (
    <div
      role="img"
      aria-label={label}
      className={cn("flex w-full items-center justify-center rounded-card bg-dark", s.frame)}
    >
      <div
        className={cn(
          "flex items-center justify-center rounded-full border-2 border-dashed border-grey-400",
          s.guide,
        )}
      >
        <User aria-hidden className={cn("text-grey-500", s.icon)} strokeWidth={1.5} />
      </div>
    </div>
  );
}
