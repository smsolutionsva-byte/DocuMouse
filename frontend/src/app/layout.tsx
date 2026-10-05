import type { Metadata, Viewport } from "next";
import "@fontsource-variable/instrument-sans/wght.css";
import "@fontsource-variable/inter/wght.css";
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";

export const metadata: Metadata = {
  title: { default: "DocuMouse", template: "%s · DocuMouse" },
  description: "Drop your documents in. DocuMouse figures them out.",
};

export const viewport: Viewport = {
  themeColor: "#f6f4ef",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
