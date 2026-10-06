import type { Metadata } from "next";
import { Geist_Mono, Montserrat, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// next/font/google descarga las fuentes al construir y las sirve desde el propio dominio (CSP: font-src 'self').
const montserrat = Montserrat({
  variable: "--font-montserrat",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["600", "700"],
  display: "swap",
});

// Números de causa y parámetros (font-mono). globals.css espera --font-geist-mono.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Gestión Judicial", template: "%s · Gestión Judicial" },
  description: "Gestión de lotes y casos judiciales",
};

// Aplica el tema guardado antes del primer pintado para evitar el destello claro/oscuro.
// Debe coincidir con aplicarTema() de src/components/ui/ThemeToggle.tsx.
const SCRIPT_TEMA =
  "(function(){try{var t=localStorage.getItem('tema');if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t}}catch(e){}})()";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es"
      suppressHydrationWarning
      className={`${montserrat.variable} ${sourceSerif.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/*
          Única excepción permitida a la regla de no usar dangerouslySetInnerHTML: es una cadena
          constante escrita aquí, sin datos externos ni interpolación. Tiene que ser un script
          inline síncrono para correr antes de pintar; la CSP lo permite con 'unsafe-inline'.
        */}
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
