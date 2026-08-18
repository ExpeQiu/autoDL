import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "生成测试平台",
  description: "文本 / 图片 / 视频生成验收台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
