import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  themeColor: "#060608",
  colorScheme: "dark",
};

export const metadata: Metadata = {
  metadataBase: new URL("https://ouaish.com"),
  title: "Ouaish Labs",
  description: "Ouaish Labs — Coming soon.",
  openGraph: {
    title: "Ouaish Labs",
    description: "Ouaish Labs — Coming soon.",
    url: "https://ouaish.com",
    siteName: "Ouaish Labs",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Ouaish Labs",
      },
    ],
    type: "website",
  },
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
