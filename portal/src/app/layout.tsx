import type { Metadata } from "next";
import { Geist_Mono, Public_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// next/font/google descarga las fuentes al construir y las sirve desde el propio dominio (CSP: font-src 'self').
// Public Sans (USWDS): sobria, de lectura institucional y con cifras tabulares para tablas densas.
const publicSans = Public_Sans({
  variable: "--font-public-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

// Variable con eje óptico: los títulos grandes usan el corte de display y los pequeños el de texto.
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  axes: ["opsz"],
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
      className={`${publicSans.variable} ${sourceSerif.variable} ${geistMono.variable} h-full antialiased`}
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
