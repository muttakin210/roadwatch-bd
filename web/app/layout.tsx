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

// Runs before the first paint: tags <html data-os="…"> so globals.css can give each platform its native
// font, corners and control sizes (no flash of the wrong look). iPadOS reports itself as a Mac with touch.
const DETECT_OS = `(function(){try{var n=navigator,u=n.userAgent||"",p=(n.userAgentData&&n.userAgentData.platform)||n.platform||"",o=/android/i.test(u)?"android":/iphone|ipad|ipod/i.test(u)||(/mac/i.test(p)&&n.maxTouchPoints>1)?"ios":/mac/i.test(p)?"mac":/win/i.test(p)?"windows":/linux|cros|x11/i.test(p+" "+u)?"linux":"other";document.documentElement.setAttribute("data-os",o)}catch(e){}})()`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${bengali.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: DETECT_OS }} />
      </head>
      <body className="min-h-full flex flex-col font-sans">
        <I18nProvider>
          <AuthProvider>
            <Header />
            <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 md:py-8">{children}</main>
            <ServiceWorker />
            <TrafficBackground />
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
