import type { Metadata, Viewport } from "next";
import { Geist, Noto_Sans_Bengali } from "next/font/google";
import Header from "@/components/Header";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const bengali = Noto_Sans_Bengali({ variable: "--font-bengali", subsets: ["bengali"] });

export const metadata: Metadata = {
  title: "RoadWatch BD",
  description: "Find possible traffic jams, mid-road bus stops and wrong-way driving in road videos.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0b6e4f" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${bengali.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <I18nProvider>
          <Header />
          <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}
