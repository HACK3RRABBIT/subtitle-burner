import "./globals.css";

export const metadata = {
  title: "Subtitle Burner",
  description: "Upload a video, get one back with subtitles burned in, plus a full text transcript.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
