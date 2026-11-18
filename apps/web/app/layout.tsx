import type { Metadata } from "next";
import "./style.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "FrameBounty — custom data, collected with purpose",
  description:
    "A marketplace for custom datasets with buyer and contributor agents and human review.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
