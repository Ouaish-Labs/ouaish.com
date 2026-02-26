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
        width={280}
        height={280}
        priority
      />
    </main>
  );
}
