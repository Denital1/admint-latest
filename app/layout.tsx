import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./components/providers";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AdMint — Tokenize Your Attention",
  description: "A marketplace for tokenized advertising rights on Solana",
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-art-theme="apricot" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className={`${inter.variable} ${geistMono.variable} antialiased`}>
        <script dangerouslySetInnerHTML={{__html: `try{var t=localStorage.getItem("admint:appearance");if(["apricot","matcha","ink","plum"].includes(t))document.documentElement.dataset.artTheme=t}catch(e){}`}} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
