import { useEffect, useState } from "react";
import { ClaimPage } from "./Claim";
import { Instructions } from "./Instructions";
import { Queue } from "./Queue";

function useHash() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    const update = () => {
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", update);
    return () => {
      window.removeEventListener("hashchange", update);
    };
  }, []);

  return hash;
}

function Page({ hash }: Readonly<{ hash: string }>) {
  const claim = /^#\/claims\/(.+)$/.exec(hash);
  if (claim?.[1]) return <ClaimPage key={claim[1]} claimId={claim[1]} />;
  if (hash === "#/instructions") return <Instructions />;
  return <Queue />;
}

export function App() {
  const hash = useHash();

  return (
    <>
      <header className="masthead">
        <a className="brand" href="#/">
          UnderCover
        </a>
        <span className="tagline">Claims desk</span>
        <nav>
          <a
            href="#/"
            aria-current={
              hash.startsWith("#/instructions") ? undefined : "page"
            }
          >
            Queue
          </a>
          <a
            href="#/instructions"
            aria-current={hash === "#/instructions" ? "page" : undefined}
          >
            Instructions
          </a>
        </nav>
      </header>
      <main>
        <Page hash={hash} />
      </main>
    </>
  );
}
