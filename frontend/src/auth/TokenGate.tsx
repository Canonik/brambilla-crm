import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { KeyRound } from "lucide-react";
import { getToken, setToken, subscribeToken } from "./token";
import { USING_MOCKS } from "@/api/transport";
import { getPipelines } from "@/api/endpoints";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { InlineError } from "@/components/ui/States";

/**
 * Every API call needs the CRM's bearer token. When none is configured the
 * app asks for it once and keeps it in this browser. A rejected token brings
 * this screen back with the reason.
 */
export function TokenGate({ children }: { children: ReactNode }) {
  const [token, setLocal] = useState<string | null>(getToken());
  const [rejected, setRejected] = useState(false);

  useEffect(() => {
    const unsub = subscribeToken((t) => setLocal(t));
    const onUnauthorized = () => setRejected(true);
    window.addEventListener("crm:unauthorized", onUnauthorized);
    return () => {
      unsub();
      window.removeEventListener("crm:unauthorized", onUnauthorized);
    };
  }, []);

  if (USING_MOCKS || token) return <>{children}</>;
  return <TokenForm rejected={rejected} onDone={() => setRejected(false)} />;
}

function TokenForm({ rejected, onDone }: { rejected: boolean; onDone: () => void }) {
  const [value, setValue] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const t = value.trim();
    if (!t) return;
    setChecking(true);
    setError(null);
    setToken(t);
    try {
      await getPipelines("deals");
      onDone();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(new Error("The CRM rejected this token. Check it on the platform's Deploy page."));
      } else if (err instanceof ApiError && err.isNetwork) {
        setError(err);
        setToken(null);
      } else {
        // Any other answer means the token was accepted.
        onDone();
      }
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-paper px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 shadow-card">
        <div className="mb-5 flex items-center gap-3">
          <span className="inline-flex size-9 items-center justify-center rounded-md bg-gentian font-wide text-[18px] font-bold text-white">B</span>
          <div>
            <h1 className="font-wide text-[17px] font-semibold text-ink">Brambilla CRM</h1>
            <p className="text-[12.5px] text-ink-2">Connect to the CRM service</p>
          </div>
        </div>
        <Label htmlFor="token">API token</Label>
        <div className="relative mt-1">
          <KeyRound className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
          <Input
            id="token"
            type="password"
            autoComplete="off"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Paste the token from the Deploy page"
            className="pl-8"
          />
        </div>
        <p className="mt-1.5 text-[12px] text-ink-3">Sent as a bearer token on every request and kept only in this browser.</p>
        {rejected && !error ? <InlineError error={new Error("Your previous token was rejected. Enter a valid one to continue.")} className="mt-3" /> : null}
        {error ? <InlineError error={error} className="mt-3" /> : null}
        <Button type="submit" variant="primary" size="lg" className="mt-4 w-full" loading={checking} disabled={!value.trim()}>
          Continue
        </Button>
      </form>
    </div>
  );
}
