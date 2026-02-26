import Image from "next/image";
import FogLayer from "./components/FogLayer";

export default function Home() {
  return (
    <main className="scene">
      <FogLayer />
      <Image
        className="logo"
        src="/logo.png"
        alt="Ouaish Labs"
        width={560}
        height={560}
        priority
      />
      <footer className="copyright">
        &copy; {new Date().getFullYear()} Ouaish Labs
      </footer>
    </main>
  );
}
