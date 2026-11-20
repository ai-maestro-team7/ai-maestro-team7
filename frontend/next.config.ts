import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // S3 + CloudFront 정적 배포 계획에 맞춰 HTML 파일로 내보낸다.
  output: "export",
  // `/jobs/` → `/jobs/index.html`로 내보내 S3 정적 호스팅에서 경로가 그대로 열리게 한다.
  trailingSlash: true,
  images: { unoptimized: true },
  // cacheComponents·partialPrefetching(PPR)은 정적 내보내기와 함께 쓸 수 없어 끈다
  // ("PPR cannot be enabled in export mode").
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
