import type { Metadata } from "next";
import { Noto_Sans_KR } from "next/font/google";
import { Footer } from "@/components/layout/Footer";
import { Gnb } from "@/components/layout/Gnb";
import "./globals.css";

const notoSansKr = Noto_Sans_KR({
  variable: "--font-noto-sans-kr",
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "부산커리어 · AI 취업 멘토링",
    template: "%s · 부산커리어",
  },
  description: "부산 청년을 위한 AI 취업 멘토링 시연 화면",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${notoSansKr.variable} h-full`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only rounded-control bg-white px-3 py-2 text-small font-medium text-grey-900 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50"
        >
          본문으로 건너뛰기
        </a>
        <Gnb />
        {children}
        <Footer />
      </body>
    </html>
  );
}
