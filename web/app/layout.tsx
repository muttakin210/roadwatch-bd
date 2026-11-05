import type { Metadata, Viewport } from "next";
import { Geist, Noto_Sans_Bengali } from "next/font/google";
import Header from "@/components/Header";
import ServiceWorker from "@/components/ServiceWorker";
import TrafficBackground from "@/components/TrafficBackground";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const bengali = Noto_Sans_Bengali({ variable: "--font-bengali", subsets: ["bengali"] });

export const metadata: Metadata = {
  title: "RoadWatch BD",
  description: "Find possible traffic jams, mid-road bus stops and wrong-way driving in road videos.",
  applicationName: "RoadWatch BD",
  // iOS/iPadOS "Add to Home Screen": open full-screen with our icon and title
  appleWebApp: { capable: true, title: "RoadWatch", statusBarStyle: "default" },
  icons: { apple: "/apple-touch-icon.png" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover", // use the whole screen on phones with notches; content is padded below
  themeColor: "#0b6e4f",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${bengali.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <I18nProvider>
          <AuthProvider>
            <Header />
            <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">{children}</main>
            <ServiceWorker />
            <TrafficBackground />
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
