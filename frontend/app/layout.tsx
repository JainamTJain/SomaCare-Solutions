import "./globals.css";
import { LanguageProvider } from "../lib/i18n";

export const metadata = {
  title: "Sorety",
  description: "The shift, in the CNA's language.",
  manifest: "/manifest.json",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
