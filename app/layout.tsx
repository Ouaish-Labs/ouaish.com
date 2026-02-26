import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
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
